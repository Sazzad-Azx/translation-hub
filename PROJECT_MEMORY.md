# FundedNext Translation Hub - Project Memory

## Overview

A web application for managing Intercom article translations across 11 languages (AR, ZH-CN, FR, DE, HI, IT, JA, FA, ES, TH, PT-BR).

- **GitHub:** `Sazzad-Azx/translation-hub` (main branch)
- **Live URL:** https://fn-translation-hub.vercel.app
- **Tech Stack:** Flask (Python 3.12) backend, vanilla JS/HTML/CSS frontend, Supabase (PostgreSQL) for data storage, Intercom API for articles, OpenAI GPT-4o-mini for translation, deployed on Vercel as serverless functions.

---

## Project Structure

All files live inside `.cursor/intercom-translator/`.

### Core Application Files

| File | Purpose |
|------|---------|
| `app.py` | Flask app with all API routes (~1900 lines). Uses `before_request` auth middleware. Public paths: `/`, `/api/health`, `/api/auth/login`, `/api/cron/sync`, `/api/cron/pull`. |
| `api/index.py` | Vercel serverless entry point — imports Flask app, sets static/template folders. |
| `config.py` | Environment variables, target languages dict, Supabase/Intercom/OpenAI config. |
| `vercel.json` | Vercel config with crons (00:00 UTC sync, 01:30 UTC pull), `@vercel/static` builder, routes. |
| `requirements.txt` | Python dependencies: `requests`, `openai`, `python-dotenv`, `flask`, `flask-cors`, `pg8000`, `openpyxl`. |

### Frontend Files

| File | Purpose |
|------|---------|
| `templates/index.html` | Single-page HTML with all sections (login, sidebar, dashboard, content hub, pull, translate, push, automation, glossary, admin panel, etc.). |
| `static/app.js` | All frontend JS (~4700 lines). Global `state` object, section lazy-loading via `switchSection()`, fetch interceptor for auth tokens, event listeners for every section. |
| `static/style.css` | All CSS (~3800 lines). Uses CSS variables: `--primary`, `--bg`, `--card-bg`, `--border`, `--text`, `--text-muted`, `--radius`. |

### Backend Services

| File | Purpose | Supabase Table |
|------|---------|----------------|
| `auth_service.py` | Login (SHA-256+salt), JWT token generation/verification, admin CRUD. Super admin from env vars, other admins from Supabase. | `admins` |
| `pull_service.py` | Sync source list from Intercom (metadata only), pull full article content (title + body). | `pull_registry` |
| `translate_service.py` | List articles for translation, compute language statuses (TRANSLATED, OUTDATED, MISSING, etc.), trigger GPT translation. | `article_translations` |
| `push_service.py` | Push translated articles back to Intercom. Multi-locale support. | `article_translations` |
| `content_hub_service.py` | Content Hub with health statuses: NEEDS_PULL, OUTDATED, NEEDS_TRANSLATION, NEEDS_PUSH, COMPLETE, FAILED. | `article_translations` |
| `glossary_service.py` | Glossary CRUD, XLSX import/export. Source term column auto-detected from glossary's source language. | `glossaries`, `glossary_terms`, `glossary_term_translations` |
| `automation_service.py` | Auto-sync and auto-pull toggle settings. Two keys: `auto_sync_pull`, `auto_pull_articles`. | `automation_settings` |
| `intercom_client.py` | Intercom API wrapper — get articles, get collections, create/update translations. |  |
| `translator.py` | GPT translation with glossary integration. |  |
| `workflow.py` | Orchestrates pull → translate → push workflow. |  |
| `content_supabase.py` | Helper for `intercom_content_items` and `intercom_content_versions` tables. | `intercom_content_items`, `intercom_content_versions` |
| `translation_supabase.py` | Helper for `article_translations` table. | `article_translations` |
| `supabase_client.py` | Generic Supabase REST client. |  |
| `sync_service.py` | Sync service utilities. |  |

---

## Supabase Tables

