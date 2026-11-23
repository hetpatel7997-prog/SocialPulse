"""Followers, following, content analytics, data cleaning, insights and machine learning pages."""
import pandas as pd
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db
from models import Dataset
from services import analytics_engine as ae, data_cleaner as dc, ml_engine as ml, repository as repo

analytics_bp = Blueprint("analytics", __name__)


def _people(kind):
    frames = repo.load_frames(current_user.id)
    view = request.args.get("view", "all")
    q = request.args.get("q", "").strip()
    sort = request.args.get("sort", "username")
    direction = request.args.get("dir", "asc")
    page = request.args.get("page", 1, type=int)
    pv = ae.people_view(frames["followers"], frames["following"], kind, view, q, sort, direction, page)
    ctx = ae.analyze(frames)
    return render_template(f"{kind}.html", kind=kind, pv=pv, view=view, q=q, sort=sort, dir=direction, fstats=ctx["fstats"],
                           charts=ctx["charts"], growth=ctx["growth"], has_demo=frames["has_demo"])


@analytics_bp.route("/followers")
@login_required
def followers():
    return _people("followers")


@analytics_bp.route("/following")
@login_required
def following():
    return _people("following")


def _date_arg(name):
    v = request.args.get(name, "").strip()
    try:
        return str(pd.Timestamp(v).date()) if v else None
    except (ValueError, TypeError):
        return None


@analytics_bp.route("/content")
@login_required
def content():
    frames = repo.load_frames(current_user.id)
    filters = {"date_from": _date_arg("date_from"), "date_to": _date_arg("date_to"),
               "ctype": request.args.get("ctype") or None,
               "tier": request.args.get("tier") if request.args.get("tier") in ("high", "average", "low") else None}
    ctx = ae.analyze(frames, filters)
    return render_template("content.html", ctx=ctx, filters=filters, has_demo=frames["has_demo"])


@analytics_bp.route("/insights")
@login_required
def insights():
    frames = repo.load_frames(current_user.id)
    ctx = ae.analyze(frames)
    try:
        repo.save_result(current_user.id, "insights", ctx["insights"])
    except Exception:
        db.session.rollback()
    return render_template("insights.html", ctx=ctx, has_demo=frames["has_demo"])


@analytics_bp.route("/machine-learning")
@login_required
def machine_learning():
    frames = repo.load_frames(current_user.id)
    ctx = ae.analyze(frames)
    p = ctx["all_posts"]
    results = {"kmeans": ml.kmeans_clusters(p), "anomalies": ml.anomalies(p),
               "trends": ml.trends(p), "forecast": ml.forecast(p)}
    try:
        repo.save_result(current_user.id, "ml", results)
    except Exception:
        db.session.rollback()
    return render_template("machine_learning.html", r=results, has_posts=ctx["caps"]["posts"], has_demo=frames["has_demo"])


# ---------- data cleaning ----------
def _preview(kind, df, n=10):
    cols = [c for c in dc.columns_for(kind) if c in df.columns and df[c].notna().any()]
    head = df[cols].head(n).astype(object).where(df[cols].head(n).notna(), "-")
    return cols, [[str(v)[:70] for v in row] for row in head.values.tolist()]


@analytics_bp.route("/cleaning")
@login_required
def cleaning():
    raws = Dataset.query.filter_by(user_id=current_user.id, is_cleaned=False).order_by(Dataset.created_at.desc()).all()
    selected = request.args.get("dataset", type=int)
    ds = next((d for d in raws if d.id == selected), raws[0] if raws else None)
    data = None
    if ds:
        df = repo.dataset_df(ds)
        report = dc.quality_report(ds.kind, df)
        cleaned, changes = dc.clean(ds.kind, df)
        existing = Dataset.query.filter_by(user_id=current_user.id, source_dataset_id=ds.id, is_cleaned=True).first()
        data = {"ds": ds, "report": report, "changes": changes, "existing": existing,
                "raw_preview": _preview(ds.kind, df), "clean_preview": _preview(ds.kind, cleaned),
                "clean_rows": len(cleaned)}
    return render_template("cleaning.html", raws=raws, data=data)


@analytics_bp.route("/cleaning/<int:dataset_id>/save", methods=["POST"])
@login_required
def save_cleaned(dataset_id):
    raw = Dataset.query.filter_by(id=dataset_id, user_id=current_user.id, is_cleaned=False).first_or_404()
    df = repo.dataset_df(raw)
    cleaned, changes = dc.clean(raw.kind, df)
    if not len(cleaned):
        flash("Cleaning would remove every record, so nothing was saved.", "danger")
        return redirect(url_for("analytics.cleaning", dataset=raw.id))
    old = Dataset.query.filter_by(user_id=current_user.id, source_dataset_id=raw.id, is_cleaned=True).all()
    repo.delete_datasets([d.id for d in old])
    stats = {"duplicates": sum(c["count"] for c in changes if "duplicate" in c["step"]),
             "invalid": sum(c["count"] for c in changes if "invalid records" in c["step"]),
             "missing": sum(dc.missing_summary(raw.kind, cleaned).values())}
    repo.save_dataset(current_user.id, raw.file_id, raw.kind, cleaned, raw.name, raw.snapshot_date, stats,
                      is_cleaned=True, source_id=raw.id)
    db.session.commit()
    flash("Cleaned version saved. Dashboards now use it; the raw data is untouched.", "success")
    return redirect(url_for("analytics.cleaning", dataset=raw.id))


@analytics_bp.route("/cleaning/<int:dataset_id>/revert", methods=["POST"])
@login_required
def revert_cleaned(dataset_id):
    raw = Dataset.query.filter_by(id=dataset_id, user_id=current_user.id, is_cleaned=False).first_or_404()
    old = Dataset.query.filter_by(user_id=current_user.id, source_dataset_id=raw.id, is_cleaned=True).all()
    repo.delete_datasets([d.id for d in old])
    db.session.commit()
    flash("Cleaned version removed. Analytics now use the raw data again.", "success")
    return redirect(url_for("analytics.cleaning", dataset=raw.id))
