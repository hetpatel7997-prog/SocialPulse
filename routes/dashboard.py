"""Landing page, dashboard shell, profile and settings."""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db
from models import UploadedFile
from services import analytics_engine as ae, repository as repo
from routes.auth import validate_password

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
def landing():
    return render_template("index.html")


@dashboard_bp.route("/dashboard")
@login_required
def index():
    frames = repo.load_frames(current_user.id)       # always scoped to the signed-in user
    ctx = ae.analyze(frames)
    recent = (UploadedFile.query.filter_by(user_id=current_user.id)
              .order_by(UploadedFile.created_at.desc()).limit(5).all())
    q = {k: sum(m[k] for m in ctx["meta"]) for k in ("records", "duplicates", "missing", "invalid")}
    has_data = ctx["caps"]["followers"] or ctx["caps"]["following"] or ctx["caps"]["posts"]
    return render_template("dashboard.html", ctx=ctx, recent=recent, quality=q, has_data=has_data,
                           has_demo=frames["has_demo"])


@dashboard_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        current_user.full_name = request.form.get("full_name", "").strip()[:100] or None
        handle = request.form.get("instagram_handle", "").strip().lstrip("@")[:60]
        current_user.instagram_handle = handle or None
        db.session.commit()
        flash("Profile saved.", "success")
        return redirect(url_for("dashboard.profile"))
    return render_template("profile.html")


@dashboard_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        error = None
        if not current_user.check_password(current):
            error = "Your current password is incorrect."
        elif validate_password(new):
            error = validate_password(new)
        elif new != confirm:
            error = "New passwords do not match."
        if error:
            flash(error, "danger")
            return render_template("settings.html"), 400
        current_user.set_password(new)
        db.session.commit()
        flash("Password changed.", "success")
        return redirect(url_for("dashboard.settings"))
    return render_template("settings.html")


@dashboard_bp.route("/settings/delete-data", methods=["POST"])
@login_required
def delete_data():
    if not current_user.check_password(request.form.get("password", "")):
        flash("Password incorrect. Your data was not deleted.", "danger")
        return redirect(url_for("dashboard.settings"))
    repo.delete_all_user_data(current_user.id)
    flash("All your uploaded files, datasets, analyses and reports were deleted.", "success")
    return redirect(url_for("dashboard.settings"))
