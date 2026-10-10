"""Rule-based safety layer: re-checks every LLM finding against numeric reference ranges."""
import re

# Fallback ranges (adult) used only when the report has no readable range.
FALLBACK = [
    (("hemoglobin", "haemoglobin"), (12.0, 17.0)),
    (("wbc", "white blood"), (4000, 11000)),
    (("platelet",), (150000, 410000)),
    (("fasting blood sugar", "fasting glucose", "blood sugar"), (70, 100)),
    (("hba1c",), (4.0, 5.6)),
    (("total cholesterol",), (None, 200)),
    (("ldl",), (None, 100)),
    (("hdl",), (40, None)),
    (("creatinine",), (0.7, 1.3)),
    (("vitamin d",), (30, 100)),
]


def to_num(s):
    m = re.search(r"-?\d[\d,]*\.?\d*", str(s))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def parse_range(s):
    """'13.0 - 17.0' -> (13.0, 17.0); '< 200' -> (None, 200); '> 40' -> (40, None)."""
    s = str(s or "").replace(",", "")
    m = re.search(r"(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)", s)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r"[<≤]\s*(\d+\.?\d*)", s)
    if m:
        return None, float(m.group(1))
    m = re.search(r"[>≥]\s*(\d+\.?\d*)", s)
    if m:
        return float(m.group(1)), None
    return None


def fallback_range(name):
    n = str(name).lower()
    for keys, rng in FALLBACK:
        if any(k in n for k in keys):
            return rng
    return None


def status(v, lo, hi):
    if lo is not None and v < lo:
        return "low"
    if hi is not None and v > hi:
        return "high"
    return "normal"


def verify(findings):
    """Return (checked_findings, stats). Rule result overrides the LLM when they disagree."""
    out, stats = [], {"verified": 0, "corrected": 0, "unchecked": 0, "ocr_suspect": 0}
    for f in findings:
        f = dict(f)
        f["check"], f["corrected"] = "", False
        v = to_num(f.get("value"))
        rng, src = parse_range(f.get("normal_range")), "report range"
        if rng is None:
            rng, src = fallback_range(f.get("name")), "reference table"
        if v is None or rng is None:
            stats["unchecked"] += 1
            f["check"] = "Not auto-verified"
            out.append(f)
            continue
        lo, hi = rng
        rs = status(v, lo, hi)
        if rs != f.get("status"):
            f["check"] = f"⚠️ Rule check ({src}) = {rs}; AI said {f.get('status')}. Rule result used."
            f["status"], f["corrected"] = rs, True
            stats["corrected"] += 1
        else:
            f["check"] = f"✔ Verified by rule check ({src})"
            stats["verified"] += 1
        # Possible OCR decimal loss, e.g. "41" read instead of "4.1"
        decimals = any(b is not None and b != int(b) for b in (lo, hi))
        if rs != "normal" and decimals and v == int(v) and status(v / 10, lo, hi) == "normal":
            f["check"] += f" | Possible OCR error: maybe {v / 10:g}. Check the original."
            stats["ocr_suspect"] += 1
        out.append(f)
    return out, stats
