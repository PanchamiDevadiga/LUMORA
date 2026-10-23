"""Report calculations used by dashboards. Pure Python on top of employee_repo."""
from app.database import employee_repo as er


def build_comparisons(user_id):
    """Compare repeat attempts of the SAME scenario only (same rubric, so the comparison is fair).

    We never say someone "improved". We only report what each analysis noted, as observations.
    """
    scenarios = {}
    for row in er.comparison_rows(user_id):
        sc = scenarios.setdefault(row["scenario_id"], {"title": row["title"], "attempts": {}})
        att = sc["attempts"].setdefault(row["assessment_id"], {"date": row["submitted_at"], "findings": {}})
        att["findings"][row["competency"]] = row

    result = []
    for sc in scenarios.values():
        attempts = list(sc["attempts"].values())
        if len(attempts) < 2:
            continue
        first, last = attempts[0], attempts[-1]
        rows = []
        for name in sorted(set(first["findings"]) & set(last["findings"])):
            a, b = first["findings"][name], last["findings"][name]
            if a["status"] != "completed" or b["status"] != "completed":
                note = "Not enough evidence in one of the attempts to compare."
            elif a["has_dev"] and not b["has_dev"]:
                note = "A development area noted in the first attempt was not noted in the latest one."
            elif a["has_dev"] and b["has_dev"]:
                note = "The same development area was noted in both attempts."
            elif not a["has_dev"] and b["has_dev"]:
                note = "A development area was noted in the latest attempt that was not noted before."
            else:
                note = "No development area was noted in either attempt."
            rows.append({"competency": name, "note": note})
        result.append({"title": sc["title"], "attempts": len(attempts),
                       "first": first["date"], "last": last["date"], "rows": rows})
    return result
