"""
kie_extractor.py — Hybrid Key Information Extraction for Vietnamese Admin Documents.

Stage 1 : Regex / pattern matching  → confidence ≥ 0.90
Stage 2 : LLM (Ollama) context      → confidence 0.60–0.80  (optional)
Stage 3 : Merge                     → prefer stage-1 when confidence ≥ 0.85

Dynamic Template support: pass a list of CustomFieldDef to extract additional
domain-specific fields (e.g. ten_bi_cao for courts, so_so_bhxh for insurance).
"""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.schemas import CustomFieldDef, KIETemplate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Confidence constants
# ---------------------------------------------------------------------------
_CONF_HIGH = 0.93   # strong regex match (pattern unambiguous)
_CONF_MED = 0.80    # heuristic / partial regex match
_CONF_LLM = 0.72    # typical LLM extraction
_CONF_LLM_LOW = 0.55  # LLM but uncertain field
_MERGE_THRESHOLD = 0.85  # keep stage-1 result if confidence ≥ this

# ---------------------------------------------------------------------------
# Vietnamese document type keywords  (display name, compiled pattern)
# ---------------------------------------------------------------------------
_DOC_TYPES: list[tuple[str, re.Pattern[str]]] = [
    ("Quyết định",      re.compile(r'\bquy[eế]t\s+[dđ][iị]nh\b', re.I | re.U)),
    ("Nghị quyết",      re.compile(r'\bngh[iị]\s+quy[eế]t\b', re.I | re.U)),
    ("Thông tư",        re.compile(r'\bth[oô]ng\s+t[uư]\b', re.I | re.U)),
    ("Nghị định",       re.compile(r'\bngh[iị]\s+[dđ][iị]nh\b', re.I | re.U)),
    ("Công văn",        re.compile(r'\bc[oô]ng\s+v[aă]n\b', re.I | re.U)),
    ("Chỉ thị",         re.compile(r'\bch[iỉ]\s+th[iị]\b', re.I | re.U)),
    ("Thông báo",       re.compile(r'\bth[oô]ng\s+b[aá]o\b', re.I | re.U)),
    ("Báo cáo",         re.compile(r'\bb[aá]o\s+c[aá]o\b', re.I | re.U)),
    ("Tờ trình",        re.compile(r'\bt[oờ]\s+tr[iì]nh\b', re.I | re.U)),
    ("Biên bản",        re.compile(r'\bbi[eê]n\s+b[aả]n\b', re.I | re.U)),
    ("Hợp đồng",        re.compile(r'\bh[oợ]p\s+[dđ][oồ]ng\b', re.I | re.U)),
    ("Pháp lệnh",       re.compile(r'\bph[aá]p\s+l[eệ]nh\b', re.I | re.U)),
    ("Luật",            re.compile(r'\blu[aậ]t\b', re.I | re.U)),
    ("Kế hoạch",        re.compile(r'\bk[eế]\s+ho[aạ]ch\b', re.I | re.U)),
    ("Giấy phép",       re.compile(r'\bgi[aấ]y\s+ph[eé]p\b', re.I | re.U)),
    ("Giấy chứng nhận", re.compile(r'\bgi[aấ]y\s+ch[uứ]ng\s+nh[aậ]n\b', re.I | re.U)),
    ("Hướng dẫn",       re.compile(r'\bh[uư][oớ]ng\s+d[aẫ]n\b', re.I | re.U)),
    ("Quy chế",         re.compile(r'\bquy\s+ch[eế]\b', re.I | re.U)),
    ("Quy định",        re.compile(r'\bquy\s+[dđ][iị]nh\b', re.I | re.U)),
]

