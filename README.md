
# LUMORA
Illuminate Potential. Inspire Growth.

AI-powered employee development platform (college hackathon project).

Built in phases. **Phase 1:** folders, config, database schema, app starts.
**Phase 2:** demo accounts, login, logout, forgot/reset password.

## Setup (Windows PowerShell, inside the LUMORA folder)

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Then open `.env` and fill in `FLASK_SECRET_KEY`, `DB_USER`, and `DB_PASSWORD`.

Never share `.env` with anyone or commit it to Git.

## AI configuration

Set `AI_MODE` in your `.env` file:

- **`AI_MODE=mock`** — uses the local demo AI. No API credentials are required.
- **`AI_MODE=live`** — uses the configured live AI provider. Set both `AI_API_KEY` and `AI_MODEL` to valid values.

The application refuses to start in live mode if either credential is missing. Keep your API key private and never commit it to Git.

## Check MySQL, create tables, run

```powershell
python -m scripts.check_db
python -m scripts.init_db
python run.py
```

Open http://127.0.0.1:5000 in the browser.

## Tests

```powershell
pytest
```

## Phase 2: demo accounts

```powershell
python -m scripts.seed_demo
python run.py
```

Open http://127.0.0.1:5000 and sign in.

| Role | Email |
|---|---|
| Employee | ananya.rao@brightwave-demo.example (also rohan.kulkarni, divya.shenoy, ... EMP001-EMP010) |
| HR | meera.nair@brightwave-demo.example, arjun.shetty@brightwave-demo.example |

Password for every demo account: `Lumora@Demo2026` (or your `DEMO_PASSWORD` from `.env`).

These are fictional accounts for demonstration only.

## Forgot password

- The page gives the same answer whether or not the email exists.
- Tokens are single-use, expire after 30 minutes, and only a hash is stored.
- If email is set up (`MAIL_*` in `.env`), the link is emailed.
- **Development only:** if email is NOT set up and `FLASK_DEBUG=true`, the link is shown on the page. A real deployment must never do this.
- Google sign-in accounts recover through Google, not LUMORA.

## Test database

`pytest` uses a separate database called `lumora_test_db`. Ensure the test database is configured as required by the test setup; tests should not use your production database.
