"""Flexible import engine for Instagram exports (JSON, CSV, XLSX, HTML).

It does not assume one fixed structure. It looks at keys, columns, file names and
the data the user selected, and returns only the datasets it can recognise.
"""
import io
import json
import re
from dataclasses import dataclass, field
import pandas as pd
from bs4 import BeautifulSoup

from services.data_cleaner import ensure_columns, NUM_COLS


class ParseError(Exception):
    """A problem the user can understand and fix."""


@dataclass
class ParsedDataset:
    kind: str            # followers / following / posts
    df: pd.DataFrame
    name: str = ""


@dataclass
class ParseResult:
    datasets: list = field(default_factory=list)
    skipped: list = field(default_factory=list)   # notes about parts we did not use


ACCOUNT_ALIASES = {
    "username": ["username", "user_name", "user", "handle", "account", "account_name", "instagram_username", "profile"],
    "profile_url": ["profile_url", "url", "link", "href", "profile_link"],
    "followed_at": ["followed_at", "date", "timestamp", "followed_date", "follow_date", "followed_on", "time"],
}
POST_ALIASES = {
    "external_id": ["external_id", "id", "post_id", "media_id", "permalink", "uri", "url", "shortcode"],
    "caption": ["caption", "title", "description", "text", "post_caption"],
    "content_type": ["content_type", "type", "media_type", "post_type", "format"],
    "posted_at": ["posted_at", "date", "timestamp", "created_at", "post_date", "time", "publish_time", "published_at", "taken_at"],
    "likes": ["likes", "like_count", "likes_count", "total_likes"],
    "comments": ["comments", "comment_count", "comments_count", "total_comments"],
    "shares": ["shares", "share_count", "shares_count"],
    "saves": ["saves", "save_count", "saved"],
    "reach": ["reach", "accounts_reached"],
    "impressions": ["impressions", "views", "video_views", "plays"],
}
POST_SIGNALS = {"likes", "like_count", "likes_count", "total_likes", "comments", "comment_count", "comments_count",
                "caption", "reach", "impressions", "shares", "saves", "post_caption", "total_comments"}
USER_SIGNALS = set(ACCOUNT_ALIASES["username"])
JSON_POST_KEYS = {"ig_stories": "story", "ig_reels_media": "reel", "ig_archived_post_media": None,
                  "posts": None, "media": None, "ig_posts": None}


# ---------- small helpers ----------
def fix_text(value):
    """Instagram JSON stores UTF-8 as latin-1 escapes; undo that so emoji/accents look right."""
    if isinstance(value, str):
        try:
            return value.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return value
    return value


def parse_dates(series):
    s = pd.Series(series).reset_index(drop=True)
    num = pd.to_numeric(s, errors="coerce")
    nn = num.dropna()
    if len(nn) and len(nn) >= 0.8 * s.notna().sum() and (nn > 1e8).all():
        return pd.to_datetime(num, unit="ms" if nn.median() > 1e11 else "s", errors="coerce")
    return pd.to_datetime(s, errors="coerce", utc=True, format="mixed").dt.tz_localize(None)


def to_number(series):
    s = pd.Series(series).astype("string").str.replace(r"[,\s]", "", regex=True)
    return pd.to_numeric(s, errors="coerce")


def kind_from_text(text):
    t = (text or "").lower()
    if "following" in t:
        return "following"
    if "follower" in t:
        return "followers"
    return None


def username_from_href(href):
    m = re.search(r"instagram\.com/(?:_u/)?([A-Za-z0-9._]+)/?$", href or "")
    return m.group(1) if m else None


def _map_columns(df, aliases):
    cols = list(df.columns)
    rename, used = {}, set()
    for target, names in aliases.items():
        for n in names:
            if n in cols and n not in used:
                rename[n] = target
                used.add(n)
                break
    return df.rename(columns=rename)


