# backend/main.py

from fastapi import FastAPI, UploadFile, File, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from typing import Optional
import os
import shutil
import uuid # For generating unique IDs for uploaded files
from io import BytesIO

from backend.models import InvoiceData
from backend.config import MINIO_AUDIO_BUCKET, MINIO_PDF_BUCKET
from backend.services.llm_service import load_qwen2_audio_model, extract_and_validate_invoice_data, qwen2_audio_model, qwen2_audio_processor, device
from backend.services.pdf_service import generate_invoice_pdf
from backend.core.utils import check_model_devices
from backend.services.storage_service import minio_storage_service # Import the MinIO service instance

app = FastAPI(
    title="Voice-Powered Invoice Generator Backend",
    description="API for processing audio requests to generate structured invoice data and PDF invoices, with MinIO storage.",
    version="0.1.0"
)

# Startup event: Initialize MinIO client and ensure buckets exist, load LLM model
@app.on_event("startup")
async def startup_event():
    """
    Initializes MinIO client (which in turn ensures buckets exist)
    and loads the Qwen2-Audio LLM model on application startup.
    """
    print("Application startup: Initializing services...")
    try:
        # MinIO storage service is instantiated globally in storage_service.py
        # Its __init__ method will ensure buckets exist.
        _ = minio_storage_service
        print("MinIO storage service initialized and buckets ensured.")
        load_qwen2_audio_model()
    except Exception as e:
        print(f"CRITICAL ERROR during startup: {e}")
        # Depending on criticality, you might want to exit or log more severely
        # For now, just print and allow app to start, but subsequent calls will fail.

@app.get("/")
async def root():
    """Root endpoint providing a welcome message."""
    return {"message": "Welcome to the Voice-Powered Invoice Generator Backend. Visit /docs for API documentation."}

@app.post("/load_model/", summary="Load the Qwen2-Audio LLM Model")
async def load_model_endpoint():
    """
    Explicitly loads the Qwen2-Audio model and processor into memory.
    This can be called if the model failed to load at startup or for re-initialization.
    """
    status_message = load_qwen2_audio_model()
    return {"status": status_message}

@app.get("/model_status/", summary="Check Qwen2-Audio Model Device and Memory Status")
async def get_model_status():
    """
    Provides detailed information about the Qwen2-Audio model's device placement
    and GPU memory usage if running on CUDA.
    """
    status_message = check_model_devices(qwen2_audio_model, device)
    return {"status": status_message}

@app.post("/generate_invoice_from_audio/", response_model=dict, summary="Generate Invoice from Audio Input")
async def generate_invoice_from_audio_endpoint(
    audio_file: UploadFile = File(..., description="The audio file (e.g., MP3, WAV) containing the invoice request."),
    transcript_text: Optional[str] = File(None, description="Optional pre-provided transcript of the audio.")
):
    """
    Receives an audio file, uploads it to MinIO, uses the Qwen2-Audio model to extract invoice data,
    autofills missing details, generates a PDF invoice, uploads the PDF to MinIO,
    and returns the structured data along with the PDF's MinIO path.

    Returns:
        JSONResponse: Contains the extracted InvoiceData and the MinIO object name for the PDF.
    """
    if qwen2_audio_model is None or qwen2_audio_processor is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Qwen2-Audio model is not loaded. Please call /load_model/ first."
        )

    # Generate a unique object name for the audio file in MinIO
    file_extension = os.path.splitext(audio_file.filename)[1]
    audio_object_name = f"audio-{uuid.uuid4()}{file_extension}"

    try:
        # 1. Read audio content into BytesIO
        audio_content = await audio_file.read()
        audio_bytesio = BytesIO(audio_content)

        # 2. Upload audio to MinIO
        minio_storage_service.upload_file(
            bucket_name=MINIO_AUDIO_BUCKET,
            object_name=audio_object_name,
            data=audio_bytesio,
            length=len(audio_content),
            content_type=audio_file.content_type
        )
        print(f"Audio uploaded to MinIO: {MINIO_AUDIO_BUCKET}/{audio_object_name}")

        # 3. Process audio with LLM to extract invoice data (LLM service will download from MinIO internally)
        invoice_data = await extract_and_validate_invoice_data(audio_object_name, transcript_text)

        # 4. Generate PDF and upload to MinIO
        pdf_object_name = generate_invoice_pdf(invoice_data)
        print(f"PDF generated and uploaded to MinIO: {MINIO_PDF_BUCKET}/{pdf_object_name}")

        return JSONResponse(content={
            "invoice_data": invoice_data.model_dump(),
            "audio_object_name": audio_object_name, # Return the MinIO path for the uploaded audio
            "pdf_object_name": pdf_object_name,     # Return the MinIO path for the generated PDF
            "message": "Invoice generated successfully."
        })
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Service error: {e}")
    except Exception as e:
        # Catch-all for unexpected errors
        print(f"Unexpected error in generate_invoice_from_audio_endpoint: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {e}")

