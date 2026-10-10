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

from rules import urgency, verify

# Featherless is OpenAI-compatible
client = OpenAI(
    base_url="https://api.featherless.ai/v1",
    api_key=os.environ["FEATHERLESS_API_KEY"],
)
# Check the exact model id on featherless.ai/models and change if needed
MODEL = os.environ.get("FEATHERLESS_MODEL", "Qwen/Qwen2.5-72B-Instruct")

EXTRACT_PROMPT = """You extract lab values from medical report text (may contain OCR typos).
Reply ONLY with valid JSON (no markdown):
{"findings": [{"name": "test name", "value": "number as written", "unit": "unit", "normal_range": "reference range as written"}]}
Fix obvious typos in test NAMES (e.g. "HbAtc" -> "HbA1c"). Copy numbers exactly. Do not judge or explain."""

EXPLAIN_PROMPT = """You explain lab results to a patient in simple words. You are not a doctor.
You get a list of tests with a VERIFIED status (normal/high/low). Use these statuses exactly; never contradict them.
Reply ONLY with valid JSON (no markdown):
{"summary": "3-4 simple sentences mentioning every high/low test correctly",
 "meanings": {"<test name exactly as given>": "one simple sentence"},
 "questions_for_doctor": ["...", "..."]}
Rules: never diagnose, never prescribe or suggest treatment. Use wording like "may be linked to".
Questions must only be about tests that are high or low. Write all text in the requested language."""


def call_json(system: str, user: str, max_tokens: int = 1500) -> dict:
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0.1,
        max_tokens=max_tokens,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    if not getattr(resp, "choices", None):
        raise RuntimeError(f"Featherless returned no result for model '{MODEL}': {resp}")
    raw = resp.choices[0].message.content
    match = re.search(r"\{.*\}", raw, re.S)  # strip any extra text around JSON
    return json.loads(match.group(0))


def analyze(text: str, lang: str):
    """Step 1 LLM extracts -> Step 2 rules verify -> Step 3 LLM explains verified data."""
    extracted = call_json(EXTRACT_PROMPT, text, max_tokens=1500)
    checked, stats = verify(extracted.get("findings", []))
    facts = "\n".join(
        f"- {f.get('name')}: {f.get('value')} {f.get('unit', '')} "
        f"(normal {f.get('normal_range') or 'n/a'}) -> {f['status'].upper()}"
        for f in checked
    )
    explained = call_json(EXPLAIN_PROMPT, f"Language: {lang}\n\nVerified results:\n{facts}")
    return checked, stats, urgency(checked), explained


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
    with st.spinner("Analyzing (extract, verify, explain)..."):
        try:
            checked, stats, level, explained = analyze(text, lang)
        except Exception as e:
            st.error(f"Something went wrong: {e}")
            st.stop()

    badge = {"routine": "🟢 Routine", "see_doctor_soon": "🟡 See a doctor soon", "urgent": "🔴 Urgent: see a doctor promptly"}
    st.subheader(badge[level])
    st.write(explained.get("summary", ""))

    st.subheader("Findings")
    st.caption(
        f"Status set by rule engine for {stats['verified']} tests; "
        f"{stats['unchecked']} could not be auto-verified"
    )
    icon = {"normal": "✅", "high": "⬆️", "low": "⬇️", "unclear": "❔"}
    meanings = explained.get("meanings", {})
    for f in checked:
        st.markdown(
            f"{icon.get(f['status'], '❔')} **{f.get('name')}**: {f.get('value')} {f.get('unit', '')} "
            f"(normal: {f.get('normal_range') or 'n/a'}). {meanings.get(f.get('name'), '')}"
        )
        if "OCR" in f["check"] or f["status"] == "unclear":
            st.caption(f["check"])

    st.subheader("Ask your doctor")
    for q in explained.get("questions_for_doctor", []):
        st.markdown(f"- {q}")

st.divider()
st.warning("Educational tool only. Not a diagnosis or a substitute for a doctor.")
