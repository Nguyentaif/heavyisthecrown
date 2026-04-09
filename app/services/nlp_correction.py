import logging
import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

logger = logging.getLogger(__name__)

_tokenizer = None
_model = None

def get_corrector_model():
    global _tokenizer, _model
    if _tokenizer is None or _model is None:
        try:
            model_name = "bmd1905/vietnamese-correction-v2"
            _tokenizer = AutoTokenizer.from_pretrained(model_name)
            _model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
            logger.info("Successfully loaded NLP correction model from Hugging Face.")
        except Exception as e:
            logger.warning(f"Could not load NLP correction model. Falling back to passthrough. Error: {e}")
            _model = "FAILED"
    return _tokenizer, _model

def correct_text_nlp(text: str) -> str:
    """
    Apply NLP Error Correction on OCR text.
    For production, this utilizes a fine-tuned Hugging Face model
    or passes through if the model is not initialized.
    """
    if not text or len(text.strip()) == 0:
        return text

    tokenizer, model = get_corrector_model()
    
    # If model failed to load, return original
    if model == "FAILED" or model is None:
        return text

    try:
        inputs = tokenizer(text, return_tensors="pt", max_length=512, truncation=True)
        outputs = model.generate(**inputs, max_length=512)
        corrected = tokenizer.decode(outputs[0], skip_special_tokens=True)
        return corrected
    except Exception as e:
        logger.error(f"NLP correction failed during inference: {e}")
    
    return text
