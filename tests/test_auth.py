from models import User


def register(client, username="alice", email="alice@example.com", password="secret123"):
    return client.post("/register", data={"username": username, "email": email,
                                          "password": password, "confirm_password": password})


def login(client, identity="alice", password="secret123"):
    return client.post("/login", data={"identity": identity, "password": password})


def test_register_creates_hashed_user(client):
    r = register(client)
    assert r.status_code == 302
    user = User.query.filter_by(username="alice").first()
    assert user is not None
    assert user.password_hash != "secret123"
    assert user.check_password("secret123")


def test_register_rejects_weak_password_and_duplicates(client):
    assert register(client, password="short").status_code == 400
    register(client)
    assert register(client).status_code == 400


def test_login_logout_flow(client):
    register(client)
    assert login(client, password="wrong").status_code == 401
    assert login(client).status_code == 302
    assert client.get("/dashboard").status_code == 200
    client.post("/logout")
    assert client.get("/dashboard").status_code == 302


def test_dashboard_requires_login(client):
    r = client.get("/dashboard")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_open_redirect_blocked(client):
    register(client)
    r = client.post("/login?next=https://evil.example", data={"identity": "alice", "password": "secret123"})
    assert r.headers["Location"].endswith("/dashboard")


def test_profile_and_password_change(client):
    register(client)
    login(client)
    client.post("/profile", data={"full_name": "Alice A", "instagram_handle": "@alice_ig"})
    user = User.query.filter_by(username="alice").first()
    assert user.instagram_handle == "alice_ig"
    r = client.post("/settings", data={"current_password": "secret123",
                                       "new_password": "newpass456", "confirm_password": "newpass456"})
    assert r.status_code == 302
    assert User.query.filter_by(username="alice").first().check_password("newpass456")
