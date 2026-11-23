"""Generate, list, download and delete PDF / Excel reports."""
import logging
import os
import uuid
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from extensions import db
from models import Report
from services import analytics_engine as ae, repository as repo
from services.report_generator import generate_pdf, generate_excel

reports_bp = Blueprint("reports", __name__)
log = logging.getLogger(__name__)


@reports_bp.route("/reports")
@login_required
def index():
    reports = Report.query.filter_by(user_id=current_user.id).order_by(Report.created_at.desc()).all()
    return render_template("reports.html", reports=reports)


@reports_bp.route("/reports/generate", methods=["POST"])
@login_required
def generate():
    kind = request.form.get("type")
    if kind not in ("pdf", "xlsx"):
        flash("Choose PDF or Excel.", "danger")
        return redirect(url_for("reports.index"))
    frames = repo.load_frames(current_user.id)
    ctx = ae.analyze(frames)
    if not (ctx["caps"]["followers"] or ctx["caps"]["following"] or ctx["caps"]["posts"]):
        flash("There is no data to report on yet. Import a file first.", "danger")
        return redirect(url_for("reports.index"))
    name = f"{uuid.uuid4().hex}.{kind}"
    path = os.path.join(repo.user_report_dir(current_user.id), name)
    account = current_user.instagram_handle or current_user.username
    if frames["has_demo"]:
        account += " (includes DEMO data)"
    try:
        (generate_pdf if kind == "pdf" else generate_excel)(ctx, path, account)
    except Exception:
        log.exception("Report generation failed")
        flash("The report could not be generated.", "danger")
        return redirect(url_for("reports.index"))
    db.session.add(Report(user_id=current_user.id, report_type=kind, file_name=name, size_bytes=os.path.getsize(path)))
    db.session.commit()
    flash("Report ready. Use Download below.", "success")
    return redirect(url_for("reports.index"))


@reports_bp.route("/reports/<int:report_id>/download")
@login_required
def download(report_id):
    rep = Report.query.filter_by(id=report_id, user_id=current_user.id).first_or_404()
    path = os.path.join(repo.user_report_dir(current_user.id), rep.file_name)
    if not os.path.isfile(path):
        flash("That report file no longer exists.", "danger")
        return redirect(url_for("reports.index"))
    return send_file(path, as_attachment=True, download_name=f"SocialPulse_report_{rep.created_at:%Y%m%d_%H%M}.{rep.report_type}")


@reports_bp.route("/reports/<int:report_id>/delete", methods=["POST"])
@login_required
def delete(report_id):
    rep = Report.query.filter_by(id=report_id, user_id=current_user.id).first_or_404()
    path = os.path.join(repo.user_report_dir(current_user.id), rep.file_name)
    if os.path.isfile(path):
        os.remove(path)
    db.session.delete(rep)
    db.session.commit()
    flash("Report deleted.", "success")
    return redirect(url_for("reports.index"))
