# LUMORA
Illuminate Potential. Inspire Growth.

AI-powered employee development platform (college hackathon project).
Built in phases. **Phase 1:** folders, config, database schema, app starts.
**Phase 2:** demo accounts, login, logout, forgot/reset password.

## Setup (Windows PowerShell, inside the LUMORA folder)
```
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```
Then open `.env` and fill FLASK_SECRET_KEY, DB_USER, DB_PASSWORD.
Never share `.env` with anyone.

## Check MySQL, create tables, run
```
python -m scripts.check_db
python -m scripts.init_db
python run.py
```
Open http://127.0.0.1:5000 in the browser.

## Tests
```
pytest
```

## Phase 2: demo accounts
```
python -m scripts.seed_demo
python run.py
```
Open http://127.0.0.1:5000 and sign in.

| Role | Email | 
|------|-------|
| Employee | ananya.rao@brightwave-demo.example (also rohan.kulkarni, divya.shenoy, ... EMP001-EMP010) |
| HR | meera.nair@brightwave-demo.example, arjun.shetty@brightwave-demo.example |

Password for every demo account: `Lumora@Demo2026` (or your DEMO_PASSWORD from `.env`).
These are fictional accounts for demonstration only.

## Forgot password
- The page gives the same answer whether or not the email exists.
- Tokens are single-use, expire after 30 minutes, and only a hash is stored.
- If email is set up (MAIL_* in `.env`), the link is emailed.
- **Development only:** if email is NOT set up and `FLASK_DEBUG=true`, the link is shown on the page. A real deployment must never do this.
- Google sign-in accounts recover through Google, not LUMORA.

## Tests
`pytest` uses a separate database called `lumora_test_db` (created and removed automatically). It never touches `lumora_db`.
