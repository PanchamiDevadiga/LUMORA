"""Deterministic demonstration analysis. NO AI model is used here.

It looks for sentences in the response that contain simple cue words for each
competency, and quotes the first one it finds. Same input -> same output, so the
hackathon demo never depends on the internet or an API key.
"""
import re

MOCK_MODEL = "lumora-mock-v1"
MOCK_LIMITATIONS = (
    "Demonstration analysis made by LUMORA's built-in rule-based mock, not by an AI model. "
    "It looks for evidence of each competency in a single response. It cannot judge overall ability, "
    "and missing evidence does not mean missing skill."
)

# cues: words showing the behaviour. gaps: (what is not shown, words that would show it).
RULES = {
    "Communication": {
        "cues": ["inform", "notify", "update", "tell", "explain", "let them know", "communicate",
                 "email", "call", "share", "message", "speak", "reach out", "let the", "know about", "keep them"],
        "strength": "an intention to keep the people affected informed",
        "gaps": [("A revised timeline or follow-up time is not specified.",
                  ["by ", "tomorrow", "friday", "monday", "next week", "timeline", "follow up",
                   "follow-up", "hours", "days", "date"])],
        "advice": "Practise sharing a delay with a clear update, a revised timeline and a follow-up commitment.",
    },
    "Problem Solving": {
        "cues": ["option", "alternative", "solution", "analy", "root cause", "investigate", "prioriti",
                 "plan", "fix", "workaround", "break down", "steps"],
        "strength": "a structured attempt to work through the problem",
        "gaps": [("The response does not describe how the chosen approach would be checked.",
                  ["verify", "test", "confirm", "validate", "measure", "check"])],
        "advice": "Practise stating how you would confirm that a fix has actually worked.",
    },
    "Collaboration": {
        "cues": ["team", "together", "colleague", "ask", "help", "support", "discuss", "involve",
                 "agree", "pair", "feedback", "manager"],
        "strength": "an effort to involve other people",
        "gaps": [("The response does not say how other people's views would be gathered.",
                  ["ask", "feedback", "input", "views", "opinion", "listen", "discuss"])],
        "advice": "Practise inviting input from the people affected before settling on a plan.",
    },
    "Accountability": {
        "cues": ["i will", "i'll", "take responsibility", "own", "my mistake", "ensure", "commit",
                 "responsible", "follow through", "report", "apolog"],
        "strength": "a willingness to take ownership",
        "gaps": [("The response does not say how a repeat of the issue would be prevented.",
                  ["prevent", "review", "lesson", "avoid", "next time", "retrospective", "process"])],
        "advice": "Practise pairing ownership with one concrete step that stops the issue happening again.",
    },
    "Adaptability": {
        "cues": ["adjust", "adapt", "change", "flexib", "re-plan", "replan", "new approach", "learn",
                 "pivot", "reprioriti", "switch", "try"],
        "strength": "a readiness to adjust to the new situation",
        "gaps": [("The response does not explain how the plan would be reviewed if things change again.",
                  ["again", "monitor", "re-check", "review", "contingen", "depending"])],
        "advice": "Practise setting a checkpoint where a new plan is reviewed and adjusted.",
    },
}

_STOP = {"should", "would", "could", "about", "their", "which", "where", "there", "other", "these",
         "those", "being", "response", "scenario", "demonstrates", "describes", "rubric"}


def _sentences(text):
    parts = re.split(r"(?<=[.!?])\s+|\n+", text.strip())
    return [p.strip() for p in parts if len(p.strip()) >= 12]


def _generic_cues(rubric):
    words = []
    for w in re.findall(r"[A-Za-z]{6,}", rubric or ""):
        w = w.lower()
        if w not in _STOP and w not in words:
            words.append(w)
    return words[:12]


def analyse(response_text, competencies):
    """competencies: list of dicts with name, description, rubric. Returns {"findings": [...]}."""
    sentences = _sentences(response_text)
    lowered_all = response_text.lower()
    findings = []

    for comp in competencies:
        name = comp["name"]
        rule = RULES.get(name)
        cues = rule["cues"] if rule else _generic_cues(comp.get("rubric", ""))
        hits = [s for s in sentences if any(c in s.lower() for c in cues)]

        if not hits:
            findings.append({
                "competency": name,
                "finding": f"There is not enough in this response to say how it addresses {name}.",
                "evidence": None, "development_area": None, "recommendation": None,
                "confidence": "low", "status": "insufficient_evidence",
            })
            continue

        strength = rule["strength"] if rule else "content that relates to this competency's rubric"
        gap = advice = None
        if rule:
            for label, words in rule["gaps"]:
                if not any(w in lowered_all for w in words):
                    gap, advice = label, rule["advice"]
                    break
        findings.append({
            "competency": name,
            "finding": f"The response shows {strength}.",
            "evidence": hits[0][:300],  # a real sentence from the response
            "development_area": gap,
            "recommendation": advice,
            "confidence": "moderate" if len(hits) >= 2 else "low",
            "status": "completed",
        })
    return {"findings": findings}