@app.post("/generate_invoice_from_data/", response_model=dict, summary="Generate Invoice from Structured Data")
async def generate_invoice_from_data_endpoint(invoice_data: InvoiceData):
    """
    Generates a PDF invoice directly from provided structured invoice data and uploads it to MinIO.
    This endpoint can be used if the frontend already has the parsed invoice details.

    Args:
        invoice_data (InvoiceData): The structured invoice data.

    Returns:
        JSONResponse: Contains the processed InvoiceData and the MinIO object name for the PDF.
    """
    try:
        # Create a mutable copy to apply autofill without affecting the original request payload
        invoice_data_processed = invoice_data.model_copy(deep=True)
        from backend.core.utils import autofill_invoice_data
        invoice_data_processed = autofill_invoice_data(invoice_data_processed)

        # Generate PDF and upload to MinIO
        pdf_object_name = generate_invoice_pdf(invoice_data_processed)
        print(f"PDF generated and uploaded to MinIO: {MINIO_PDF_BUCKET}/{pdf_object_name}")

        return JSONResponse(content={
            "invoice_data": invoice_data_processed.model_dump(),
            "pdf_object_name": pdf_object_name,
            "message": "Invoice PDF generated from provided data and stored in MinIO."
        })
    except Exception as e:
        print(f"Error in generate_invoice_from_data_endpoint: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error generating invoice from data: {e}")

@app.get("/download_invoice/{object_name:path}", summary="Download Generated Invoice PDF from MinIO")
async def download_invoice(object_name: str):
    """
    Downloads a previously generated PDF invoice from MinIO by its object name (path within the bucket).

    Args:
        object_name (str): The full object name (e.g., 'invoice_client_INV-2025-XXX.pdf') of the PDF in the MinIO bucket.

    Returns:
        FileResponse: The PDF file.
    """
    try:
        # Check if the object exists in MinIO
        if not minio_storage_service.object_exists(MINIO_PDF_BUCKET, object_name):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Invoice PDF '{object_name}' not found in MinIO bucket '{MINIO_PDF_BUCKET}'.")

        # Download the file from MinIO
        pdf_data_bytesio = minio_storage_service.download_file(MINIO_PDF_BUCKET, object_name)
        
        # Determine the filename for the client download
        filename_for_download = os.path.basename(object_name)

        return FileResponse(
            content=pdf_data_bytesio.getvalue(), # Get the content bytes from BytesIO
            media_type="application/pdf",
            filename=filename_for_download,
            headers={"Content-Disposition": f"attachment; filename={filename_for_download}"}
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        print(f"Error downloading invoice from MinIO: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An error occurred while downloading the PDF: {e}")

@app.get("/get_audio/{object_name:path}", summary="Get Audio Input from MinIO")
async def get_audio(object_name: str):
    """
    Retrieves a previously uploaded audio input file from MinIO by its object name.

    Args:
        object_name (str): The full object name (e.g., 'audio-UUID.wav') of the audio in the MinIO bucket.

    Returns:
        FileResponse: The audio file.
    """
    try:
        # Check if the object exists in MinIO
        if not minio_storage_service.object_exists(MINIO_AUDIO_BUCKET, object_name):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Audio file '{object_name}' not found in MinIO bucket '{MINIO_AUDIO_BUCKET}'.")

        # Download the file from MinIO
        audio_data_bytesio = minio_storage_service.download_file(MINIO_AUDIO_BUCKET, object_name)
        
        # Determine the filename for the client download
        filename_for_download = os.path.basename(object_name)
        # Attempt to infer content type; fallback to octet-stream
        content_type = "application/octet-stream"
        if filename_for_download.lower().endswith(".wav"):
            content_type = "audio/wav"
        elif filename_for_download.lower().endswith(".mp3"):
            content_type = "audio/mpeg" # or audio/mp3

        return FileResponse(
            content=audio_data_bytesio.getvalue(),
            media_type=content_type,
            filename=filename_for_download,
            headers={"Content-Disposition": f"inline; filename={filename_for_download}"} # Use inline to play in browser
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        print(f"Error getting audio from MinIO: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An error occurred while retrieving the audio: {e}")
