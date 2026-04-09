# VN-Digitize-AI

A production-grade, deterministic document preprocessing and OCR engine designed specifically to handle both scanned and camera-captured documents, with specialized support for Vietnamese text.

VN-Digitize-AI transforms raw images into clean, normalized, and OCR-ready files, extracts text using a hybrid Tesseract + VietOCR approach, and provides document summarization capabilities using local LLMs via Ollama. It exposes all these features through a robust FastAPI application.

## Key Features

- **Advanced Document Preprocessing**:
  - Automatic cropping and deskewing.
  - Shadow and yellow stain removal for camera-captured images.
  - Denoising and adaptive binarization (configurable).
  - **Red Stamp Preservation**: Specifically detects and preserves red ink elements (like official company/government stamps) which are often lost during normal binarization pipelines.
  - Blank page detection and automatic removal.
- **High-Accuracy Vietnamese OCR**:
  - Utilizes **Tesseract** for robust layout analysis and line bounding box detection.
  - Feeds cropped bounding boxes into **VietOCR** (`vgg_transformer` model) for state-of-the-art Vietnamese text recognition.
- **Key Information Extraction (KIE)**:
  - Extracts structured fields (document number, date, issuing organization, document type, and subject) from Vietnamese administrative/legal documents.
  - Uses a **hybrid approach**: rule-based regex patterns for high confidence (deterministic) and local LLM context inference as a fallback.
- **Document Summarization**:
  - Summarizes extracted OCR text locally, privately, and securely using **Ollama** (defaults to `qwen2.5:3b-instruct`).
- **Scanner & Barcode Integration**:
  - Supports direct integration with physical scanners.
  - Automatically splits document bundles based on detected barcodes.
- **FastAPI Backend**:
  - High-performance REST API.
  - Modular endpoints for preprocessing, OCR, and summarization, or full end-to-end pipelines.

## Quick Start Demo

You can try the full pipeline (Preprocessing -> OCR -> Summary) using the included `demo.py` script:

```bash
python demo.py
```
*Make sure to place an `image.png` in the root directory before running or update the script's `input_image_path`. The outputs (cleaned images, OCR JSONs, and text summaries) will be saved in the `data/manual_preprocess/` directory.*

## Installation

### Prerequisites
1. **Python 3.10+** (Recommended)
2. **Tesseract OCR**: Needs to be installed on your system. It relies on standard system PATH or default Windows installation paths (`C:/Program Files/Tesseract-OCR/tesseract.exe`).
3. **Ollama**: (Optional, required only for auto-summarization). Needs to be installed and running locally with the target model pulled (e.g., `ollama run qwen2.5:3b-instruct`).

### Setup

Install the required Python dependencies:

```bash
pip install -r requirements.txt
```

*Note: The first time you run the OCR service, `vietocr` will download its `vgg_transformer` weights.*

## Main API Endpoints

Start the API server:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Core Endpoints

- **`POST /api/v1/scan-upload`**: Scan documents from a connected physical scanner or upload image files. Automatically separates documents into bundles if barcodes are found.
- **`POST /api/v1/preprocess`**: Run the configurable preprocessing pipeline on local filesystem images.
- **`POST /api/v1/upload-preprocess`**: Unified endpoint to upload files and immediately run the preprocessing pipeline (auto-crop, deskew, binarize, etc.).
- **`POST /api/v1/ocr-fulltext`**: Extract full text from images using the hybrid Tesseract + VietOCR method.
- **`POST /api/v1/kie`**: Extract structured Key Information (KIE) from raw OCR text.
- **`POST /api/v1/ocr-kie`**: Full pipeline from image to OCR to KIE. Returns both per-page extraction and merged document-level KIE results.
- **`POST /api/v1/auto-summary`**: Submit pure text to be summarized by the local Ollama model.
- **`POST /api/v1/ocr-auto-summary`**: Convenience endpoint for end-to-end OCR extraction followed by immediate summarization.

Review the Swagger/OpenAPI documentation at `http://localhost:8000/docs` while the server is running to detailed request options, including how to toggle specific preprocessing features (like `preserve_red_stamp` or `shadow_removal`).

## Testing

The repository includes a comprehensive `pytest` suite testing both API endpoints and core services.

```bash
pytest
```
