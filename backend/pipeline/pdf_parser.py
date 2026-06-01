"""
PDF Parser Module
Extracts text from PDF files using PyMuPDF with Tesseract OCR fallback for scanned documents.
"""

import fitz  # PyMuPDF
import io
from typing import Optional
from PIL import Image
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to import pytesseract, but handle if not installed
try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    logger.warning("Tesseract not available. OCR fallback disabled.")


def extract_text_from_pdf(file_bytes: bytes, dpi: int = 300) -> str:
    """
    Extract text from a PDF file using PyMuPDF.
    Falls back to Tesseract OCR for scanned/image-based pages.
    
    Args:
        file_bytes: PDF file content as bytes
        dpi: DPI for image rendering (higher = better OCR quality)
    
    Returns:
        Extracted text from all pages concatenated
    """
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as e:
        logger.error(f"Failed to open PDF: {e}")
        raise ValueError(f"Invalid PDF file: {e}")
    
    full_text = ""
    total_pages = len(doc)
    logger.info(f"Processing PDF with {total_pages} pages")
    
    for page_num in range(total_pages):
        page = doc[page_num]
        
        # Try to extract text directly first
        text = page.get_text()
        
        # If page has no text or minimal text (scanned PDF), use OCR
        if not text or len(text.strip()) < 50:
            logger.info(f"Page {page_num + 1}: Using OCR fallback")
            ocr_text = _extract_text_with_ocr(page, dpi)
            if ocr_text:
                text = ocr_text
            else:
                logger.warning(f"Page {page_num + 1}: OCR produced no text")
        else:
            logger.info(f"Page {page_num + 1}: Extracted {len(text)} chars via PyMuPDF")
        
        full_text += text + "\n\n"
    
    doc.close()
    
    clean_text = full_text.strip()
    logger.info(f"Total extracted text: {len(clean_text)} characters")
    
    return clean_text


def _extract_text_with_ocr(page: fitz.Page, dpi: int = 300) -> Optional[str]:
    """
    Extract text from a PDF page using Tesseract OCR.
    
    Args:
        page: PyMuPDF Page object
        dpi: Resolution for image rendering
    
    Returns:
        Extracted text or None if OCR failed
    """
    if not TESSERACT_AVAILABLE:
        logger.warning("Tesseract not available, skipping OCR")
        return None
    
    try:
        # Render page to image at specified DPI
        zoom = dpi / 72  # 72 is the default PDF DPI
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        
        # Convert to PIL Image
        img_bytes = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_bytes))
        
        # Run OCR
        text = pytesseract.image_to_string(img)
        
        return text.strip() if text else None
        
    except Exception as e:
        logger.error(f"OCR failed: {e}")
        return None


def is_pdf_scanned(file_bytes: bytes, sample_pages: int = 3) -> bool:
    """
    Quick check to determine if a PDF is scanned/image-based.
    
    Args:
        file_bytes: PDF file content as bytes
        sample_pages: Number of pages to sample
    
    Returns:
        True if PDF appears to be scanned, False otherwise
    """
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pages_to_check = min(sample_pages, len(doc))
        
        scanned_pages = 0
        for i in range(pages_to_check):
            page = doc[i]
            text = page.get_text()
            if not text or len(text.strip()) < 100:
                scanned_pages += 1
        
        doc.close()
        
        # If majority of sampled pages have no text, consider it scanned
        return scanned_pages > pages_to_check / 2
        
    except Exception as e:
        logger.error(f"Error checking if PDF is scanned: {e}")
        return False


if __name__ == "__main__":
    # Simple test if run directly
    import sys
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
        with open(pdf_path, "rb") as f:
            content = f.read()
        result = extract_text_from_pdf(content)
        print(f"\n--- Extracted Text (first 1000 chars) ---\n{result[:1000]}")
    else:
        print("Usage: python pdf_parser.py <path_to_pdf>")