1. `pull_registry` — Tracks articles pulled from Intercom (intercom_id, title, body_html, pull_status, source_updated_at, pulled_at, etc.)
2. `article_translations` — Stores translated content per article per locale (translated_title, translated_body_html, status, pushed_at, push_error, etc.)
3. `admins` — Admin users (name, email, password_hash, password_salt, role, is_active)
4. `automation_settings` — Automation toggle states (key, enabled, last_run_at, last_run_status, last_run_message, next_run_at)
5. `glossaries` — Glossary metadata (name, source_locale, target_locales)
6. `glossary_terms` — Source terms in a glossary
7. `glossary_term_translations` — Translations of glossary terms per locale
8. `intercom_content_items` — Cached Intercom article metadata
9. `intercom_content_versions` — Versioned content snapshots

---

## Authentication System

- **Super Admin:** `sazzad@nextventures.io` / `Sazzad123` — credentials stored in environment variables (`SUPER_ADMIN_EMAIL`, `SUPER_ADMIN_PASSWORD`).
- **Other Admins:** Stored in Supabase `admins` table. Super admin can add/edit/delete admins from the Admin Panel.
- **Roles:** `super_admin`, `admin`, `editor`, `viewer`.
- **Token:** JWT with 24-hour expiry, generated on login. Frontend stores in `localStorage('authToken')`.
- **Fetch Interceptor:** Global `window.fetch` override adds `Authorization: Bearer <token>` to all `/api/` requests. 401 responses auto-redirect to login page.
- **Middleware:** `app.py` `before_request` checks auth for all API routes except public paths.

---

## UI Sections

| Section | Nav Item | Status |
|---------|----------|--------|
| Dashboard | `data-section="dashboard"` | Active |
| Content Hub | `data-section="content-hub"` | Active |
| Pull | `data-section="pull"` | Active |
| Translate | `data-section="translate"` | Active |
| Push | `data-section="push"` | Active |
| Automation | `data-section="automation"` | Active |
| Fundee Update | `data-section="fundee-update"` | Placeholder (Coming Soon) |
| Language | `data-section="language"` | Placeholder (Coming Soon) |
| Glossary | `data-section="glossary"` | Active |
| Admin Panel | `data-section="admin"` | Active (super admin only) |

### Section Initialization Pattern

Each section uses lazy-loading — initialized on first visit via `switchSection()`:
- `initContentHub()`, `initPullSection()`, `initTranslateSection()`, `initPushSection()`, `initAutomationSection()`, `initGlossarySection()`, `initAdminSection()`

### Refresh Button

The global refresh button (top-right) is context-aware — it calls the appropriate reload function based on the active section (e.g., `loadHubArticles()`, `loadPullArticles()`, `autoRefreshStatus()`).

---

## Automation

Two automation cards, each with independent toggle:

### 1. Auto Sync Source List
- **Cron:** `0 0 * * *` (daily at 00:00 UTC)
- **Endpoint:** `GET /api/cron/sync`
- **Action:** Calls `sync_source_list()` from `pull_service.py` — fetches article metadata from Intercom and upserts into `pull_registry`.
- **Settings Key:** `auto_sync_pull`

### 2. Auto Pull Articles
- **Cron:** `30 1 * * *` (daily at 01:30 UTC)
- **Endpoint:** `GET /api/cron/pull`
- **Action:** Calls `run_auto_pull()` from `automation_service.py` — finds all articles with `never_pulled` or `updated_in_source` status and pulls their full content.
- **Settings Key:** `auto_pull_articles`

### Cron Authentication
Cron endpoints are in `PUBLIC_PATHS` (bypass user auth). They check for `x-vercel-cron` header (sent by Vercel automatically) or a `CRON_SECRET` bearer token.

---

## Key API Routes

### Auth
- `POST /api/auth/login` — Login with email/password
- `GET /api/auth/me` — Get current user info
- `POST /api/auth/logout` — Logout
- `GET /api/auth/admins` — List admins (super admin only)
- `POST /api/auth/admins` — Add admin (super admin only)
- `PUT /api/auth/admins/<id>` — Update admin (super admin only)
- `DELETE /api/auth/admins/<id>` — Delete admin (super admin only)

