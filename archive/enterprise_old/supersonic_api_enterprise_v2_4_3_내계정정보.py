from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import sys
import threading
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "supersonic_enterprise_config_v1.json"
DB_PATH = BASE_DIR / "supersonic_enterprise_v1.db"
SECRET_PATH = BASE_DIR / ".supersonic_api_secret"
COOKIE_NAME = "ss_session"
PBKDF2_ITERATIONS = 260_000
ENTERPRISE_HTML_PATH = BASE_DIR / "supersonic_enterprise_dashboard_v2_4_1_내계정정보.html"
ADMIN_HTML_PATH = BASE_DIR / "supersonic_enterprise_admin_v2_HQ권한.html"

ROLE_SUPER_ADMIN = "SUPER_ADMIN"
ROLE_HQ_ADMIN = "HQ_ADMIN"
ROLE_BRANCH_ADMIN = "BRANCH_ADMIN"
ROLE_VIEWER = "VIEWER"
VALID_ROLES = {ROLE_SUPER_ADMIN, ROLE_HQ_ADMIN, ROLE_BRANCH_ADMIN, ROLE_VIEWER}

PERMISSION_FIELDS = (
    "can_view",
    "can_view_weekly",
    "can_view_settlement",
    "can_view_personal",
    "can_manage_riders",
    "can_send_sms",
)

_FIREBASE_READY = False
_FIREBASE_LOCK = threading.Lock()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(dt: datetime | None = None) -> str:
    return (dt or now_utc()).isoformat(timespec="seconds")


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"설정 파일이 없습니다: {CONFIG_PATH.name}")
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


CONFIG = load_config()
SERVICE = CONFIG.get("service", {})
CENTERS: dict[str, dict[str, Any]] = CONFIG.get("centers", {})


def ensure_secret() -> bytes:
    env_secret = os.getenv("SUPERSONIC_AUTH_SECRET", "").strip()
    if env_secret:
        return env_secret.encode("utf-8")
    if SECRET_PATH.exists():
        return SECRET_PATH.read_bytes().strip()
    raw = base64.urlsafe_b64encode(secrets.token_bytes(48))
    SECRET_PATH.write_bytes(raw)
    try:
        os.chmod(SECRET_PATH, 0o600)
    except OSError:
        pass
    return raw


AUTH_SECRET = ensure_secret()


def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with db_connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tenants (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            );

            CREATE TABLE IF NOT EXISTS center_permissions (
                user_id TEXT NOT NULL,
                center_slug TEXT NOT NULL,
                can_view INTEGER NOT NULL DEFAULT 1,
                can_view_weekly INTEGER NOT NULL DEFAULT 1,
                can_view_settlement INTEGER NOT NULL DEFAULT 0,
                can_view_personal INTEGER NOT NULL DEFAULT 0,
                can_manage_riders INTEGER NOT NULL DEFAULT 0,
                can_send_sms INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, center_slug),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                user_id TEXT,
                tenant_id TEXT,
                username TEXT,
                action TEXT NOT NULL,
                center_slug TEXT,
                ip TEXT,
                detail TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at);
            CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id);
            CREATE INDEX IF NOT EXISTS idx_session_user ON sessions(user_id);
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO tenants(id,name,active,created_at) VALUES(?,?,1,?)",
            ("internal", "SUPERSONIC Internal", iso_utc()),
        )
        conn.commit()


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return base64.b64encode(salt).decode(), base64.b64encode(digest).decode()


def verify_password(password: str, salt_b64: str, expected_b64: str) -> bool:
    try:
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(expected_b64)
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return hmac.compare_digest(actual, expected)


def token_hash(token: str) -> str:
    return hmac.new(AUTH_SECRET, token.encode("utf-8"), hashlib.sha256).hexdigest()


def create_admin(username: str, tenant_id: str = "internal") -> None:
    init_db()
    username = username.strip()
    if not username:
        raise ValueError("사용자명이 비어 있습니다.")
    password = getpass.getpass("새 관리자 비밀번호: ")
    confirm = getpass.getpass("비밀번호 확인: ")
    if password != confirm:
        raise ValueError("비밀번호가 일치하지 않습니다.")
    if len(password) < 10:
        raise ValueError("비밀번호는 10자 이상으로 설정하세요.")
    salt_b64, hash_b64 = hash_password(password)
    user_id = "usr_" + secrets.token_hex(8)
    with db_connect() as conn:
        tenant = conn.execute("SELECT id FROM tenants WHERE id=?", (tenant_id,)).fetchone()
        if not tenant:
            conn.execute(
                "INSERT INTO tenants(id,name,active,created_at) VALUES(?,?,1,?)",
                (tenant_id, tenant_id, iso_utc()),
            )
        conn.execute(
            "INSERT INTO users(id,tenant_id,username,password_salt,password_hash,role,active,created_at) "
            "VALUES(?,?,?,?,?,?,1,?)",
            (user_id, tenant_id, username, salt_b64, hash_b64, ROLE_SUPER_ADMIN, iso_utc()),
        )
        for slug in CENTERS:
            conn.execute(
                "INSERT OR REPLACE INTO center_permissions("
                "user_id,center_slug,can_view,can_view_weekly,can_view_settlement,can_view_personal,can_manage_riders,can_send_sms"
                ") VALUES(?,?,1,1,1,1,1,1)",
                (user_id, slug),
            )
        conn.commit()
    print(f"관리자 생성 완료: {username} / 권한: {ROLE_SUPER_ADMIN} / DP {len(CENTERS)}개")



