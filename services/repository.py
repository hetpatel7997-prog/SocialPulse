"""Database access helpers. Every query is filtered by user_id so users only see their own data."""
import os
from datetime import datetime
import pandas as pd
from flask import current_app
from extensions import db
from models import (UploadedFile, Dataset, Follower, Following, Post, EngagementMetric,
                    AnalyticsResult, Report)
from services import data_cleaner as dc
from services.analytics_engine import with_metrics

POST_DB_COLS = ["external_id", "caption", "content_type", "posted_at", "likes", "comments", "shares", "saves", "reach", "impressions"]


def user_upload_dir(user_id):
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], str(user_id))
    os.makedirs(path, exist_ok=True)
    return path


def user_report_dir(user_id):
    path = os.path.join(current_app.config["REPORT_FOLDER"], str(user_id))
    os.makedirs(path, exist_ok=True)
    return path


# ---------- saving ----------
def save_dataset(user_id, file_id, kind, df, name, snapshot, stats=None, is_cleaned=False, source_id=None):
    stats = stats or {}
    ds = Dataset(user_id=user_id, file_id=file_id, kind=kind, name=(name or kind)[:150], snapshot_date=snapshot,
                 is_cleaned=is_cleaned, source_dataset_id=source_id, record_count=len(df),
                 duplicate_count=stats.get("duplicates", 0), missing_count=stats.get("missing", 0),
                 invalid_count=stats.get("invalid", 0))
    db.session.add(ds)
    db.session.flush()
    records = dc.df_to_records(kind, df)
    now = datetime.utcnow()
    if kind in ("followers", "following"):
        model = Follower if kind == "followers" else Following
        for r in records:
            r.update(user_id=user_id, dataset_id=ds.id, created_at=now, updated_at=now)
            r["username"] = r["username"][:100]
            if r.get("profile_url"):
                r["profile_url"] = r["profile_url"][:300]
        for i in range(0, len(records), 5000):
            db.session.bulk_insert_mappings(model, records[i:i + 5000])
    else:
        pm = with_metrics(df)
        posts = []
        for r in records:
            if r.get("caption"):
                r["caption"] = r["caption"][:60000]
            if r.get("external_id"):
                r["external_id"] = r["external_id"][:120]
            posts.append(Post(user_id=user_id, dataset_id=ds.id, **r))
        db.session.add_all(posts)
        db.session.flush()
        metrics = []
        for post, m in zip(posts, pm.itertuples()):
            inter = None if pd.isna(m.interactions) else int(m.interactions)
            rate = round(inter / post.reach * 100, 2) if inter is not None and post.reach else None
            metrics.append({"user_id": user_id, "post_id": post.id, "total_interactions": inter,
                            "engagement_rate": rate, "is_outlier": bool(m.is_outlier),
                            "performance_tier": m.tier if isinstance(m.tier, str) else None,
                            "created_at": now, "updated_at": now})
        if metrics:
            db.session.bulk_insert_mappings(EngagementMetric, metrics)
    return ds


# ---------- loading ----------
def effective_datasets(user_id, kind):
    """(dataset_to_use, raw_dataset) pairs. A cleaned copy replaces its raw dataset when one exists."""
    raws = (Dataset.query.filter_by(user_id=user_id, kind=kind, is_cleaned=False)
            .order_by(Dataset.snapshot_date, Dataset.id).all())
    cleaned = {d.source_dataset_id: d for d in
               Dataset.query.filter_by(user_id=user_id, kind=kind, is_cleaned=True).order_by(Dataset.id).all()}
    return [(cleaned.get(r.id, r), r) for r in raws]


def _accounts_frame(user_id, kind):
    model = Follower if kind == "followers" else Following
    parts = []
    for ds, raw in effective_datasets(user_id, kind):
        rows = (db.session.query(model.username, model.profile_url, model.followed_at)
                .filter(model.dataset_id == ds.id, model.user_id == user_id).all())
        if rows:
            df = pd.DataFrame([tuple(r) for r in rows], columns=["username", "profile_url", "followed_at"])
            df["snapshot"] = (raw.snapshot_date or raw.created_at).strftime("%Y-%m-%d")
            parts.append(df)
    if not parts:
        return None
    df = pd.concat(parts, ignore_index=True)
    df["followed_at"] = pd.to_datetime(df["followed_at"], errors="coerce")
    df["_k"] = df["username"].str.lower()
    return df.drop_duplicates(["snapshot", "_k"]).drop(columns="_k").reset_index(drop=True)


