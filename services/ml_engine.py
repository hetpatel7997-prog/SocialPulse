"""Optional advanced analytics. Each function says when there is not enough data
and never claims to predict Instagram's algorithm."""
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

FEATURES = ["likes", "comments", "shares", "saves", "reach", "impressions"]
NAMES = {2: ["Lower performers", "Higher performers"], 3: ["Lower performers", "Typical posts", "Top performers"],
         4: ["Lowest performers", "Below typical", "Above typical", "Top performers"]}


def _na(reason):
    return {"available": False, "reason": reason}


def kmeans_clusters(p):
    if p is None or len(p) == 0:
        return _na("No posts imported.")
    feats = [c for c in FEATURES if c in p and p[c].notna().mean() >= 0.8]
    d = p.dropna(subset=feats) if feats else p.iloc[0:0]
    if len(feats) < 2 or len(d) < 12:
        return _na("Needs at least 12 posts with two or more numeric measures (for example likes and comments).")
    X = StandardScaler().fit_transform(d[feats])
    best = None
    for k in range(2, min(4, len(d) // 4) + 1):
        km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(X)
        if len(set(km.labels_)) < 2:
            continue
        s = silhouette_score(X, km.labels_)
        if best is None or s > best[0]:
            best = (s, k, km)
    if best is None:
        return _na("Posts are too similar to separate into groups.")
    s, k, km = best
    d = d.assign(cluster=km.labels_)
    order = d.groupby("cluster")[feats[0]].mean().sort_values().index.tolist()
    rank = {c: i for i, c in enumerate(order)}
    clusters = []
    for c in order:
        g = d[d["cluster"] == c]
        clusters.append({"name": NAMES[k][rank[c]], "size": int(len(g)), "share": round(len(g) / len(d) * 100, 1),
                         "means": {f: round(float(g[f].mean()), 1) for f in feats}})
    pts = d.assign(rank=d["cluster"].map(rank)).head(500)
    return {"available": True, "k": k, "silhouette": round(float(s), 2), "features": feats, "clusters": clusters,
            "points": [{"x": float(r[feats[0]]), "y": float(r[feats[1]]), "c": int(r["rank"])} for _, r in pts.iterrows()],
            "x_label": feats[0], "y_label": feats[1],
            "explanation": "K-Means groups posts with similar numbers. The number of groups (2-4) was chosen using the silhouette score, "
                           "which measures how well-separated the groups are (closer to 1 is better). Groups describe past posts only."}


def anomalies(p):
    if p is None or "interactions" not in p or p["interactions"].notna().sum() < 8:
        return _na("Needs at least 8 posts with likes or comments.")
    d = p.dropna(subset=["interactions"]).copy()
    x = d["interactions"]
    med = x.median()
    mad = (x - med).abs().median()
    if mad > 0:
        d["score"] = 0.6745 * (x - med) / mad
        flagged = d[d["score"].abs() > 3.5]
        method = "robust z-score (median and MAD), flagging scores beyond ±3.5"
    else:
        q1, q3 = x.quantile([.25, .75]); iqr = q3 - q1
        d["score"] = (x - med) / (iqr if iqr else 1)
        flagged = d[(x > q3 + 1.5 * iqr) | (x < q1 - 1.5 * iqr)] if iqr else d.iloc[0:0]
        method = "IQR rule (1.5 × interquartile range)"
    flagged = flagged.reindex(flagged["score"].abs().sort_values(ascending=False).index).head(12)
    rows = [{"date": r.posted_at.strftime("%d %b %Y") if pd.notna(r.posted_at) else "-",
             "caption": (r.caption[:60] + "…") if isinstance(r.caption, str) and len(r.caption) > 60 else (r.caption if isinstance(r.caption, str) else "(no caption)"),
             "interactions": int(r.interactions), "direction": "Unusually high" if r.score > 0 else "Unusually low"}
            for r in flagged.itertuples()]
    return {"available": True, "rows": rows, "typical": round(float(med), 1), "method": method,
            "explanation": f"Posts whose likes + comments are far from the typical value ({med:,.0f}) are flagged using the {method}."}


def _monthly(p, how):
    d = p.dropna(subset=["posted_at"])
    if d.empty:
        return None
    per = d["posted_at"].dt.to_period("M")
    s = d.groupby(per).size() if how == "count" else d.dropna(subset=["interactions"]).groupby(
        d.dropna(subset=["interactions"])["posted_at"].dt.to_period("M"))["interactions"].mean()
    if s.empty:
        return None
    return s.reindex(pd.period_range(s.index.min(), s.index.max(), freq="M"))


def _fit(s):
    y = s.interpolate().to_numpy(dtype=float)
    x = np.arange(len(y))
    slope, icpt = np.polyfit(x, y, 1)
    pred = slope * x + icpt
    ss_res, ss_tot = ((y - pred) ** 2).sum(), ((y - y.mean()) ** 2).sum()
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
    return slope, icpt, float(r2), y


def trends(p):
    if p is None or len(p) == 0:
        return _na("No posts imported.")
    out = {"available": False, "items": []}
    for how, label in (("inter", "Average likes + comments per post"), ("count", "Posts per month")):
        s = _monthly(p, how)
        if s is None or s.notna().sum() < 4:
            continue
        slope, icpt, r2, y = _fit(s)
        rel = slope / y.mean() * 100 if y.mean() else 0
        direction = "roughly flat" if abs(rel) < 5 else ("rising" if rel > 0 else "falling")
        out["items"].append({"label": label, "direction": direction, "change_pct": round(rel, 1), "r2": round(r2, 2),
                             "months": [str(m) for m in s.index], "values": [None if pd.isna(v) else round(float(v), 1) for v in s.values]})
    if not out["items"]:
        return _na("Needs at least 4 months of dated posts.")
    out["available"] = True
    out["explanation"] = ("A straight line is fitted to the monthly values. The change shows the line's slope as a percentage of the "
                          "average per month; R² shows how closely the line follows the data (low values mean the trend is weak).")
    return out


def forecast(p, months_ahead=3):
    if p is None or len(p) == 0:
        return _na("No posts imported.")
    s = _monthly(p, "inter")
    if s is None or s.notna().sum() < 6:
        return _na("Needs at least 6 months of posts with likes or comments. Forecasts from less data would be unreliable.")
    slope, icpt, r2, y = _fit(s)
    n = len(y)
    future = [max(0.0, slope * (n + i) + icpt) for i in range(months_ahead)]
    labels = [str(m) for m in s.index] + [str(s.index[-1] + i) for i in range(1, months_ahead + 1)]
    conf = "low" if r2 < 0.3 else ("moderate" if r2 < 0.6 else "reasonable")
    return {"available": True, "labels": labels, "actual": [round(float(v), 1) for v in y] + [None] * months_ahead,
            "forecast": [None] * (n - 1) + [round(float(y[-1]), 1)] + [round(v, 1) for v in future],
            "r2": round(r2, 2), "confidence": conf,
            "explanation": f"A linear trend extended {months_ahead} months for average likes + comments per post. Confidence is {conf} (R² = {r2:.2f}). "
                           "This is only a continuation of past numbers; it cannot predict Instagram's algorithm, viral posts or future follower counts."}