# ---------------------------------------------------------------------------
# Issuing-organisation prefix pattern (first ~20 lines of doc)
# ---------------------------------------------------------------------------
_ORG_LINE = re.compile(
    # Top-level government / legislative bodies (no further prefix needed)
    r'^(CHÍNH\s+PHỦ|QUỐC\s+HỘI|CHỦ\s+TỊCH\s+NƯỚC|TÒA\s+ÁN\s+NHÂN\s+DÂN|VIỆN\s+KIỂM\s+SÁT|'
    # Ministries, committees, departments …
    r'BỘ|UỶ\s+BAN|ỦY\s+BAN|UBND|SỞ|CỤC|TỔNG\s+CỤC|BAN|HỘI\s+ĐỒNG|'
    r'TRƯỜNG|VIỆN|TRUNG\s+TÂM|CÔNG\s+TY|TẬP\s+ĐOÀN|PHÒNG|CHI\s+CỤC|'
    r'VĂN\s+PHÒNG|THÀNH\s+PHỐ|TỈNH|HUYỆN|XÃ|PHƯỜNG|THỊ\s+TRẤN|'
    r'THỊ\s+XÃ|ĐẠI\s+HỌC|CAO\s+ĐẲNG|TRUNG\s+CẤP)\b',
    re.U,  # intentionally NOT re.I — org names are always all-caps in headers
)

# ---------------------------------------------------------------------------
# Document number patterns
# ---------------------------------------------------------------------------
_SO_PATTERNS: list[re.Pattern[str]] = [
    # Best: 123/2024/QĐ-BYT  or  45/2024/TT-BTC
    re.compile(r'[Ss][oố][:\.\s]+(\d+/\d{4}/[\w][\w\-]*/[\w][\w\-]*)', re.U),
    # Common: 123/QĐ-UBND
    re.compile(r'[Ss][oố][:\.\s]+(\d+/[\w][\w\-]*/[\w][\w\-]*)', re.U),
    # Simple: 45/UBND-VP
    re.compile(r'[Ss][oố][:\.\s]+(\d+/[\w][\w/\-]+)', re.U),
    # Fallback: Số 1234
    re.compile(r'[Ss][oố][:\.\s]+(\d[\d\-/\w]+)', re.U),
]

# ---------------------------------------------------------------------------
# Date patterns
# ---------------------------------------------------------------------------
_DATE_FULL = re.compile(
    r'ng[àa]y\s+(\d{1,2})\s+th[aá]ng\s+(\d{1,2})\s+n[aă]m\s+(\d{4})',
    re.I | re.U,
)
# Captures the FULL date line including optional city prefix, e.g. "Hà Nội, ngày 30 tháng 6 năm 2024"
_DATE_FULL_LINE = re.compile(
    r'([^\n,]+,\s*ng[àa]y\s+\d{1,2}\s+th[aá]ng\s+\d{1,2}\s+n[aă]m\s+\d{4})',
    re.I | re.U,
)
_DATE_DMY = re.compile(r'\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b')

# ---------------------------------------------------------------------------
# Subject / trích yếu patterns
# ---------------------------------------------------------------------------
_VV = re.compile(r'[Vv]/[Vv][:\s]+(.*)', re.U)
_VE_VIEC = re.compile(r'[Vv]ề\s+vi[eệ]c[:\s]+(.*)', re.I | re.U)

# ---------------------------------------------------------------------------
# JSON extraction helper (for LLM response that may include extra text)
# ---------------------------------------------------------------------------
_JSON_BLOCK = re.compile(r'\{.*\}', re.S)

# ============================================================================
# Stage 1 — Regex extraction
# ============================================================================


def _kie_field(value: str | None, confidence: float) -> dict[str, Any]:
    if value is None:
        return {"value": None, "confidence": 0.0}
    return {"value": value.strip(), "confidence": round(confidence, 4)}


# Lines that introduce referenced (not main) documents — must be skipped
_REF_LINE_PREFIX = re.compile(
    r'^\s*(c[aă]n\s+c[uứ]|theo\s+(ngh[iị]|quy[eế]t|lu[aậ]t|th[oô]ng|quy[eế]t|ph[aá]p))',
    re.I | re.U,
)


def _extract_so_van_ban(text: str) -> dict[str, Any]:
    """Extract document number from the top of the document only, ignoring reference lines."""
    lines = text.splitlines()
    # Only search in the first 25 lines to stay in the header/preamble zone
    header_lines = []
    for line in lines[:25]:
        if _REF_LINE_PREFIX.match(line):
            continue  # skip "Căn cứ ..." / "Theo ..." reference lines
        header_lines.append(line)
    header_text = "\n".join(header_lines)

    for i, pattern in enumerate(_SO_PATTERNS):
        m = pattern.search(header_text)
        if m:
            value = m.group(1).strip().rstrip(".,;:")
            # Confidence degrades slightly for weaker patterns
            conf = _CONF_HIGH if i == 0 else (_CONF_HIGH - 0.03 * i)
            return _kie_field(value, max(conf, _CONF_MED))
    return _kie_field(None, 0.0)


