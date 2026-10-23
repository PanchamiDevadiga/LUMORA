"""Flask extensions are created here and connected to the app in create_app()."""
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect()
