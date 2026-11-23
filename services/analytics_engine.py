"""All analytics, as pure pandas functions (no database or Flask), so they are easy to test.

`frames` is a dict:
  followers / following : DataFrame with username, profile_url, followed_at, snapshot (YYYY-MM-DD) or None
  posts                 : DataFrame of post columns or None
  meta                  : list of dataset summaries (for the data quality section)
"""
import numpy as np
import pandas as pd

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WEEKDAY_NAMES = ["Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays"]


def _key(s):
    return s.astype("string").str.strip().str.lstrip("@").str.lower()


def has_rows(df):
    return df is not None and len(df) > 0


def snapshot_list(df):
    return sorted(df["snapshot"].dropna().unique().tolist()) if has_rows(df) else []


def latest(df, back=0):
    """Rows of the newest snapshot (or `back` snapshots before it)."""
    snaps = snapshot_list(df)
    if len(snaps) <= back:
        return None
    return df[df["snapshot"] == snaps[-1 - back]].copy()


# ---------- followers / following ----------
def follow_stats(followers, following):
    f, g = latest(followers), latest(following)
    out = {"followers": len(f) if has_rows(f) else None, "following": len(g) if has_rows(g) else None,
           "mutual": None, "not_following_back": None, "fans": None, "ratio": None}
    if has_rows(f) and has_rows(g):
        fk, gk = set(_key(f["username"])), set(_key(g["username"]))
        out.update(mutual=len(fk & gk), not_following_back=len(gk - fk), fans=len(fk - gk),
                   ratio=round(len(fk) / len(gk), 2) if gk else None)
    return out


def growth(followers):
    snaps = snapshot_list(followers)
    if len(snaps) < 2:
        return None
    counts = followers.groupby("snapshot")["username"].nunique()
    cur, prev = latest(followers), latest(followers, 1)
    ck, pk = set(_key(cur["username"])), set(_key(prev["username"]))
    return {"labels": snaps, "values": [int(counts[s]) for s in snaps],
            "new": len(ck - pk), "lost": len(pk - ck), "from": snaps[-2], "to": snaps[-1]}