def _extract_ngay_ban_hanh(text: str) -> dict[str, Any]:
    # Best: full line with city, e.g. "Hà Nội, ngày 30 tháng 6 năm 2024"
    m_line = _DATE_FULL_LINE.search(text)
    if m_line:
        raw_val = m_line.group(1).strip()
        # Clean prefix: remove 'Số: 123...' if Tesseract merges them on the same line
        parts = raw_val.split(',', 1)
        if len(parts) == 2:
            prefix = parts[0].strip()
            words = prefix.split()
            valid_words = []
            for w in reversed(words):
                # Stop if we hit a word containing slashes, colons, or looks like "Số"
                if '/' in w or ':' in w or 'Số' in w or 'số' in w.lower():
                    break
                valid_words.append(w)
            
            if valid_words:
                clean_prefix = " ".join(reversed(valid_words))
                raw_val = f"{clean_prefix}, {parts[1].strip()}"
            else:
                raw_val = parts[1].strip()
        return _kie_field(raw_val, _CONF_HIGH)

    # Good: bare date phrase without city, e.g. "ngày 30 tháng 6 năm 2024"
    m = _DATE_FULL.search(text)
    if m:
        day, month, year = m.group(1), m.group(2), m.group(3)
        value = f"ngày {day} tháng {month} năm {year}"
        return _kie_field(value, _CONF_HIGH)

    # Fallback: DD/MM/YYYY — less confident because could be any date
    m2 = _DATE_DMY.search(text)
    if m2:
        day, month, year = m2.group(1), m2.group(2), m2.group(3)
        # Only accept plausible dates
        if 1 <= int(day) <= 31 and 1 <= int(month) <= 12 and 1990 <= int(year) <= 2099:
            value = f"{day.zfill(2)}/{month.zfill(2)}/{year}"
            return _kie_field(value, _CONF_MED)

    return _kie_field(None, 0.0)


def _extract_loai_van_ban(text: str) -> dict[str, Any]:
    """
    Identify the MAIN document type from the HEADER ONLY (first ~15 lines).
    Lines beginning with 'Căn cứ' / 'Theo' are reference lines and must be
    excluded — they may mention other document types that are NOT the main type.
    """
    lines = text.splitlines()
    # Limit to header block; skip reference lines entirely
    header_lines: list[str] = []
    for line in lines[:15]:
        if _REF_LINE_PREFIX.match(line):
            continue
        header_lines.append(line)
    head = "\n".join(header_lines)

    best_name: str | None = None
    best_pos: int = len(head) + 1
    best_conf = 0.0

    for display_name, pattern in _DOC_TYPES:
        m = pattern.search(head)
        if m:
            pos = m.start()
            # Earlier in document → higher confidence
            conf = _CONF_HIGH if pos < 300 else _CONF_MED
            if pos < best_pos:
                best_pos = pos
                best_name = display_name
                best_conf = conf

    return _kie_field(best_name, best_conf)


def _extract_co_quan_ban_hanh(text: str) -> dict[str, Any]:
    """Look for issuing-org lines in the first 20 lines (usually header block)."""
    lines = text.splitlines()
    candidates: list[tuple[int, str]] = []  # (line_index, cleaned_text)

    for i, raw_line in enumerate(lines[:20]):
        line = raw_line.strip()
        if not line:
            continue
        if _ORG_LINE.match(line):
            candidates.append((i, line))

    if not candidates:
        return _kie_field(None, 0.0)

    # If multiple, prefer the earliest that is NOT just a generic top header
    # (e.g. the second line after "CỘNG HOÀ XÃ HỘI..." is usually the org)
    value = candidates[0][1]
    # Merge consecutive org lines (e.g. "BỘ Y TẾ" on one line, "---" separator next)
    # → just take the first clean match
    conf = _CONF_HIGH if candidates[0][0] <= 5 else _CONF_MED
    return _kie_field(value, conf)


