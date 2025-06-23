# backend/services/storage_service.py

import os
from io import BytesIO
from minio import Minio
from minio.error import S3Error
from backend.config import MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, MINIO_SECURE, MINIO_AUDIO_BUCKET, MINIO_PDF_BUCKET

class MinIOStorageService:
    """
    Service class for interacting with MinIO (S3-compatible) storage.
    Handles uploading, downloading, and checking existence of objects in specified buckets.
    """
    def __init__(self):
        """
        Initializes the MinIO client.
        Ensures the necessary buckets exist on startup.
        """
        try:
            self.client = Minio(
                endpoint=MINIO_ENDPOINT,
                access_key=MINIO_ACCESS_KEY,
                secret_key=MINIO_SECRET_KEY,
                secure=MINIO_SECURE,
                # Set a higher timeout for potentially large file uploads/downloads
                # or slow network conditions. Default is usually sufficient but good for large files.
                # Timeout in seconds. Can be None for no timeout.
                http_client=None # Use default http client, or provide custom
            )
            print(f"MinIO client initialized for endpoint: {MINIO_ENDPOINT}, Secure: {MINIO_SECURE}")
            self._ensure_buckets_exist()
        except Exception as e:
            print(f"ERROR: Failed to initialize MinIO client: {e}")
            raise

    def _ensure_buckets_exist(self):
        """
        Ensures that the audio and PDF buckets exist. Creates them if they don't.
        """
        buckets_to_create = [MINIO_AUDIO_BUCKET, MINIO_PDF_BUCKET]
        for bucket_name in buckets_to_create:
            try:
                if not self.client.bucket_exists(bucket_name):
                    self.client.make_bucket(bucket_name)
                    print(f"MinIO bucket '{bucket_name}' created successfully.")
                else:
                    print(f"MinIO bucket '{bucket_name}' already exists.")
            except S3Error as e:
                print(f"ERROR: S3 Error ensuring bucket '{bucket_name}': {e}")
                raise
            except Exception as e:
                print(f"ERROR: Unexpected error ensuring bucket '{bucket_name}': {e}")
                raise

    def upload_file(self, bucket_name: str, object_name: str, data: BytesIO, length: int, content_type: str = "application/octet-stream") -> str:
        """
        Uploads a file (BytesIO object) to a specified MinIO bucket.

        Args:
            bucket_name (str): The name of the bucket.
            object_name (str): The desired name of the object in the bucket.
            data (BytesIO): The file data as a BytesIO object.
            length (int): The length of the data in bytes.
            content_type (str): The MIME type of the file.

        Returns:
            str: The full path of the uploaded object (bucket_name/object_name).
        """
        try:
            self.client.put_object(
                bucket_name=bucket_name,
                object_name=object_name,
                data=data,
                length=length,
                content_type=content_type
            )
            print(f"Successfully uploaded {object_name} to bucket {bucket_name}")
            # Construct a downloadable URL (for MinIO, this usually implies access via its API/proxy)
            # For direct public access, you'd need presigned URLs or public buckets configured externally.
            # Here, we return a logical path that your FastAPI can use to retrieve.
            return f"{bucket_name}/{object_name}"
        except S3Error as e:
            print(f"ERROR: S3 Error uploading {object_name} to {bucket_name}: {e}")
            raise
        except Exception as e:
            print(f"ERROR: Unexpected error uploading {object_name}: {e}")
            raise

    def download_file(self, bucket_name: str, object_name: str) -> BytesIO:
        """
        Downloads a file from a specified MinIO bucket.

        Args:
            bucket_name (str): The name of the bucket.
            object_name (str): The name of the object to download.

        Returns:
            BytesIO: The file data as a BytesIO object.
        """
        try:
            response = self.client.get_object(bucket_name, object_name)
            file_data = BytesIO(response.read())
            file_data.seek(0) # Reset stream position to the beginning
            response.close()
            response.release_conn()
            print(f"Successfully downloaded {object_name} from bucket {bucket_name}")
            return file_data
        except S3Error as e:
            if e.code == "NoSuchKey":
                print(f"ERROR: Object '{object_name}' not found in bucket '{bucket_name}'.")
                raise FileNotFoundError(f"Object '{object_name}' not found in bucket '{bucket_name}'.")
            else:
                print(f"ERROR: S3 Error downloading {object_name} from {bucket_name}: {e}")
                raise
        except Exception as e:
            print(f"ERROR: Unexpected error downloading {object_name}: {e}")
            raise

    def object_exists(self, bucket_name: str, object_name: str) -> bool:
        """
        Checks if an object exists in a specified MinIO bucket.

        Args:
            bucket_name (str): The name of the bucket.
            object_name (str): The name of the object to check.

        Returns:
            bool: True if the object exists, False otherwise.
        """
        try:
            self.client.stat_object(bucket_name, object_name)
            return True
        except S3Error as e:
            if e.code == "NoSuchKey":
                return False
            else:
                print(f"ERROR: S3 Error checking existence of {object_name} in {bucket_name}: {e}")
                raise
        except Exception as e:
            print(f"ERROR: Unexpected error checking existence of {object_name}: {e}")
            raise

# Instantiate the service globally or pass it around via dependency injection in FastAPI
# For simplicity, we'll instantiate it here. FastAPI's Depends can be used for DI.
minio_storage_service = MinIOStorageService()
