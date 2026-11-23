"""Upload page, file import, demo data and import history."""
import hashlib
import logging
import os
import uuid
from datetime import datetime
import pandas as pd
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from extensions import db
from models import UploadedFile, Dataset
from services import data_cleaner as dc, repository as repo
from services.instagram_parser import parse_file, ParseError
from services.demo_data import build_demo

uploads_bp = Blueprint("uploads", __name__)
log = logging.getLogger(__name__)


@uploads_bp.route("/upload")
@login_required
def upload_page():
    has_demo = UploadedFile.query.filter_by(user_id=current_user.id, is_demo=True).count() > 0
    return render_template("upload.html", has_demo=has_demo, today=datetime.now().strftime("%Y-%m-%d"),
                           max_mb=current_app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024))


def _fail(message, code=400):
    return jsonify(ok=False, error=message), code


@uploads_bp.route("/upload/file", methods=["POST"])
@login_required
def upload_file():
    f = request.files.get("file")
    if not f or not f.filename:
        return _fail("No file was selected.")
    display = os.path.basename(f.filename)[:255]
    ext = display.rsplit(".", 1)[-1].lower() if "." in display else ""
    if ext not in current_app.config["ALLOWED_EXTENSIONS"]:
        return _fail("Unsupported file type. Upload .json, .csv, .xlsx or .html files.")
    raw = f.read()
    if not raw:
        return _fail("The file is empty.")
    try:
        snapshot = datetime.strptime(request.form.get("snapshot_date") or datetime.now().strftime("%Y-%m-%d"), "%Y-%m-%d")
    except ValueError:
        return _fail("Snapshot date is not valid.")
    kind = request.form.get("kind", "auto")
    sha = hashlib.sha256(raw).hexdigest()
    same = UploadedFile.query.filter_by(user_id=current_user.id, sha256=sha, status="processed").first()
    if same:
        return _fail(f"This exact file was already imported on {same.created_at:%d %b %Y}. Duplicate uploads are skipped.", 409)

    stored = f"{uuid.uuid4().hex}.{secure_filename(ext) or 'dat'}"
    path = os.path.join(repo.user_upload_dir(current_user.id), stored)
    with open(path, "wb") as out:
        out.write(raw)
    up = UploadedFile(user_id=current_user.id, original_name=display, stored_name=stored, extension=ext,
                      size_bytes=len(raw), sha256=sha, status="uploaded")
    db.session.add(up)
    db.session.commit()

    try:
        result = parse_file(path, ext, display, kind)
    except ParseError as e:
        up.status, up.error_message = "failed", str(e)
        db.session.commit()
        return _fail(str(e), 422)
    except Exception:
        log.exception("Unexpected parse failure")
        up.status, up.error_message = "failed", "Unexpected error while reading the file."
        db.session.commit()
        return _fail("Unexpected error while reading the file.", 500)

    summary = []
    try:
        for part in result.datasets:
            df, stats = dc.prepare_raw(part.kind, part.df)
            if not len(df):
                continue
            repo.save_dataset(current_user.id, up.id, part.kind, df, part.name or display, snapshot, stats)
            summary.append({"kind": part.kind, "name": part.name or display, **stats})
        if not summary:
            raise ParseError("Every record in this file was invalid or empty.")
        up.status = "processed"
        db.session.commit()
    except ParseError as e:
        db.session.rollback()
        repo.delete_datasets([d.id for d in Dataset.query.filter_by(file_id=up.id).all()])
        up.status, up.error_message = "failed", str(e)
        db.session.commit()
        return _fail(str(e), 422)
    except Exception:
        db.session.rollback()
        log.exception("Import failed")
        up = db.session.get(UploadedFile, up.id)
        repo.delete_datasets([d.id for d in Dataset.query.filter_by(file_id=up.id).all()])
        up.status, up.error_message = "failed", "The data could not be saved."
        db.session.commit()
        return _fail("The data could not be saved. Please try again.", 500)
    totals = {k: sum(s[k] for s in summary) for k in ("records", "duplicates", "missing", "invalid")}
    return jsonify(ok=True, file=display, size=len(raw), datasets=summary, totals=totals, skipped=result.skipped)


@uploads_bp.route("/upload/demo", methods=["POST"])
@login_required
def load_demo():
    if UploadedFile.query.filter_by(user_id=current_user.id, is_demo=True).count():
        flash("Demo data is already loaded. Delete it from Import history first to reload it.", "warning")
        return redirect(url_for("dashboard.index"))
    demo = build_demo()
    up = UploadedFile(user_id=current_user.id, original_name="DEMO - sample data (not real accounts)",
                      stored_name=f"demo-{uuid.uuid4().hex}", extension="demo", size_bytes=0, status="processed", is_demo=True)
    db.session.add(up)
    db.session.flush()
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    for date, df in demo["followers_snapshots"]:
        d, s = dc.prepare_raw("followers", df)
        repo.save_dataset(current_user.id, up.id, "followers", d, "DEMO followers", pd.Timestamp(date).to_pydatetime(), s)
    d, s = dc.prepare_raw("following", demo["following"])
    repo.save_dataset(current_user.id, up.id, "following", d, "DEMO following", today, s)
    d, s = dc.prepare_raw("posts", demo["posts"])
    repo.save_dataset(current_user.id, up.id, "posts", d, "DEMO posts", today, s)
    db.session.commit()
    flash("Demo data loaded. Everything you see now is sample data, not a real account.", "success")
    return redirect(url_for("dashboard.index"))


@uploads_bp.route("/history")
@login_required
def history():
    files = (UploadedFile.query.filter_by(user_id=current_user.id).order_by(UploadedFile.created_at.desc()).all())
    rows = []
    for fl in files:
        ds = Dataset.query.filter_by(file_id=fl.id, is_cleaned=False).all()
        cleaned = {d.source_dataset_id for d in Dataset.query.filter_by(file_id=fl.id, is_cleaned=True).all()}
        rows.append({"file": fl, "datasets": [{"d": d, "cleaned": d.id in cleaned} for d in ds]})
    return render_template("history.html", rows=rows)


@uploads_bp.route("/history/<int:file_id>/delete", methods=["POST"])
@login_required
def delete_upload(file_id):
    up = UploadedFile.query.filter_by(id=file_id, user_id=current_user.id).first_or_404()
    name = up.original_name
    repo.delete_file(up)
    db.session.commit()
    flash(f"Deleted {name} and all records created from it.", "success")
    return redirect(url_for("uploads.history"))