def _clean_ocr_text(text: str) -> str:
    """Tự động sửa một số lỗi OCR mạn tính của Tesseract trên các văn bản hành chính."""
    # Mất chữ 'Q' ở đầu dòng
    text = re.sub(r'^[uU]y định\b', 'Quy định', text)
    # Lỗi sai dấu
    text = text.replace('chồng tệ nạn', 'chống tệ nạn')
    text = text.replace('vưem ninh', 'vực an ninh')
    # Chữ cái đầu viết hoa
    if text:
        text = text[0].upper() + text[1:]
    return text

def _extract_trich_yeu(text: str) -> dict[str, Any]:
    """
    Extract subject (trích yếu) using two strategies:
    1. Explicit markers: 'V/v ...' or 'Về việc ...'
    2. Structural: the first non-empty line immediately after the document-type
       title line (all-caps, centred — e.g. "NGHỊ ĐỊNH").
    Strategy 1 always wins when present (it is the most reliable signal).
    """
    # Strategy 1 — explicit V/v marker (highest confidence)
    m = _VV.search(text)
    if m:
        raw = m.group(1).strip().rstrip(".,;:")
        if raw:
            return _kie_field(raw, _CONF_HIGH)

    m2 = _VE_VIEC.search(text)
    if m2:
        raw = m2.group(1).strip().rstrip(".,;:")
        if raw:
            return _kie_field(raw, _CONF_HIGH)

    # Strategy 2 — structural: line directly below the document-type title
    lines = [ln.strip() for ln in text.splitlines()]
    for i, line in enumerate(lines[:25]):
        if not line:
            continue
        
        # A title line is relatively short and is NOT a reference line
        if len(line) <= 60 and not _REF_LINE_PREFIX.match(line):
            for _, pattern in _DOC_TYPES:
                m = pattern.search(line)
                # The doc type keyword in Vietnamese admin docs is almost always uppercase 
                # (e.g. "NGHỊ ĐỊNH", not "Nghị định"). This prevents false positives on summary text.
                if m and m.group() == m.group().upper():
                    # Title found, now collect the abstract lines just below it
                    abstract_lines = []
                    for j in range(i + 1, min(i + 15, len(lines))):
                        candidate = lines[j]
                        if not candidate:
                            continue
                        
                        # Stop collecting if we hit reference lines ("Căn cứ", "Theo")
                        if _REF_LINE_PREFIX.match(candidate):
                            break
                        # Stop if we hit an article or chapter header ("Điều 1.", "CHƯƠNG I")
                        if re.match(r'^(đi[eề]u\s+\d+|ch[uư][oơ]ng\s+[IVX]+)\b', candidate, re.I):
                            break
                            
                        abstract_lines.append(candidate)
                    
                    if abstract_lines:
                        # Join and trim trailing punctuation common at the end of abstracts before references
                        abstract_text = " ".join(abstract_lines).strip().rstrip(".,;:")
                        abstract_text = _clean_ocr_text(abstract_text)
                        return _kie_field(abstract_text, _CONF_MED)
                    
                    break  # title found, but no candidate below it

    return _kie_field(None, 0.0)


def _stage1_regex(text: str) -> dict[str, Any]:
    # Normalize fraction slash (U+2044) and backslashes often produced by Tesseract in document numbers
    norm_text = text.replace('⁄', '/').replace('\\', '/')
    return {
        "so_van_ban":       _extract_so_van_ban(norm_text),
        "ngay_ban_hanh":    _extract_ngay_ban_hanh(norm_text),
        "co_quan_ban_hanh": _extract_co_quan_ban_hanh(norm_text),
        "loai_van_ban":     _extract_loai_van_ban(norm_text),
        "trich_yeu":        _extract_trich_yeu(norm_text),
    }


# ============================================================================
# Stage 2 — LLM (Ollama) extraction
# ============================================================================

