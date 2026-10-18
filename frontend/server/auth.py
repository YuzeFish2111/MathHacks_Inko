"""Username and password accounts. Passwords are salted and hashed with scrypt;
sessions are random tokens in an HttpOnly cookie (only their hash is stored)."""
import base64
import hashlib
import hmac
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, File, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from . import db, imaging
from .errors import InkoError

router = APIRouter(prefix="/api")

COOKIE = "inko_session"
SESSION_DAYS = 30
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, dklen=32, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode("utf-8"), salt=base64.b64decode(salt),
                                n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Checked when a username does not exist, so a wrong username takes as long as a wrong password.
_DUMMY_HASH = hash_password("not-a-real-password")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def user_json(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "username": row["username"],
        "avatar_url": f"/api/me/avatar?v={row['avatar_version']}" if row["avatar_version"] else None,
    }


def current_user(request: Request):
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    with db.connect() as conn:
        row = conn.execute(
            "SELECT u.*, s.expires_at FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?",
            (_token_hash(token),),
        ).fetchone()
    if not row or row["expires_at"] < _now().isoformat():
        return None
    return row


def require_user(request: Request):
    user = current_user(request)
    if not user:
        raise InkoError("not_signed_in")
    return user


def _start_session(request: Request, response: Response, user_id: int) -> None:
    token = secrets.token_urlsafe(32)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (_token_hash(token), user_id, _now().isoformat(), (_now() + timedelta(days=SESSION_DAYS)).isoformat()),
        )
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax", secure=secure, path="/")


class SignUpBody(BaseModel):
    name: str
    username: str
    password: str


class SignInBody(BaseModel):
    username: str
    password: str


@router.post("/auth/signup")
def sign_up(body: SignUpBody, request: Request, response: Response):
    name, username = body.name.strip(), body.username.strip()
    if not 1 <= len(name) <= 60:
        raise InkoError("invalid_input", "Please enter your name.")
    if not USERNAME_RE.match(username):
        raise InkoError("invalid_input", "Usernames need 3 to 30 letters, numbers, dots, dashes, or underscores.")
    if not 6 <= len(body.password) <= 200:
        raise InkoError("invalid_input", "Passwords need at least 6 characters.")
    try:
        with db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO users (name, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (name, username, hash_password(body.password), _now().isoformat()),
            )
            user_id = cur.lastrowid
    except sqlite3.IntegrityError:
        raise InkoError("username_taken")
    _start_session(request, response, user_id)
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return {"user": user_json(row)}


@router.post("/auth/signin")
def sign_in(body: SignInBody, request: Request, response: Response):
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (body.username.strip(),)).fetchone()
    if not verify_password(body.password, row["password_hash"] if row else _DUMMY_HASH) or not row:
        raise InkoError("bad_credentials")
    _start_session(request, response, row["id"])
    return {"user": user_json(row)}


@router.post("/auth/signout")
def sign_out(request: Request, response: Response):
    token = request.cookies.get(COOKIE)
    if token:
        with db.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    user = current_user(request)
    return {"user": user_json(user) if user else None}


@router.post("/me/avatar")
async def upload_avatar(request: Request, file: UploadFile = File(...)):
    user = require_user(request)
    jpeg = await run_in_threadpool(imaging.avatar_jpeg, await file.read())
    with db.connect() as conn:
        conn.execute("UPDATE users SET avatar = ?, avatar_version = avatar_version + 1 WHERE id = ?", (jpeg, user["id"]))
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    return {"user": user_json(row)}


@router.get("/me/avatar")
def get_avatar(request: Request):
    user = require_user(request)
    with db.connect() as conn:
        row = conn.execute("SELECT avatar FROM users WHERE id = ?", (user["id"],)).fetchone()
    if not row or not row["avatar"]:
        raise InkoError("not_found")
    return Response(row["avatar"], media_type="image/jpeg", headers={"Cache-Control": "private, max-age=31536000"})
