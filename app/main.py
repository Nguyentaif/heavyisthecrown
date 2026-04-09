from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from app.schemas import (
    AutoSummaryRequest,
    AutoSummaryResponse,
    CustomFieldDef,  # noqa: F401  (re-exported for OpenAPI visibility)
    ExtractFieldsRequest,
    ExtractFieldsResponse,
    KIEField,
    KIERequest,
    KIEResponse,
    KIEResult,
    KIETemplate,    # noqa: F401
    OCRAutoSummaryRequest,
    OCRAutoSummaryResponse,
    OCRKIEPageResult,
    OCRKIERequest,
    OCRKIEResponse,
    PostprocessRequest,
    PostprocessResponse,
    OCRRequest,
    OCRResponse,
    PreprocessRequest,
    PreprocessResponse,
    ScanUploadResponse,
    ScannerSettings,
    SplitDocumentRequest,
    SplitDocumentResponse,
    UploadPreprocessResponse,
    ValidationResult,
    AsyncTaskResponse,
    TaskStatusResponse,
    ExportPDFRequest,
    ExportPDFResponse,
    ExportPDFRequest,
    ExportPDFResponse,
    FeedbackRequest,
    FeedbackResponse,
)
from app.services.barcode_splitter import split_pages_by_barcode
from app.services.document_splitter import split_document_by_content
from app.services.kie_extractor import extract_kie, extract_kie_from_pages
from app.services.ocr import run_ocr_fulltext
from app.services.postprocessing import run_postprocess_pipeline
from app.services.preprocessing import run_preprocess_pipeline
from app.services.pdf_exporter import create_searchable_pdf
from app.services.feedback import save_feedback
from app.services.nlp_correction import correct_text_nlp
from app.services.scanner import ScanConfig, scan_from_device
from app.services.summarizer import summarize_with_ollama
from app.services.validation import validate_document_logic
from app.celery_app import celery_app
from app.tasks import process_ocr_kie, process_split_document

app = FastAPI(title="VN-Digitize OCR API", version="0.1.0")

DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"
PREPROCESSED_DIR = DATA_DIR / "preprocessed"


def _save_uploads(files: list[UploadFile], destination: Path) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    saved_paths: list[Path] = []
    for file in files:
        suffix = Path(file.filename or "page").suffix or ".png"
        out_path = destination / f"{uuid4().hex}{suffix}"
        with out_path.open("wb") as out:
            out.write(file.file.read())
        saved_paths.append(out_path)
    return saved_paths


def _to_kie_result(raw: dict) -> KIEResult:
    raw_custom = raw.get("custom_fields", {})
    custom_kie = {k: KIEField(**v) for k, v in raw_custom.items()}
    return KIEResult(
        so_van_ban=raw["so_van_ban"],
        ngay_ban_hanh=raw["ngay_ban_hanh"],
        co_quan_ban_hanh=raw["co_quan_ban_hanh"],
        loai_van_ban=raw["loai_van_ban"],
        trich_yeu=raw["trich_yeu"],
        custom_fields=custom_kie,
        model_used=raw.get("model_used"),
    )


@app.post("/api/v1/scan-upload", response_model=ScanUploadResponse)
def scan_or_upload(
    source: str = Form(..., description="scanner or upload"),
    dpi: int = Form(300),
    color_mode: str = Form("color"),
    files: list[UploadFile] = File(default_factory=list),
) -> ScanUploadResponse:
    if source not in {"scanner", "upload"}:
        raise HTTPException(status_code=400, detail="source must be scanner or upload")

    session_dir = RAW_DIR / uuid4().hex
    session_dir.mkdir(parents=True, exist_ok=True)

    if source == "scanner":
        try:
            settings = ScannerSettings(dpi=dpi, color_mode=color_mode)
            page_paths = scan_from_device(
                session_dir, ScanConfig(dpi=settings.dpi, color_mode=settings.color_mode)
            )
        except NotImplementedError as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover
            raise HTTPException(status_code=500, detail=f"scanner error: {exc}") from exc
    else:
        if not files:
            raise HTTPException(status_code=400, detail="files are required for upload")
        page_paths = _save_uploads(files, session_dir)

    if not page_paths:
        raise HTTPException(status_code=400, detail="no pages available after input")

    try:
        bundles = split_pages_by_barcode(page_paths)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ScanUploadResponse(
        source=source,
        total_pages=len(page_paths),
        bundles=bundles,
        saved_pages=[str(path) for path in page_paths],
    )