_KIE_CORE_FIELDS_RULES = """\
1. loai_van_ban:
   - CHỈ lấy từ phần TIÊU ĐỀ / ĐẦU văn bản (thường viết HOA, căn giữa).
   - Ví dụ hợp lệ: "NGHỊ ĐỊNH", "THÔNG TƯ", "QUYẾT ĐỊNH", "NGHỊ QUYẾT".
   - KHÔNG lấy từ phần thân hoặc các câu viện dẫn (Căn cứ..., Theo...).

2. so_van_ban:
   - Trích số ĐẦY ĐỦ của văn bản CHÍNH (ví dụ: "73/2024/NĐ-CP").
   - KHÔNG trả về số bộ phận / số rút gọn.
   - Bỏ qua các số được nhắc đến trong "Căn cứ Nghị định số...", "Theo Quyết định...".

3. co_quan_ban_hanh:
   - Lấy từ góc TRÊN BÊN TRÁI của đầu văn bản.
   - Thường viết HOA (ví dụ: "CHÍNH PHỦ", "BỘ Y TẾ", "UBND TỈNH...").

4. ngay_ban_hanh:
   - Lấy từ dòng chứa ngày tháng (ví dụ: "Hà Nội, ngày 30 tháng 6 năm 2024").
   - Trả về TOÀN BỘ cụm từ bao gồm địa danh nếu có.

{trich_yeu_rule}
"""

_KIE_CORE_OUTPUT = """\
  "loai_van_ban": "...",
  "so_van_ban": "...",
  "ngay_ban_hanh": "...",
  "co_quan_ban_hanh": "...",
  "trich_yeu": "..."""""


def _build_kie_prompt(
    text: str,
    custom_fields: list[Any] | None = None,
    stage1_hints: dict[str, Any] | None = None,
) -> str:
    """
    Build the KIE prompt. If custom_fields are provided, append their rules
    and output keys to the prompt so the LLM extracts them too.
    """
    custom_rules = ""
    custom_output = ""
    if custom_fields:
        rule_lines = []
        output_lines = []
        for i, cf in enumerate(custom_fields, start=6):
            rule_lines.append(
                f"{i}. {cf.field_key}:\n"
                f"   - {cf.description}\n"
                f"   - Nếu không tìm thấy → trả về null."
            )
            output_lines.append(f'  "{cf.field_key}": "..."')
        custom_rules = "\n\nCÁC TRƯỜNG BỔ SUNG (THEO TEMPLATE ĐƠN VỊ):\n" + "\n\n".join(rule_lines)
        custom_output = ",\n" + ",\n".join(output_lines)

    trich_yeu_rule = (
        "5. trich_yeu:\n"
        "   - Câu / dòng nằm NGAY BÊN DƯỚI tên loại văn bản.\n"
        "   - Hoặc nội dung sau \"V/v\" / \"Về việc\"."
    )
    
    if stage1_hints and stage1_hints.get("trich_yeu") and stage1_hints["trich_yeu"].get("value"):
        raw_trich_yeu = stage1_hints["trich_yeu"]["value"]
        trich_yeu_rule = (
            "5. trich_yeu:\n"
            f"   - GỢI Ý LỜI GIẢI (đã xử lý sơ bộ): \"{raw_trich_yeu}\"\n"
            "   - Hãy lấy đoạn trên làm gốc, đối chiếu với văn bản để sửa thêm các lỗi chính tả OCR (nếu còn sót) cho chuẩn tiếng Việt.\n"
            "   - Trả về nội dung trích yếu cuối cùng (sau khi sửa lỗi)."
        )

    prompt = (
        "Bạn là chuyên gia trích xuất thông tin có cấu trúc từ văn bản pháp lý tiếng Việt (KIE).\n\n"
        "QUY TẮC NGHIÊM NGẶT TỪNG TRƯỜNG:\n"
        + _KIE_CORE_FIELDS_RULES.format(trich_yeu_rule=trich_yeu_rule)
        + custom_rules
        + "\n\nƯU TIÊN: PHẦN ĐẦU > THÂN VĂN BẢN.\n"
        "Nếu không tìm thấy → trả về null. Không hallucinate.\n\n"
        "ĐẦU RA — chỉ JSON thuần, không markdown, không giải thích:\n"
        "{\n"
        + _KIE_CORE_OUTPUT
        + custom_output
        + "\n}\n\nVĂN BẢN ĐẦU VÀO:\n"
        + text
    )
    return prompt


