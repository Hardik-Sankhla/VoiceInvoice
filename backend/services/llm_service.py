# backend/services/llm_service.py

import torch
from transformers import Qwen2AudioForConditionalGeneration, AutoProcessor
import librosa
import re
import json
import os
from typing import Dict, Any, Optional
from backend.config import QWEN2_AUDIO_MODEL_NAME, MINIO_AUDIO_BUCKET
from backend.models import InvoiceData, InvoiceItem
from backend.core.utils import clear_gpu_memory, autofill_invoice_data
from backend.services.storage_service import minio_storage_service # Import the MinIO service

# Global variables to hold model instances for efficiency
qwen2_audio_processor = None
qwen2_audio_model = None
device = "cuda" if torch.cuda.is_available() else "cpu"

def load_qwen2_audio_model() -> str:
    """
    Loads the Qwen2-Audio model and processor.
    Uses 8-bit quantization for GPU to reduce VRAM usage.
    """
    global qwen2_audio_processor, qwen2_audio_model, device

    if qwen2_audio_model is None or qwen2_audio_processor is None:
        try:
            print(f"Loading Qwen2-Audio model from {QWEN2_AUDIO_MODEL_NAME} for device: {device}")
            qwen2_audio_processor = AutoProcessor.from_pretrained(QWEN2_AUDIO_MODEL_NAME, trust_remote_code=True)

            if device == "cuda":
                qwen2_audio_model = Qwen2AudioForConditionalGeneration.from_pretrained(
                    QWEN2_AUDIO_MODEL_NAME,
                    load_in_8bit=True,
                    device_map="auto",
                    torch_dtype=torch.float16,
                    trust_remote_code=True
                )
                print("Attempting to load model with 8-bit quantization.")
            else:
                qwen2_audio_model = Qwen2AudioForConditionalGeneration.from_pretrained(
                    QWEN2_AUDIO_MODEL_NAME,
                    device_map="auto",
                    torch_dtype=torch.float32,
                    trust_remote_code=True
                )
                print("Loading model for CPU in float32.")

            qwen2_audio_model.eval()
            status_message = f"Qwen2-Audio model loaded on {device} successfully!"
            print(status_message)
            return status_message
        except Exception as e:
            error_message = f"Error loading Qwen2-Audio model: {e}"
            print(error_message)
            qwen2_audio_processor = None
            qwen2_audio_model = None
            clear_gpu_memory()
            return f"Failed to load Qwen2-Audio model: {e}"
    else:
        status_message = "Qwen2-Audio model already loaded."
        print(status_message)
        return status_message

def create_qwen_invoice_prompt(audio_data_path: str, prompt_text: str = "") -> Dict:
    """
    Creates the prompt for the Qwen2-Audio LLM, instructing it to extract structured invoice data.
    The output format is explicitly requested as JSON.

    Args:
        audio_data_path (str): The local file path to the audio data.
                               This function assumes the audio is already downloaded locally.
        prompt_text (str): Optional pre-provided transcript or additional prompt text.

    Returns:
        Dict: Inputs prepared for the Qwen2-Audio model.
    """
    if qwen2_audio_processor is None:
        raise RuntimeError("Qwen2-Audio processor is not loaded. Please load the model first.")

    try:
        # librosa expects a file path or file-like object. We are passing a local path.
        audio, _ = librosa.load(audio_data_path, sr=qwen2_audio_processor.feature_extractor.sampling_rate)
    except Exception as e:
        raise ValueError(f"Error loading audio file from {audio_data_path}: {e}")

    # Define the desired JSON schema for the LLM. Updated to match Pydantic model closely.
    json_schema = """
    {
      "client_name": "string (e.g., John Doe, ACME Corp)",
      "client_address": "string (e.g., 123 Main St, Anytown, CA)",
      "invoice_number": "string (optional, e.g., INV-2025-001)",
      "invoice_date": "YYYY-MM-DD (optional, defaults to today if not specified)",
      "due_date": "YYYY-MM-DD (optional, defaults to invoice_date + 30 days if not specified)",
      "items": [
        {
          "description": "string (e.g., Laptop, Consulting Services)",
          "quantity": "float (e.g., 1.0, 2.5)",
          "unit_price": "float (e.g., 1200.00, 75.50)"
        }
      ],
      "notes": "string (optional, any additional notes)"
    }
    """

    # Craft the prompt for the LLM, instructing it to act as an invoice data extractor.
    messages = [
        {"role": "system", "content": "You are an AI assistant that extracts structured invoice data from spoken requests. Your output MUST be a valid JSON object matching the provided schema. Do not include any other text or explanation outside the JSON. Extract all available details, and use best guesses for missing information (like current date for invoice_date)."},
        {"role": "user", "content": f"Here is the invoice request. Please extract the details into a JSON object. Ensure item totals are calculated by quantity * unit_price. If no explicit invoice or due date, use today's date and 30 days from today respectively. If a field is not mentioned, omit it or set it to null. Here's the schema: {json_schema}\n\nInvoice request: {prompt_text}"}
    ]

    # Qwen2-Audio expects a single audio input along with a list of messages
    # The `audio` parameter is specifically for the audio input, not part of the messages content.
    inputs = qwen2_audio_processor(audio=audio, text=messages, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()} # Move inputs to correct device

    return inputs

