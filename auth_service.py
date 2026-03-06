"""
Authentication service for Translation Hub.
Super admin credentials stored in environment variables.
Other admin credentials stored in Supabase.
"""
import os
import hashlib
import secrets
import time
import json
import requests
from typing import Optional, Dict, List

# ─── Config ────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SUPER_ADMIN_EMAIL = os.getenv("SUPER_ADMIN_EMAIL", "")
SUPER_ADMIN_PASSWORD = os.getenv("SUPER_ADMIN_PASSWORD", "")

# In-memory session store  {token: {email, role, name, expires_at}}
_sessions: Dict[str, dict] = {}

# Session duration: 24 hours
SESSION_TTL = 86400


def _sb_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _hash_password(password: str) -> str:
    """SHA-256 hash with a fixed salt prefix."""
    salted = f"fnth_salt_{password}"
    return hashlib.sha256(salted.encode("utf-8")).hexdigest()


# ─── Table bootstrap ──────────────────────────────────────────
def ensure_admins_table() -> bool:
    """Create the admins table in Supabase if it doesn't exist."""
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/admins?select=id&limit=1",
            headers=_sb_headers(),
        )
        if r.status_code == 200:
            return True
    except Exception:
        pass

    # Table doesn't exist – return SQL for manual creation
    return False


def get_admins_table_sql() -> str:
    return """
CREATE TABLE IF NOT EXISTS admins (
    id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'admin',
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_admins_email ON admins(email);
"""


# ─── Authentication ───────────────────────────────────────────
def login(email: str, password: str) -> Optional[dict]:
    """
    Authenticate a user.  Returns session dict or None.
    Checks super admin first, then Supabase admins table.
    """
    email = email.strip().lower()

    # 1) Super admin check
    sa_email = SUPER_ADMIN_EMAIL.strip().lower()
    if email == sa_email and password == SUPER_ADMIN_PASSWORD:
        token = _create_session(email, "super_admin", "Super Admin")
        return {
            "token": token,
            "email": email,
            "name": "Super Admin",
            "role": "super_admin",
        }

    # 2) Supabase admin check
    pw_hash = _hash_password(password)
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/admins"
            f"?email=eq.{email}&is_active=eq.true&select=*",
            headers=_sb_headers(),
        )
        if r.status_code == 200:
            rows = r.json()
            if rows and rows[0].get("password_hash") == pw_hash:
                admin = rows[0]
                token = _create_session(
                    admin["email"],
                    admin.get("role", "admin"),
                    admin.get("name", "Admin"),
                )
                return {
                    "token": token,
                    "email": admin["email"],
                    "name": admin.get("name", "Admin"),
                    "role": admin.get("role", "admin"),
                }
    except Exception as e:
        print(f"[auth] Supabase admin lookup error: {e}", flush=True)

    return None


def _create_session(email: str, role: str, name: str) -> str:
    token = secrets.token_hex(32)
    _sessions[token] = {
        "email": email,
        "role": role,
        "name": name,
        "expires_at": time.time() + SESSION_TTL,
    }
    return token


def validate_session(token: str) -> Optional[dict]:
    """Return session dict if valid, else None."""
    if not token:
        return None
    session = _sessions.get(token)
    if not session:
        return None
    if time.time() > session["expires_at"]:
        _sessions.pop(token, None)
        return None
    return session


def logout(token: str):
    _sessions.pop(token, None)


# ─── Admin CRUD (super-admin only) ───────────────────────────
def list_admins() -> List[dict]:
    """List all admins from Supabase (excluding password hash)."""
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/admins"
            f"?select=id,email,name,role,is_active,created_at&order=created_at.desc",
            headers=_sb_headers(),
        )
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"[auth] list_admins error: {e}", flush=True)
    return []


def create_admin(email: str, password: str, name: str, role: str = "admin") -> dict:
    """Create a new admin in Supabase."""
    email = email.strip().lower()

    # Check not super admin email
    if email == SUPER_ADMIN_EMAIL.strip().lower():
        return {"success": False, "error": "Cannot create admin with super admin email"}

    pw_hash = _hash_password(password)
    body = {
        "email": email,
        "password_hash": pw_hash,
        "name": name.strip(),
        "role": role,
        "is_active": True,
    }
    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/admins",
            headers=_sb_headers(),
            json=body,
        )
        if r.status_code in (200, 201):
            data = r.json()
            admin = data[0] if isinstance(data, list) else data
            return {
                "success": True,
                "admin": {
                    "id": admin["id"],
                    "email": admin["email"],
                    "name": admin["name"],
                    "role": admin["role"],
                    "is_active": admin["is_active"],
                },
            }
        else:
            err = r.text
            if "duplicate" in err.lower() or "unique" in err.lower():
                return {"success": False, "error": "An admin with this email already exists"}
            return {"success": False, "error": f"Failed to create admin: {err}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def update_admin(admin_id: int, data: dict) -> dict:
    """Update an admin's name, role, or is_active status."""
    update = {}
    if "name" in data:
        update["name"] = data["name"].strip()
    if "role" in data:
        update["role"] = data["role"]
    if "is_active" in data:
        update["is_active"] = data["is_active"]
    if "password" in data and data["password"]:
        update["password_hash"] = _hash_password(data["password"])

    if not update:
        return {"success": False, "error": "No fields to update"}

    update["updated_at"] = "now()"

    try:
        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/admins?id=eq.{admin_id}",
            headers=_sb_headers(),
            json=update,
        )
        if r.status_code in (200, 204):
            return {"success": True}
        return {"success": False, "error": f"Update failed: {r.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def delete_admin(admin_id: int) -> dict:
    """Delete an admin from Supabase."""
    try:
        r = requests.delete(
            f"{SUPABASE_URL}/rest/v1/admins?id=eq.{admin_id}",
            headers=_sb_headers(),
        )
        if r.status_code in (200, 204):
            return {"success": True}
        return {"success": False, "error": f"Delete failed: {r.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
