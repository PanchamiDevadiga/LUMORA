"""Employee portal routes. The real pages are built in Phase 4."""
from flask import Blueprint, render_template

from app.auth.decorators import login_required, role_required

bp = Blueprint("employee", __name__, url_prefix="/employee")


@bp.route("/")
@login_required
@role_required("employee")
def index():
    return render_template("employee/index.html")
