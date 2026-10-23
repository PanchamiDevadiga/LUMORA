"""Add the fictional demo company, teams, 2 HR users and 10 employees.

Run from the LUMORA folder:  python -m scripts.seed_demo
Safe to run again: existing accounts are skipped (their passwords are not changed).
"""
from app import create_app
from app.auth import services
from app.config import Config
from app.database import repositories as repo

COMPANY = "Brightwave Technologies (Demo)"
DOMAIN = "brightwave-demo.example"   # .example can never be a real address

HR_USERS = [
    ("HR001", "Meera Nair", "meera.nair", "People Operations"),
    ("HR002", "Arjun Shetty", "arjun.shetty", "People Operations"),
]
EMPLOYEES = [
    ("EMP001", "Ananya Rao", "ananya.rao", "Engineering"),
    ("EMP002", "Rohan Kulkarni", "rohan.kulkarni", "Engineering"),
    ("EMP003", "Divya Shenoy", "divya.shenoy", "Engineering"),
    ("EMP004", "Karthik Bhat", "karthik.bhat", "Design"),
    ("EMP005", "Sneha Pai", "sneha.pai", "Design"),
    ("EMP006", "Vikram Hegde", "vikram.hegde", "Customer Success"),
    ("EMP007", "Nisha Dsouza", "nisha.dsouza", "Customer Success"),
    ("EMP008", "Aditya Naik", "aditya.naik", "Operations"),
    ("EMP009", "Pooja Kamath", "pooja.kamath", "Operations"),
    ("EMP010", "Imran Sheikh", "imran.sheikh", "Operations"),
]


def main():
    app = create_app()
    with app.app_context():
        company_id = repo.ensure_company(COMPANY)
        password_hash = services.hash_password(Config.DEMO_PASSWORD)
        added = skipped = 0
        rows = [(r, *u) for r, group in (("hr", HR_USERS), ("employee", EMPLOYEES)) for u in group]
        for role, emp_id, name, handle, team in rows:
            email = f"{handle}@{DOMAIN}"
            if repo.get_user_by_email(email):
                skipped += 1
                continue
            user_id = repo.create_user(company_id, emp_id, name, email, role, password_hash)
            repo.add_team_member(user_id, repo.ensure_team(company_id, team))
            if role == "hr":
                repo.add_role_history(user_id, None, "hr", None, "Demo seed")
            added += 1
        print(f"Demo accounts added: {added}, already there: {skipped}.")
        print(f"Example employee: ananya.rao@{DOMAIN}")
        print(f"Example HR:       meera.nair@{DOMAIN}")
        print("All demo accounts use the demo password (see DEMO_PASSWORD in config / README).")


if __name__ == "__main__":
    main()
