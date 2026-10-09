"""Local image, PDF, and text ingestion with recoverable failures."""
import shutil
from pathlib import Path
from uuid import uuid4
from contracts import SourceDoc
SOURCE_DIR = Path("data/sources")
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_PAGES = 30

def ingest_text(text, announcement_date=None):
    text = text if isinstance(text, str) else ""
    return SourceDoc(uuid4().hex, "text", text, None, announcement_date, None,
                     [] if text.strip() else ["Announcement text is empty."])

def _ocr(image):
    import pytesseract
    from PIL import ImageOps
    image = ImageOps.grayscale(image)
    if image.width < 1200:
        ratio = min(3, 1200 / max(1, image.width))
        image = image.resize((round(image.width * ratio), round(image.height * ratio)))
    image = ImageOps.autocontrast(image)
    result = pytesseract.image_to_data(
        image, lang="eng+fil", output_type=pytesseract.Output.DICT, timeout=45)
    words, scores = [], []
    for word, score in zip(result["text"], result["conf"]):
        if word.strip() and float(score) >= 0:
            words.append(word)
            scores.append(float(score))
    return " ".join(words), sum(scores)/len(scores) if scores else 0.0

def ingest_file(path, announcement_date=None):
    doc = SourceDoc(uuid4().hex, "text", "", None, announcement_date, None, [])
    scores = []
    try:
        path = Path(path)
        suffix = path.suffix.lower()
        if suffix not in (".png", ".jpg", ".jpeg", ".pdf"):
            doc.warnings.append("Unsupported file. Use PNG, JPG, or PDF.")
            return doc
        doc.kind = "pdf" if suffix == ".pdf" else "image"
        if path.stat().st_size > MAX_FILE_BYTES:
            doc.warnings.append("File exceeds the 20 MB limit.")
            return doc
        SOURCE_DIR.mkdir(parents=True, exist_ok=True)
        destination = SOURCE_DIR / (doc.source_id + suffix)
        shutil.copyfile(path, destination)
        doc.original_path = str(destination.resolve())
        from PIL import Image, ImageOps
        if doc.kind == "image":
            with Image.open(destination) as image:
                if image.width * image.height > 25_000_000:
                    raise ValueError("Image exceeds the pixel limit.")
                doc.text, score = _ocr(ImageOps.exif_transpose(image))
                scores.append(score)
        else:
            import fitz
            import io
            pieces = []
            with fitz.open(destination) as pdf:
                if pdf.needs_pass:
                    raise ValueError("Password-protected PDF is unsupported.")
                if len(pdf) > MAX_PAGES:
                    raise ValueError(f"PDF exceeds the {MAX_PAGES} page limit.")
                for number, page in enumerate(pdf, 1):
                    text = page.get_text().strip()
                    if len(text) < 20:
                        try:
                            # Limit raster allocation before rendering.
                            if page.rect.width * page.rect.height * (150/72)**2 > 25_000_000:
                                raise ValueError("Page exceeds the pixel limit.")
                            pix = page.get_pixmap(dpi=150)
                            image = Image.open(io.BytesIO(pix.tobytes("png")))
                            text, score = _ocr(image)
                            scores.append(score)
                        except Exception as exc:
                            doc.warnings.append(f"Page {number} OCR failed: {exc}")
                    pieces.append(text)
            doc.text = "\n\n".join(pieces)
    except Exception as exc:
        doc.warnings.append("Could not read source: " + str(exc)[:300])
    if scores:
        doc.ocr_confidence = sum(scores) / len(scores)
        if min(scores) < 60:
            doc.warnings.append("OCR confidence below 60. Correct source text before analysis.")
    if len(doc.text.strip()) < 20:
        doc.warnings.append("Little or no readable text. Paste or correct the announcement.")
    return doc
