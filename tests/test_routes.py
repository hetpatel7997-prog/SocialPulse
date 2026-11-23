"""End-to-end tests through the Flask app (uses in-memory SQLite)."""
import io
import os
from models import User, UploadedFile, Follower, Report

SAMPLES = os.path.join(os.path.dirname(__file__), "sample_data")


def make_user(client, name="alice"):
    client.post("/register", data={"username": name, "email": f"{name}@example.com", "password": "secret123", "confirm_password": "secret123"})
    client.post("/login", data={"identity": name, "password": "secret123"})


def upload(client, filename, kind="auto", date="2026-01-01"):
    with open(os.path.join(SAMPLES, filename), "rb") as fh:
        return client.post("/upload/file", data={"file": (io.BytesIO(fh.read()), filename), "kind": kind, "snapshot_date": date},
                           content_type="multipart/form-data")


def test_all_pages_require_login(client):
    for path in ["/dashboard", "/upload", "/history", "/followers", "/following", "/content", "/cleaning",
                 "/insights", "/machine-learning", "/reports", "/profile", "/settings"]:
        assert client.get(path).status_code == 302, path


def test_pages_render_empty_for_new_user(client):
    make_user(client)
    for path in ["/dashboard", "/upload", "/history", "/followers", "/following", "/content", "/cleaning",
                 "/insights", "/machine-learning", "/reports", "/profile", "/settings"]:
        assert client.get(path).status_code == 200, path


def test_upload_json_summary_and_duplicates(client):
    make_user(client)
    r = upload(client, "followers_1.json")
    body = r.get_json()
    assert r.status_code == 200 and body["ok"]
    assert body["totals"]["records"] == 30 and body["totals"]["duplicates"] == 1
    again = upload(client, "followers_1.json")           # identical file
    assert again.status_code == 409


def test_upload_all_formats_and_analytics_pages(client):
    make_user(client)
    for f, k in [("followers_1.json", "auto"), ("following.json", "auto"), ("posts_with_engagement.csv", "auto"),
                 ("posts_with_engagement.xlsx", "auto"), ("followers_1.html", "followers"), ("posts_1.json", "auto")]:
        assert upload(client, f, k, date="2026-02-01" if f.endswith("html") else "2026-01-01").status_code in (200, 409), f
    for path in ["/dashboard", "/followers?view=mutual", "/following?view=not_back", "/content", "/cleaning", "/insights", "/machine-learning"]:
        assert client.get(path).status_code == 200, path


def test_invalid_uploads_rejected(client):
    make_user(client)
    bad = client.post("/upload/file", data={"file": (io.BytesIO(b"hello"), "x.exe")}, content_type="multipart/form-data")
    assert bad.status_code == 400
    empty = client.post("/upload/file", data={"file": (io.BytesIO(b""), "x.json")}, content_type="multipart/form-data")
    assert empty.status_code == 400
    broken = client.post("/upload/file", data={"file": (io.BytesIO(b"{oops"), "x.json")}, content_type="multipart/form-data")
    assert broken.status_code == 422 and not broken.get_json()["ok"]


def test_users_cannot_see_or_delete_each_others_data(app):
    a, b = app.test_client(), app.test_client()
    make_user(a, "alice"); make_user(b, "bob")
    upload(a, "followers_1.json")
    fid = UploadedFile.query.filter_by(user_id=User.query.filter_by(username="alice").first().id).first().id
    assert b.post(f"/history/{fid}/delete").status_code == 404
    assert b"sample_user_1" not in b.get("/followers").data


def test_delete_upload_removes_records(client):
    make_user(client)
    upload(client, "followers_1.json")
    fid = UploadedFile.query.first().id
    assert Follower.query.count() > 0
    client.post(f"/history/{fid}/delete")
    assert Follower.query.count() == 0 and UploadedFile.query.count() == 0


def test_cleaning_creates_separate_cleaned_dataset(client):
    from models import Dataset
    make_user(client)
    upload(client, "posts_with_engagement.csv")
    raw = Dataset.query.filter_by(is_cleaned=False).first()
    client.post(f"/cleaning/{raw.id}/save")
    assert Dataset.query.filter_by(is_cleaned=True, source_dataset_id=raw.id).count() == 1
    assert Dataset.query.filter_by(is_cleaned=False).count() == 1       # raw still there
    client.post(f"/cleaning/{raw.id}/revert")
    assert Dataset.query.filter_by(is_cleaned=True).count() == 0


def test_demo_mode_and_reports(client, app):
    make_user(client)
    client.post("/upload/demo")
    assert b"Demo mode" in client.get("/dashboard").data
    for kind in ("pdf", "xlsx"):
        client.post("/reports/generate", data={"type": kind})
    reps = Report.query.all()
    assert len(reps) == 2
    for r in reps:
        resp = client.get(f"/reports/{r.id}/download")
        assert resp.status_code == 200 and len(resp.data) > 500


def test_report_without_data_refused(client):
    make_user(client)
    client.post("/reports/generate", data={"type": "pdf"})
    assert Report.query.count() == 0


def test_delete_all_data_needs_password(client):
    make_user(client)
    client.post("/upload/demo")
    client.post("/settings/delete-data", data={"password": "wrong"})
    assert UploadedFile.query.count() == 1
    client.post("/settings/delete-data", data={"password": "secret123"})
    assert UploadedFile.query.count() == 0
