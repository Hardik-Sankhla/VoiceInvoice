# backend/core/utils.py

import torch
import gc
import re
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from backend.config import user_db, item_db # These are now mock DBs, kept for autofill logic
from backend.models import InvoiceData, InvoiceItem, ValidationError # ValidationError for type hinting/catching

def clear_gpu_memory():
    """Clears CUDA memory cache and runs garbage collection."""
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    gc.collect()

def autofill_invoice_data(invoice_data: InvoiceData) -> InvoiceData:
    """
    Autofills invoice data based on simulated local databases (user_db, item_db).
    Fills in missing client address, item prices, and calculates totals/dates.

    Args:
        invoice_data (InvoiceData): The invoice data Pydantic model to autofill.

    Returns:
        InvoiceData: The updated invoice data with autofilled information.
    """
    # Create a mutable copy to avoid modifying the original object in place
    # if this function is called on an object that might be reused or
    # that came directly from a FastAPI request body.
    invoice_data_copy = invoice_data.model_copy(deep=True)

    if invoice_data_copy.client_name:
        normalized_client_name = invoice_data_copy.client_name.lower().strip()
        if normalized_client_name in user_db:
            client_info = user_db[normalized_client_name]
            if not invoice_data_copy.client_address:
                invoice_data_copy.client_address = client_info.get("address")
            # Only update tax_rate if it's not explicitly set in the incoming data
            if invoice_data_copy.tax_rate is None or invoice_data_copy.tax_rate == 0.08: # Default value
                invoice_data_copy.tax_rate = client_info.get("default_tax_rate", 0.08)

    for item in invoice_data_copy.items:
        # If unit_price is missing but description exists, try to autofill
        if not item.unit_price and item.description:
            normalized_description = item.description.lower().strip()
            for db_item, db_info in item_db.items():
                if db_item in normalized_description: # Simple substring match
                    item.unit_price = db_info.get("unit_price")
                    # Break after finding the first match
                    break
        # Ensure item total is calculated or re-calculated after autofill of unit_price
        if item.quantity is not None and item.unit_price is not None:
            item.total = round(item.quantity * item.unit_price, 2)
        elif item.total is None: # If no quantity/unit_price but total needed
             item.total = 0.0 # Default to 0 if not enough info

    # Recalculate totals after autofilling item prices and ensure they are not None
    invoice_data_copy.subtotal = round(sum(item.total for item in invoice_data_copy.items if item.total is not None), 2)
    effective_tax_rate = invoice_data_copy.tax_rate if invoice_data_copy.tax_rate is not None else 0.0
    invoice_data_copy.tax_amount = round(invoice_data_copy.subtotal * effective_tax_rate, 2)
    invoice_data_copy.grand_total = round(invoice_data_copy.subtotal + invoice_data_copy.tax_amount, 2)

    # Handle dates
    if not invoice_data_copy.invoice_date:
        invoice_data_copy.invoice_date = datetime.now().strftime("%Y-%m-%d")
    if not invoice_data_copy.due_date:
        try:
            invoice_date_dt = datetime.strptime(invoice_data_copy.invoice_date, "%Y-%m-%d")
            invoice_data_copy.due_date = (invoice_date_dt + timedelta(days=30)).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            # Fallback if invoice_date is invalid or not set
            invoice_data_copy.due_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")


    return invoice_data_copy

def check_model_devices(qwen2_audio_model: Optional[Any], device: str) -> str:
    """
    Checks the device placement and memory usage of the Qwen2-Audio model.
    """
    status_output = []
    status_output.append("--- Checking Model Device Placement ---")

    if qwen2_audio_model:
        try:
            if hasattr(qwen2_audio_model, 'hf_device_map') and qwen2_audio_model.hf_device_map:
                status_output.append(f"Qwen2-Audio model device map: {qwen2_audio_model.hf_device_map}")
            else:
                qwen_device = next(qwen2_audio_model.parameters()).device
                status_output.append(f"Qwen2-Audio model (first parameter) is on: {qwen_device}")

            status_output.append(f"Qwen2-Audio model data type: {next(qwen2_audio_model.parameters()).dtype}")

            if device == "cuda":
                status_output.append(f"Current GPU Memory Allocated: {torch.cuda.memory_allocated() / (1024**3):.2f} GB")
                status_output.append(f"Current GPU Memory Cached: {torch.cuda.memory_reserved() / (1024**3):.2f} GB")
                status_output.append(f"Max GPU Memory Allocated: {torch.cuda.max_memory_allocated() / (1024**3):.2f} GB")
                status_output.append(f"Max GPU Memory Cached: {torch.cuda.max_memory_reserved() / (1024**3):.2f} GB")
        except Exception as e:
            status_output.append(f"Error checking model device: {e}")
    else:
        status_output.append("Qwen2-Audio model is not loaded.")

    status_output.append(f"System detected device: {device}")
    if device == "cuda":
        status_output.append(f"Number of CUDA devices: {torch.cuda.device_count()}")
        if torch.cuda.device_count() > 0:
            status_output.append(f"Current CUDA device: {torch.cuda.current_device()} ({torch.cuda.get_device_name(torch.cuda.current_device())})")
            status_output.append(f"Total GPU Memory on current device: {torch.cuda.get_device_properties(torch.cuda.current_device()).total_memory / (1024**3):.2f} GB")
        else:
            status_output.append("No CUDA devices detected. Running on CPU.")

    return "\n".join(status_output)
