# Dockerfile

# Use a specific Python base image with CUDA support if you intend to run on GPU
# FROM nvcr.io/nvidia/pytorch:23.08-py3 # Or a similar image with PyTorch and CUDA pre-installed

# For CPU-only deployment (more portable) - UPDATED TO PYTHON 3.11 (HIGHLY STABLE)
FROM python:3.11-slim-buster

# Set the working directory in the container
WORKDIR /app

# Copy only requirements.txt first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
# Added --default-timeout and --retries for robust downloads
RUN pip install --no-cache-dir --upgrade pip --default-timeout=1000 --retries 5 && \
    pip install --no-cache-dir -r requirements.txt --default-timeout=1000 --retries 5

# Copy the entire backend application
COPY ./backend /app/backend

# Expose the port FastAPI will run on
EXPOSE 8000

# Command to run the application using Uvicorn
# --host 0.0.0.0 makes the server accessible from outside the container
# --port 8000 specifies the port
# REMOVED --factory: 'app' is already the FastAPI instance, not a factory function.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
