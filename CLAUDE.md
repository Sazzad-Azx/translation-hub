# Translation Hub - Project Guide

## Overview
Intercom Translation Workflow — a Python/Flask web app that automatically translates Intercom FAQ articles to 40+ languages using OpenAI GPT models, with Supabase as backend storage.

## Quick Start
```bash
pip install -r requirements.txt
python run_web.py
# Server starts at http://localhost:5000
```

## Tech Stack
- **Backend**: Python 3.8+, Flask
- **Translation**: OpenAI GPT (gpt-4.1 / gpt-4.1-mini)
- **Storage**: Supabase (PostgreSQL)
- **Frontend**: HTML templates + static assets
- **APIs**: Intercom API, OpenAI API

## Key Files
- `app.py` — Main Flask application with all routes
- `run_web.py` — Entry point to start the web server
- `config.py` — All configuration (API keys, languages, Supabase)
- `main.py` — CLI entry point for batch translation
- `translator.py` — GPT translation logic
- `intercom_client.py` — Intercom API client
- `supabase_client.py` — Supabase database client
- `translate_service.py` — Translation orchestration service
- `pull_service.py` — Pull articles from Intercom
- `push_service.py` — Push translations to Intercom
- `sync_service.py` — Sync workflow
- `language_service.py` — Language management
- `glossary_service.py` — Glossary/terminology management
- `auth_service.py` — Authentication
- `templates/` — Jinja2 HTML templates
- `static/` — CSS, JS, images
- `api/` — API route modules

## Environment Variables
Required in `.env`:
- `INTERCOM_ACCESS_TOKEN` — Intercom API token
- `OPENAI_API_KEY` — OpenAI API key
- `SUPABASE_URL` — Supabase project URL
- `SUPABASE_SERVICE_KEY` — Supabase service role key

## Target Languages
11 default languages (Arabic, Chinese, French, German, Hindi, Italian, Japanese, Persian, Spanish, Thai, Portuguese-BR), expandable to 40+ via config.

## API Endpoints
- `GET /api/health` — Health check
- `GET /api/article-translations` — List translations
- `POST /api/article-translations` — Save a translation
