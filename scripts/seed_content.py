"""Add demo competencies, scenarios, training activities, assignments and 3 sample responses.

Run AFTER seed_demo:   python -m scripts.seed_content
Safe to run again: anything that already exists is skipped.
Everything here is fictional demonstration data (scenarios are flagged is_demo = 1).
"""
from datetime import date, timedelta

from app import create_app
from app.ai import service as ai_service
from app.database import employee_repo as er
from app.database import repositories as repo
from app.database.connection import execute, query_all, query_one
from scripts.seed_demo import COMPANY, DOMAIN

COMPETENCIES = {
    "Communication": "Keeping the right people informed, clearly and on time.",
    "Problem Solving": "Working through a problem in a structured way and checking the result.",
    "Collaboration": "Involving others and drawing on their knowledge and views.",
    "Accountability": "Taking ownership of outcomes, including mistakes, and acting to put things right.",
    "Adaptability": "Adjusting plans sensibly when circumstances change.",
}

# title, text, instructions, {competency: rubric}, team filter (None = everyone), deadline days, allow_reassessment
SCENARIOS = [
    ("The delayed client delivery",
     "You lead a small team delivering a feature for an important client. Two days before the agreed date, "
     "you find that a key dependency will take a week longer than planned. The client does not know yet.",
     "In a few sentences, describe what you would do in the next 24 hours and why.",
     {"Communication": "Looks for: telling the affected people early, saying what is known and unknown, and giving a way forward such as a revised date or next update time.",
      "Accountability": "Looks for: owning the situation instead of blaming others, and a concrete step to reduce the chance of it recurring.",
      "Problem Solving": "Looks for: considering options to recover time or reduce impact, and a way to check the plan is working."},
     None, 7, 0),
    ("Conflicting priorities from two managers",
     "Two managers each ask you for an urgent piece of work due on the same afternoon. You cannot finish both, "
     "and neither knows about the other request.",
     "Describe how you would handle this, including who you would talk to.",
     {"Collaboration": "Looks for: involving the people affected and inviting their views rather than deciding alone.",
      "Communication": "Looks for: making both requests visible to the right people and being clear about what can be delivered and when.",
      "Adaptability": "Looks for: a workable plan that can be adjusted if priorities shift again."},
     None, 14, 0),
    ("A new tool replaces the team's workflow",
     "Your company is replacing the tool your team has used for years. Some colleagues are frustrated, "
     "and the first week of use is slower than before.",
     "Describe how you would approach the first few weeks, for yourself and for your team.",
     {"Adaptability": "Looks for: willingness to learn the new way of working and a way to review how it is going.",
      "Collaboration": "Looks for: sharing what is learned with colleagues and listening to their concerns."},
     ("Engineering", "Design"), 10, 0),
    ("A mistake found after release",
     "A week after a release, you discover that a mistake you made is causing wrong figures in a customer report. "
     "Nobody else has noticed yet.",
     "Describe what you would do and in what order.",
     {"Accountability": "Looks for: raising the issue promptly and taking ownership, with a step to prevent a repeat.",
      "Problem Solving": "Looks for: working out the impact, planning a fix and checking that it worked."},
     ("Customer Success", "Operations"), 5, 1),
]

ACTIVITIES = [
    ("Communication", "Writing a delay update", "Practise a three-part update: what happened, the revised timeline, and when you will update again.", "Write a clear delay message with a revised date and a follow-up time.", "exercise", 15),
    ("Communication", "Keeping people informed under pressure", "A short reading on updating stakeholders when plans change.", "Choose an update rhythm that fits the situation.", "reading", 10),
    ("Problem Solving", "Checking that a fix worked", "Practise writing a simple way to confirm a fix before calling it done.", "Define one measurable check for any proposed fix.", "exercise", 20),
    ("Problem Solving", "Comparing options quickly", "A worksheet for listing options and their trade-offs.", "Compare two or three options against clear criteria.", "worksheet", 15),
    ("Collaboration", "Asking for input early", "Practise inviting views from the people your decision affects.", "Ask for input before settling on a plan.", "exercise", 15),
    ("Collaboration", "Making priorities visible", "A short guide to sharing competing requests openly.", "Show competing priorities to the right people.", "reading", 10),
    ("Accountability", "Own it, then prevent it", "Practise pairing ownership of a mistake with one preventive step.", "Name a concrete step that makes a repeat less likely.", "exercise", 15),
    ("Accountability", "A simple blameless review", "A template for reviewing what happened without blame.", "Run a short review and capture one lesson.", "worksheet", 20),
    ("Adaptability", "Setting a checkpoint", "Practise adding a review date to any new plan.", "Schedule a point to re-check a plan.", "exercise", 10),
    ("Adaptability", "Learning a new tool together", "A short guide to sharing tips while a team changes tools.", "Share what you learn and gather concerns.", "reading", 10),
]