def _posts_frame(user_id):
    parts = []
    for ds, _raw in effective_datasets(user_id, "posts"):
        cols = [getattr(Post, c) for c in POST_DB_COLS]
        rows = db.session.query(*cols).filter(Post.dataset_id == ds.id, Post.user_id == user_id).all()
        if rows:
            parts.append(pd.DataFrame([tuple(r) for r in rows], columns=POST_DB_COLS))
    if not parts:
        return None
    df = pd.concat(parts, ignore_index=True)
    df["posted_at"] = pd.to_datetime(df["posted_at"], errors="coerce")
    for c in dc.NUM_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ("external_id", "caption", "content_type"):
        df[c] = df[c].astype("string")
    return df[~dc.duplicate_mask("posts", df)].reset_index(drop=True)


def load_frames(user_id):
    meta = []
    for kind in ("followers", "following", "posts"):
        for ds, _raw in effective_datasets(user_id, kind):
            meta.append({"kind": kind, "name": ds.name, "records": ds.record_count, "duplicates": ds.duplicate_count,
                         "missing": ds.missing_count, "invalid": ds.invalid_count, "is_cleaned": ds.is_cleaned})
    return {"followers": _accounts_frame(user_id, "followers"), "following": _accounts_frame(user_id, "following"),
            "posts": _posts_frame(user_id), "meta": meta,
            "has_demo": UploadedFile.query.filter_by(user_id=user_id, is_demo=True).count() > 0}


def dataset_df(ds):
    """One dataset (raw or cleaned) as a DataFrame."""
    if ds.kind in ("followers", "following"):
        model = Follower if ds.kind == "followers" else Following
        rows = db.session.query(model.username, model.profile_url, model.followed_at).filter(
            model.dataset_id == ds.id, model.user_id == ds.user_id).all()
        return pd.DataFrame([tuple(r) for r in rows], columns=dc.ACCOUNT_COLS)
    rows = db.session.query(*[getattr(Post, c) for c in POST_DB_COLS]).filter(
        Post.dataset_id == ds.id, Post.user_id == ds.user_id).all()
    df = pd.DataFrame([tuple(r) for r in rows], columns=POST_DB_COLS)
    df["posted_at"] = pd.to_datetime(df["posted_at"], errors="coerce")
    return df


# ---------- deleting ----------
def delete_datasets(dataset_ids):
    if not dataset_ids:
        return
    post_ids = db.session.query(Post.id).filter(Post.dataset_id.in_(dataset_ids))
    EngagementMetric.query.filter(EngagementMetric.post_id.in_(post_ids)).delete(synchronize_session=False)
    for model in (Follower, Following, Post):
        model.query.filter(model.dataset_id.in_(dataset_ids)).delete(synchronize_session=False)
    AnalyticsResult.query.filter(AnalyticsResult.dataset_id.in_(dataset_ids)).delete(synchronize_session=False)
    Dataset.query.filter(Dataset.id.in_(dataset_ids)).update({"source_dataset_id": None}, synchronize_session=False)
    Dataset.query.filter(Dataset.id.in_(dataset_ids)).delete(synchronize_session=False)


def delete_file(upload):
    """Remove an uploaded file, its datasets and every record derived from it."""
    ids = [d.id for d in Dataset.query.filter_by(file_id=upload.id).all()]
    delete_datasets(ids)
    path = os.path.join(user_upload_dir(upload.user_id), upload.stored_name)
    if os.path.isfile(path):
        os.remove(path)
    db.session.delete(upload)


def delete_all_user_data(user_id):
    for up in UploadedFile.query.filter_by(user_id=user_id).all():
        delete_file(up)
    for rep in Report.query.filter_by(user_id=user_id).all():
        path = os.path.join(user_report_dir(user_id), rep.file_name)
        if os.path.isfile(path):
            os.remove(path)
        db.session.delete(rep)
    AnalyticsResult.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    db.session.commit()


def save_result(user_id, result_type, payload):
    """Keep the latest computed analysis (insights / ML) for the user."""
    AnalyticsResult.query.filter_by(user_id=user_id, result_type=result_type).delete()
    db.session.add(AnalyticsResult(user_id=user_id, result_type=result_type, payload=payload))
    db.session.commit()