def create_user(
    username: str,
    tenant_id: str,
    role: str,
    center_slugs: list[str],
    feature_names: set[str],
) -> None:
    init_db()
    username = username.strip()
    role = role.strip().upper()
    if not username:
        raise ValueError("사용자명이 비어 있습니다.")
    if role not in VALID_ROLES:
        raise ValueError(f"지원하지 않는 역할입니다: {role}")
    bad_centers = [x for x in center_slugs if x not in CENTERS]
    if bad_centers:
        raise ValueError("존재하지 않는 센터: " + ", ".join(bad_centers))
    password = getpass.getpass("새 사용자 비밀번호: ")
    confirm = getpass.getpass("비밀번호 확인: ")
    if password != confirm:
        raise ValueError("비밀번호가 일치하지 않습니다.")
    if len(password) < 10:
        raise ValueError("비밀번호는 10자 이상으로 설정하세요.")

    feature_map = {
        "view": "can_view",
        "weekly": "can_view_weekly",
        "settlement": "can_view_settlement",
        "personal": "can_view_personal",
        "manage": "can_manage_riders",
        "sms": "can_send_sms",
    }
    unknown = feature_names - set(feature_map)
    if unknown:
        raise ValueError("지원하지 않는 기능: " + ", ".join(sorted(unknown)))
    if "view" not in feature_names:
        feature_names.add("view")

    salt_b64, hash_b64 = hash_password(password)
    user_id = "usr_" + secrets.token_hex(8)
    with db_connect() as conn:
        tenant = conn.execute("SELECT id FROM tenants WHERE id=?", (tenant_id,)).fetchone()
        if not tenant:
            conn.execute(
                "INSERT INTO tenants(id,name,active,created_at) VALUES(?,?,1,?)",
                (tenant_id, tenant_id, iso_utc()),
            )
        conn.execute(
            "INSERT INTO users(id,tenant_id,username,password_salt,password_hash,role,active,created_at) "
            "VALUES(?,?,?,?,?,?,1,?)",
            (user_id, tenant_id, username, salt_b64, hash_b64, role, iso_utc()),
        )
        for slug in center_slugs:
            values = {field: 0 for field in PERMISSION_FIELDS}
            for feature in feature_names:
                values[feature_map[feature]] = 1
            conn.execute(
                "INSERT INTO center_permissions("
                "user_id,center_slug,can_view,can_view_weekly,can_view_settlement,can_view_personal,can_manage_riders,can_send_sms"
                ") VALUES(?,?,?,?,?,?,?,?)",
                (
                    user_id, slug, values["can_view"], values["can_view_weekly"],
                    values["can_view_settlement"], values["can_view_personal"],
                    values["can_manage_riders"], values["can_send_sms"],
                ),
            )
        conn.commit()
    print(f"사용자 생성 완료: {username} / {role} / DP {len(center_slugs)}개 / 기능 {','.join(sorted(feature_names))}")



def reset_user_password(username: str) -> None:
    init_db()
    username = username.strip()
    if not username:
        raise ValueError("사용자명이 비어 있습니다.")

    with db_connect() as conn:
        user = conn.execute(
            "SELECT id,username,role,active FROM users WHERE username=? COLLATE NOCASE",
            (username,),
        ).fetchone()
    if not user:
        raise ValueError(f"존재하지 않는 사용자입니다: {username}")

    password = getpass.getpass("새 비밀번호: ")
    confirm = getpass.getpass("비밀번호 확인: ")
    if password != confirm:
        raise ValueError("비밀번호가 일치하지 않습니다.")
    if len(password) < 10:
        raise ValueError("비밀번호는 10자 이상으로 설정하세요.")

    salt_b64, hash_b64 = hash_password(password)
    with db_connect() as conn:
        conn.execute(
            "UPDATE users SET password_salt=?,password_hash=? WHERE id=?",
            (salt_b64, hash_b64, user["id"]),
        )
        # 기존 세션도 제거해서 새 비밀번호 기준으로 다시 로그인하게 함
        conn.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
        conn.commit()

    print(f"비밀번호 재설정 완료: {user['username']} / {user['role']} / {'사용' if user['active'] else '중지'}")


def list_users() -> None:
    init_db()
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT u.id,u.username,u.tenant_id,u.role,u.active,COUNT(p.center_slug) AS center_count "
            "FROM users u LEFT JOIN center_permissions p ON p.user_id=u.id "
            "GROUP BY u.id ORDER BY u.created_at"
        ).fetchall()
    if not rows:
        print("등록 사용자 없음")
        return
    for r in rows:
        state = "사용" if r["active"] else "중지"
        print(f"{r['username']} · {r['role']} · tenant={r['tenant_id']} · DP={r['center_count']} · {state}")


def ensure_firebase() -> None:
    global _FIREBASE_READY
    if _FIREBASE_READY:
        return
    with _FIREBASE_LOCK:
        if not _FIREBASE_READY:
            from firebase_uploader import init_firebase
            init_firebase()
            _FIREBASE_READY = True


def firebase_get(path: str) -> Any:
    ensure_firebase()
    from firebase_admin import db
    return db.reference(path).get()


def firebase_update(path: str, changes: dict[str, Any]) -> None:
    ensure_firebase()
    from firebase_admin import db
    db.reference(path).update(changes)


def parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone(timedelta(hours=9)))
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def data_age_seconds(data: dict[str, Any]) -> int | None:
    candidates = (
        data.get("uploadedAt"),
        data.get("collectedAt"),
        data.get("updatedAt"),
        data.get("generatedAt"),
    )
    for value in candidates:
        dt = parse_timestamp(value)
        if dt:
            return max(0, int((now_utc() - dt).total_seconds()))
    return None


def safe_live_data(data: Any, permission: dict[str, Any]) -> Any:
    if not isinstance(data, dict):
        return data
    if permission.get("can_view_personal"):
        return data
    clean = dict(data)
    riders = []
    for rider in data.get("riders") or []:
        if not isinstance(rider, dict):
            continue
        r = dict(rider)
        r.pop("phone", None)
        r.pop("userId", None)
        r.pop("riderKey", None)
        riders.append(r)
    clean["riders"] = riders
    return clean


def audit(
    action: str,
    user: sqlite3.Row | dict[str, Any] | None = None,
    center_slug: str | None = None,
    ip: str = "",
    detail: dict[str, Any] | str | None = None,
    dedupe_seconds: int = 0,
) -> None:
    user_id = user["id"] if user else None
    tenant_id = user["tenant_id"] if user else None
    username = user["username"] if user else None
    detail_text = detail if isinstance(detail, str) else json.dumps(detail or {}, ensure_ascii=False, separators=(",", ":"))
    with db_connect() as conn:
        if dedupe_seconds and user_id:
            cutoff = iso_utc(now_utc() - timedelta(seconds=dedupe_seconds))
            exists = conn.execute(
                "SELECT 1 FROM audit_logs WHERE user_id=? AND action=? AND COALESCE(center_slug,'')=COALESCE(?, '') "
                "AND created_at>=? LIMIT 1",
                (user_id, action, center_slug, cutoff),
            ).fetchone()
            if exists:
                return
        conn.execute(
            "INSERT INTO audit_logs(created_at,user_id,tenant_id,username,action,center_slug,ip,detail) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (iso_utc(), user_id, tenant_id, username, action, center_slug, ip, detail_text),
        )
        conn.commit()


def load_user_by_session(token: str) -> sqlite3.Row | None:
    if not token:
        return None
    th = token_hash(token)
    now = iso_utc()
    with db_connect() as conn:
        row = conn.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id "
            "WHERE s.token_hash=? AND s.expires_at>? AND u.active=1",
            (th, now),
        ).fetchone()
        if row:
            conn.execute("UPDATE sessions SET last_seen_at=? WHERE token_hash=?", (now, th))
            conn.commit()
        return row


def permission_for(user: sqlite3.Row, center_slug: str) -> dict[str, int] | None:
    if center_slug not in CENTERS:
        return None
    with db_connect() as conn:
        row = conn.execute(
            "SELECT * FROM center_permissions WHERE user_id=? AND center_slug=?",
            (user["id"], center_slug),
        ).fetchone()
    if not row:
        return None
    return {k: int(row[k]) for k in PERMISSION_FIELDS}


def list_permissions(user: sqlite3.Row) -> dict[str, dict[str, int]]:
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT * FROM center_permissions WHERE user_id=?",
            (user["id"],),
        ).fetchall()
    out: dict[str, dict[str, int]] = {}
    for row in rows:
        out[row["center_slug"]] = {k: int(row[k]) for k in PERMISSION_FIELDS}
    return out