def people_view(followers, following, kind, view="all", q="", sort="username", direction="asc",
                page=1, per_page=25):
    base = latest(followers) if kind == "followers" else latest(following)
    other = latest(following) if kind == "followers" else latest(followers)
    g = growth(followers) if kind == "followers" else None
    empty = {"rows": [], "total": 0, "page": 1, "pages": 1, "counts": {}, "reason": None}
    if not has_rows(base):
        empty["reason"] = f"No {kind} data imported yet."
        return empty
    bk = _key(base["username"])
    ok = set(_key(other["username"])) if has_rows(other) else None
    counts = {"all": len(base)}
    if ok is not None:
        counts["mutual"] = int(bk.isin(ok).sum())
        counts["fans" if kind == "followers" else "not_back"] = int((~bk.isin(ok)).sum())
    if g:
        counts["new"], counts["lost"] = g["new"], g["lost"]
    reason, df = None, base
    if view == "mutual":
        df, reason = (base[bk.isin(ok)], None) if ok is not None else (base.iloc[0:0], "Import both followers and following to see mutual connections.")
    elif view in ("fans", "not_back"):
        df, reason = (base[~bk.isin(ok)], None) if ok is not None else (base.iloc[0:0], "Import both followers and following to compare them.")
    elif view in ("new", "lost") and g:
        cur, prev = latest(followers), latest(followers, 1)
        ck, pk = _key(cur["username"]), _key(prev["username"])
        df = cur[~ck.isin(set(pk))] if view == "new" else prev[~pk.isin(set(ck))]
    elif view in ("new", "lost"):
        reason = "Upload follower exports from at least two different dates to compare snapshots."
        df = base.iloc[0:0]
    if q:
        df = df[df["username"].astype("string").str.contains(q.strip().lstrip("@"), case=False, regex=False, na=False)]
    sort = sort if sort in ("username", "followed_at") else "username"
    df = df.sort_values(sort, ascending=(direction != "desc"), na_position="last",
                        key=(lambda s: s.astype("string").str.lower()) if sort == "username" else None)
    total = len(df)
    pages = max(1, -(-total // per_page))
    page = min(max(1, page), pages)
    chunk = df.iloc[(page - 1) * per_page: page * per_page]
    rows = [{"username": r.username, "url": r.profile_url if isinstance(r.profile_url, str) else f"https://www.instagram.com/{r.username}",
             "followed_at": r.followed_at.strftime("%d %b %Y") if pd.notna(r.followed_at) else None}
            for r in chunk.itertuples()]
    return {"rows": rows, "total": total, "page": page, "pages": pages, "counts": counts, "reason": reason}


# ---------- posts ----------
def with_metrics(posts):
    p = posts.copy()
    lk, cm = pd.to_numeric(p["likes"], errors="coerce"), pd.to_numeric(p["comments"], errors="coerce")
    p["likes"], p["comments"] = lk, cm
    p["interactions"] = np.where(lk.notna() | cm.notna(), lk.fillna(0) + cm.fillna(0), np.nan)
    p["tier"], p["is_outlier"] = None, False
    inter = p["interactions"]
    if inter.notna().sum() >= 4:
        q1, q3 = inter.quantile([0.25, 0.75])
        high = (inter >= q3) & (q3 > q1)
        low = (inter <= q1) & (q1 < q3)
        p["tier"] = np.select([high, low, inter.notna()], ["high", "low", "average"], default=None)
        iqr = q3 - q1
        p["is_outlier"] = ((inter > q3 + 1.5 * iqr) | (inter < q1 - 1.5 * iqr)) if iqr > 0 else False
    return p


def apply_filters(p, date_from=None, date_to=None, ctype=None, tier=None):
    if date_from:
        p = p[p["posted_at"] >= pd.Timestamp(date_from)]
    if date_to:
        p = p[p["posted_at"] < pd.Timestamp(date_to) + pd.Timedelta(days=1)]
    if ctype:
        p = p[p["content_type"] == ctype]
    if tier:
        p = p[p["tier"] == tier]
    return p


def capabilities(frames, p):
    has_posts = has_rows(p)
    dated = has_posts and p["posted_at"].notna().any()
    return {
        "followers": has_rows(frames.get("followers")), "following": has_rows(frames.get("following")),
        "posts": has_posts, "dates": bool(dated),
        "likes": bool(has_posts and p["likes"].notna().any()),
        "comments": bool(has_posts and p["comments"].notna().any()),
        "types": bool(has_posts and p["content_type"].notna().mean() >= 0.5 and p["content_type"].nunique() >= 2),
        "growth": len(snapshot_list(frames.get("followers"))) >= 2,
    }


def engagement_rate(p, followers_count):
    if not followers_count or p is None or not has_rows(p):
        return None
    inter = p["interactions"].dropna()
    return round(float(inter.mean()) / followers_count * 100, 2) if len(inter) else None


def _short(text, n=70):
    if not isinstance(text, str) or not text.strip():
        return "(no caption)"
    t = " ".join(text.split())
    return t if len(t) <= n else t[: n - 1] + "…"


def post_rows(p, n=10, ascending=False, by="interactions"):
    d = p.dropna(subset=[by]).sort_values(by, ascending=ascending).head(n)
    avg = p[by].mean() if by in p and p[by].notna().any() else None
    rows = []
    for r in d.itertuples():
        rows.append({"date": r.posted_at.strftime("%d %b %Y") if pd.notna(r.posted_at) else "-",
                     "type": r.content_type if isinstance(r.content_type, str) else "-",
                     "caption": _short(r.caption),
                     "likes": None if pd.isna(r.likes) else int(r.likes),
                     "comments": None if pd.isna(r.comments) else int(r.comments),
                     "interactions": None if pd.isna(r.interactions) else int(r.interactions),
                     "vs_avg": round(r.interactions / avg, 2) if avg else None})
    return rows


def recent_rows(p, n=10):
    d = p.sort_values("posted_at", ascending=False, na_position="last").head(n)
    return [{"date": r.posted_at.strftime("%d %b %Y") if pd.notna(r.posted_at) else "-",
             "type": r.content_type if isinstance(r.content_type, str) else "-", "caption": _short(r.caption),
             "likes": None, "comments": None, "interactions": None, "vs_avg": None} for r in d.itertuples()]


def type_table(p):
    d = p[p["content_type"].notna()]
    g = d.groupby("content_type").agg(posts=("content_type", "size"), avg_likes=("likes", "mean"),
                                      avg_comments=("comments", "mean"), avg_interactions=("interactions", "mean"),
                                      total_interactions=("interactions", "sum")).reset_index()
    g = g.sort_values("avg_interactions", ascending=False, na_position="last")
    return [{k: (None if pd.isna(v) else (round(float(v), 1) if isinstance(v, (float, np.floating)) else v))
             for k, v in row.items()} for row in g.to_dict("records")]


# ---------- chart payloads (Chart.js friendly) ----------
def _empty(reason):
    return {"empty": reason}


def _months(d):
    per = d["posted_at"].dropna().dt.to_period("M")
    return pd.period_range(per.min(), per.max(), freq="M")


def build_charts(frames, p, caps, fstats):
    ch = {}
    if fstats["followers"] is not None and fstats["following"] is not None:
        ch["followers_vs_following"] = {"labels": ["Followers", "Following"], "series": [
            {"name": "Accounts", "data": [fstats["followers"], fstats["following"]]}]}
    else:
        ch["followers_vs_following"] = _empty("Import both a followers and a following file.")
    g = growth(frames.get("followers"))
    ch["follower_growth"] = ({"labels": g["labels"], "series": [{"name": "Followers", "data": g["values"]}]}
                             if g else _empty("Needs follower exports from two or more different dates."))

    if not caps["posts"]:
        reason = "Import a posts file."
        for k in ("post_engagement", "content_performance", "posting_frequency", "likes_comments",
                  "distribution", "heatmap", "weekday"):
            ch[k] = _empty(reason)
        return ch
    d = p[p["posted_at"].notna()] if caps["dates"] else p.iloc[0:0]
    inter = p.dropna(subset=["interactions"])

    if len(inter):
        top = inter.sort_values("interactions", ascending=False).head(15)
        ch["post_engagement"] = {"labels": [(r.posted_at.strftime("%d %b %y") if pd.notna(r.posted_at) else "undated") + f" #{i + 1}"
                                            for i, r in enumerate(top.itertuples())],
                                 "series": [{"name": "Likes + comments", "data": [int(x) for x in top["interactions"]]}]}
        counts, edges = np.histogram(inter["interactions"], bins=min(10, max(3, len(inter) // 3)))
        ch["distribution"] = {"labels": [f"{int(edges[i])}–{int(edges[i + 1])}" for i in range(len(counts))],
                              "series": [{"name": "Posts", "data": [int(c) for c in counts]}]}
        if caps["types"]:
            by = inter.groupby("content_type")["interactions"].sum()
            ch["content_performance"] = {"labels": by.index.tolist(), "series": [{"name": "Interactions", "data": [int(x) for x in by.values]}],
                                         "note": "Share of total likes + comments by content type"}
        elif inter["tier"].notna().any():
            t = inter["tier"].value_counts()
            ch["content_performance"] = {"labels": [x.title() for x in t.index], "series": [{"name": "Posts", "data": [int(x) for x in t.values]}],
                                         "note": "Posts by performance tier (the export has no reliable content type)"}
        else:
            ch["content_performance"] = _empty("Not enough posts with likes or comments.")
    else:
        for k in ("post_engagement", "distribution", "content_performance"):
            ch[k] = _empty("The posts file has no like or comment counts, so engagement can't be measured.")

    if len(d):
        months = _months(d)
        per = d["posted_at"].dt.to_period("M")
        cnt = per.value_counts().reindex(months, fill_value=0).sort_index()
        days_idx = pd.date_range(d["posted_at"].min().normalize(), d["posted_at"].max().normalize())
        daily = d["posted_at"].dt.normalize().value_counts().reindex(days_idx, fill_value=0).sort_index().tail(180)
        ch["posting_frequency"] = {"labels": [str(m) for m in cnt.index], "series": [{"name": "Posts", "data": [int(x) for x in cnt.values]}],
                                   "daily": {"labels": [x.strftime("%d %b") for x in daily.index], "data": [int(x) for x in daily.values]}}
        wd = d["posted_at"].dt.weekday.value_counts().reindex(range(7), fill_value=0).sort_index()
        ch["weekday"] = {"labels": WEEKDAYS, "series": [{"name": "Posts", "data": [int(x) for x in wd.values]}]}
        hm = pd.crosstab(per, d["posted_at"].dt.weekday).reindex(index=months, columns=range(7), fill_value=0)
        ch["heatmap"] = {"rows": [str(m) for m in hm.index], "cols": WEEKDAYS, "values": hm.values.tolist(), "max": int(hm.values.max())}
        lc = d.groupby(per).agg(likes=("likes", "sum"), comments=("comments", "sum")).reindex(months, fill_value=0)
        if caps["likes"] or caps["comments"]:
            series = []
            if caps["likes"]:
                series.append({"name": "Likes", "data": [int(x) for x in lc["likes"]]})
            if caps["comments"]:
                series.append({"name": "Comments", "data": [int(x) for x in lc["comments"]]})
            ch["likes_comments"] = {"labels": [str(m) for m in lc.index], "series": series}
        else:
            ch["likes_comments"] = _empty("No like or comment counts in the export.")
    else:
        for k in ("posting_frequency", "heatmap", "weekday"):
            ch[k] = _empty("The posts file has no usable dates.")
        ch["likes_comments"] = _empty("The posts file has no usable dates.")
    return ch


# ---------- main entry ----------
def analyze(frames, filters=None):
    """Compute everything the pages and reports need from `frames`."""
    filters = filters or {}
    posts = frames.get("posts")
    pm = with_metrics(posts) if has_rows(posts) else None
    caps = capabilities(frames, pm)
    fstats = follow_stats(frames.get("followers"), frames.get("following"))
    pf = apply_filters(pm, **filters) if pm is not None else None
    n_posts = len(pf) if pf is not None else None
    fol = fstats["followers"]
    rate = engagement_rate(pf, fol) if (pf is not None and fol and (caps["likes"] or caps["comments"])) else None
    fmt = lambda v: None if v is None else f"{int(v):,}"
    kpis = [
        {"label": "Total followers", "value": fmt(fol), "note": "Import a followers file"},
        {"label": "Total following", "value": fmt(fstats["following"]), "note": "Import a following file"},
        {"label": "Total posts", "value": fmt(n_posts), "note": "Import a posts file"},
        {"label": "Total likes", "value": fmt(pf["likes"].sum()) if caps["likes"] else None, "note": "Not in your export"},
        {"label": "Total comments", "value": fmt(pf["comments"].sum()) if caps["comments"] else None, "note": "Not in your export"},
        {"label": "Engagement rate", "value": f"{rate}%" if rate is not None else None,
         "note": "Needs followers plus likes or comments"},
    ]
    from services.insights_engine import generate
    ctx = {"caps": caps, "fstats": fstats, "kpis": kpis, "posts": pf, "all_posts": pm,
           "charts": build_charts(frames, pf, caps, fstats) if pm is not None or caps["followers"] or caps["following"] else {},
           "growth": growth(frames.get("followers")), "engagement_rate": rate,
           "followers": latest(frames.get("followers")), "following": latest(frames.get("following")),
           "meta": frames.get("meta", [])}
    if pf is not None and len(pf):
        inter_ok = pf["interactions"].notna().any()
        ctx["top_posts"] = post_rows(pf, 10) if inter_ok else recent_rows(pf, 10)
        ctx["bottom_posts"] = post_rows(pf, 10, ascending=True) if inter_ok else []
        ctx["type_table"] = type_table(pf) if caps["types"] and inter_ok else []
        ctx["tiers"] = pf["tier"].value_counts().to_dict() if inter_ok else {}
        ctx["avg_likes"] = None if not caps["likes"] else round(float(pf["likes"].mean()), 1)
        ctx["avg_comments"] = None if not caps["comments"] else round(float(pf["comments"].mean()), 1)
        d = pf["posted_at"].dropna()
        ctx["posts_per_month"] = round(len(d) / max(1, (d.max() - d.min()).days / 30.44), 1) if len(d) > 1 else None
        ctx["types_available"] = sorted(pf["content_type"].dropna().unique().tolist())
    else:
        ctx.update(top_posts=[], bottom_posts=[], type_table=[], tiers={}, avg_likes=None, avg_comments=None,
                   posts_per_month=None, types_available=sorted(pm["content_type"].dropna().unique().tolist()) if pm is not None else [])
    ctx["insights"] = generate(ctx, pm)
    return ctx
