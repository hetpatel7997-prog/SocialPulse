"""Tests for the parsing, cleaning, analytics, ML and report services (no web server needed)."""
import json
import pandas as pd
import pytest
from services.instagram_parser import parse_file, ParseError
from services.data_cleaner import prepare_raw, clean, quality_report
from services import analytics_engine as ae, ml_engine as ml
from services.demo_data import build_demo
from services.report_generator import generate_excel, generate_pdf


def write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return str(p)


def follower_json():
    return json.dumps([
        {"string_list_data": [{"href": "https://www.instagram.com/alice", "value": "alice", "timestamp": 1700000000}]},
        {"string_list_data": [{"href": "https://www.instagram.com/Bob", "value": "Bob", "timestamp": 1700100000}]},
        {"string_list_data": [{"value": "bob", "timestamp": 1700100000}]},
        {"string_list_data": [{"value": "not valid!", "timestamp": 1}]}])


def test_json_followers_duplicates_and_invalid(tmp_path):
    r = parse_file(write(tmp_path, "followers_1.json", follower_json()), "json", "followers_1.json")
    assert r.datasets[0].kind == "followers"
    df, stats = prepare_raw("followers", r.datasets[0].df)
    assert stats["records"] == 2 and stats["duplicates"] == 1 and stats["invalid"] == 1


def test_json_following_dict_key(tmp_path):
    data = {"relationships_following": [{"title": "carol", "string_list_data": [{"href": "https://www.instagram.com/carol", "timestamp": 1700000000}]}]}
    r = parse_file(write(tmp_path, "following.json", json.dumps(data)), "json", "following.json")
    assert r.datasets[0].kind == "following" and r.datasets[0].df["username"].tolist() == ["carol"]


def test_csv_posts_and_cleaning(tmp_path):
    csv = "date,caption,likes,comments,type\n2024-01-05,hi,10,2,Reel\n2024-01-06,yo,1500,40,image\n2024-01-05,hi,10,2,Reel\n"
    r = parse_file(write(tmp_path, "p.csv", csv), "csv", "p.csv")
    df, stats = prepare_raw("posts", r.datasets[0].df)
    assert stats["duplicates"] == 1 and len(df) == 2
    cleaned, changes = clean("posts", df)
    assert set(cleaned["content_type"]) == {"reel", "photo"} or set(cleaned["content_type"]) == {"photo", "reel"}


def test_excel_parsing(tmp_path):
    x = tmp_path / "t.xlsx"
    pd.DataFrame({"Username": ["a", "b"], "Date": ["2024-01-01", "2024-02-01"]}).to_excel(x, index=False, sheet_name="Followers")
    r = parse_file(str(x), "xlsx", "t.xlsx")
    assert r.datasets[0].kind == "followers" and len(r.datasets[0].df) == 2


def test_html_parsing(tmp_path):
    html = '<html><head><title>Followers</title></head><body><div><div><a href="https://www.instagram.com/zed">zed</a></div><div>Mar 05, 2024 3:14 pm</div></div></body></html>'
    r = parse_file(write(tmp_path, "followers_1.html", html), "html", "followers_1.html")
    assert r.datasets[0].df["username"].tolist() == ["zed"]
    assert r.datasets[0].df["followed_at"].notna().all()


def test_invalid_and_empty_files(tmp_path):
    with pytest.raises(ParseError):
        parse_file(write(tmp_path, "bad.json", "{not json"), "json", "bad.json")
    with pytest.raises(ParseError):
        parse_file(write(tmp_path, "e.csv", "   "), "csv", "e.csv")
    with pytest.raises(ParseError):
        parse_file(write(tmp_path, "u.csv", "username,date\nx,2024-01-01\n"), "csv", "u.csv")  # ambiguous
    assert parse_file(write(tmp_path, "u.csv", "username,date\nx,2024-01-01\n"), "csv", "u.csv", "following").datasets[0].kind == "following"


def demo_frames():
    d = build_demo(today="2026-06-01")
    fol = []
    for date, df in d["followers_snapshots"]:
        x, _ = prepare_raw("followers", df)
        x["snapshot"] = date.strftime("%Y-%m-%d")
        fol.append(x)
    fg, _ = prepare_raw("following", d["following"]); fg["snapshot"] = "2026-06-01"
    po, _ = prepare_raw("posts", d["posts"])
    return {"followers": pd.concat(fol), "following": fg, "posts": po, "meta": [
        {"kind": "posts", "name": "demo", "records": len(po), "duplicates": 0, "missing": 0, "invalid": 0, "is_cleaned": False}]}


def test_followers_analysis_and_dashboard():
    ctx = ae.analyze(demo_frames())
    fs = ctx["fstats"]
    assert fs["mutual"] + fs["fans"] == fs["followers"]
    assert fs["mutual"] + fs["not_following_back"] == fs["following"]
    assert ctx["caps"]["growth"] and ctx["kpis"][2]["value"] == "96"
    assert ctx["charts"]["heatmap"]["max"] > 0


def test_empty_dataset_makes_no_claims():
    ctx = ae.analyze({"followers": None, "following": None, "posts": None})
    assert ctx["kpis"][0]["value"] is None
    assert ctx["insights"][0]["title"] == "No data yet"


def test_missing_likes_not_faked():
    fr = demo_frames(); fr["posts"]["likes"] = pd.NA; fr["posts"]["comments"] = pd.NA
    ctx = ae.analyze(fr)
    assert ctx["kpis"][3]["value"] is None and ctx["kpis"][5]["value"] is None
    assert "empty" in ctx["charts"]["post_engagement"]


def test_single_snapshot_has_no_unfollow_claims():
    fr = demo_frames(); fr["followers"] = ae.latest(fr["followers"])
    assert ae.people_view(fr["followers"], fr["following"], "followers", "lost")["reason"]


def test_ml_modules():
    p = ae.analyze(demo_frames())["all_posts"]
    assert ml.kmeans_clusters(p)["available"] and ml.anomalies(p)["available"]
    assert not ml.kmeans_clusters(p.head(5))["available"]
    assert not ml.forecast(p.head(5))["available"]


def test_reports_generate(tmp_path):
    ctx = ae.analyze(demo_frames())
    x = generate_excel(ctx, str(tmp_path / "r.xlsx"), "demo")
    assert {"Overview", "Followers", "Following", "Mutual Connections", "Posts", "Insights"} <= set(pd.ExcelFile(x).sheet_names)
    pdf = generate_pdf(ctx, str(tmp_path / "r.pdf"), "demo")
    assert open(pdf, "rb").read(4) == b"%PDF"
    only_posts = ae.analyze({"followers": None, "following": None, "posts": demo_frames()["posts"]})
    names = pd.ExcelFile(generate_excel(only_posts, str(tmp_path / "p.xlsx"))).sheet_names
    assert "Followers" not in names and "Posts" in names
