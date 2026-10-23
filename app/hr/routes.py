"""HR portal routes. The real pages are built in Phase 5."""
from flask import Blueprint, render_template

from app.auth.decorators import login_required, role_required

bp = Blueprint("hr", __name__, url_prefix="/hr")


@bp.route("/")
@login_required
@role_required("hr")
def index():
    return render_template("hr/index.html")
