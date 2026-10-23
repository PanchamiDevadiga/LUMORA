"""HR portal routes. The full pages are built in Phase 5."""
from flask import Blueprint, render_template

from app.auth.decorators import login_required, role_required

bp = Blueprint("hr", __name__, url_prefix="/hr")


@bp.route("/")
@login_required
@role_required("hr")
def overview():
    return render_template("hr/overview.html")
