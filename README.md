# 🩺 ReportSimple

**Understand your medical report in plain language.** Upload a lab report (PDF, photo or text) and get a simple, verified explanation plus questions to ask your doctor.

Built for **ForgeHacks Online 2026** · Track: **AI + Healthcare**

## The problem
Most people receive lab reports full of numbers, units and abbreviations with no explanation. They wait days for a doctor visit, search confusing information online, or panic over normal values. This is worse for people who are not comfortable with medical English.

**Target users:** patients and families, especially in areas with limited access to doctors, and people who prefer reading in their own language (English and Bangla supported).

## How it works
```
Report (PDF / photo / text)
        │
        ▼
  OCR (Tesseract, pdfplumber)           ← reads scanned or digital reports
        │
        ▼
  LLM Step 1: EXTRACT                   ← Featherless AI (Qwen2.5)
  test name, value, unit, range
        │
        ▼
  RULE ENGINE (rules.py)                ← deterministic safety layer
  parses ranges, sets high/low/normal,
  computes urgency, flags OCR errors
        │
        ▼
  LLM Step 2: EXPLAIN                   ← only sees VERIFIED statuses
  plain-language summary, per-test
  meaning, questions for the doctor
        │
        ▼
  Streamlit UI
```

### Why not "just a wrapper"
LLMs sometimes get numbers wrong (for example calling a high value "low"). In our tests the model mislabeled HbA1c and wrote a wrong summary. So the LLM is **never trusted to judge values**: a rule engine decides high/low/normal and urgency, and the LLM only explains results that are already verified.

### Technical components
- **Featherless AI** (OpenAI-compatible API, open-source Qwen2.5 model) for extraction and explanation
- **OCR:** Tesseract + pdf2image for photos and scanned PDFs, pdfplumber for digital PDFs
- **Rule engine:** range parsing (`13.0 - 17.0`, `< 200`, `> 40`), fallback reference table, urgency heuristic, OCR decimal-error detection
- **Streamlit** for the UI, English and Bangla output

## Real-world impact
- Helps people understand results before or after a doctor visit and ask better questions
- Reduces panic and misinformation from searching numbers online
- Language support lowers the barrier for non-native English readers
- Safe by design: never diagnoses, never suggests treatment, always shows a disclaimer

## Run locally
```bash
sudo apt install tesseract-ocr tesseract-ocr-ben poppler-utils   # OCR tools
pip install -r requirements.txt
export FEATHERLESS_API_KEY="your_key"
export FEATHERLESS_MODEL="Qwen/Qwen2.5-7B-Instruct"   # optional
streamlit run app.py
```
Try it with `sample_blood_report.pdf` or `sample_blood_report.png` (made-up data).

## Limitations
- Educational tool only. **Not a diagnosis and not a replacement for a doctor.**
- OCR can misread blurry photos; the app shows the extracted text so users can check it.
- The urgency level is a simple heuristic, not clinical triage.
- Reference ranges come from the report itself; a small fallback table covers common adult tests.

## Future work
Sex/age-specific ranges, more languages, trend tracking across reports, doctor-shareable summaries.
