"""
Authentication service for Translation Hub.
Super admin credentials stored in environment variables.
Other admin credentials stored in Supabase.

Uses stateless HMAC-signed tokens so authentication works
correctly on serverless platforms (Vercel) where each request
may hit a different process instance.
"""
import os
import hashlib
import hmac
import secrets
import time
import json
import base64
import requests
from typing import Optional, Dict, List

# ─── Config ────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SUPER_ADMIN_EMAIL = os.getenv("SUPER_ADMIN_EMAIL", "sazzad@nextventures.io")
SUPER_ADMIN_PASSWORD = os.getenv("SUPER_ADMIN_PASSWORD", "Sazzad123")
AUTH_SECRET = os.getenv("AUTH_SECRET", os.getenv("JWT_SECRET_KEY", "fnth-default-secret-change-me"))

# Token duration: 24 hours
TOKEN_TTL = 86400


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


def auto_create_table() -> dict:
    """Try to create the admins table using pg8000 or the Supabase DB URL."""
    sql = get_admins_table_sql()
    db_url = os.getenv("SUPABASE_DB_URL", "")

    # Method 1: Try SUPABASE_DB_URL with pg8000
    if db_url:
        try:
            import pg8000
            import urllib.parse as urlparse
            parsed = urlparse.urlparse(db_url)
            conn = pg8000.connect(
                host=parsed.hostname,
                port=parsed.port or 5432,
                database=parsed.path.lstrip("/"),
                user=parsed.username,
                password=parsed.password,
                ssl_context=True,
            )
            cur = conn.cursor()
            cur.execute(sql)
            conn.commit()
            cur.close()
            conn.close()
            return {"success": True, "method": "pg8000"}
        except Exception as e:
            print(f"[auth] pg8000 auto-create failed: {e}", flush=True)

    # Method 2: Try creating via PostgREST (won't work for DDL, but as fallback)
    # Actually, just create a simple check by inserting and catching error
    # Instead, inform the user
    return {
        "success": False,
        "error": "Auto-create not available. Please run the SQL in Supabase SQL Editor.",
        "sql": sql,
    }


# ─── Stateless Token helpers ──────────────────────────────────
def _create_token(email: str, role: str, name: str) -> str:
    """Create a self-contained HMAC-signed token embedding user info."""
    payload = json.dumps({
        "email": email,
        "role": role,
        "name": name,
        "exp": int(time.time()) + TOKEN_TTL,
    }, separators=(",", ":"))
    payload_b64 = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8")
    sig = hmac.new(AUTH_SECRET.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def validate_session(token: str) -> Optional[dict]:
    """Verify an HMAC-signed token and return the payload dict, or None."""
    if not token:
        return None
    try:
        parts = token.rsplit(".", 1)
        if len(parts) != 2:
            return None
        payload_b64, sig = parts
        expected_sig = hmac.new(
            AUTH_SECRET.encode("utf-8"),
            payload_b64.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        if time.time() > payload.get("exp", 0):
            return None
        return {
            "email": payload["email"],
            "role": payload["role"],
            "name": payload["name"],
        }
    except Exception:
        return None


# ─── Authentication ───────────────────────────────────────────
def login(email: str, password: str) -> Optional[dict]:
    """
    Authenticate a user.  Returns dict with signed token or None.
    Checks super admin first, then Supabase admins table.
    """
    email = email.strip().lower()

    # 1) Super admin check
    sa_email = SUPER_ADMIN_EMAIL.strip().lower()
    if email == sa_email and password == SUPER_ADMIN_PASSWORD:
        token = _create_token(email, "super_admin", "Super Admin")
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
                token = _create_token(
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


def logout(token: str):
    """Stateless tokens don't need server-side invalidation."""
    pass


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
