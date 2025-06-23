
## 📁 Project Structure



```bash
VoiceBillAI/
├── backend/
│   ├── __init__.py         # Makes 'backend' a Python package
│   ├── config.py           # Centralized configuration (MinIO, model name, mock DBs)
│   ├── main.py             # FastAPI application, defines API endpoints
│   ├── models.py           # Pydantic models for data validation and serialization
│   ├── core/
│   │   ├── __init__.py     # Makes 'core' a Python package
│   │   └── utils.py        # Utility functions (GPU clear, data autofill, model status)
│   └── services/
│       ├── __init__.py     # Makes 'services' a Python package
│       ├── llm_service.py  # Handles LLM (Qwen2-Audio) loading, prompting, and inference
│       ├── pdf_service.py  # Handles PDF generation and upload to MinIO
│       └── storage_service.py # Handles all MinIO (S3-compatible) storage interactions
├── Dockerfile              # Defines how to build the Docker image for the backend
├── docker-compose.yml      # Orchestrates the backend service and MinIO service
├── requirements.txt        # Lists all Python dependencies for the backend
└── .env                    # (Optional) File to store environment variables locally, not committed to git.
                            # Example: MINIO_ENDPOINT=localhost:9000
                            #          MINIO_ACCESS_KEY=myaccesskey
                            #          MINIO_SECRET_KEY=mysecretkey
```

Explanation:

VoiceBillAI/: This is your project's root directory.
backend/: This directory contains all the Python source code for your FastAPI application.
__init__.py: These empty files are crucial. They tell Python that the directories they reside in (backend, core, services) are Python packages, allowing you to import modules from them (e.g., from backend.config import ...).
core/: Contains core utility functions that might be used across different services.
services/: Contains distinct service modules, each responsible for a specific high-level task (LLM interaction, PDF generation, storage). This promotes modularity and separation of concerns.
Dockerfile: Instructions for Docker to build the container image for your backend application.
docker-compose.yml: Defines how to run multiple Docker containers together (your backend and the minio database) and how they interact.
requirements.txt: Lists all the Python libraries your backend application depends on. pip uses this file to install them.
.env: (Highly Recommended) This file is not directly used by Docker Compose by default, but it's good practice for local development to store sensitive environment variables (like API keys, MinIO credentials) that you don't want hardcoded or committed to version control. You would typically use a library like python-dotenv in your main.py to load these, or rely on Docker Compose's environment section to pass them in. For this setup, docker-compose.yml directly defines the environment variables for the containers, which is good for self-contained deployment.
