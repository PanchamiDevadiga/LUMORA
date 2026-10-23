"""UI glue for LUMORA (Phase 3).

* Defines the sidebar navigation for the employee and HR workspaces.
* Resolves each link to its real endpoint when that page exists, and to a
  friendly "coming in a later phase" page when it does not yet. As later phases
  add pages named below, the links switch over automatically.
* Provides template helpers (`nav_for`, `safe_url`, `auth_mode`).
* Registers demo-mode-only preview routes so the design can be reviewed.
"""
from flask import Blueprint, abort, current_app, render_template, request, url_for
from werkzeug.routing import BuildError

ui_bp = Blueprint("ui", __name__)

# (slug, label, icon, endpoint). The endpoint is what later phases must create.
EMPLOYEE_NAV = [
    {"title": None, "links": [
        ("overview", "Overview", "dashboard", "employee.overview"),
        ("assessments", "My Assessments", "clipboard", "employee.assessments"),
        ("insights", "My Insights", "lightbulb", "employee.insights"),
        ("learning", "Learning Path", "learn", "employee.learning"),
        ("progress", "My Progress", "trend", "employee.progress"),
        ("reviews", "Review Requests", "message", "employee.reviews"),
        ("profile", "My Profile", "user", "employee.profile"),
    ]},
]

HR_NAV = [
    {"title": "People", "links": [
        ("overview", "Overview", "dashboard", "hr.overview"),
        ("directory", "Employee Directory", "users", "hr.directory"),
    ]},
    {"title": "Assessments", "links": [
        ("scenarios", "Scenario Management", "clipboard", "hr.scenarios"),
        ("assignments", "Assessment Assignments", "send", "hr.assignments"),
        ("reports", "Development Reports", "file", "hr.reports"),
    ]},
    {"title": "Insight", "links": [
        ("talent", "Talent & Skills Explorer", "search", "hr.talent"),
        ("matching", "Project Matching", "link", "hr.matching"),
        ("insights", "Organisational Insights", "chart", "hr.insights"),
    ]},
    {"title": "Governance", "links": [
        ("governance", "Review & Governance", "shield", "hr.governance"),
        ("settings", "Settings", "sliders", "hr.settings"),
    ]},
]

_NAVS = {"employee": EMPLOYEE_NAV, "hr": HR_NAV}


def safe_url(endpoint, fallback="#", **values):
    """url_for that returns `fallback` instead of raising when the endpoint is not built yet."""
    try:
        return url_for(endpoint, **values)
    except BuildError:
        return fallback


def _is_active(href, slug):
    path = request.path
    if slug == "overview":  # Overview must match exactly or it would highlight on every page.
        return path == href
    return path == href or path.startswith(href.rstrip("/") + "/")


def nav_for(area):
    """Return nav groups for `area` with resolved hrefs and the active link flagged."""
    groups = []
    for group in _NAVS.get(area, EMPLOYEE_NAV):
        links = []
        for slug, label, icon, endpoint in group["links"]:
            href = safe_url(endpoint, fallback=None)
            if href is None:
                href = url_for("ui.coming_soon", area=area, slug=slug)
            links.append({"label": label, "icon": icon, "href": href, "active": _is_active(href, slug)})
        groups.append({"title": group["title"], "links": links})
    return groups


def _label_for(area, slug):
    for group in _NAVS[area]:
        for s, label, _icon, _endpoint in group["links"]:
            if s == slug:
                return label
    return None


# Fictional preview identities, only ever used by the demo-mode preview routes below.
PREVIEW_USERS = {
    "employee": {"full_name": "Maya Fernandes", "team": "Customer Success"},
    "hr": {"full_name": "Rohan Kulkarni", "team": "People Operations"},
}


@ui_bp.before_request
def _demo_only():
    # Preview pages exist only to review the design. They never appear outside demo mode.
    if current_app.config.get("AUTH_MODE", "demo") != "demo":
        abort(404)


@ui_bp.route("/dev/ui/<area>")
def styleguide(area):
    if area not in _NAVS:
        abort(404)
    return render_template("dev/styleguide.html", area=area, preview_user=PREVIEW_USERS[area])


@ui_bp.route("/soon/<area>/<slug>")
def coming_soon(area, slug):
    if area not in _NAVS or _label_for(area, slug) is None:
        abort(404)
    return render_template("dev/coming_soon.html", area=area, slug=slug, label=_label_for(area, slug))


def init_ui(app):
    """Call once from create_app() after the other blueprints are registered."""
    app.register_blueprint(ui_bp)

    @app.context_processor
    def _inject_ui():
        return {
            "nav_for": nav_for,
            "safe_url": safe_url,
            "auth_mode": app.config.get("AUTH_MODE", "demo"),
            # Becomes True in Phase 7 once the real Google OIDC routes exist and are configured.
            "google_enabled": app.config.get("AUTH_MODE") == "google" and bool(app.config.get("GOOGLE_CLIENT_ID")),
        }
