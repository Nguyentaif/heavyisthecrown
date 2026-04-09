import math
import logging
from pathlib import Path
import fitz  # PyMuPDF
from PIL import Image

logger = logging.getLogger(__name__)

def create_searchable_pdf(pages_data: list[dict], output_path: str) -> str:
    """
    Creates a searchable PDF/A-like file by overlaying OCR text as an invisible layer 
    on top of the original images.
    
    pages_data is expected to be a list of dictionaries, each resembling an OCRPageResult:
    {
        "input_path": str,
        "lines": [
            {"text": str, "bbox": [xmin, ymin, xmax, ymax], "confidence": float}, ...
        ]
    }
    """
    doc = fitz.open()

    # Create a basic font for unicode (searchable layer)
    # PyMuPDF's built-in Helvetica might lack some Vietnamese accents, 
    # but works reasonably well for basic searchable background layer overlay.
    
    for page_info in pages_data:
        img_path = page_info.get("input_path")
        lines = page_info.get("lines", [])

        if not img_path or not Path(img_path).exists():
            logger.warning(f"Image not found for PDF export: {img_path}")
            continue

        # Get image dimensions to set page size
        try:
            with Image.open(img_path) as im:
                width, height = im.size
        except Exception as e:
            logger.warning(f"Error reading image dimensions for {img_path}: {str(e)}")
            continue

        # Create a new PDF page with the same dimensions
        page = doc.new_page(width=width, height=height)

        # 1. Overlay the scanned image as the background
        rect = fitz.Rect(0, 0, width, height)
        page.insert_image(rect, filename=img_path)

        # 2. Add invisible text layer based on OCR lines
        for line in lines:
            text = line.get("text", "")
            if not text:
                continue

            bbox = line.get("bbox", [])
            if len(bbox) != 4:
                continue

            x0, y0, x1, y1 = bbox
            line_width = x1 - x0
            line_height = y1 - y0

            if line_width <= 0 or line_height <= 0:
                continue

            # Approximate font size to fit the bounding box height
            fontsize = line_height * 0.8
            # Render_mode = 3 means invisible text (stroke and fill not painted)
            try:
                page.insert_text(
                    (x0, y1 - (line_height * 0.2)), # Baseline estimation
                    text,
                    fontsize=fontsize,
                    fontname="helv",
                    render_mode=3
                )
            except Exception as e:
                # If unicode fails with basic font, it silently skips that specific line's visibility layer
                pass

    doc.save(output_path, deflate=True) # basic compression
    doc.close()
    
    return output_path
