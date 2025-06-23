# backend/models.py

from pydantic import BaseModel, Field, ValidationError # Ensure ValidationError is imported for potential use
from typing import List, Optional, Any
import datetime

class InvoiceItem(BaseModel):
    """
    Represents a single item in an invoice.
    """
    description: str = Field(..., description="Description of the item or service.")
    quantity: float = Field(..., gt=0, description="Quantity of the item, must be greater than 0.")
    unit_price: float = Field(..., gt=0, description="Unit price of the item, must be greater than 0.")
    total: Optional[float] = Field(None, description="Calculated total for the item (quantity * unit_price).")

    def model_post_init(self, __context: Any) -> None:
        """
        Pydantic V2 post-initialization hook. Calculates total if not provided.
        """
        if self.total is None:
            self.total = round(self.quantity * self.unit_price, 2) # Round to 2 decimal places


class InvoiceData(BaseModel):
    """
    Represents the complete structured data for an invoice.
    """
    client_name: Optional[str] = Field(None, description="Name of the client.")
    client_address: Optional[str] = Field(None, description="Billing address of the client.")
    invoice_number: Optional[str] = Field(None, description="Unique invoice identification number.")
    invoice_date: Optional[str] = Field(None, description="Date the invoice was issued (YYYY-MM-DD format).")
    due_date: Optional[str] = Field(None, description="Date the payment is due (YYYY-MM-DD format).")
    items: List[InvoiceItem] = Field(default_factory=list, description="List of invoice items.")
    subtotal: Optional[float] = Field(None, description="Sum of all item totals.")
    tax_rate: Optional[float] = Field(0.08, ge=0, le=1, description="Tax rate applicable (e.g., 0.08 for 8%).")
    tax_amount: Optional[float] = Field(None, description="Calculated tax amount.")
    grand_total: Optional[float] = Field(None, description="Total amount including subtotal and tax.")
    notes: Optional[str] = Field(None, description="Any additional notes for the invoice.")

    def model_post_init(self, __context: Any) -> None:
        """
        Pydantic V2 post-initialization hook. Calculates subtotal, tax_amount, and grand_total.
        These are primarily for consistency and display, the autofill_invoice_data
        utility will ensure robust calculation.
        """
        # Ensure item totals are calculated before summing for subtotal
        for item in self.items:
            if item.total is None: # This should ideally be handled by InvoiceItem's post_init
                item.total = round(item.quantity * item.unit_price, 2)

        self.subtotal = round(sum(item.total for item in self.items if item.total is not None), 2) if self.items else 0.0
        # Ensure tax_rate is not None before multiplication
        effective_tax_rate = self.tax_rate if self.tax_rate is not None else 0.0
        self.tax_amount = round(self.subtotal * effective_tax_rate, 2)
        self.grand_total = round(self.subtotal + self.tax_amount, 2)
