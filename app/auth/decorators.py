"""Backend permission checks. Hiding a button is never enough."""
from functools import wraps

from flask import abort, flash, g, redirect, url_for


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("user") is None:
            flash("Please sign in to continue.", "info")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapped


def role_required(role):
    """Use under @login_required. The role comes from the database, never from the browser."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.user["role"] != role:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator
