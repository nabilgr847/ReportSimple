import io
import json
import os
import re

import pdfplumber
import pytesseract
import streamlit as st
from openai import OpenAI
from pdf2image import convert_from_bytes
from PIL import Image

from rules import verify

# Featherless is OpenAI-compatible
client = OpenAI(
    base_url="https://api.featherless.ai/v1",
    api_key=os.environ["FEATHERLESS_API_KEY"],
)
# Check the exact model id on featherless.ai/models and change if needed
MODEL = os.environ.get("FEATHERLESS_MODEL", "Qwen/Qwen2.5-72B-Instruct")

SYSTEM = """You are a careful medical report explainer for patients, not a doctor.
Given report text, reply ONLY with valid JSON (no markdown) in this shape:
{
 "summary": "3-4 simple sentences",
 "findings": [
   {"name": "test/item", "value": "as written", "normal_range": "if known",
    "status": "normal|high|low|unclear", "meaning": "one simple sentence"}
 ],
 "urgency": "routine|see_doctor_soon|urgent",
 "questions_for_doctor": ["...", "..."]
}
The text comes from OCR and may have small typos (e.g. "41" for "4.1", "HbAtc" for "HbA1c"); use the reference range to fix obvious ones.
Never diagnose. Never prescribe. If unsure, use status "unclear".
Write all text fields in the requested language."""


def analyze(text: str, lang: str) -> dict:
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0.2,
        max_tokens=1200,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Language: {lang}\n\nReport:\n{text}"},
        ],
    )
    if not getattr(resp, "choices", None):
        raise RuntimeError(f"Featherless returned no result for model '{MODEL}': {resp}")
    raw = resp.choices[0].message.content
    match = re.search(r"\{.*\}", raw, re.S)  # strip any extra text around JSON
    return json.loads(match.group(0))


def extract_text(file) -> str:
    """Read text from txt / PDF (digital or scanned) / image."""
    data = file.read()
    name = file.name.lower()
    if name.endswith(".txt"):
        return data.decode("utf-8", errors="ignore")
    if name.endswith(".pdf"):
        text = ""
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                text += (page.extract_text() or "") + "\n"
        if len(text.strip()) < 30:  # scanned PDF -> OCR each page
            for img in convert_from_bytes(data, dpi=200):
                text += pytesseract.image_to_string(img) + "\n"
        return text
    img = Image.open(io.BytesIO(data))
    return pytesseract.image_to_string(img)


st.set_page_config(page_title="ReportSimple", page_icon="🩺")
st.title("🩺 ReportSimple")
st.caption("Understand your medical report in plain language.")

lang = st.selectbox("Language", ["English", "Bangla"])
upload = st.file_uploader(
    "Upload report (PDF, photo, or .txt)", type=["pdf", "png", "jpg", "jpeg", "txt"]
)
text = st.text_area("...or paste report text", height=200)
if upload:
    with st.spinner("Reading your report..."):
        text = extract_text(upload)
    with st.expander("Text read from your file (check if correct)"):
        st.text(text)

if st.button("Explain", type="primary") and text.strip():
    with st.spinner("Analyzing..."):
        try:
            data = analyze(text, lang)
        except Exception as e:
            st.error(f"Something went wrong: {e}")
            st.stop()

    badge = {"routine": "🟢 Routine", "see_doctor_soon": "🟡 See a doctor soon", "urgent": "🔴 Urgent"}
    st.subheader(badge.get(data.get("urgency"), "Result"))
    st.write(data.get("summary", ""))

    checked, stats = verify(data.get("findings", []))
    st.subheader("Findings")
    st.caption(
        f"Rule check: {stats['verified']} verified, {stats['corrected']} corrected, "
        f"{stats['unchecked']} not auto-verified"
    )
    icon = {"normal": "✅", "high": "⬆️", "low": "⬇️", "unclear": "❔"}
    for f in checked:
        line = (
            f"{icon.get(f.get('status'), '❔')} **{f.get('name')}**: {f.get('value')} "
            f"(normal: {f.get('normal_range') or 'n/a'})"
        )
        if not f["corrected"]:
            line += f". {f.get('meaning', '')}"
        st.markdown(line)
        st.caption(f["check"])

    st.subheader("Ask your doctor")
    for q in data.get("questions_for_doctor", []):
        st.markdown(f"- {q}")

st.divider()
st.warning("Educational tool only. Not a diagnosis or a substitute for a doctor.")