def client_ip(handler: BaseHTTPRequestHandler) -> str:
    forwarded = handler.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    return forwarded or (handler.client_address[0] if handler.client_address else "")


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "SUPERSONIC-API/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        # 운영 콘솔은 필수 오류만 남기기 위해 기본 HTTP access log를 숨깁니다.
        return

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin", "").strip()
        if not origin:
            return True
        return origin in set(SERVICE.get("allowed_origins") or [])

    def _common_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        origin = self.headers.get("Origin", "").strip()
        if origin and self._origin_allowed():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.send_header("Vary", "Origin")

    def _client_disconnected(self, exc: BaseException) -> bool:
        if isinstance(exc, (BrokenPipeError, ConnectionAbortedError, ConnectionResetError)):
            return True
        if isinstance(exc, OSError) and getattr(exc, "winerror", None) in {10038, 10053, 10054}:
            return True
        return False

    def _json(self, status: int, payload: Any, extra_headers: dict[str, str] | None = None) -> bool:
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self._common_headers()
            for key, value in (extra_headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(raw)
            return True
        except BaseException as exc:
            if self._client_disconnected(exc):
                # 브라우저 새로고침/탭 이동/요청 취소는 정상적인 클라이언트 종료입니다.
                # Firebase/API 장애로 기록하지 않고 조용히 종료합니다.
                try:
                    self._headers_buffer = []
                except Exception:
                    pass
                return False
            raise

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        if length > 1_000_000:
            raise ValueError("요청이 너무 큽니다.")
        raw = self.rfile.read(length)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON object가 필요합니다.")
        return data

    def _session_token(self) -> str:
        auth = self.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        morsel = cookie.get(COOKIE_NAME)
        return morsel.value if morsel else ""

    def _user(self) -> sqlite3.Row | None:
        return load_user_by_session(self._session_token())

    def _require_user(self) -> sqlite3.Row | None:
        user = self._user()
        if not user:
            self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "LOGIN_REQUIRED"})
            return None
        return user

    def _require_super_admin(self) -> sqlite3.Row | None:
        user = self._require_user()
        if not user:
            return None
        if user["role"] != ROLE_SUPER_ADMIN:
            self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "SUPER_ADMIN_REQUIRED"})
            return None
        return user

    def _require_admin_manager(self) -> sqlite3.Row | None:
        user = self._require_user()
        if not user:
            return None
        if user["role"] not in {ROLE_SUPER_ADMIN, ROLE_HQ_ADMIN}:
            self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "ADMIN_MANAGER_REQUIRED"})
            return None
        return user

    def _hq_scope(self, user: sqlite3.Row) -> dict[str, dict[str, int]]:
        if user["role"] != ROLE_HQ_ADMIN:
            return {}
        return list_permissions(user)

    def _validate_hq_grant(
        self,
        admin_user: sqlite3.Row,
        tenant_id: str,
        role: str,
        center_slugs: list[str],
        feature_names: set[str],
    ) -> str | None:
        if admin_user["role"] != ROLE_HQ_ADMIN:
            return None
        if tenant_id != admin_user["tenant_id"]:
            return "TENANT_SCOPE_DENIED"
        if role not in {ROLE_BRANCH_ADMIN, ROLE_VIEWER}:
            return "ROLE_SCOPE_DENIED"

        hq_perms = self._hq_scope(admin_user)
        feature_to_field = {
            "view": "can_view",
            "weekly": "can_view_weekly",
            "settlement": "can_view_settlement",
            "personal": "can_view_personal",
            "manage": "can_manage_riders",
            "sms": "can_send_sms",
        }
        for slug in center_slugs:
            p = hq_perms.get(slug)
            if not p or not p.get("can_view"):
                return "CENTER_SCOPE_DENIED"
            for feature in feature_names:
                field = feature_to_field.get(feature)
                if field and not p.get(field):
                    return "FEATURE_SCOPE_DENIED"
        return None

    def _center_permission(self, user: sqlite3.Row, slug: str, field: str) -> dict[str, int] | None:
        permission = permission_for(user, slug)
        if not permission or not permission.get(field):
            self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "CENTER_PERMISSION_DENIED"})
            return None
        return permission

    def do_OPTIONS(self) -> None:
        if not self._origin_allowed():
            self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "ORIGIN_DENIED"})
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,Authorization")
        self.send_header("Access-Control-Max-Age", "600")
        self._common_headers()
        self.end_headers()

    def do_GET(self) -> None:
        if not self._origin_allowed():
            self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "ORIGIN_DENIED"})
            return
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)

        if path in {"/", "/enterprise", "/enterprise.html"}:
            if not ENTERPRISE_HTML_PATH.exists():
                self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "ENTERPRISE_HTML_NOT_FOUND"})
                return
            raw = ENTERPRISE_HTML_PATH.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self._common_headers()
            try:
                self.end_headers()
                self.wfile.write(raw)
            except BaseException as exc:
                if not self._client_disconnected(exc):
                    raise
            return

        if path == "/api/health":
            self._json(HTTPStatus.OK, {"ok": True, "service": "SUPERSONIC Enterprise API", "version": "v2.4.3"})
            return

        if path in {"/admin", "/admin.html"}:
            admin_user = self._require_admin_manager()
            if not admin_user:
                return
            if not ADMIN_HTML_PATH.exists():
                self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "ADMIN_HTML_NOT_FOUND"})
                return
            raw = ADMIN_HTML_PATH.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self._common_headers()
            try:
                self.end_headers()
                self.wfile.write(raw)
            except BaseException as exc:
                if not self._client_disconnected(exc):
                    raise
            return

        user = self._require_user()
        if not user:
            return

        if path == "/api/me":
            perms = list_permissions(user)
            self._json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "user": {
                        "id": user["id"],
                        "username": user["username"],
                        "tenantId": user["tenant_id"],
                        "role": user["role"],
                    },
                    "permissions": perms,
                },
            )
            return

        if path == "/api/account/me":
            perms = list_permissions(user)
            visible = []
            for slug, p in perms.items():
                if not p.get("can_view"):
                    continue
                center = CENTERS.get(slug, {})
                visible.append({
                    "slug": slug,
                    "name": center.get("name") or slug,
                    "dpCode": center.get("dp_code") or "",
                    "permissions": p,
                })
            self._json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "account": {
                        "id": user["id"],
                        "username": user["username"],
                        "tenantId": user["tenant_id"],
                        "role": user["role"],
                        "active": int(user["active"]),
                        "createdAt": user["created_at"],
                        "centers": visible,
                    },
                },
            )
            return

        if path == "/api/centers":
            perms = list_permissions(user)
            centers = []
            for slug, center in CENTERS.items():
                p = perms.get(slug)
                if not p or not p.get("can_view"):
                    continue
                centers.append(
                    {
                        "slug": slug,
                        "name": center.get("name"),
                        "dpCode": center.get("dp_code"),
                        "teams": center.get("teams", []),
                        "settlementUnit": center.get("settlement_unit", 0),
                        "permissions": p,
                    }
                )
            self._json(HTTPStatus.OK, {"ok": True, "centers": centers})
            return

        if path in {"/api/live", "/api/weekly", "/api/system/status"}:
            slug = (query.get("center") or query.get("area") or [""])[0].strip()
            if slug not in CENTERS:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "INVALID_CENTER"})
                return
            permission_field = "can_view_weekly" if path == "/api/weekly" else "can_view"
            permission = self._center_permission(user, slug, permission_field)
            if not permission:
                return
            center = CENTERS[slug]
            try:
                if path == "/api/weekly":
                    data = firebase_get(center["weekly_path"]) or []
                    audit("WEEKLY_VIEW", user, slug, client_ip(self), dedupe_seconds=1800)
                    self._json(HTTPStatus.OK, {"ok": True, "center": slug, "data": data})
                    return

                data = firebase_get(center["live_path"]) or {}
                if path == "/api/system/status":
                    age = data_age_seconds(data) if isinstance(data, dict) else None
                    stale_after = int(SERVICE.get("stale_after_seconds", 240))
                    status = "UNKNOWN" if age is None else ("STALE" if age > stale_after else "OK")
                    self._json(
                        HTTPStatus.OK,
                        {
                            "ok": True,
                            "center": slug,
                            "status": status,
                            "dataAgeSeconds": age,
                            "staleAfterSeconds": stale_after,
                            "collectedAt": data.get("collectedAt") if isinstance(data, dict) else None,
                            "uploadedAt": data.get("uploadedAt") if isinstance(data, dict) else None,
                            "collectionDurationMs": data.get("collectionDurationMs") if isinstance(data, dict) else None,
                            "payloadBytes": data.get("payloadBytes") if isinstance(data, dict) else None,
                        },
                    )
                    return

                audit("LIVE_VIEW", user, slug, client_ip(self), dedupe_seconds=600)
                self._json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "center": slug,
                        "data": safe_live_data(data, permission),
                    },
                )
                return
            except Exception as exc:
                print(f"[API 오류] {path} / {slug}: {exc}")
                self._json(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": "DATA_SOURCE_ERROR"})
                return

        if path == "/api/admin/overview":
            if user["role"] not in {ROLE_SUPER_ADMIN, ROLE_HQ_ADMIN}:
                self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "ADMIN_MANAGER_REQUIRED"})
                return

            is_super = user["role"] == ROLE_SUPER_ADMIN
            with db_connect() as conn:
                if is_super:
                    tenant_rows = conn.execute(
                        "SELECT id,name,active,created_at FROM tenants ORDER BY created_at,id"
                    ).fetchall()
                    user_rows = conn.execute(
                        "SELECT id,tenant_id,username,role,active,created_at FROM users ORDER BY created_at,id"
                    ).fetchall()
                else:
                    tenant_rows = conn.execute(
                        "SELECT id,name,active,created_at FROM tenants WHERE id=?",
                        (user["tenant_id"],),
                    ).fetchall()
                    user_rows = conn.execute(
                        "SELECT id,tenant_id,username,role,active,created_at FROM users "
                        "WHERE tenant_id=? AND role IN (?,?) ORDER BY created_at,id",
                        (user["tenant_id"], ROLE_BRANCH_ADMIN, ROLE_VIEWER),
                    ).fetchall()

                user_ids = [r["id"] for r in user_rows]
                if user_ids:
                    marks = ",".join("?" for _ in user_ids)
                    perm_rows = conn.execute(
                        "SELECT user_id,center_slug,can_view,can_view_weekly,can_view_settlement,"
                        "can_view_personal,can_manage_riders,can_send_sms FROM center_permissions "
                        f"WHERE user_id IN ({marks}) ORDER BY user_id,center_slug",
                        user_ids,
                    ).fetchall()
                else:
                    perm_rows = []

            perms_by_user: dict[str, list[dict[str, Any]]] = {}
            for row in perm_rows:
                perms_by_user.setdefault(row["user_id"], []).append(dict(row))

            users = []
            for row in user_rows:
                item = dict(row)
                item["permissions"] = perms_by_user.get(row["id"], [])
                item["isCurrent"] = row["id"] == user["id"]
                if is_super:
                    item["manageable"] = row["id"] != user["id"]
                else:
                    item["manageable"] = (
                        row["id"] != user["id"]
                        and row["tenant_id"] == user["tenant_id"]
                        and row["role"] in {ROLE_BRANCH_ADMIN, ROLE_VIEWER}
                    )
                users.append(item)

            if is_super:
                visible_centers = CENTERS
                roles = sorted(VALID_ROLES)
            else:
                hq_perms = list_permissions(user)
                visible_centers = {
                    slug: center for slug, center in CENTERS.items()
                    if hq_perms.get(slug, {}).get("can_view")
                }
                roles = [ROLE_BRANCH_ADMIN, ROLE_VIEWER]

            centers = [
                {"slug": slug, "name": center.get("name") or slug, "dpCode": center.get("dp_code") or ""}
                for slug, center in visible_centers.items()
            ]
            self._json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "currentUserId": user["id"],
                    "adminMode": "SUPER" if is_super else "HQ",
                    "canCreateTenant": is_super,
                    "currentTenantId": user["tenant_id"],
                    "tenants": [dict(r) for r in tenant_rows],
                    "users": users,
                    "centers": centers,
                    "roles": roles,
                },
            )
            return

        if path == "/api/audit":
            if user["role"] not in {ROLE_SUPER_ADMIN, ROLE_HQ_ADMIN}:
                self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "ADMIN_REQUIRED"})
                return
            limit = min(500, max(1, int((query.get("limit") or ["100"])[0])))
            with db_connect() as conn:
                rows = conn.execute(
                    "SELECT created_at,username,action,center_slug,ip,detail FROM audit_logs "
                    "ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            self._json(HTTPStatus.OK, {"ok": True, "logs": [dict(r) for r in rows]})
            return

        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "NOT_FOUND"})

    def do_POST(self) -> None:
        if not self._origin_allowed():
            self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "ORIGIN_DENIED"})
            return
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            body = self._read_json()
        except Exception:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "INVALID_JSON"})
            return

        if path == "/api/auth/login":
            username = str(body.get("username", "")).strip()
            password = str(body.get("password", ""))
            with db_connect() as conn:
                user = conn.execute(
                    "SELECT * FROM users WHERE username=? COLLATE NOCASE AND active=1",
                    (username,),
                ).fetchone()
            if not user or not verify_password(password, user["password_salt"], user["password_hash"]):
                audit("LOGIN_FAILED", None, None, client_ip(self), {"username": username})
                self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "INVALID_LOGIN"})
                return
            token = secrets.token_urlsafe(40)
            th = token_hash(token)
            hours = int(SERVICE.get("session_hours", 12))
            expires = now_utc() + timedelta(hours=hours)
            with db_connect() as conn:
                conn.execute("DELETE FROM sessions WHERE expires_at<=?", (iso_utc(),))
                conn.execute(
                    "INSERT INTO sessions(token_hash,user_id,created_at,expires_at,last_seen_at) VALUES(?,?,?,?,?)",
                    (th, user["id"], iso_utc(), iso_utc(expires), iso_utc()),
                )
                conn.commit()
            audit("LOGIN_SUCCESS", user, None, client_ip(self))
            cookie = f"{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={hours*3600}"
            if SERVICE.get("secure_cookie"):
                cookie += "; Secure"
            self._json(
                HTTPStatus.OK,
                {"ok": True, "user": {"username": user["username"], "role": user["role"], "tenantId": user["tenant_id"]}},
                {"Set-Cookie": cookie},
            )
            return

        user = self._require_user()
        if not user:
            return

        if path == "/api/auth/logout":
            token = self._session_token()
            if token:
                with db_connect() as conn:
                    conn.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(token),))
                    conn.commit()
            audit("LOGOUT", user, None, client_ip(self))
            self._json(
                HTTPStatus.OK,
                {"ok": True},
                {"Set-Cookie": f"{COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"},
            )
            return

        if path == "/api/admin/tenant/create":
            if user["role"] != ROLE_SUPER_ADMIN:
                self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "SUPER_ADMIN_REQUIRED"})
                return
            name = str(body.get("name", "")).strip()
            tenant_id = str(body.get("id", "")).strip()
            if not name:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "TENANT_NAME_REQUIRED"})
                return
            if not tenant_id:
                tenant_id = "tn_" + secrets.token_hex(5)
            if not re.fullmatch(r"[A-Za-z0-9_-]{2,40}", tenant_id):
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "INVALID_TENANT_ID"})
                return
            try:
                with db_connect() as conn:
                    conn.execute("INSERT INTO tenants(id,name,active,created_at) VALUES(?,?,1,?)",
                                 (tenant_id, name, iso_utc()))
                    conn.commit()
            except sqlite3.IntegrityError:
                self._json(HTTPStatus.CONFLICT, {"ok": False, "error": "TENANT_ID_EXISTS"})
                return
            audit("ADMIN_TENANT_CREATE", user, None, client_ip(self), {"tenantId": tenant_id, "name": name})
            self._json(HTTPStatus.CREATED, {"ok": True, "tenantId": tenant_id})
            return

        if path == "/api/admin/user/create":
            if user["role"] not in {ROLE_SUPER_ADMIN, ROLE_HQ_ADMIN}:
                self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "ADMIN_MANAGER_REQUIRED"})
                return
            username = str(body.get("username", "")).strip()
            password = str(body.get("password", ""))
            tenant_id = str(body.get("tenantId", "")).strip()
            role = str(body.get("role", "")).strip().upper()
            center_slugs = body.get("centers") or []
            features = body.get("features") or []

            if user["role"] == ROLE_HQ_ADMIN:
                tenant_id = user["tenant_id"]

            if not re.fullmatch(r"[A-Za-z0-9_.-]{3,40}", username):
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "INVALID_USERNAME"})
                return
            if len(password) < 10:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "PASSWORD_TOO_SHORT"})
                return
            if role not in VALID_ROLES:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "INVALID_ROLE"})
                return
            if not isinstance(center_slugs, list) or not center_slugs:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "CENTER_REQUIRED"})
                return
            center_slugs = list(dict.fromkeys(str(x).strip() for x in center_slugs if str(x).strip()))
            if any(x not in CENTERS for x in center_slugs):
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "INVALID_CENTER"})
                return
            if not isinstance(features, list):
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "INVALID_FEATURES"})
                return

            feature_map = {"view":"can_view","weekly":"can_view_weekly","settlement":"can_view_settlement",
                           "personal":"can_view_personal","manage":"can_manage_riders","sms":"can_send_sms"}
            feature_names = {str(x).strip().lower() for x in features}
            if feature_names - set(feature_map):
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "INVALID_FEATURES"})
                return
            feature_names.add("view")
            if "manage" in feature_names:
                feature_names.add("personal")

            scope_error = self._validate_hq_grant(user, tenant_id, role, center_slugs, feature_names)
            if scope_error:
                self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": scope_error})
                return

            salt_b64, hash_b64 = hash_password(password)
            new_user_id = "usr_" + secrets.token_hex(8)
            try:
                with db_connect() as conn:
                    tenant = conn.execute("SELECT id FROM tenants WHERE id=? AND active=1", (tenant_id,)).fetchone()
                    if not tenant:
                        self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "INVALID_TENANT"})
                        return
                    conn.execute(
                        "INSERT INTO users(id,tenant_id,username,password_salt,password_hash,role,active,created_at) "
                        "VALUES(?,?,?,?,?,?,1,?)",
                        (new_user_id, tenant_id, username, salt_b64, hash_b64, role, iso_utc()),
                    )
                    for slug in center_slugs:
                        values = {field: 0 for field in PERMISSION_FIELDS}
                        for feature in feature_names:
                            values[feature_map[feature]] = 1
                        conn.execute(
                            "INSERT INTO center_permissions(user_id,center_slug,can_view,can_view_weekly,"
                            "can_view_settlement,can_view_personal,can_manage_riders,can_send_sms) VALUES(?,?,?,?,?,?,?,?)",
                            (new_user_id, slug, values["can_view"], values["can_view_weekly"],
                             values["can_view_settlement"], values["can_view_personal"],
                             values["can_manage_riders"], values["can_send_sms"]),
                        )
                    conn.commit()
            except sqlite3.IntegrityError:
                self._json(HTTPStatus.CONFLICT, {"ok": False, "error": "USERNAME_EXISTS"})
                return

            audit("ADMIN_USER_CREATE", user, None, client_ip(self),
                  {"targetUserId":new_user_id,"username":username,"tenantId":tenant_id,
                   "role":role,"centers":center_slugs,"features":sorted(feature_names)})
            self._json(HTTPStatus.CREATED, {"ok": True, "userId": new_user_id})
            return

        if path == "/api/admin/user/update":
            if user["role"] not in {ROLE_SUPER_ADMIN, ROLE_HQ_ADMIN}:
                self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "ADMIN_MANAGER_REQUIRED"})
                return
            target_id = str(body.get("userId", "")).strip()
            if target_id == user["id"]:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "CURRENT_ADMIN_PROTECTED"})
                return

            tenant_id = str(body.get("tenantId", "")).strip()
            role = str(body.get("role", "")).strip().upper()
            active = 1 if bool(body.get("active", True)) else 0
            center_slugs = body.get("centers") or []
            features = body.get("features") or []

            if user["role"] == ROLE_HQ_ADMIN:
                tenant_id = user["tenant_id"]

            if role not in VALID_ROLES:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "INVALID_ROLE"})
                return
            if not isinstance(center_slugs, list) or not center_slugs:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "CENTER_REQUIRED"})
                return
            center_slugs = list(dict.fromkeys(str(x).strip() for x in center_slugs if str(x).strip()))
            if any(x not in CENTERS for x in center_slugs):
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "INVALID_CENTER"})
                return
            if not isinstance(features, list):
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "INVALID_FEATURES"})
                return

            feature_map = {"view":"can_view","weekly":"can_view_weekly","settlement":"can_view_settlement",
                           "personal":"can_view_personal","manage":"can_manage_riders","sms":"can_send_sms"}
            feature_names = {str(x).strip().lower() for x in features}
            if feature_names - set(feature_map):
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "INVALID_FEATURES"})
                return
            feature_names.add("view")
            if "manage" in feature_names:
                feature_names.add("personal")

            with db_connect() as conn:
                target = conn.execute(
                    "SELECT id,tenant_id,role FROM users WHERE id=?",
                    (target_id,),
                ).fetchone()
            if not target:
                self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "USER_NOT_FOUND"})
                return

            if user["role"] == ROLE_HQ_ADMIN:
                if target["tenant_id"] != user["tenant_id"]:
                    self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "TENANT_SCOPE_DENIED"})
                    return
                if target["role"] not in {ROLE_BRANCH_ADMIN, ROLE_VIEWER}:
                    self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "TARGET_ROLE_PROTECTED"})
                    return

            scope_error = self._validate_hq_grant(user, tenant_id, role, center_slugs, feature_names)
            if scope_error:
                self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": scope_error})
                return

            with db_connect() as conn:
                tenant = conn.execute("SELECT id FROM tenants WHERE id=? AND active=1", (tenant_id,)).fetchone()
                if not tenant:
                    self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "INVALID_TENANT"})
                    return
                conn.execute("UPDATE users SET tenant_id=?,role=?,active=? WHERE id=?",
                             (tenant_id, role, active, target_id))
                conn.execute("DELETE FROM center_permissions WHERE user_id=?", (target_id,))
                for slug in center_slugs:
                    values = {field: 0 for field in PERMISSION_FIELDS}
                    for feature in feature_names:
                        values[feature_map[feature]] = 1
                    conn.execute(
                        "INSERT INTO center_permissions(user_id,center_slug,can_view,can_view_weekly,"
                        "can_view_settlement,can_view_personal,can_manage_riders,can_send_sms) VALUES(?,?,?,?,?,?,?,?)",
                        (target_id, slug, values["can_view"], values["can_view_weekly"],
                         values["can_view_settlement"], values["can_view_personal"],
                         values["can_manage_riders"], values["can_send_sms"]),
                    )
                conn.execute("DELETE FROM sessions WHERE user_id=?", (target_id,))
                conn.commit()

            audit("ADMIN_USER_UPDATE", user, None, client_ip(self),
                  {"targetUserId":target_id,"tenantId":tenant_id,"role":role,"active":active,
                   "centers":center_slugs,"features":sorted(feature_names)})
            self._json(HTTPStatus.OK, {"ok": True})
            return

        if path == "/api/admin/user/reset-password":
            if user["role"] not in {ROLE_SUPER_ADMIN, ROLE_HQ_ADMIN}:
                self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "ADMIN_MANAGER_REQUIRED"})
                return
            target_id = str(body.get("userId", "")).strip()
            password = str(body.get("password", ""))
            if target_id == user["id"]:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "CURRENT_ADMIN_PROTECTED"})
                return
            if len(password) < 10:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "PASSWORD_TOO_SHORT"})
                return

            with db_connect() as conn:
                target = conn.execute(
                    "SELECT id,tenant_id,role FROM users WHERE id=?",
                    (target_id,),
                ).fetchone()
            if not target:
                self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "USER_NOT_FOUND"})
                return
            if user["role"] == ROLE_HQ_ADMIN:
                if target["tenant_id"] != user["tenant_id"]:
                    self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "TENANT_SCOPE_DENIED"})
                    return
                if target["role"] not in {ROLE_BRANCH_ADMIN, ROLE_VIEWER}:
                    self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "TARGET_ROLE_PROTECTED"})
                    return

            salt_b64, hash_b64 = hash_password(password)
            with db_connect() as conn:
                conn.execute(
                    "UPDATE users SET password_salt=?,password_hash=? WHERE id=?",
                    (salt_b64, hash_b64, target_id),
                )
                conn.execute("DELETE FROM sessions WHERE user_id=?", (target_id,))
                conn.commit()
            audit("ADMIN_PASSWORD_RESET", user, None, client_ip(self), {"targetUserId": target_id})
            self._json(HTTPStatus.OK, {"ok": True})
            return

        if path == "/api/save-teammap":
            slug = str(body.get("area") or body.get("center") or "").strip()
            permission = self._center_permission(user, slug, "can_manage_riders")
            if not permission:
                return
            center = CENTERS[slug]
            changes = body.get("changes") or {}
            if not isinstance(changes, dict) or not changes:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "EMPTY_CHANGES"})
                return
            if len(changes) > 1000:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "TOO_MANY_CHANGES"})
                return
            allowed_teams = set(center.get("teams") or [])
            clean_changes: dict[str, str] = {}
            for key, team in changes.items():
                key = str(key).strip()
                team = str(team).strip()
                if not (key.startswith("phone_") or key.startswith("uid_")):
                    self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "UNSAFE_RIDER_KEY"})
                    return
                if team not in allowed_teams:
                    self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "INVALID_TEAM"})
                    return
                clean_changes[key] = team
            try:
                firebase_update(center["team_map_path"], clean_changes)
                audit(
                    "TEAMMAP_UPDATE",
                    user,
                    slug,
                    client_ip(self),
                    {"count": len(clean_changes), "keys": list(clean_changes.keys())[:20]},
                )
                self._json(HTTPStatus.OK, {"ok": True, "updated": len(clean_changes)})
            except Exception as exc:
                print(f"[API 오류] TEAMMAP_UPDATE / {slug}: {exc}")
                self._json(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": "DATA_SOURCE_ERROR"})
            return

        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "NOT_FOUND"})