### Pull
- `GET /api/pull/articles` — List pull registry articles (paginated, searchable, filterable)
- `POST /api/pull/sync-source` — Sync article metadata from Intercom
- `POST /api/pull/execute` — Pull full content for selected articles
- `GET /api/pull/stats` — Pull statistics

### Translate
- `GET /api/translate/articles` — List articles with translation statuses
- `GET /api/translate/article/<id>` — Article detail with translation previews
- `POST /api/translate/execute` — Execute translation for selected articles/languages

### Push
- `GET /api/push/articles` — List articles for push
- `GET /api/push/articles-multi` — List articles with multi-locale status matrix
- `POST /api/push/execute` — Push translations to Intercom

### Content Hub
- `GET /api/content-hub/articles` — List articles with health status
- `GET /api/dashboard/stats` — Dashboard statistics

### Glossary
- `GET /api/glossary/list` — List glossaries
- `POST /api/glossary/create` — Create glossary
- `DELETE /api/glossary/<id>` — Delete glossary (hard delete)
- `POST /api/glossary/<id>/import` — Import XLSX
- `GET /api/glossary/<id>/export` — Export XLSX

### Automation
- `GET /api/automation/settings?key=<key>` — Get automation settings
- `POST /api/automation/toggle` — Toggle automation (body: `{key, enabled}`)
- `POST /api/automation/run-now` — Manual trigger (body: `{key}`)
- `GET /api/automation/table-status` — Check if table exists
- `POST /api/automation/create-table` — Auto-create table
- `GET /api/cron/sync` — Cron endpoint for auto-sync (00:00 UTC)
- `GET /api/cron/pull` — Cron endpoint for auto-pull (01:30 UTC)

---

## Environment Variables (Vercel)

| Variable | Description |
|----------|-------------|
| `INTERCOM_ACCESS_TOKEN` | Intercom API token (base64 encoded) |
| `OPENAI_API_KEY` | OpenAI API key for GPT translation |
| `OPENAI_MODEL` | Model name (default: `gpt-4o-mini`) |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Supabase service role key |
| `SUPER_ADMIN_EMAIL` | Super admin email (default: `sazzad@nextventures.io`) |
| `SUPER_ADMIN_PASSWORD` | Super admin password (default: `Sazzad123`) |
| `FLASK_SECRET_KEY` | Flask secret for JWT signing |
| `SUPABASE_DB_URL` | (Optional) Direct Postgres URI for auto-creating tables |
| `CRON_SECRET` | (Optional) Bearer token for cron endpoint auth |

---

## Target Languages

```python
{
    "ar": "Arabic (UAE)",
    "zh-CN": "Chinese - Simplified",
    "fr": "French",
    "de": "German",
    "hi": "Hindi",
    "it": "Italian",
    "ja": "Japanese - Japan",
    "fa": "Persian",
    "es": "Spanish",
    "th": "Thai",
    "pt-BR": "Portuguese - Brazil"
}
```

Base language: `en` (English)

---

## Development Notes

- **Local run:** Set env vars in `.env`, run `python app.py` → `http://127.0.0.1:5000`
- **Deploy:** Push to `main` branch → Vercel auto-deploys
- **Duplicate function:** `escapeHtml()` is defined twice in `app.js` (lines ~736 and ~1201) — second overrides first, no errors
- **Table setup:** Each module (Pull, Glossary, Admin, Automation) has its own table setup banner with "Auto-Create Table" and "Copy SQL" buttons
- **Pull statuses:** `never_pulled`, `updated_in_source` (Needs Update), `up_to_date`, `failed`, `pulling`
- **Health statuses:** `NEEDS_PULL`, `OUTDATED`, `NEEDS_TRANSLATION`, `NEEDS_PUSH`, `COMPLETE`, `FAILED`
