"""Data quality checks and cleaning.

Two levels, so raw and cleaned data stay distinct:
  prepare_raw()  - used at import. Drops only unusable rows (invalid / exact duplicates)
                   and reports how many. The original file is kept on disk untouched.
  clean()        - used on the Data Cleaning page. Standardises values, removes
                   case-insensitive duplicates. Saved as a NEW dataset; raw stays as is.
"""
import re
import numpy as np
import pandas as pd

USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")
ACCOUNT_COLS = ["username", "profile_url", "followed_at"]
NUM_COLS = ["likes", "comments", "shares", "saves", "reach", "impressions"]
POST_COLS = ["external_id", "caption", "content_type", "posted_at"] + NUM_COLS
TYPE_MAP = {"image": "photo", "photo": "photo", "picture": "photo", "video": "video",
            "reel": "reel", "reels": "reel", "clips": "reel", "carousel": "carousel",
            "carousel_album": "carousel", "album": "carousel", "sidecar": "carousel",
            "story": "story", "stories": "story"}


def columns_for(kind):
    return ACCOUNT_COLS if kind in ("followers", "following") else POST_COLS


def ensure_columns(kind, df):
    df = df.copy()
    for c in columns_for(kind):
        if c not in df.columns:
            df[c] = pd.NA
    return df[columns_for(kind)]


def _clean_username(s):
    return s.astype("string").str.strip().str.lstrip("@")


def _account_key(df):
    return _clean_username(df["username"]).str.lower()


def _post_key(df):
    ext = df["external_id"].astype("string").str.strip()
    fallback = df["posted_at"].astype("string").fillna("") + "|" + \
        df["caption"].astype("string").fillna("").str.strip().str.lower()
    return ext.where(ext.notna() & (ext != ""), fallback)


def invalid_mask(kind, df):
    if kind in ("followers", "following"):
        u = _clean_username(df["username"])
        return ~u.fillna("").str.match(USERNAME_RE)
    empty = df[["caption", "posted_at", "external_id"] + ["likes", "comments"]].isna().all(axis=1)
    negative = (df[NUM_COLS].apply(pd.to_numeric, errors="coerce") < 0).any(axis=1)
    return empty | negative


def duplicate_mask(kind, df):
    key = _account_key(df) if kind in ("followers", "following") else _post_key(df)
    return key.duplicated(keep="first").fillna(False).astype(bool)


def available_columns(kind, df):
    """Columns that actually contain data. All-empty columns are 'unavailable', not 'missing'."""
    return [c for c in columns_for(kind) if c in df.columns and df[c].notna().any()]


def missing_summary(kind, df):
    return {c: int(df[c].isna().sum()) for c in available_columns(kind, df) if df[c].isna().any()}


def outlier_mask(series):
    s = pd.to_numeric(series, errors="coerce")
    if s.notna().sum() < 8:
        return pd.Series(False, index=series.index)
    q1, q3 = s.quantile([0.25, 0.75])
    iqr = q3 - q1
    if iqr == 0:
        return pd.Series(False, index=series.index)
    return ((s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)).fillna(False)


def quality_report(kind, df):
    """Counts shown on the Data Cleaning page. Does not change the data."""
    df = ensure_columns(kind, df)
    n = len(df)
    inv = invalid_mask(kind, df)
    dup = duplicate_mask(kind, df[~inv]) if n else pd.Series(dtype=bool)
    miss = missing_summary(kind, df)
    rows_missing = int(df[available_columns(kind, df)].isna().any(axis=1).sum()) if n else 0
    outliers = {c: int(outlier_mask(df[c]).sum()) for c in NUM_COLS
                if kind == "posts" and c in available_columns(kind, df)}
    outliers = {c: v for c, v in outliers.items() if v}
    bad = int(inv.sum()) + int(dup.sum())
    score = round(100 * (1 - (bad + rows_missing) / n)) if n else 0
    return {"records": n, "invalid": int(inv.sum()), "duplicates": int(dup.sum()),
            "missing": miss, "missing_total": int(sum(miss.values())),
            "unavailable": [c for c in columns_for(kind) if c not in available_columns(kind, df)],
            "outliers": outliers, "score": max(0, min(100, score))}


