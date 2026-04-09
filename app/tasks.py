from app.celery_app import celery_app
from app.services.kie_extractor import extract_kie_from_pages, extract_kie
from app.services.ocr import run_ocr_fulltext
from app.services.document_splitter import split_document_by_content
from app.services.preprocessing import run_preprocess_pipeline
from app.services.validation import validate_document_logic
import logging

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, name="app.tasks.process_ocr_kie")
def process_ocr_kie(self, request_data: dict) -> dict:
    """
    Task for running OCR and KIE asynchronously.
    request_data should be a dict equivalent to OCRKIERequest.
    """
    try:
        self.update_state(state='PROGRESS', meta={'message': 'Running OCR...'})
        ocr_result = run_ocr_fulltext(
            input_paths=request_data["input_paths"],
            lang=request_data.get("lang", "vie"),
            psm=request_data.get("psm", 3),
            oem=request_data.get("oem", 3),
        )

        self.update_state(state='PROGRESS', meta={'message': 'Running KIE extraction...'})
        kie_result = extract_kie_from_pages(
            ocr_pages=ocr_result["pages"],
            model=request_data.get("model", "qwen2.5:3b-instruct"),
            ollama_url=request_data.get("ollama_url", "http://localhost:11434"),
            use_llm=request_data.get("use_llm", True),
            template=request_data.get("template"),
        )
        
        # Build schemas dicts
        pages = []
        for ocr_page, kie_page in zip(ocr_result["pages"], kie_result["pages"]):
            pages.append({
                "input_path": ocr_page["input_path"],
                "full_text": ocr_page["full_text"],
                "lines": ocr_page["lines"],
                "kie": kie_page["kie"]
            })
            
        return {
            "status": "success",
            "pages": pages,
            "document": kie_result["document"]
        }
    except Exception as e:
        logger.exception("Task process_ocr_kie failed")
        return {"status": "error", "message": str(e)}

@celery_app.task(bind=True, name="app.tasks.process_split_document")
def process_split_document(self, request_data: dict) -> dict:
    try:
        self.update_state(state='PROGRESS', meta={'message': 'Running OCR...'})
        ocr_result = run_ocr_fulltext(
            input_paths=request_data["input_paths"],
            lang=request_data.get("lang", "vie"),
            psm=request_data.get("psm", 3),
            oem=request_data.get("oem", 3),
        )
        self.update_state(state='PROGRESS', meta={'message': 'Running Document Splitting...'})
        split_result = split_document_by_content(
            ocr_pages=ocr_result["pages"],
            model=request_data.get("model", "qwen2.5:3b-instruct"),
            ollama_url=request_data.get("ollama_url", "http://localhost:11434"),
            use_llm=request_data.get("use_llm", True),
            template=request_data.get("template"),
        )
        return {"status": "success", "result": split_result}
    except Exception as e:
        logger.exception("Task process_split_document failed")
        return {"status": "error", "message": str(e)}