SAMPLE_RESPONSES = {  # employee email handle -> response to scenario 1
    "ananya.rao": "I would tell the client today that the dependency is delayed and explain what we know so far. "
                  "I would take responsibility for the plan and list two options to recover time, such as reducing scope or adding a helper.",
    "rohan.kulkarni": "First I would email the client to let them know about the delay and promise a revised delivery date by Friday. "
                      "I will own the slip and ask the team to review what we can prevent next time. I would also test the options before we commit.",
    "divya.shenoy": "I would sit down with the team and look at the plan together. We would list what is blocked and what could move forward.",
}


def main():
    app = create_app()
    with app.app_context():
        company = query_one("SELECT id FROM companies WHERE name = %s", (COMPANY,))
        hr = repo.get_user_by_email(f"meera.nair@{DOMAIN}")
        if not company or not hr:
            print("Please run  python -m scripts.seed_demo  first.")
            return
        cid = company["id"]

        comp_ids = {}
        for name, desc in COMPETENCIES.items():
            row = query_one("SELECT id FROM competencies WHERE company_id = %s AND name = %s", (cid, name))
            comp_ids[name] = row["id"] if row else execute(
                "INSERT INTO competencies (company_id, name, description) VALUES (%s, %s, %s)", (cid, name, desc))

        for comp, title, desc, objective, rtype, minutes in ACTIVITIES:
            if not query_one("SELECT id FROM training_activities WHERE company_id = %s AND title = %s", (cid, title)):
                execute("INSERT INTO training_activities (company_id, competency_id, title, description, "
                        "learning_objective, resource_type, is_demo_resource, duration_minutes) "
                        "VALUES (%s, %s, %s, %s, %s, %s, 1, %s)",
                        (cid, comp_ids[comp], title, desc, objective, rtype, minutes))

        people = query_all(
            "SELECT u.id, u.email, t.name AS team FROM users u "
            "LEFT JOIN team_memberships tm ON tm.user_id = u.id LEFT JOIN teams t ON t.id = tm.team_id "
            "WHERE u.company_id = %s AND u.role = 'employee' AND u.status = 'active'", (cid,))

        scenario_ids = []
        for title, text, instr, rubrics, teams, days, reassess in SCENARIOS:
            row = query_one("SELECT id FROM scenarios WHERE company_id = %s AND title = %s", (cid, title))
            if row:
                scenario_ids.append(row["id"])
                continue
            sid = execute("INSERT INTO scenarios (company_id, title, scenario_text, instructions, status, "
                          "created_by, is_demo, published_at) VALUES (%s, %s, %s, %s, 'published', %s, 1, NOW())",
                          (cid, title, text, instr, hr["id"]))
            for comp, rubric in rubrics.items():
                execute("INSERT INTO scenario_competencies (scenario_id, competency_id, rubric) VALUES (%s, %s, %s)",
                        (sid, comp_ids[comp], rubric))
            aid = execute("INSERT INTO assignments (scenario_id, assigned_by, deadline, allow_reassessment) "
                          "VALUES (%s, %s, %s, %s)", (sid, hr["id"], date.today() + timedelta(days=days), reassess))
            for p in people:
                if teams is None or p["team"] in teams:
                    execute("INSERT IGNORE INTO assignment_recipients (assignment_id, user_id) VALUES (%s, %s)",
                            (aid, p["id"]))
            scenario_ids.append(sid)

        # Three sample responses, analysed through the same pipeline employees use (mock mode unless a key is set).
        done = 0
        for handle, text in SAMPLE_RESPONSES.items():
            user = repo.get_user_by_email(f"{handle}@{DOMAIN}")
            rec = query_one(
                "SELECT ar.id FROM assignment_recipients ar JOIN assignments a ON a.id = ar.assignment_id "
                "WHERE ar.user_id = %s AND a.scenario_id = %s AND ar.status = 'assigned'",
                (user["id"], scenario_ids[0]))
            if rec:
                cfg = app.config
                created = er.create_response_with_assessment(
                    rec["id"], user["id"], text, cfg["AI_MODE"],
                    cfg["AI_MODEL"] if cfg["AI_MODE"] == "live" else "lumora-mock-v1")
                if created:
                    ai_service.analyse(created[1])
                    done += 1
        print(f"Competencies: {len(COMPETENCIES)}  Scenarios: {len(SCENARIOS)}  Activities: {len(ACTIVITIES)}")
        print(f"Sample responses analysed this run: {done}")
        print("Employees to try: ananya.rao (has insights), karthik.bhat (fresh)  @" + DOMAIN)


if __name__ == "__main__":
    main()