def process_llm_output(output_ids: torch.Tensor, original_input_len: int) -> str:
    """Decodes the LLM output and extracts the JSON string."""
    if qwen2_audio_processor is None:
        raise RuntimeError("Qwen2-Audio processor is not loaded.")

    # Decode the generated tokens
    # Ensure to skip the original input tokens by slicing `output_ids`
    generated_text = qwen2_audio_processor.decode(output_ids[0, original_input_len:], skip_special_tokens=True)
    return generated_text

async def extract_and_validate_invoice_data(audio_object_name: str, transcript_text: str = "") -> InvoiceData:
    """
    Downloads an audio file from MinIO, processes it with the LLM to extract invoice data,
    validates it with Pydantic, and autofills missing information.

    Args:
        audio_object_name (str): The object name of the audio file in the MinIO audio bucket.
        transcript_text (str): Optional pre-provided transcript of the audio.

    Returns:
        InvoiceData: The validated and autofilled Pydantic model representing the invoice.
    """
    if qwen2_audio_model is None or qwen2_audio_processor is None:
        raise RuntimeError("Qwen2-Audio model and/or processor not loaded. Call load_qwen2_audio_model() first.")

    temp_audio_file_path = f"/tmp/{audio_object_name.split('/')[-1]}" # Use /tmp for temporary storage

    try:
        # 1. Download audio from MinIO to a temporary local file
        audio_data_bytesio = minio_storage_service.download_file(MINIO_AUDIO_BUCKET, audio_object_name)
        with open(temp_audio_file_path, "wb") as f:
            f.write(audio_data_bytesio.read())
        print(f"Downloaded audio from MinIO to temporary path: {temp_audio_file_path}")

        # 2. Create prompt and get inputs for the LLM using the local file
        llm_inputs = create_qwen_invoice_prompt(temp_audio_file_path, transcript_text)
        original_input_len = llm_inputs['input_ids'].shape[1]

        # 3. Generate response from LLM
        with torch.no_grad():
            generated_ids = qwen2_audio_model.generate(**llm_inputs, max_new_tokens=2048)

        # 4. Process LLM output
        llm_raw_output = process_llm_output(generated_ids, original_input_len)
        print(f"LLM Raw Output:\n{llm_raw_output}")

        # 5. Extract JSON part using regex
        json_match = re.search(r"```json\s*(\{.*\})\s*```", llm_raw_output, re.DOTALL)
        if not json_match:
            # Fallback: try to find the JSON directly if it's not wrapped in markdown
            json_match = re.search(r"(\{.*\})", llm_raw_output, re.DOTALL)

        if not json_match:
            raise ValueError("Could not extract a valid JSON object from LLM output.")

        json_str = json_match.group(1)

        try:
            extracted_data = json.loads(json_str)
            print(f"Extracted JSON Data: {extracted_data}")
            # Validate and convert to Pydantic model
            invoice_data = InvoiceData.model_validate(extracted_data)
            print(f"Validated Invoice Data (before autofill): {invoice_data.model_dump_json(indent=2)}")
            # Autofill missing details using the comprehensive function from utils
            invoice_data = autofill_invoice_data(invoice_data)
            print(f"Final Invoice Data (after autofill): {invoice_data.model_dump_json(indent=2)}")
            return invoice_data
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to decode JSON from LLM output: {e}. Raw output: {json_str}")
        except Exception as e: # Catch Pydantic ValidationError here and re-raise as ValueError
            if "validation" in str(e).lower() and "model" in str(e).lower(): # Simple check for Pydantic validation error
                raise ValueError(f"Pydantic validation failed for extracted data: {e}. Data: {json_str}")
            else:
                raise RuntimeError(f"An unexpected error occurred during data extraction or validation: {e}")
    finally:
        # Clean up the temporary audio file
        if os.path.exists(temp_audio_file_path):
            os.remove(temp_audio_file_path)
            print(f"Cleaned up temporary audio file: {temp_audio_file_path}")

