# backend/services/pdf_service.py

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
# from reportlab.pdfgen import canvas # Not directly used with SimpleDocTemplate for main content
import os
from io import BytesIO
from datetime import datetime

from backend.models import InvoiceData
from backend.config import MINIO_PDF_BUCKET
from backend.services.storage_service import minio_storage_service # Import the MinIO service

def generate_invoice_pdf(invoice: InvoiceData) -> str:
    """
    Generates a PDF invoice from the InvoiceData Pydantic model
    and uploads it to the MinIO PDF bucket.

    Args:
        invoice (InvoiceData): The Pydantic model containing invoice data.

    Returns:
        str: The MinIO object name (path within the bucket) of the generated PDF.
    """
    if not invoice.invoice_number:
        # Generate a simple invoice number if not provided
        invoice_number = f"INV-{invoice.invoice_date.replace('-', '') if invoice.invoice_date else datetime.now().strftime('%Y%m%d')}-{datetime.now().strftime('%H%M%S')}"
        invoice.invoice_number = invoice_number
    else:
        invoice_number = invoice.invoice_number

    # Sanitize client name for filename
    sanitized_client_name = "".join(c for c in invoice.client_name if c.isalnum() or c in [' ', '_']).replace(' ', '_') if invoice.client_name else "unknown_client"
    # Create a unique filename for the PDF in MinIO
    pdf_object_name = f"invoice_{sanitized_client_name}_{invoice_number}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"

    # Use BytesIO to create the PDF in memory
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=inch, leftMargin=inch,
                            topMargin=inch, bottomMargin=inch)
    elements = []
    styles = getSampleStyleSheet()

    # --- Header ---
    elements.append(Paragraph("<b>INVOICE</b>", styles['h1']))
    elements.append(Spacer(1, 0.2 * inch))
    elements.append(Paragraph(f"<b>Invoice #:</b> {invoice_number}", styles['Normal']))
    elements.append(Paragraph(f"<b>Date:</b> {invoice.invoice_date if invoice.invoice_date else 'N/A'}", styles['Normal']))
    elements.append(Paragraph(f"<b>Due Date:</b> {invoice.due_date if invoice.due_date else 'N/A'}", styles['Normal']))
    elements.append(Spacer(1, 0.4 * inch))

    # --- Client Information ---
    elements.append(Paragraph("<b>Bill To:</b>", styles['h3']))
    if invoice.client_name:
        elements.append(Paragraph(invoice.client_name, styles['Normal']))
    if invoice.client_address:
        elements.append(Paragraph(invoice.client_address, styles['Normal']))
    elements.append(Spacer(1, 0.4 * inch))

    # --- Items Table ---
    if invoice.items:
        data = [['Description', 'Quantity', 'Unit Price', 'Total']]
        for item in invoice.items:
            # Ensure item totals are calculated if not present (though autofill_invoice_data handles this)
            item_total = item.total if item.total is not None else (item.quantity * item.unit_price if item.quantity is not None and item.unit_price is not None else 0.0)
            data.append([
                item.description,
                f"{item.quantity:.2f}",
                f"${item.unit_price:.2f}",
                f"${item_total:.2f}"
            ])

        table_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ADD8E6')), # Light blue header
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F0F8FF')), # Alice blue rows
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#C0C0C0')), # Silver grid lines
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#808080')), # Grey box border
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'), # Align Qty, Unit Price, Total to right
        ])

        item_table = Table(data, colWidths=[3*inch, 0.8*inch, 1*inch, 1*inch])
        item_table.setStyle(table_style)
        elements.append(item_table)
        elements.append(Spacer(1, 0.2 * inch))

    # --- Totals ---
    # Ensure all totals are float and not None before formatting
    subtotal = invoice.subtotal if invoice.subtotal is not None else 0.0
    tax_amount = invoice.tax_amount if invoice.tax_amount is not None else 0.0
    grand_total = invoice.grand_total if invoice.grand_total is not None else 0.0
    tax_rate_display = invoice.tax_rate * 100 if invoice.tax_rate is not None else 0.0

    totals_data = [
        ['Subtotal:', f"${subtotal:.2f}"],
        [f"Tax ({tax_rate_display:.0f}%):", f"${tax_amount:.2f}"],
        ['Grand Total:', f"${grand_total:.2f}"]
    ]
    totals_table = Table(totals_data, colWidths=[4.8*inch, 1.2*inch])
    totals_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(totals_table)
    elements.append(Spacer(1, 0.3 * inch))

    # --- Notes ---
    if invoice.notes:
        elements.append(Paragraph("<b>Notes:</b>", styles['h3']))
        elements.append(Paragraph(invoice.notes, styles['Normal']))
        elements.append(Spacer(1, 0.2 * inch))

    # --- Footer (Optional) ---
    elements.append(Spacer(1, 0.5 * inch))
    elements.append(Paragraph("<i>Thank you for your business!</i>", styles['Italic']))

    # Build PDF in memory
    try:
        doc.build(elements)
        buffer.seek(0) # Reset buffer position to the beginning

        # Upload the PDF from memory to MinIO
        minio_storage_service.upload_file(
            bucket_name=MINIO_PDF_BUCKET,
            object_name=pdf_object_name,
            data=buffer,
            length=buffer.tell(), # Get the current position (which is the file size)
            content_type="application/pdf"
        )
        print(f"Invoice PDF generated and uploaded to MinIO: {MINIO_PDF_BUCKET}/{pdf_object_name}")
        return pdf_object_name
    except Exception as e:
        print(f"Error generating or uploading PDF: {e}")
        raise RuntimeError(f"Failed to generate or upload PDF: {e}")

