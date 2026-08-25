from __future__ import annotations

import json
import os
import shutil
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .core import WorkbenchError, cases_root, utc_now, validate_case_id
from .security import hash_password, new_token, token_digest, verify_password


SCHEMA_VERSION = 1


class WorkbenchStore:
    def __init__(self, root=None):
        self.root = cases_root(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / "workbench.db"
        self._lock = threading.RLock()
        self.initialize()

    def connect(self):
        connection = sqlite3.connect(self.path, timeout=20)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=20000")
        return connection

    def initialize(self):
        with self._lock, self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    display_name TEXT NOT NULL DEFAULT '', password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('admin','supervisor','investigator','reviewer')),
                    totp_secret TEXT NOT NULL DEFAULT '', disabled INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
                    created_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, expires_at TEXT NOT NULL,
                    ip TEXT NOT NULL DEFAULT '', user_agent TEXT NOT NULL DEFAULT '', revoked_at TEXT
                );
                CREATE TABLE IF NOT EXISTS cases (
                    case_id TEXT PRIMARY KEY, payload TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
                    assigned_user_id INTEGER REFERENCES users(id), supervisor_user_id INTEGER REFERENCES users(id),
                    archived_at TEXT, retention_date TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, occurred_at TEXT NOT NULL, actor_user_id INTEGER,
                    action TEXT NOT NULL, case_id TEXT, detail TEXT NOT NULL DEFAULT '', ip TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(actor_user_id) REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER REFERENCES users(id), case_id TEXT,
                    kind TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL, read_at TEXT
                );
                CREATE TABLE IF NOT EXISTS login_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, occurred_at TEXT NOT NULL, username TEXT NOT NULL,
                    ip TEXT NOT NULL, successful INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audit_case ON audit_events(case_id, id DESC);
                CREATE INDEX IF NOT EXISTS idx_login_attempt ON login_attempts(username, ip, occurred_at DESC);
            """)
            db.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('schema_version',?)", (str(SCHEMA_VERSION),))
        os.chmod(self.path, 0o600)
        self.migrate_json_cases()

    def migrate_json_cases(self):
        for path in self.root.glob("*/workbench.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                with self.connect() as db:
                    exists = db.execute("SELECT 1 FROM cases WHERE case_id=?", (data["case_id"],)).fetchone()
                    if not exists:
                        self.save_case(data, actor=None, action="case_migrated")
            except (OSError, ValueError, KeyError, sqlite3.Error):
                continue

    def ensure_bootstrap_user(self, username: str, password: str, totp_secret: str = ""):
        if not username or not password:
            return
        now = utc_now()
        with self._lock, self.connect() as db:
            row = db.execute("SELECT id,password_hash FROM users WHERE username=? COLLATE NOCASE", (username,)).fetchone()
            if row:
                if not verify_password(password, row["password_hash"]):
                    db.execute("UPDATE users SET password_hash=?,totp_secret=?,updated_at=? WHERE id=?", (hash_password(password), totp_secret, now, row["id"]))
                elif totp_secret:
                    db.execute("UPDATE users SET totp_secret=?,updated_at=? WHERE id=?", (totp_secret, now, row["id"]))
                return
            db.execute("INSERT INTO users(username,display_name,password_hash,role,totp_secret,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (username, username, hash_password(password), "admin", totp_secret, now, now))

    def list_users(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT id,username,display_name,role,disabled,created_at,updated_at,(totp_secret!='') AS mfa_enabled FROM users ORDER BY username")]

    def create_user(self, username, display_name, password, role, totp_secret=""):
        if role not in {"admin", "supervisor", "investigator", "reviewer"}:
            raise WorkbenchError("invalid role")
        if not username or any(character.isspace() for character in username):
            raise WorkbenchError("username is required and cannot contain spaces")
        now = utc_now()
        try:
            with self.connect() as db:
                cursor = db.execute("INSERT INTO users(username,display_name,password_hash,role,totp_secret,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (username, display_name or username, hash_password(password), role, totp_secret, now, now))
                user_id = cursor.lastrowid
        except sqlite3.IntegrityError as exc:
            raise WorkbenchError("username already exists") from exc
        return next(user for user in self.list_users() if user["id"] == user_id)

    def change_password(self, user_id, old_password, new_password):
        with self.connect() as db:
            row = db.execute("SELECT password_hash FROM users WHERE id=?", (user_id,)).fetchone()
            if not row or not verify_password(old_password, row["password_hash"]):
                raise WorkbenchError("current password is incorrect")
            db.execute("UPDATE users SET password_hash=?,updated_at=? WHERE id=?", (hash_password(new_password), utc_now(), user_id))
            db.execute("UPDATE sessions SET revoked_at=? WHERE user_id=?", (utc_now(), user_id))

    def authenticate(self, username: str, password: str):
        with self.connect() as db:
            row = db.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE AND disabled=0", (username,)).fetchone()
        return dict(row) if row and verify_password(password, row["password_hash"]) else None

    def login_blocked(self, username: str, ip: str, window_minutes=15, limit=8):
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).replace(microsecond=0).isoformat()
        with self.connect() as db:
            count = db.execute("SELECT COUNT(*) FROM login_attempts WHERE username=? COLLATE NOCASE AND ip=? AND successful=0 AND occurred_at>=?", (username, ip, cutoff)).fetchone()[0]
        return count >= limit

    def record_login(self, username: str, ip: str, successful: bool, actor=None):
        with self.connect() as db:
            db.execute("INSERT INTO login_attempts(occurred_at,username,ip,successful) VALUES(?,?,?,?)", (utc_now(), username, ip, int(successful)))
        self.audit(actor, "login_succeeded" if successful else "login_failed", detail=username, ip=ip)

    def create_session(self, user_id: int, ip="", user_agent="", hours=12):
        token = new_token()
        now = datetime.now(timezone.utc).replace(microsecond=0)
        with self.connect() as db:
            db.execute("INSERT INTO sessions(token_hash,user_id,created_at,last_seen_at,expires_at,ip,user_agent) VALUES(?,?,?,?,?,?,?)", (token_digest(token), user_id, now.isoformat(), now.isoformat(), (now + timedelta(hours=hours)).isoformat(), ip, user_agent[:300]))
        return token

    def session_user(self, token: str, idle_minutes=30):
        if not token:
            return None
        now = datetime.now(timezone.utc).replace(microsecond=0)
        idle_cutoff = (now - timedelta(minutes=idle_minutes)).isoformat()
        with self.connect() as db:
            row = db.execute("SELECT u.*,s.last_seen_at,s.expires_at FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.revoked_at IS NULL AND u.disabled=0", (token_digest(token),)).fetchone()
            if not row or row["expires_at"] < now.isoformat() or row["last_seen_at"] < idle_cutoff:
                return None
            db.execute("UPDATE sessions SET last_seen_at=? WHERE token_hash=?", (now.isoformat(), token_digest(token)))
        return dict(row)

    def revoke_session(self, token: str):
        with self.connect() as db:
            db.execute("UPDATE sessions SET revoked_at=? WHERE token_hash=?", (utc_now(), token_digest(token)))

    def list_cases(self, include_archived=False):
        query = "SELECT payload FROM cases" + ("" if include_archived else " WHERE archived_at IS NULL") + " ORDER BY updated_at DESC"
        with self.connect() as db:
            return [json.loads(row["payload"]) for row in db.execute(query)]

    def load_case(self, case_id: str):
        validate_case_id(case_id)
        with self.connect() as db:
            row = db.execute("SELECT payload,version,assigned_user_id,supervisor_user_id,archived_at,retention_date FROM cases WHERE case_id=?", (case_id,)).fetchone()
        if not row:
            raise WorkbenchError(f"case not found: {case_id}")
        data = json.loads(row["payload"])
        data["record_meta"] = {key: row[key] for key in ("version", "assigned_user_id", "supervisor_user_id", "archived_at", "retention_date")}
        return data

    def update_case_meta(self, case_id, assigned_user_id=None, supervisor_user_id=None, retention_date=None, archived=None):
        validate_case_id(case_id)
        fields, values = [], []
        for field, value in (("assigned_user_id", assigned_user_id), ("supervisor_user_id", supervisor_user_id), ("retention_date", retention_date)):
            if value is not None:
                fields.append(f"{field}=?")
                values.append(value or None)
        if archived is not None:
            fields.append("archived_at=?")
            values.append(utc_now() if archived else None)
        if not fields:
            return
        values.append(case_id)
        with self.connect() as db:
            db.execute(f"UPDATE cases SET {','.join(fields)},updated_at=? WHERE case_id=?", (*values[:-1], utc_now(), values[-1]))

    def add_notification(self, user_id, case_id, kind, message):
        with self.connect() as db:
            db.execute("INSERT INTO notifications(user_id,case_id,kind,message,created_at) VALUES(?,?,?,?,?)", (user_id, case_id, kind, message, utc_now()))

    def notifications(self, user_id, limit=100):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM notifications WHERE user_id IS NULL OR user_id=? ORDER BY id DESC LIMIT ?", (user_id, min(limit, 200)))]

    def save_case(self, data, actor=None, action="case_updated", expected_version=None, detail=""):
        case_id = validate_case_id(data["case_id"])
        now = utc_now()
        data["updated_at"] = now
        payload_data = {key: value for key, value in data.items() if key != "record_meta"}
        payload = json.dumps(payload_data, separators=(",", ":"), sort_keys=True)
        with self._lock, self.connect() as db:
            row = db.execute("SELECT version FROM cases WHERE case_id=?", (case_id,)).fetchone()
            if row:
                if expected_version is not None and row["version"] != expected_version:
                    raise WorkbenchError("case changed in another session; reload and try again")
                db.execute("UPDATE cases SET payload=?,version=version+1,updated_at=? WHERE case_id=?", (payload, now, case_id))
            else:
                db.execute("INSERT INTO cases(case_id,payload,created_at,updated_at) VALUES(?,?,?,?)", (case_id, payload, data.get("created_at", now), now))
        self.audit(actor, action, case_id, detail)

    def audit(self, actor, action, case_id=None, detail="", ip=""):
        actor_id = actor.get("id") if isinstance(actor, dict) else actor
        with self.connect() as db:
            db.execute("INSERT INTO audit_events(occurred_at,actor_user_id,action,case_id,detail,ip) VALUES(?,?,?,?,?,?)", (utc_now(), actor_id, action, case_id, detail[:1000], ip))

    def audit_events(self, case_id=None, limit=200):
        query = "SELECT a.*,u.username FROM audit_events a LEFT JOIN users u ON u.id=a.actor_user_id"
        params = []
        if case_id:
            query += " WHERE a.case_id=?"
            params.append(case_id)
        query += " ORDER BY a.id DESC LIMIT ?"
        params.append(min(limit, 500))
        with self.connect() as db:
            return [dict(row) for row in db.execute(query, params)]

    def backup(self, destination=None):
        backup_dir = self.root / "backups"
        backup_dir.mkdir(mode=0o700, exist_ok=True)
        target = Path(destination) if destination else backup_dir / f"workbench-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.db"
        with self.connect() as source, sqlite3.connect(target) as output:
            source.backup(output)
            result = output.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise WorkbenchError(f"backup integrity check failed: {result}")
        os.chmod(target, 0o600)
        return target