def prepare_raw(kind, df):
    """Import-time step: drop unusable rows and duplicates, report counts."""
    df = ensure_columns(kind, df)
    total = len(df)
    inv = invalid_mask(kind, df)
    valid = df[~inv].copy()
    dup = duplicate_mask(kind, valid)
    out = valid[~dup].copy()
    if kind in ("followers", "following"):
        out["username"] = _clean_username(out["username"])
    stats = {"records_in": total, "records": len(out), "invalid": int(inv.sum()),
             "duplicates": int(dup.sum()), "missing": int(sum(missing_summary(kind, out).values()))}
    return out.reset_index(drop=True), stats


def clean(kind, df):
    """Cleaning step. Returns (cleaned_df, list of {step, count})."""
    df = ensure_columns(kind, df)
    changes = []
    inv = invalid_mask(kind, df)
    if inv.sum():
        changes.append({"step": "Removed invalid records", "count": int(inv.sum())})
    df = df[~inv].copy()
    if kind in ("followers", "following"):
        lowered = _clean_username(df["username"]).str.lower()
        changed = int((lowered != df["username"].astype("string")).sum())
        df["username"] = lowered
        if changed:
            changes.append({"step": "Standardised usernames to lowercase", "count": changed})
        if df["profile_url"].notna().any():
            df["profile_url"] = df["profile_url"].astype("string").str.strip()
    else:
        t = df["content_type"].astype("string").str.strip().str.lower().str.replace(r"[\s-]+", "_", regex=True)
        mapped = t.map(TYPE_MAP)
        n_types = int((mapped.notna() & (mapped != df["content_type"].astype("string"))).sum())
        df["content_type"] = mapped.where(mapped.notna(), t.where(t.isin(list(TYPE_MAP.values())), pd.NA))
        if n_types:
            changes.append({"step": "Standardised content types", "count": n_types})
        cap = df["caption"].astype("string").str.strip().replace("", pd.NA)
        n_cap = int((cap.fillna("") != df["caption"].astype("string").fillna("")).sum())
        df["caption"] = cap
        if n_cap:
            changes.append({"step": "Trimmed whitespace in captions", "count": n_cap})
        d = pd.to_datetime(df["posted_at"], errors="coerce")
        bad_date = d.notna() & ((d < pd.Timestamp("2010-10-06")) | (d > pd.Timestamp.now() + pd.Timedelta(days=1)))
        if bad_date.sum():
            d = d.mask(bad_date)
            changes.append({"step": "Cleared implausible dates (before Instagram existed or in the future)",
                            "count": int(bad_date.sum())})
        df["posted_at"] = d
        for c in NUM_COLS:
            df[c] = pd.to_numeric(df[c], errors="coerce").round()
    dup = duplicate_mask(kind, df)
    if dup.sum():
        changes.append({"step": "Removed duplicate records", "count": int(dup.sum())})
    df = df[~dup].reset_index(drop=True)
    return df, changes


def df_to_records(kind, df):
    """DataFrame -> list of plain dicts for the database (NaN/NaT -> None, numbers -> int)."""
    df = ensure_columns(kind, df)
    out = []
    for row in df.to_dict("records"):
        rec = {}
        for k, v in row.items():
            if v is None or v is pd.NA or (not isinstance(v, str) and pd.isna(v)):
                rec[k] = None
            elif k in NUM_COLS:
                rec[k] = int(v)
            elif isinstance(v, pd.Timestamp):
                rec[k] = v.to_pydatetime()
            elif isinstance(v, (np.generic,)):
                rec[k] = v.item()
            else:
                rec[k] = v
        out.append(rec)
    return out
