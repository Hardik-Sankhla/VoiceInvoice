# D:\GNPL-Private\VoiceInvoice\backend\config.py

import os

# --- General Application Configuration ---
# Setting the environment to development by default if not specified
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# --- Model Configuration ---
QWEN2_AUDIO_MODEL_NAME = "Qwen/Qwen2-Audio-7B-Instruct" # Name of the pre-trained Qwen2-Audio model

# --- MinIO S3 Compatible Storage Configuration ---
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000") # MinIO server endpoint
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin") # MinIO access key
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin") # MinIO secret key
MINIO_SECURE = os.getenv("MINIO_SECURE", "False").lower() == "true" # Use HTTPS if true

# Bucket names for audio inputs and generated PDFs
MINIO_AUDIO_BUCKET = os.getenv("MINIO_AUDIO_BUCKET", "audio-inputs")
MINIO_PDF_BUCKET = os.getenv("MINIO_PDF_BUCKET", "generated-invoices")

# --- Simulated Local Databases for Autofill (for demonstration/development) ---
# In a production environment, these would typically be replaced with actual databases (SQL, NoSQL).
user_db = {
    "john doe": {"name": "John Doe", "address": "123 Elm St, Springfield, IL", "email": "john.doe@example.com", "default_tax_rate": 0.07},
    "acme corp": {"name": "ACME Corporation", "address": "456 Oak Ave, Metropolis, NY", "email": "info@acmecorp.com", "default_tax_rate": 0.09},
}

item_db = {
    "laptop": {"description": "Laptop Computer", "unit_price": 1200.00},
    "keyboard": {"description": "Mechanical Keyboard", "unit_price": 75.00},
    "mouse": {"description": "Wireless Mouse", "unit_price": 25.00},
    "software license": {"description": "Software License (Annual)", "unit_price": 300.00},
    "consulting services": {"description": "Consulting Services (Hourly)", "unit_price": 150.00},
    "web development": {"description": "Web Development Services", "unit_price": 100.00},
    "graphic design": {"description": "Graphic Design Services", "unit_price": 80.00},
}

# No longer using local file system paths for audio/PDFs directly in services,
# these are replaced by MinIO buckets.
# LOCAL_AUDIO_FOLDER and LOCAL_PDF_FOLDER are removed from here.

print(f"Configuration Loaded: Environment={ENVIRONMENT}, MinIO Endpoint={MINIO_ENDPOINT}, Audio Bucket={MINIO_AUDIO_BUCKET}, PDF Bucket={MINIO_PDF_BUCKET}")
