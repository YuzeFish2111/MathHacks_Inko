import uuid

from fastapi.testclient import TestClient
from PIL import Image

from server.auth import hash_password, verify_password
from server.errors import MESSAGES
from server.main import app

from .helpers import encode, handwriting, page_on_table


def new_client():
    return TestClient(app)


def sign_up(client, username=None, password="secret123", name="Ada Lovelace"):
    username = username or f"user_{uuid.uuid4().hex[:8]}"
    res = client.post("/api/auth/signup", json={"name": name, "username": username, "password": password})
    assert res.status_code == 200, res.text
    return username


def analyze(client, img=None):
    data = encode(img if img is not None else handwriting(), "JPEG")
    return client.post("/analyze", files={"file": ("a.jpg", data, "image/jpeg")})


def test_password_hashing():
    stored = hash_password("hunter22")
    assert stored.startswith("scrypt$") and "hunter22" not in stored
    assert verify_password("hunter22", stored)
    assert not verify_password("hunter23", stored)
    assert hash_password("hunter22") != stored  # salted


def test_sign_up_sign_in_sign_out():
    client = new_client()
    assert client.get("/api/me").json() == {"user": None}
    username = sign_up(client)
    me = client.get("/api/me").json()["user"]
    assert me["username"] == username and me["name"] == "Ada Lovelace"
    assert "password" not in str(me)

    cookie = client.cookies.get("inko_session")
    assert cookie
    client.post("/api/auth/signout")
    assert client.get("/api/me").json() == {"user": None}

    other = new_client()
    res = other.post("/api/auth/signin", json={"username": username.upper(), "password": "secret123"})
    assert res.status_code == 200, "usernames are case-insensitive"
    assert other.get("/api/me").json()["user"]["username"] == username


def test_wrong_password_and_taken_username():
    client = new_client()
    username = sign_up(client)
    res = new_client().post("/api/auth/signin", json={"username": username, "password": "nope-nope"})
    assert res.status_code == 401
    assert res.json()["error"]["message"] == MESSAGES["bad_credentials"]
    res = new_client().post("/api/auth/signin", json={"username": "nobody_here", "password": "whatever1"})
    assert res.status_code == 401
    res = new_client().post("/api/auth/signup", json={"name": "B", "username": username, "password": "secret123"})
    assert res.status_code == 409


def test_sign_up_validation():
    client = new_client()
    for body in ({"name": "", "username": "okname", "password": "secret123"},
                 {"name": "A", "username": "x", "password": "secret123"},
                 {"name": "A", "username": "has space", "password": "secret123"},
                 {"name": "A", "username": "okname2", "password": "123"},
                 {"name": "A"}):
        res = client.post("/api/auth/signup", json=body)
        assert res.status_code == 400, body


def test_signed_in_results_are_saved_and_listed():
    client = new_client()
    sign_up(client)
    first = analyze(client).json()
    assert first["saved"] is True
    second = analyze(client).json()
    items = client.get("/api/history").json()["items"]
    assert [i["id"] for i in items] == [first["result_id"], second["result_id"]]   # oldest first
    full = client.get(f"/api/history/{first['result_id']}").json()
    assert full["overall_score"] == first["overall_score"]
    assert client.get(full["analysis"]["rectifiedImage"]).headers["content-type"] == "image/jpeg"
    assert client.get(items[0]["thumb_url"]).status_code == 200
    assert client.delete("/api/history").json()["deleted"] == 2
    assert client.get("/api/history").json()["items"] == []


def test_guest_result_can_be_saved_after_signing_in():
    client = new_client()
    guest = analyze(client).json()
    assert guest["saved"] is False
    assert client.get("/api/history").status_code == 401
    sign_up(client)
    assert client.post("/api/history/save", json={"result_id": guest["result_id"]}).json() == {"saved": True}
    assert [i["id"] for i in client.get("/api/history").json()["items"]] == [guest["result_id"]]


def test_tilted_result_is_not_saved_until_confirmed():
    client = new_client()
    sign_up(client)
    tilted = analyze(client, page_on_table(True)).json()
    assert tilted["photo_check"]["tilted"] and tilted["saved"] is False
    assert client.get("/api/history").json()["items"] == []
    client.post("/api/history/save", json={"result_id": tilted["result_id"]})
    assert len(client.get("/api/history").json()["items"]) == 1


def test_history_is_private():
    alice, bob = new_client(), new_client()
    sign_up(alice)
    sign_up(bob)
    rid = analyze(alice).json()["result_id"]
    assert bob.get(f"/api/history/{rid}").status_code == 404
    assert bob.get(f"/api/history/{rid}/image.jpg").status_code == 404
    assert bob.get("/api/history").json()["items"] == []
    assert bob.delete("/api/history").json()["deleted"] == 0            # bob's "delete all" can't reach alice's
    assert [i["id"] for i in alice.get("/api/history").json()["items"]] == [rid]


def test_avatar_upload_accepts_heic():
    client = new_client()
    sign_up(client)
    img = Image.new("RGB", (800, 600), (200, 120, 90))
    import io
    buf = io.BytesIO()
    img.save(buf, "HEIF")
    res = client.post("/api/me/avatar", files={"file": ("me.HEIC", buf.getvalue(), "image/heic")})
    assert res.status_code == 200, res.text
    url = res.json()["user"]["avatar_url"]
    pic = client.get(url)
    assert pic.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(pic.content)).size == (256, 256)