def serve() -> None:
    init_db()
    host = str(SERVICE.get("api_host", "127.0.0.1"))
    port = int(SERVICE.get("api_port", 8787))
    server = ThreadingHTTPServer((host, port), ApiHandler)
    print("SUPERSONIC Enterprise API Core v2.4.3")
    print(f"주소: http://{host}:{port}")
    print(f"센터: {len(CENTERS)}개")
    print("필수 로그 모드 · Firebase 직접 접근은 API 내부에서만 수행")
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\nAPI 종료")
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="SUPERSONIC Enterprise API Core v2.4.3")
    parser.add_argument("--init-admin", metavar="USERNAME", help="최초 SUPER_ADMIN 계정 생성")
    parser.add_argument("--create-user", metavar="USERNAME", help="권한 제한 사용자 생성")
    parser.add_argument("--tenant", default="internal", help="사용자 소속 tenant id")
    parser.add_argument("--role", default=ROLE_VIEWER, choices=sorted(VALID_ROLES), help="사용자 역할")
    parser.add_argument("--centers", default="", help="허용 센터 slug. 쉼표 구분, 예: dalseoa,dalseob")
    parser.add_argument("--features", default="view,weekly", help="허용 기능. view,weekly,settlement,personal,manage,sms")
    parser.add_argument("--list-users", action="store_true", help="등록 사용자 목록")
    parser.add_argument("--reset-password", metavar="USERNAME", help="기존 사용자 비밀번호 재설정")
    parser.add_argument("--check", action="store_true", help="설정/DB 초기화 상태만 점검")
    args = parser.parse_args()

    init_db()
    if args.init_admin:
        create_admin(args.init_admin, args.tenant)
        return
    if args.create_user:
        centers = [x.strip() for x in args.centers.split(",") if x.strip()]
        if not centers:
            raise SystemExit("--create-user 사용 시 --centers가 필요합니다.")
        features = {x.strip().lower() for x in args.features.split(",") if x.strip()}
        create_user(args.create_user, args.tenant, args.role, centers, features)
        return
    if args.reset_password:
        reset_user_password(args.reset_password)
        return
    if args.list_users:
        list_users()
        return
    if args.check:
        with db_connect() as conn:
            user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        print(f"설정 정상 · DP {len(CENTERS)}개 · 사용자 {user_count}명 · DB {DB_PATH.name}")
        return
    serve()


if __name__ == "__main__":
    main()
