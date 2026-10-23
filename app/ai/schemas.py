"""Rules every AI result must pass before it is saved.

The AI (live or mock) returns data shaped like:
  {"findings": [{"competency", "finding", "evidence", "development_area",
                 "recommendation", "confidence", "status"}, ...]}
Nothing is saved unless it passes validate_result().
"""
import re

CONFIDENCE = ("low", "moderate", "high")
STATUS = ("completed", "insufficient_evidence")
REQUIRED_KEYS = ("competency", "finding", "evidence", "development_area",
                 "recommendation", "confidence", "status")
MAX_TEXT = 1200


class AIValidationError(ValueError):
    """The AI result was not usable. The message is safe to log (it holds no response text)."""


def normalise(text):
    """Lower-case and squeeze spaces so quotes can be compared fairly."""
    return re.sub(r"\s+", " ", (text or "")).strip().casefold()


def evidence_is_real(evidence, response_text):
    """True only if the evidence is actually written in the employee's response."""
    quote = normalise(evidence).strip(" .\"'\u2018\u2019\u201c\u201d")
    return len(quote) >= 8 and quote in normalise(response_text)


def _clean(value, field, allow_none):
    if value is None or (isinstance(value, str) and not value.strip()):
        if allow_none:
            return None
        raise AIValidationError(f"'{field}' is empty")
    if not isinstance(value, str):
        raise AIValidationError(f"'{field}' must be text")
    return value.strip()[:MAX_TEXT]


def insufficient_finding(name):
    return {
        "competency": name,
        "finding": f"There is not enough in this response to say how it addresses {name}.",
        "evidence": None, "development_area": None, "recommendation": None,
        "confidence": "low", "status": "insufficient_evidence",
    }


def validate_result(data, expected_names, response_text):
    """Return a clean list of findings (one per expected competency) or raise AIValidationError."""
    if not isinstance(data, dict) or not isinstance(data.get("findings"), list):
        raise AIValidationError("result must be an object with a 'findings' list")

    expected = {n.casefold(): n for n in expected_names}
    clean, seen = [], set()
    for item in data["findings"]:
        if not isinstance(item, dict):
            raise AIValidationError("each finding must be an object")
        missing = [k for k in REQUIRED_KEYS if k not in item]
        if missing:
            raise AIValidationError(f"finding is missing: {', '.join(missing)}")

        name = expected.get(str(item["competency"]).strip().casefold())
        if name is None:
            raise AIValidationError("a finding names a competency that is not part of this scenario")
        if name in seen:
            raise AIValidationError("a competency appears twice")
        seen.add(name)

        status, confidence = item["status"], item["confidence"]
        if status not in STATUS or confidence not in CONFIDENCE:
            raise AIValidationError("status or confidence has an unexpected value")

        finding = _clean(item["finding"], "finding", allow_none=False)
        if status == "insufficient_evidence":
            clean.append({**insufficient_finding(name), "finding": finding})
            continue

        evidence = _clean(item["evidence"], "evidence", allow_none=False)
        if not evidence_is_real(evidence, response_text):
            raise AIValidationError("evidence is not found in the employee's response")
        clean.append({
            "competency": name, "finding": finding, "evidence": evidence,
            "development_area": _clean(item["development_area"], "development_area", True),
            "recommendation": _clean(item["recommendation"], "recommendation", True),
            "confidence": confidence, "status": "completed",
        })

    if not clean:
        raise AIValidationError("no findings returned")
    for name in expected_names:  # anything the AI skipped is shown honestly as "not enough evidence"
        if name not in seen:
            clean.append(insufficient_finding(name))
    return clean