@app.post("/api/v1/preprocess", response_model=PreprocessResponse)
def preprocess(request: PreprocessRequest) -> PreprocessResponse:
    output_dir = PREPROCESSED_DIR / uuid4().hex
    try:
        results = run_preprocess_pipeline(request.input_paths, output_dir, request.options)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    total_outputs = sum(1 for item in results if not item["skipped_as_blank"])
    return PreprocessResponse(
        total_inputs=len(request.input_paths),
        total_outputs=total_outputs,
        results=results,
    )


@app.post("/api/v1/upload-preprocess", response_model=UploadPreprocessResponse)
def upload_and_preprocess(
    files: list[UploadFile] = File(default_factory=list),
    deskew: bool = Form(True),
    auto_crop: bool = Form(True),
    shadow_removal: bool = Form(True),
    denoise: bool = Form(True),
    remove_yellow_stains: bool = Form(True),
    binarize: bool = Form(False),
    preserve_red_stamp: bool = Form(True),
    remove_blank_pages: bool = Form(True),
    blank_ratio_threshold: float = Form(0.006),
) -> UploadPreprocessResponse:
    if not files:
        raise HTTPException(status_code=400, detail="files are required")

    raw_dir = RAW_DIR / uuid4().hex
    saved_paths = _save_uploads(files, raw_dir)

    preprocess_request = PreprocessRequest(
        input_paths=[str(path) for path in saved_paths],
        options={
            "deskew": deskew,
            "auto_crop": auto_crop,
            "shadow_removal": shadow_removal,
            "denoise": denoise,
            "remove_yellow_stains": remove_yellow_stains,
            "binarize": binarize,
            "preserve_red_stamp": preserve_red_stamp,
            "remove_blank_pages": remove_blank_pages,
            "blank_ratio_threshold": blank_ratio_threshold,
        },
    )

    output_dir = PREPROCESSED_DIR / uuid4().hex
    try:
        results = run_preprocess_pipeline(
            preprocess_request.input_paths,
            output_dir,
            preprocess_request.options,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    total_outputs = sum(1 for item in results if not item["skipped_as_blank"])
    return UploadPreprocessResponse(
        total_uploaded=len(saved_paths),
        total_outputs=total_outputs,
        saved_pages=[str(path) for path in saved_paths],
        results=results,
    )


@app.post("/api/v1/ocr-fulltext", response_model=OCRResponse)
def ocr_fulltext(request: OCRRequest) -> OCRResponse:
    try:
        result = run_ocr_fulltext(
            input_paths=request.input_paths,
            lang=request.lang,
            psm=request.psm,
            oem=request.oem,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return OCRResponse(**result)


@app.post("/api/v1/auto-summary", response_model=AutoSummaryResponse)
def auto_summary(request: AutoSummaryRequest) -> AutoSummaryResponse:
    try:
        result = summarize_with_ollama(
            text=request.text,
            model=request.model,
            ollama_url=request.ollama_url,
            max_words=request.max_words,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return AutoSummaryResponse(**result)


@app.post("/api/v1/ocr-auto-summary", response_model=OCRAutoSummaryResponse)
def ocr_auto_summary(request: OCRAutoSummaryRequest) -> OCRAutoSummaryResponse:
    try:
        ocr_result = run_ocr_fulltext(
            input_paths=request.input_paths,
            lang=request.lang,
            psm=request.psm,
            oem=request.oem,
        )
        merged_text = "\n\n".join(
            page["full_text"] for page in ocr_result["pages"] if page["full_text"]
        ).strip()
        if not merged_text:
            raise ValueError("OCR produced empty text; cannot generate summary.")
        summary_result = summarize_with_ollama(
            text=merged_text,
            model=request.model,
            ollama_url=request.ollama_url,
            max_words=request.max_words,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return OCRAutoSummaryResponse(
        ocr=OCRResponse(**ocr_result),
        summary=summary_result["summary"],
        model=summary_result["model"],
    )


@app.post("/api/v1/kie", response_model=KIEResponse)
def kie_extract(request: KIERequest) -> KIEResponse:
    """
    Extract structured key information from raw OCR text of a Vietnamese
    administrative / legal document.

    Uses a hybrid approach:
    - Stage 1: regex / pattern matching (fast, deterministic)
    - Stage 2: LLM via Ollama (optional, contextual; skipped on error/timeout)

    Optionally accepts a ``template`` with ``custom_fields`` to extract
    domain-specific fields beyond the 5 standard ones (e.g. for courts or
    insurance agencies).
    """
    merged = extract_kie(
        text=request.text,
        model=request.model,
        ollama_url=request.ollama_url,
        use_llm=request.use_llm,
        template=request.template,
    )
    # Map raw custom_fields dict -> dict[str, KIEField]
    raw_custom = merged.get("custom_fields", {})
    custom_kie = {k: KIEField(**v) for k, v in raw_custom.items()}
    result = KIEResult(
        so_van_ban=merged["so_van_ban"],
        ngay_ban_hanh=merged["ngay_ban_hanh"],
        co_quan_ban_hanh=merged["co_quan_ban_hanh"],
        loai_van_ban=merged["loai_van_ban"],
        trich_yeu=merged["trich_yeu"],
        custom_fields=custom_kie,
        model_used=merged.get("model_used"),
    )
    return KIEResponse(result=result)


@app.post("/api/v1/ocr-kie", response_model=OCRKIEResponse)
def ocr_kie(request: OCRKIERequest) -> OCRKIEResponse:
    """
    Full pipeline: images → OCR → KIE.

    Response contains:
    - ``pages``    : per-page OCR text + bounding-box lines + KIE fields
                     (for UI highlighting, QA, and debugging)
    - ``document`` : document-level KIE merged from all pages
                     (highest-confidence value per field; for business use)

    Optionally accepts a ``template`` with ``custom_fields`` for domain-specific
    extraction on top of the 5 standard administrative fields.
    """
    try:
        ocr_result = run_ocr_fulltext(
            input_paths=request.input_paths,
            lang=request.lang,
            psm=request.psm,
            oem=request.oem,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    ocr_pages = ocr_result["pages"]  # list of dicts with input_path/full_text/lines

    kie_result = extract_kie_from_pages(
        ocr_pages=ocr_pages,
        model=request.model,
        ollama_url=request.ollama_url,
        use_llm=request.use_llm,
        template=request.template,
    )

    # Build per-page schema objects (include bbox lines from OCR)
    page_schemas: list[OCRKIEPageResult] = []
    for ocr_page, kie_page in zip(ocr_pages, kie_result["pages"]):
        page_schemas.append(
            OCRKIEPageResult(
                input_path=ocr_page["input_path"],
                full_text=ocr_page["full_text"],
                lines=ocr_page["lines"],
                kie=_to_kie_result(kie_page["kie"]),
            )
        )

    return OCRKIEResponse(
        pages=page_schemas,
        document=_to_kie_result(kie_result["document"]),
    )


@app.post("/api/v1/extract-fields", response_model=ExtractFieldsResponse)
def extract_fields(request: ExtractFieldsRequest) -> ExtractFieldsResponse:
    """
    Business endpoint: images -> OCR -> KIE -> logical validation.
    """
    try:
        ocr_result = run_ocr_fulltext(
            input_paths=request.input_paths,
            lang=request.lang,
            psm=request.psm,
            oem=request.oem,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    ocr_pages = ocr_result["pages"]
    kie_result = extract_kie_from_pages(
        ocr_pages=ocr_pages,
        model=request.model,
        ollama_url=request.ollama_url,
        use_llm=request.use_llm,
        template=request.template,
    )

    page_schemas: list[OCRKIEPageResult] = []
    for ocr_page, kie_page in zip(ocr_pages, kie_result["pages"]):
        page_schemas.append(
            OCRKIEPageResult(
                input_path=ocr_page["input_path"],
                full_text=ocr_page["full_text"],
                lines=ocr_page["lines"],
                kie=_to_kie_result(kie_page["kie"]),
            )
        )

    validation = validate_document_logic(kie_result["document"])
    return ExtractFieldsResponse(
        pages=page_schemas,
        document=_to_kie_result(kie_result["document"]),
        validation=ValidationResult(**validation),
    )


@app.post("/api/v1/split-document", response_model=SplitDocumentResponse)
def split_document(request: SplitDocumentRequest) -> SplitDocumentResponse:
    """
    Split a large input into logical documents based on OCR+KIE content signals.
    """
    try:
        ocr_result = run_ocr_fulltext(
            input_paths=request.input_paths,
            lang=request.lang,
            psm=request.psm,
            oem=request.oem,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    split_result = split_document_by_content(
        ocr_pages=ocr_result["pages"],
        model=request.model,
        ollama_url=request.ollama_url,
        use_llm=request.use_llm,
        template=request.template,
    )
    # Convert nested classification payloads to schema
    for doc in split_result["documents"]:
        doc["classification"] = _to_kie_result(doc["classification"])
    return SplitDocumentResponse(**split_result)


@app.post("/api/v1/postprocess-check", response_model=PostprocessResponse)
def postprocess_check(request: PostprocessRequest) -> PostprocessResponse:
    """
    Post-processing checks: stamp/signature detection and table extraction.
    """
    try:
        ocr_result = run_ocr_fulltext(
            input_paths=request.input_paths,
            lang=request.lang,
            psm=request.psm,
            oem=request.oem,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    result = run_postprocess_pipeline(
        ocr_pages=ocr_result["pages"],
        yolo_model_path=request.yolo_model_path,
        conf_threshold=request.conf_threshold,
    )
    return PostprocessResponse(**result)


@app.post("/api/v1/async/ocr-kie", response_model=AsyncTaskResponse)
def async_ocr_kie(request: OCRKIERequest) -> AsyncTaskResponse:
    """
    Trigger async OCR -> KIE pipeline.
    """
    task = process_ocr_kie.delay(request.model_dump())
    return AsyncTaskResponse(
        task_id=task.id,
        status="PENDING",
        message="Task submitted successfully."
    )


@app.post("/api/v1/async/split-document", response_model=AsyncTaskResponse)
def async_split_document(request: SplitDocumentRequest) -> AsyncTaskResponse:
    """
    Trigger async document splitting pipeline.
    """
    task = process_split_document.delay(request.model_dump())
    return AsyncTaskResponse(
        task_id=task.id,
        status="PENDING",
        message="Task submitted successfully."
    )


@app.get("/api/v1/task/{task_id}", response_model=TaskStatusResponse)
def get_task_status(task_id: str) -> TaskStatusResponse:
    """
    Check status of an async celery task.
    """
    task_result = celery_app.AsyncResult(task_id)
    result = None
    meta = None
    status = task_result.status
    
    if task_result.state == "SUCCESS":
        result = task_result.result
    elif task_result.state == "FAILURE":
        meta = {"error": str(task_result.result)}
    elif task_result.state == "PROGRESS":
        meta = task_result.info
    
    return TaskStatusResponse(
        task_id=task_id,
        status=status,
        result=result,
        meta=meta
    )


@app.post("/api/v1/export-pdf-searchable", response_model=ExportPDFResponse)
def export_pdf_searchable(request: ExportPDFRequest) -> ExportPDFResponse:
    """
    Exports processing results into a 2-layer PDF/A-like document.
    """
    if not request.pages:
        raise HTTPException(status_code=400, detail="No pages provided to export.")
    
    # Dump the Pydantic models to a dict structure for the service
    pages_data = [page.model_dump() for page in request.pages]
    
    output_dir = DATA_DIR / "exported"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / request.output_filename

    try:
        final_pdf_path = create_searchable_pdf(pages_data, str(out_path))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create PDF: {exc}") from exc

    return ExportPDFResponse(
        output_path=final_pdf_path,
        download_url=f"/api/v1/downloads/{request.output_filename}"
    )


@app.post("/api/v1/feedback", response_model=FeedbackResponse)
def submit_feedback(request: FeedbackRequest) -> FeedbackResponse:
    """
    Submit user QA feedback when the AI extracts fields incorrectly.
    This triggers incremental learning processes in the background.
    """
    saved_count = 0
    for item in request.corrections:
        try:
            save_feedback(
                original_text=item.original_text,
                corrected_text=item.corrected_text,
                field_name=item.field_name,
                document_id=item.document_id
            )
            saved_count += 1
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Feedback save failed: {e}")
    
    return FeedbackResponse(status="success", saved_count=saved_count)


from pydantic import BaseModel
class NLPCorrectRequest(BaseModel):
    text: str

class NLPCorrectResponse(BaseModel):
    original: str
    corrected: str

@app.post("/api/v1/nlp-correct", response_model=NLPCorrectResponse)
def nlp_correct_text(request: NLPCorrectRequest) -> NLPCorrectResponse:
    """
    Correct OCR spelling mistakes using a pre-trained language model (e.g. PhoBERT variants).
    """
    corrected = correct_text_nlp(request.text)
    return NLPCorrectResponse(original=request.text, corrected=corrected)