def _extract_json_from_response(raw: str) -> dict | None:
    """Extract and parse the first JSON object found in `raw`."""
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        pass
    m = _JSON_BLOCK.search(raw)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _validate_llm_field(field_data: Any) -> dict[str, Any]:
    """Ensure a single field from LLM output conforms to {value, confidence}."""
    if not isinstance(field_data, dict):
        return _kie_field(None, 0.0)
    value = field_data.get("value")
    conf = field_data.get("confidence", 0.0)
    if not isinstance(conf, (int, float)) or not (0.0 <= float(conf) <= 1.0):
        conf = _CONF_LLM_LOW
    if value is not None and not isinstance(value, str):
        value = str(value)
    if value == "":
        value = None
    if value is None:
        return _kie_field(None, 0.0)
    return _kie_field(value, float(conf))


def _validate_llm_result(
    raw_json: dict,
    custom_field_keys: list[str] | None = None,
) -> dict[str, Any]:
    """
    Validate and normalise KIE fields from the LLM JSON response.

    Supports two response formats:
      - Flat  : {"loai_van_ban": "NGHỊ ĐỊNH", ...}
      - Nested: {"loai_van_ban": {"value": "NGHỊ ĐỊNH", "confidence": 0.9}, ...}

    If custom_field_keys is provided, also parses those keys from the LLM response
    and stores them under the special "_custom" sub-dict in the result.
    """
    core_fields = ["so_van_ban", "ngay_ban_hanh", "co_quan_ban_hanh", "loai_van_ban", "trich_yeu"]
    result: dict[str, Any] = {}

    def _parse_one(raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return _validate_llm_field(raw)
        elif isinstance(raw, str) and raw.strip():
            return _kie_field(raw.strip(), _CONF_LLM)
        return _kie_field(None, 0.0)

    for f in core_fields:
        result[f] = _parse_one(raw_json.get(f))

    # Parse custom fields — stored in a nested dict under "_custom"
    if custom_field_keys:
        custom_result: dict[str, Any] = {}
        for key in custom_field_keys:
            custom_result[key] = _parse_one(raw_json.get(key))
        result["_custom"] = custom_result

    return result


def _call_ollama(
    prompt: str,
    model: str,
    ollama_url: str,
    timeout: int = 90,
) -> dict | None:
    """
    Send prompt to Ollama. Returns parsed JSON result dict or None on any error.
    Tries /api/generate then /v1/chat/completions (same pattern as summarizer.py).
    """
    base = ollama_url.rstrip("/")
    endpoints: list[tuple[str, dict]] = [
        (
            f"{base}/api/generate",
            {"model": model, "prompt": prompt, "stream": False},
        ),
        (
            f"{base}/v1/chat/completions",
            {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
        ),
    ]

    for url, payload in endpoints:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url=url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw_bytes = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code in {404, 405}:
                continue  # try next endpoint
            logger.warning("KIE LLM HTTP error %s at %s", exc.code, url)
            return None
        except Exception as exc:  # timeout, connection refused, etc.
            logger.warning("KIE LLM request failed at %s: %s", url, exc)
            return None

        try:
            parsed = json.loads(raw_bytes)
        except json.JSONDecodeError:
            logger.warning("KIE LLM returned non-JSON from %s", url)
            return None

        # Extract text content from either API format
        text_content: str = ""
        response_text = (parsed.get("response") or "").strip()
        if response_text:
            text_content = response_text
        else:
            choices = parsed.get("choices") or []
            if choices:
                text_content = (
                    choices[0].get("message", {}).get("content", "") or ""
                ).strip()

        if not text_content:
            continue

        result_json = _extract_json_from_response(text_content)
        if result_json:
            return result_json

    return None


def _stage2_llm(
    text: str,
    model: str,
    ollama_url: str,
    custom_fields: list[Any] | None = None,
    stage1_hints: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    Call LLM and return validated KIE field dict.
    Returns None if LLM is unavailable or response is unparseable.
    If custom_fields provided, prompt is extended and extra keys are parsed.
    """
    prompt = _build_kie_prompt(text, custom_fields=custom_fields, stage1_hints=stage1_hints)
    custom_keys = [cf.field_key for cf in custom_fields] if custom_fields else None
    raw_json = _call_ollama(prompt=prompt, model=model, ollama_url=ollama_url)
    if raw_json is None:
        logger.info("KIE LLM stage skipped (Ollama unavailable or parse error).")
        return None
    return _validate_llm_result(raw_json, custom_field_keys=custom_keys)


# ============================================================================
# Stage 3 — Merge
# ============================================================================


def _merge_field(
    stage1_field: dict[str, Any],
    stage2_field: dict[str, Any] | None,
    field_name: str = "",
) -> dict[str, Any]:
    """
    Prefer stage-1 if confidence ≥ _MERGE_THRESHOLD or stage-2 is absent.
    Otherwise prefer stage-2 if it has a higher confidence.
    """
    s1_conf = stage1_field.get("confidence", 0.0)
    s1_val = stage1_field.get("value")
    
    if stage2_field is None:
        return stage1_field

    s2_conf = stage2_field.get("confidence", 0.0)
    s2_val = stage2_field.get("value")

    # Áp dụng hàm clean một lần nữa đối với kết quả của LLM (nếu có)
    if field_name == "trich_yeu" and s2_val:
        s2_val = _clean_ocr_text(s2_val)
        stage2_field["value"] = s2_val

    # Đặc cách ưu tiên LLM cho trường 'trich_yeu' vì nhiệm vụ của LLM là bổ sung sửa lỗi OCR
    if field_name == "trich_yeu" and s2_val and s1_val:
        # Nếu LLM trả về trích yếu và Regex cũng trả về, cho phép LLM override nếu LLM đủ dài tương đối
        if len(s2_val) > 10:
            return stage2_field

    # Stage-1 result is reliable → keep it
    if s1_conf >= _MERGE_THRESHOLD:
        return stage1_field

    # Stage-1 has no value → take stage-2
    if s1_val is None:
        return stage2_field

    # Both have a value: pick whichever has higher confidence
    return stage1_field if s1_conf >= s2_conf else stage2_field


def _merge_stages(
    stage1: dict[str, Any],
    stage2: dict[str, Any] | None,
    custom_fields: list[Any] | None = None,
) -> dict[str, Any]:
    """
    Merge stage-1 (regex) and stage-2 (LLM) results.
    For custom fields, the result lives in stage2["_custom"] and stage1["_custom"].
    """
    core = ["so_van_ban", "ngay_ban_hanh", "co_quan_ban_hanh", "loai_van_ban", "trich_yeu"]
    merged: dict[str, Any] = {
        f: _merge_field(stage1[f], stage2.get(f) if stage2 else None, field_name=f)
        for f in core
    }

    # Merge custom fields: regex result (stage1["_custom"]) vs LLM result (stage2["_custom"])
    if custom_fields:
        s1_custom = stage1.get("_custom", {})
        s2_custom = (stage2 or {}).get("_custom", {})
        merged_custom: dict[str, Any] = {}
        for cf in custom_fields:
            key = cf.field_key
            s1_field = s1_custom.get(key, _kie_field(None, 0.0))
            s2_field = s2_custom.get(key, _kie_field(None, 0.0))
            merged_custom[key] = _merge_field(s1_field, s2_field, field_name=key)
        merged["_custom"] = merged_custom
    else:
        merged["_custom"] = {}

    return merged


# ============================================================================
# Public API
# ============================================================================


def _extract_custom_fields_regex(
    text: str,
    custom_fields: list[Any],
) -> dict[str, Any]:
    """
    Stage-1 for custom fields: try to extract each field via its regex_pattern.
    Returns dict keyed by field_key with {value, confidence} dicts.
    """
    result: dict[str, Any] = {}
    for cf in custom_fields:
        if cf.regex_pattern:
            try:
                pattern = re.compile(cf.regex_pattern, re.I | re.U)
                m = pattern.search(text)
                if m:
                    # Use group(1) if available, else group(0)
                    try:
                        val = m.group(1).strip()
                    except IndexError:
                        val = m.group(0).strip()
                    result[cf.field_key] = _kie_field(val, _CONF_MED)
                    continue
            except re.error:
                logger.warning("Invalid regex for field '%s': %s", cf.field_key, cf.regex_pattern)
        result[cf.field_key] = _kie_field(None, 0.0)
    return result


def extract_kie(
    text: str,
    model: str = "qwen2.5:3b-instruct",
    ollama_url: str = "http://127.0.0.1:11434",
    use_llm: bool = True,
    template: Any | None = None,
) -> dict[str, Any]:
    """
    Extract KIE fields from a single text block.

    Args:
        text:       OCR text to extract from.
        model:      Ollama model name.
        ollama_url: Ollama server URL.
        use_llm:    Whether to call LLM (stage 2).
        template:   Optional KIETemplate with custom_fields for domain-specific extraction.

    Returns a dict with keys:
        so_van_ban, ngay_ban_hanh, co_quan_ban_hanh, loai_van_ban, trich_yeu,
        custom_fields (dict), model_used.
    Each field value is: {"value": str | None, "confidence": float}
    """
    text = text.strip()
    custom_fields = (template.custom_fields if template else None) or []

    if not text:
        empty = _kie_field(None, 0.0)
        return {
            "so_van_ban": empty,
            "ngay_ban_hanh": empty,
            "co_quan_ban_hanh": empty,
            "loai_van_ban": empty,
            "trich_yeu": empty,
            "custom_fields": {cf.field_key: _kie_field(None, 0.0) for cf in custom_fields},
            "model_used": None,
        }

    stage1 = _stage1_regex(text)

    # Stage-1 for custom fields (regex-based, if regex_pattern is provided)
    if custom_fields:
        stage1["_custom"] = _extract_custom_fields_regex(text, custom_fields)

    stage2: dict[str, Any] | None = None
    model_used: str | None = None

    if use_llm:
        stage2 = _stage2_llm(
            text=text,
            model=model,
            ollama_url=ollama_url,
            custom_fields=custom_fields if custom_fields else None,
            stage1_hints=stage1,
        )
        if stage2 is not None:
            model_used = model

    merged = _merge_stages(stage1, stage2, custom_fields=custom_fields if custom_fields else None)
    merged["custom_fields"] = merged.pop("_custom", {})
    merged["model_used"] = model_used
    return merged


def extract_kie_from_pages(
    ocr_pages: list[dict[str, Any]],
    model: str = "qwen2.5:3b-instruct",
    ollama_url: str = "http://127.0.0.1:11434",
    use_llm: bool = True,
    template: Any | None = None,
) -> dict[str, Any]:
    """
    Run KIE on each OCR page individually, then merge into a document-level result.

    Args:
        ocr_pages: list of dicts with keys "input_path", "full_text", "lines".
        template:  Optional KIETemplate — if provided, custom_fields are extracted too.

    Returns:
        {
            "pages":    [ { "input_path", "full_text", "kie": {...} }, ... ],
            "document": { <5 core fields + custom_fields>, "model_used" }
        }
    """
    custom_fields = (template.custom_fields if template else None) or []
    custom_keys = [cf.field_key for cf in custom_fields]

    page_results: list[dict[str, Any]] = []
    all_model_used: list[str] = []

    for page in ocr_pages:
        page_text = (page.get("full_text") or "").strip()
        page_kie = extract_kie(
            text=page_text,
            model=model,
            ollama_url=ollama_url,
            use_llm=use_llm,
            template=template,
        )
        if page_kie.get("model_used"):
            all_model_used.append(page_kie["model_used"])

        page_results.append(
            {
                "input_path": page.get("input_path", ""),
                "full_text": page_text,
                "kie": page_kie,
            }
        )

    # Document-level merge: pick the field with the highest confidence across all pages
    core_fields = ["so_van_ban", "ngay_ban_hanh", "co_quan_ban_hanh", "loai_van_ban", "trich_yeu"]
    document: dict[str, Any] = {f: _kie_field(None, 0.0) for f in core_fields}

    # Also initialise custom field slots
    doc_custom: dict[str, Any] = {k: _kie_field(None, 0.0) for k in custom_keys}

    for page_res in page_results:
        page_kie = page_res["kie"]
        for field_name in core_fields:
            candidate = page_kie.get(field_name, _kie_field(None, 0.0))
            if candidate.get("confidence", 0.0) > document[field_name].get("confidence", 0.0):
                document[field_name] = candidate

        # Merge custom fields across pages
        for key in custom_keys:
            page_cf = page_kie.get("custom_fields", {}).get(key, _kie_field(None, 0.0))
            if page_cf.get("confidence", 0.0) > doc_custom[key].get("confidence", 0.0):
                doc_custom[key] = page_cf

    document["custom_fields"] = doc_custom
    document["model_used"] = all_model_used[0] if all_model_used else None

    return {
        "pages": page_results,
        "document": document,
    }