def _finish(kind, df, name):
    """Normalise types for a recognised dataset."""
    df = ensure_columns(kind, df)
    if kind == "posts":
        for c in NUM_COLS:
            df[c] = to_number(df[c])
        df["posted_at"] = parse_dates(df["posted_at"])
        for c in ("external_id", "caption", "content_type"):
            df[c] = df[c].astype("string")
    else:
        df["followed_at"] = parse_dates(df["followed_at"])
        df["username"] = df["username"].astype("string")
        df["profile_url"] = df["profile_url"].astype("string")
    return ParsedDataset(kind, df.reset_index(drop=True), name)


# ---------- DataFrame sources (CSV / XLSX / HTML tables / flat JSON) ----------
def _frame_to_dataset(df, hint, forced, result, name):
    df = df.copy()
    df.columns = [re.sub(r"[\s\-]+", "_", str(c).strip().lower()) for c in df.columns]
    cols = set(df.columns)
    if forced in ("followers", "following", "posts"):
        kind = forced
    elif cols & POST_SIGNALS:
        kind = "posts"
    elif cols & USER_SIGNALS:
        kind = kind_from_text(hint)
        if not kind:
            result.skipped.append(f"{name}: has usernames but could not tell if it is followers or following. "
                                  "Choose the data type before uploading.")
            return
    else:
        result.skipped.append(f"{name}: columns not recognised ({', '.join(list(df.columns)[:6])}).")
        return
    df = _map_columns(df, POST_ALIASES if kind == "posts" else ACCOUNT_ALIASES)
    if kind != "posts" and "username" not in df.columns:
        result.skipped.append(f"{name}: no username column found.")
        return
    result.datasets.append(_finish(kind, df, name))


def _read_csv(raw):
    for enc in ("utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(io.BytesIO(raw), dtype=str, sep=None, engine="python", encoding=enc)
        except UnicodeDecodeError:
            continue
        except pd.errors.EmptyDataError:
            raise ParseError("The CSV file is empty.")
        except pd.errors.ParserError as e:
            raise ParseError(f"The CSV file could not be read: {e}")
    raise ParseError("The CSV file encoding is not supported.")


# ---------- JSON ----------
def _accounts_from_entries(entries):
    rows = []
    for e in entries:
        sld = e.get("string_list_data") or []
        first = sld[0] if sld and isinstance(sld[0], dict) else {}
        username = first.get("value") or e.get("title") or username_from_href(first.get("href"))
        rows.append({"username": fix_text(username), "profile_url": first.get("href"),
                     "followed_at": first.get("timestamp")})
    return pd.DataFrame(rows)


def _guess_type(media):
    if len(media) > 1:
        return "carousel"
    uri = str((media[0] or {}).get("uri", "")).lower() if media else ""
    if uri.endswith((".mp4", ".mov")):
        return "video"
    if uri.endswith((".jpg", ".jpeg", ".png", ".webp", ".heic")):
        return "photo"
    return None


def _posts_from_entries(entries, default_type):
    rows = []
    for e in entries:
        media = [m for m in (e.get("media") or []) if isinstance(m, dict)] if isinstance(e.get("media"), list) else []
        m0 = media[0] if media else {}
        rows.append({
            "external_id": e.get("id") or m0.get("uri") or e.get("uri"),
            "caption": fix_text(e.get("title") or m0.get("title") or e.get("caption")),
            "content_type": default_type or e.get("media_type") or _guess_type(media),
            "posted_at": e.get("creation_timestamp") or m0.get("creation_timestamp") or e.get("timestamp"),
            "likes": e.get("like_count", e.get("likes")),
            "comments": e.get("comment_count", e.get("comments")),
        })
    return pd.DataFrame(rows)


def _walk_json(obj, key, filename, forced, result):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (list, dict)):
                _walk_json(v, k, filename, forced, result)
        return
    if not (isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj)):
        return
    sample, k = obj[0], (key or "").lower()
    if "string_list_data" in sample:
        if any(w in k for w in ("like", "comment", "block", "request", "close_friend", "hashtag", "recent", "story")):
            result.skipped.append(f"'{key}' skipped (not followers or following).")
            return
        kind = forced if forced in ("followers", "following") else (kind_from_text(k) or kind_from_text(filename))
        if not kind:
            result.skipped.append(f"'{key or filename}': account list, but followers vs following is unclear. "
                                  "Choose the data type before uploading.")
            return
        result.datasets.append(_finish(kind, _accounts_from_entries(obj), key or filename))
    elif "media" in sample or "creation_timestamp" in sample or k in JSON_POST_KEYS:
        result.datasets.append(_finish("posts", _posts_from_entries(obj, JSON_POST_KEYS.get(k)), key or filename))
    else:
        _frame_to_dataset(pd.json_normalize(obj), f"{k} {filename}", forced, result, key or filename)


