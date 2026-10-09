from pathlib import Path
import fitz
from PIL import Image
import ingestion

def test_text_and_bad_input(tmp_path,monkeypatch):
    monkeypatch.setattr(ingestion,"SOURCE_DIR",tmp_path/"sources")
    assert ingestion.ingest_text("Sample announcement").text == "Sample announcement"
    assert ingestion.ingest_text(None).warnings
    assert ingestion.ingest_file(tmp_path/"missing.png").warnings
    assert ingestion.ingest_file(tmp_path/"unsafe.exe").warnings
    broken = tmp_path/"broken.pdf"
    broken.write_bytes(b"not a PDF")
    assert ingestion.ingest_file(broken).warnings

def test_text_pdf_retains_original(tmp_path,monkeypatch):
    monkeypatch.setattr(ingestion,"SOURCE_DIR",tmp_path/"sources")
    path = tmp_path/"text.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((50,50),"Physics lab report due October 16. Submit by email.")
        pdf.save(path)
    doc = ingestion.ingest_file(path)
    assert "Physics" in doc.text
    assert Path(doc.original_path).read_bytes() == path.read_bytes()
    assert doc.ocr_confidence is None

def test_images_and_scanned_pdf_route_through_ocr(tmp_path,monkeypatch):
    monkeypatch.setattr(ingestion,"SOURCE_DIR",tmp_path/"sources")
    monkeypatch.setattr(ingestion,"_ocr",lambda image: ("ML activity requires 300 dataset rows.",92.0))
    path = tmp_path/"image.png"
    Image.new("RGB",(800,200),"white").save(path)
    image_doc = ingestion.ingest_file(path)
    assert image_doc.text and image_doc.ocr_confidence == 92
    scanned = tmp_path/"scanned.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_image(page.rect,filename=str(path))
        pdf.save(scanned)
    pdf_doc = ingestion.ingest_file(scanned)
    assert pdf_doc.text and pdf_doc.ocr_confidence == 92

def test_blank_image_warns(tmp_path,monkeypatch):
    monkeypatch.setattr(ingestion,"SOURCE_DIR",tmp_path/"sources")
    monkeypatch.setattr(ingestion,"_ocr",lambda image: ("",0.0))
    path = tmp_path/"blank.png"
    Image.new("RGB",(300,100),"white").save(path)
    doc = ingestion.ingest_file(path)
    assert doc.warnings and doc.ocr_confidence == 0
