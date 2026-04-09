import re

def _clean_ocr_text(text: str) -> str:
    # Mất chữ 'Q' ở đầu dòng
    text = re.sub(r'^[uU]y định\b', 'Quy định', text)
    # Lỗi sai dấu
    text = text.replace('chồng tệ nạn', 'chống tệ nạn')
    text = text.replace('vưem ninh', 'vực an ninh')
    # Chữ cái đầu viết hoa
    if text:
        text = text[0].upper() + text[1:]
    return text

text1 = "uy định xử phạt vi phạm hành chính trong lĩnh vưem ninh, trật tự, an toàn xã hội; phòng, chồng tệ nạn xã hội; phòng, chống bạo lực gia đình"
print("Original:", text1)
print("Cleaned:", _clean_ocr_text(text1))