def _parse_json(raw, filename, forced, result):
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ParseError(f"This is not valid JSON: {e}")
    _walk_json(data, "", filename, forced, result)


# ---------- HTML ----------
def _parse_html(raw, filename, forced, result):
    soup = BeautifulSoup(raw.decode("utf-8", errors="replace"), "html.parser")
    hint = f"{filename} {soup.title.get_text() if soup.title else ''} {(soup.h1.get_text() if soup.h1 else '')}"
    tables = soup.find_all("table")
    for i, t in enumerate(tables):
        rows = [[c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])] for tr in t.find_all("tr")]
        if len(rows) >= 2:
            df = pd.DataFrame(rows[1:], columns=[h or f"col{j}" for j, h in enumerate(rows[0])])
            _frame_to_dataset(df, hint, forced, result, f"table {i + 1}")
    if result.datasets:
        return
    kind = forced if forced in ("followers", "following") else kind_from_text(hint)
    rows = []
    for a in soup.find_all("a", href=True):
        user = username_from_href(a["href"])
        if not user:
            continue
        text = a.get_text(strip=True) or user
        date_text = None
        box = a.find_parent("div")
        if box is not None and box.parent is not None:
            t = box.parent.get_text(" ", strip=True).replace(text, "", 1).strip()
            date_text = t if 0 < len(t) < 60 else None
        rows.append({"username": text, "profile_url": a["href"], "followed_at": date_text})
    if rows and kind:
        result.datasets.append(_finish(kind, pd.DataFrame(rows), filename))
    elif rows:
        raise ParseError("Found Instagram accounts in this HTML but could not tell if it is followers or "
                         "following. Choose the data type before uploading.")


# ---------- public entry point ----------
def parse_file(path, extension, original_name="", forced_kind=None):
    """Parse one file from disk. Raises ParseError with a friendly message on failure."""
    forced = forced_kind if forced_kind in ("followers", "following", "posts") else None
    ext = extension.lower().lstrip(".")
    with open(path, "rb") as fh:
        raw = fh.read()
    if not raw.strip():
        raise ParseError("The file is empty.")
    result = ParseResult()
    base = original_name or path
    try:
        if ext == "json":
            _parse_json(raw, base, forced, result)
        elif ext == "csv":
            _frame_to_dataset(_read_csv(raw), base, forced, result, base)
        elif ext == "xlsx":
            try:
                sheets = pd.read_excel(io.BytesIO(raw), sheet_name=None, dtype=str)
            except Exception as e:  # corrupt or not a real xlsx
                raise ParseError(f"The Excel file could not be read: {e}")
            for sheet, df in sheets.items():
                _frame_to_dataset(df, f"{sheet} {base}", forced, result, f"sheet '{sheet}'")
        elif ext in ("html", "htm"):
            _parse_html(raw, base, forced, result)
        else:
            raise ParseError(f"Unsupported file type: .{ext}")
    except ParseError:
        raise
    except Exception as e:
        raise ParseError(f"Could not process this file: {e}")

    if forced:
        found = sorted({d.kind for d in result.datasets})
        result.datasets = [d for d in result.datasets if d.kind == forced]
        if not result.datasets:
            raise ParseError(f"No {forced} data found in this file"
                             + (f" (it looks like {', '.join(found)})." if found else "."))
    if not result.datasets:
        detail = f" {result.skipped[0]}" if result.skipped else ""
        raise ParseError("No supported Instagram data was recognised in this file." + detail)
    result.datasets = [d for d in result.datasets if len(d.df)]
    if not result.datasets:
        raise ParseError("The file was recognised but contains no records.")
    return result
