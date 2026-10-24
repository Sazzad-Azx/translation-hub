"""
Run a nightly job (sync / pull / collections / sweep / costs) outside Vercel.

The Vercel crons could never finish: the sync alone spends ~45s listing
Intercom collections + articles, past the function's 10s cap, so every run
was killed before record_run() and nothing was logged (silent since 2026-06).
GitHub Actions (.github/workflows/nightly.yml) calls this instead. It drives
the existing /api/cron/* handlers in-process through Flask's test client, so
the job logic stays in exactly one place.

Usage:
    python scripts/run_cron.py sync|pull|collections|sweep|costs
Exit code is non-zero if the handler fails or any product reports an error.
"""
import os
import secrets
import sys

JOBS = ("sync", "pull", "collections", "sweep", "costs")

# A missing secret makes the handlers read every automation as "disabled" and
# skip, which still returns 200 — fail loudly instead of going green.
_INTERCOM = ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "INTERCOM_ACCESS_TOKEN")
REQUIRED_ENV = {
    "sync": _INTERCOM,
    "pull": _INTERCOM,
    "collections": _INTERCOM + ("OPENAI_API_KEY",),
    "sweep": _INTERCOM,
    "costs": ("SUPABASE_URL", "SUPABASE_SERVICE_KEY"),
}

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    job = sys.argv[1] if len(sys.argv) > 1 else ""
    if job not in JOBS:
        print(f"usage: run_cron.py {'|'.join(JOBS)}")
        return 2

    missing = [k for k in REQUIRED_ENV[job] if not os.getenv(k, "").strip()]
    if missing:
        print(f"[run_cron {job}] missing env: {', '.join(missing)} — "
              "add them as GitHub Actions repository secrets", flush=True)
        return 1

    # The handlers only accept a Bearer CRON_SECRET; mint one for this process.
    os.environ["CRON_SECRET"] = secrets.token_hex(16)
    from app import app

    resp = app.test_client().post(
        f"/api/cron/{job}",
        headers={"Authorization": f"Bearer {os.environ['CRON_SECRET']}"},
    )
    body = resp.get_json(silent=True) or {}
    print(f"[run_cron {job}] HTTP {resp.status_code}: {body}", flush=True)

    if resp.status_code != 200 or not body.get("success"):
        return 1
    failed = [pid for pid, r in (body.get("products") or {}).items()
              if not r.get("success") and not r.get("skipped")]
    if failed:
        print(f"[run_cron {job}] failed products: {failed}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
