# Hackathon submission draft

This draft follows the organizer slides supplied by the user. It records known facts and leaves missing submission information explicit.

## Project

**Name:** Panuto AI

**Description:** An offline student assistant that turns Filipino, Taglish, and English class announcements into reviewed tasks and highlights changes in revised instructions.

**Target user:** Students who receive scattered class announcements and need to track deadlines, required files, and changed requirements.

**Team members:** To be supplied by the team.

**GitHub repository:** https://github.com/RedGla/panuto-ai — currently private. The supplied submission checklist calls for a public repository; visibility has not been changed.

## Why run AI locally?

Class announcements can contain private academic information. Once the model and OCR language data are installed, Panuto can extract tasks, review revisions, and retain source-backed history without an internet connection or a hosted inference API. It supports students with unreliable connectivity while keeping announcements on their computer.

This is the intended advantage. A physical Wi-Fi-off end-to-end demonstration remains to be recorded.

## Disclosures

- Model: Qwen3 1.7B through Ollama, with thinking disabled and schema-constrained output.
- OCR: Tesseract with English and Filipino tessdata_fast language data.
- Application: Python, Streamlit, PyMuPDF, Pillow, pytesseract, jsonschema.
- Storage: SQLite; no hosted database.
- Runtime cloud APIs: none in the extraction, OCR, comparison, and storage flow.
- Internet required: initial package/runtime/model downloads, GitHub operations, and updates.
- AI development tools: OpenAI Codex assisted implementation and verification. The team should add any other tools it used.
- Existing code/assets: open-source libraries and models above; project-generated synthetic fixtures and screenshots. Vikunja and Tasks.org were inspected for feature inspiration; no source code or assets were copied.
- Build timing/originality: the team must provide accurate creation timing and any pre-existing work. This draft does not certify competition eligibility.

## Evidence

Recorded development measurements: 10/10 schema-valid synthetic samples, 51/54 exact matches on selected labels, and 1.57 seconds mean warm extraction on the selected Windows PC. Samples were used for tuning, with some few-shot overlap. These are development checks, not independent accuracy results.

Fresh-clone and real-model app flow have been exercised. Automated tests cover confirmation, persistence, revisions, organization, and backup recovery. See RESULTS.md and docs/production-features.md.

**Demo video:** Missing.
**Public X/LinkedIn video URL:** Missing.
**Physical Wi-Fi-off proof:** Missing.
**Timed rehearsals:** Missing.

## Presentation

Use the existing five-minute demo script in the execution plan, followed by three minutes for judge questions as shown in the supplied slides. Focus on original announcement, confirmed ambiguous deadline, revision diff, and source-backed history. New task organization and backup tools support daily use but should not crowd out the working local AI demonstration.
