import datetime
from pathlib import Path
from tinydb import TinyDB, Query

DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
FEEDBACK_DB_PATH = DATA_DIR / "feedback.json"

def get_db():
    return TinyDB(FEEDBACK_DB_PATH)

def save_feedback(original_text: str, corrected_text: str, field_name: str, document_id: str = "unknown") -> int:
    """
    Saves a record of AI extraction mistake corrected by QA personnel.
    """
    with get_db() as db:
        record = {
            "document_id": document_id,
            "field_name": field_name,
            "original_text": original_text,
            "corrected_text": corrected_text,
            "created_at": datetime.datetime.now().isoformat()
        }
        return db.insert(record)

def get_all_feedback() -> list[dict]:
    with get_db() as db:
        return db.all()
