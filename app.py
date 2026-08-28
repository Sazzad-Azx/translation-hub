"""
Flask web application for Intercom Translation Workflow
"""
import os
import sys
import json
from io import BytesIO
from typing import Optional, Dict

# Fix Windows console encoding for Unicode characters
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from flask import Flask, render_template, jsonify, request, send_file, g
from flask_cors import CORS
from functools import wraps
from intercom_client import IntercomClient
from translator import GPTTranslator
from workflow import TranslationWorkflow
from config import TARGET_LANGUAGES, BASE_LANGUAGE
import auth_service
import faq_search_service
import product_context

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
CORS(app, supports_credentials=True)


# The multi-tenant proxies (product_context.LazyDict / LazyStr) behave like
# dict/str for app logic but aren't real dict/str, so Flask's default JSON
# encoder can't serialize them if one lands in a response (e.g. TARGET_LANGUAGES
# returned as `languages`). Teach the encoder to materialize them.
from flask.json.provider import DefaultJSONProvider


class _TenantJSONProvider(DefaultJSONProvider):
    @staticmethod
    def default(o):
        if isinstance(o, product_context.LazyDict):
            return dict(o)
        if isinstance(o, product_context.LazyStr):
            return str(o)
        return DefaultJSONProvider.default(o)


app.json = _TenantJSONProvider(app)


@app.before_request
def log_request():
    """Log method and path for every request (server-side debug)."""
    try:
        print(f"{request.method} {request.path}", flush=True)
    except OSError:
        pass


@app.before_request
def resolve_active_product():
    """Resolve the active product (multi-tenant) onto flask.g for this request.

    Reads X-Product header / ?product= / cookie, falling back to the default
    product. Purely populates g.product — nothing breaks if a request omits it.
    """
    product_context.load_active_product()


@app.context_processor
def inject_brand():
    """Expose active product branding + the switcher's product list to templates."""
    import config as _config
    prod = product_context.current_product()
    products = [
        {"id": pid, "name": spec["name"], "short": spec["short"]}
        for pid, spec in _config.PRODUCTS.items()
    ]
    return {"brand": prod["brand"], "active_product": prod["id"], "products": products}


# ─── Auth helpers ──────────────────────────────────────────────
PUBLIC_PATHS = {'/', '/favicon.ico', '/api/health', '/api/auth/login', '/api/cron/sync', '/api/cron/pull', '/api/cron/sweep', '/api/faq/search'}
PUBLIC_PREFIXES = ('/static/',)


def _get_token():
    """Extract bearer token from Authorization header or cookie."""
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        return auth[7:]
    return request.cookies.get('auth_token', '')


@app.before_request
def require_auth():
    """Block unauthenticated access to API and pages."""
    path = request.path
    # Allow public paths
    if path in PUBLIC_PATHS:
        return None
    for prefix in PUBLIC_PREFIXES:
        if path.startswith(prefix):
            return None
    # Check token
    token = _get_token()
    session = auth_service.validate_session(token)
    if not session:
        if path.startswith('/api/'):
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        # For page requests, the frontend will show login
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    # Store session in request context
    request.auth_session = session


def require_super_admin(f):
    """Decorator: only super_admin can access this route."""
    @wraps(f)
    def decorated(*args, **kwargs):
        session = getattr(request, 'auth_session', None)
        if not session or session.get('role') != 'super_admin':
            return jsonify({'success': False, 'error': 'Forbidden: super admin only'}), 403
        return f(*args, **kwargs)
    return decorated


@app.errorhandler(404)
def not_found(e):
    """Return JSON for 404 so the API never returns HTML."""
    return jsonify({'success': False, 'error': 'Not found', 'message': str(e)}), 404


@app.errorhandler(500)
def server_error(e):
    """Return JSON for 500 so the API never returns HTML."""
    return jsonify({'success': False, 'error': 'Internal server error', 'message': str(e)}), 500


@app.errorhandler(Exception)
def handle_exception(e):
    """Catch-all: return JSON for any unhandled exception (no HTML)."""
    if hasattr(e, 'code') and e.code == 404:
        return jsonify({'success': False, 'error': 'Not found', 'message': str(e)}), 404
    if hasattr(e, 'code') and e.code == 500:
        return jsonify({'success': False, 'error': 'Internal server error', 'message': str(e)}), 500
    return jsonify({'success': False, 'error': 'Error', 'message': str(e)}), 500


# ─── Per-product API clients (multi-tenant) ──────────────────────────────────
# Clients are bound to the ACTIVE product and cached on flask.g for the duration
# of a single request. They are deliberately NOT module globals: a warm serverless
# instance persists module state across requests, so a global client would leak
# one product's Intercom token / OpenAI key into the next request for a different
# product. The g-cache is keyed by product id, so if the active product changes
# mid-request (e.g. the multi-product cron loop) the client is rebuilt correctly.

def get_intercom():
    """Intercom client for the active product (cached per request)."""
    prod = product_context.current_product()
    if getattr(g, "_intercom", None) is None or getattr(g, "_intercom_pid", None) != prod["id"]:
        g._intercom = IntercomClient(access_token=prod["intercom_token"] or None)
        g._intercom_pid = prod["id"]
    return g._intercom


def get_translator():
    """GPT translator for the active product (cached per request)."""
    prod = product_context.current_product()
    if getattr(g, "_translator", None) is None or getattr(g, "_translator_pid", None) != prod["id"]:
        g._translator = GPTTranslator(api_key=prod["openai_key"] or None)
        g._translator_pid = prod["id"]
    return g._translator


def get_workflow():
    """Translation workflow bound to the active product's clients (per request)."""
    prod = product_context.current_product()
    if getattr(g, "_workflow", None) is None or getattr(g, "_workflow_pid", None) != prod["id"]:
        g._workflow = TranslationWorkflow(get_intercom(), get_translator())
        g._workflow_pid = prod["id"]
    return g._workflow


def init_clients():
    """Deprecated no-op. Clients are now resolved per-request via get_intercom()/
    get_translator()/get_workflow(). Kept so existing call sites stay valid."""
    return None

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')


@app.route('/favicon.ico')
def favicon():
    """Return empty favicon to prevent 404 errors"""
    from flask import Response
    return Response(status=204)  # No Content


@app.route('/api/health', methods=['GET'])
def health():
    """Health check: returns JSON {ok: true} for monitoring/curl tests."""
    return jsonify({'ok': True})


# ─── FAQ search (called by fn-copilot, API key auth) ─────────
@app.route('/api/faq/search', methods=['GET'])
def faq_search():
    """
    Search English FAQ articles. Protected by X-API-Key header.
    Query params: q (required), limit (optional, max 20).
    Returns: {ok: true, results: [{title, snippet, url}]}
    """
    api_key = request.headers.get('X-API-Key', '').strip()
    expected = os.environ.get('FAQ_SEARCH_API_KEY', '').strip()
    if not expected or api_key != expected:
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 401

    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({'ok': False, 'error': 'q parameter is required'}), 400

    try:
        limit = min(int(request.args.get('limit', 20)), 20)
    except (ValueError, TypeError):
        limit = 20

    results = faq_search_service.search_articles(q, limit=limit)
    return jsonify({'ok': True, 'results': results})


# ─── Auth API routes ──────────────────────────────────────────
@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    """Login with email and password."""
    data = request.get_json(force=True)
    email = data.get('email', '')
    password = data.get('password', '')
    if not email or not password:
        return jsonify({'success': False, 'error': 'Email and password required'}), 400
    try:
        result = auth_service.login(email, password)
    except EnvironmentError as e:
        return jsonify({'success': False, 'error': f'Server misconfiguration: {e}'}), 500
    if not result:
        return jsonify({'success': False, 'error': 'Invalid email or password'}), 401
    resp = jsonify({'success': True, **result})
    resp.set_cookie('auth_token', result['token'], httponly=True, samesite='Lax', max_age=86400)
    return resp


@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    """Logout and invalidate session."""
    token = _get_token()
    auth_service.logout(token)
    resp = jsonify({'success': True})
    resp.delete_cookie('auth_token')
    return resp


@app.route('/api/auth/me', methods=['GET'])
def auth_me():
    """Get current user info."""
    session = getattr(request, 'auth_session', None)
    if not session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    return jsonify({
        'success': True,
        'email': session['email'],
        'name': session['name'],
        'role': session['role'],
    })


@app.route('/api/auth/admins', methods=['GET'])
@require_super_admin
def auth_list_admins():
    """List all admins (super admin only)."""
    admins = auth_service.list_admins()
    return jsonify({'success': True, 'admins': admins})


@app.route('/api/auth/admins', methods=['POST'])
@require_super_admin
def auth_create_admin():
    """Create a new admin (super admin only)."""
    data = request.get_json(force=True)
    email = data.get('email', '')
    password = data.get('password', '')
    name = data.get('name', '')
    role = data.get('role', 'admin')
    if not email or not password or not name:
        return jsonify({'success': False, 'error': 'Email, password, and name are required'}), 400
    result = auth_service.create_admin(email, password, name, role)
    if result.get('success'):
        return jsonify(result), 201
    return jsonify(result), 400


@app.route('/api/auth/admins/<int:admin_id>', methods=['PUT'])
@require_super_admin
def auth_update_admin(admin_id):
    """Update an admin (super admin only)."""
    data = request.get_json(force=True)
    result = auth_service.update_admin(admin_id, data)
    if result.get('success'):
        return jsonify(result)
    return jsonify(result), 400


@app.route('/api/auth/admins/<int:admin_id>', methods=['DELETE'])
@require_super_admin
def auth_delete_admin(admin_id):
    """Delete an admin (super admin only)."""
    result = auth_service.delete_admin(admin_id)
    if result.get('success'):
        return jsonify(result)
    return jsonify(result), 400


@app.route('/api/auth/admins-table', methods=['GET'])
@require_super_admin
def auth_check_admins_table():
    """Check if admins table exists."""
    exists = auth_service.ensure_admins_table()
    return jsonify({'success': True, 'exists': exists, 'sql': auth_service.get_admins_table_sql()})


@app.route('/api/auth/admins-table/create', methods=['POST'])
@require_super_admin
def auth_create_admins_table():
    """Auto-create admins table via pg8000 or Supabase."""
    result = auth_service.auto_create_table()
    return jsonify(result)


def _format_articles_for_frontend(articles):
    """Format article dicts for frontend."""
    formatted = []
    for article in articles:
        body = article.get('body') or ''
        formatted.append({
            'id': article.get('id'),
            'title': article.get('title'),
            'description': article.get('description', ''),
            'body': body[:200] + '...' if len(body) > 200 else body,
            'state': article.get('state', 'unknown')
        })
    return formatted


@app.route('/api/articles', methods=['GET'])
def get_articles():
    """Get articles from Intercom (optional collection/tag filter)."""
    try:
        init_clients()
        collection_id = request.args.get('collection_id')
        tag_id = request.args.get('tag_id')
        from_help_center = request.args.get('from_help_center', '').lower() == 'true'

        if from_help_center:
            # Fetch from FundedNext Help Center (same source as fetch-and-store)
            all_articles = []
            try:
                all_articles = get_intercom().get_fundednext_help_center_articles(limit=50, fetch_full=True)
            except Exception:
                pass
            if not all_articles:
                seen = set()
                for a in get_intercom().get_all_help_center_articles():
                    aid = a.get('id')
                    if aid is not None and str(aid) not in seen:
                        seen.add(str(aid))
                        all_articles.append(a)
                for a in get_intercom().get_articles():
                    aid = a.get('id')
                    if aid is not None and str(aid) not in seen:
                        seen.add(str(aid))
                        all_articles.append(a)
            articles = all_articles[:50]
            for i, a in enumerate(articles):
                if not (a.get('body') or a.get('title')):
                    try:
                        full = get_intercom().get_article(str(a.get('id', '')))
                        if full:
                            articles[i] = full
                    except Exception:
                        pass
        else:
            articles = get_intercom().get_articles(
                collection_id=collection_id,
                tag_id=tag_id
            )

        formatted_articles = _format_articles_for_frontend(articles)
        return jsonify({
            'success': True,
            'articles': formatted_articles,
            'count': len(formatted_articles)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/article/<article_id>', methods=['GET'])
def get_article(article_id):
    """Get a specific article"""
    try:
        init_clients()
        article = get_intercom().get_article(article_id)
        
        return jsonify({
            'success': True,
            'article': {
                'id': article.get('id'),
                'title': article.get('title'),
                'description': article.get('description', ''),
                'body': article.get('body', '')
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def _get_article_from_supabase(article_id: str) -> Optional[Dict]:
    """Try to get article from Supabase (intercom_articles or content tables)."""
    try:
        from supabase_client import list_articles
        from content_supabase import list_articles_from_content
        
        # Try intercom_articles table first
        try:
            articles = list_articles()
            for a in articles:
                if str(a.get('intercom_id', '')) == str(article_id):
                    return {
                        'id': a.get('intercom_id'),
                        'title': a.get('title', ''),
                        'description': a.get('description', ''),
                        'body': a.get('body', '')
                    }
        except Exception:
            pass
        
        # Try content_items/versions tables
        try:
            import requests
            _pctx = product_context.current_product(); SUPABASE_URL, SUPABASE_SERVICE_KEY = _pctx["supabase_url"], _pctx["supabase_key"]
            if SUPABASE_URL and SUPABASE_SERVICE_KEY:
                REST_BASE = f"{SUPABASE_URL.rstrip('/')}/rest/v1"
                headers = product_context.supabase_headers()
                # Find content_item by external_id
                items_url = f"{REST_BASE}/intercom_content_items"
                items_resp = requests.get(
                    items_url,
                    headers=headers,
                    params={"external_id": f"eq.{article_id}", "select": "id"},
                    timeout=30,
                )
                if items_resp.ok and items_resp.text:
                    items = items_resp.json()
                    if items and len(items) > 0:
                        item_id = items[0].get('id')
                        # Get version with locale='en' or first available
                        versions_url = f"{REST_BASE}/intercom_content_versions"
                        versions_resp = requests.get(
                            versions_url,
                            headers=headers,
                            params={"content_item_id": f"eq.{item_id}", "select": "title,body_raw,locale", "order": "locale.asc"},
                            timeout=30,
                        )
                        if versions_resp.ok and versions_resp.text:
                            versions = versions_resp.json()
                            if versions and len(versions) > 0:
                                # Prefer 'en' locale, else first
                                version = next((v for v in versions if v.get('locale') == 'en'), versions[0])
                                return {
                                    'id': article_id,
                                    'title': version.get('title', ''),
                                    'description': '',
                                    'body': version.get('body_raw', '')
                                }
        except Exception:
            pass
    except Exception:
        pass
    return None

@app.route('/api/preview', methods=['POST'])
def preview_translation():
    """Preview translation for a single language"""
    try:
        init_clients()
        data = request.json
        article_id = data.get('article_id')
        language = data.get('language')
        
        if not article_id or not language:
            return jsonify({
                'success': False,
                'error': 'article_id and language are required'
            }), 400
        
        # Try to get article from Supabase first
        article = _get_article_from_supabase(article_id)
        
        # If not in Supabase, try Intercom API
        if not article:
            try:
                article = get_intercom().get_article(article_id)
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': f'Article not found in Supabase or Intercom: {str(e)}'
                }), 404
        
        # Ensure article has required fields
        if not article.get('title') and not article.get('body'):
            return jsonify({
                'success': False,
                'error': 'Article has no content to translate'
            }), 400
        
        # Translate
        translated = get_translator().translate_article(
            article,
            target_language=language,
            source_language=BASE_LANGUAGE
        )
        
        return jsonify({
            'success': True,
            'translation': translated,
            'language': language,
            'language_name': TARGET_LANGUAGES.get(language, language)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/translate', methods=['POST'])
def translate_articles():
    """Translate articles to selected languages"""
    try:
        init_clients()
        data = request.json
        article_ids = data.get('article_ids', [])
        languages = data.get('languages', list(TARGET_LANGUAGES.keys()))
        
        if not article_ids:
            return jsonify({
                'success': False,
                'error': 'At least one article ID is required'
            }), 400
        
        # Run workflow
        results = get_workflow().run(
            article_ids=article_ids,
            languages=languages
        )
        
        return jsonify({
            'success': True,
            'results': results
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/languages', methods=['GET'])
def get_languages():
    """Get available target languages (refreshes from Supabase)."""
    import language_service
    language_service.load_active_languages()
    return jsonify({
        'success': True,
        'languages': TARGET_LANGUAGES,
        'base_language': BASE_LANGUAGE
    })


@app.route('/api/languages/available', methods=['GET'])
def languages_available():
    """Return the full catalogue of languages that can be added."""
    from config import ALL_AVAILABLE_LANGUAGES
    import language_service
    active = language_service.load_active_languages()
    available = {c: n for c, n in ALL_AVAILABLE_LANGUAGES.items() if c not in active}
    return jsonify({'success': True, 'available': available, 'active_codes': list(active.keys())})


@app.route('/api/languages/add', methods=['POST'])
def languages_add():
    """Add one or more languages. Body: {codes: ["ko", "ru", ...]}"""
    import language_service
    data = request.get_json(force=True)
    codes = data.get('codes', [])
    if not codes:
        return jsonify({'success': False, 'error': 'No language codes provided'}), 400

    result = language_service.add_languages(codes)
    return jsonify(result)


@app.route('/api/languages/<code>/remove', methods=['DELETE'])
def languages_remove(code):
    """Remove (deactivate) a language."""
    import language_service
    result = language_service.remove_language(code)
    if result.get('success'):
        return jsonify(result)
    return jsonify(result), 500


@app.route('/api/languages/table-setup', methods=['GET'])
def languages_table_check():
    """Check if the target_languages table exists."""
    import language_service
    exists = language_service.table_exists()
    return jsonify({'success': True, 'exists': exists})


@app.route('/api/languages/create-table', methods=['POST'])
def languages_create_table():
    """Auto-create the target_languages table and seed defaults."""
    import language_service
    result = language_service.auto_create_table()
    if result.get('success'):
        language_service.load_active_languages()
    return jsonify(result)


@app.route('/api/languages/stats', methods=['GET'])
def language_stats():
    """
    Per-language translation statistics.
    Returns translated / total counts for each target locale.
    """
    try:
        from translation_supabase import list_article_translations
        from pull_service import list_pull_articles
        import language_service
        language_service.load_active_languages()

        # Total pulled articles (denominator for each language)
        total_articles = 0
        try:
            result = list_pull_articles(page=1, page_size=1)
            total_articles = result.get('total', 0)
        except Exception:
            pass

        # All translations
        translations = []
        try:
            translations = list_article_translations()
        except Exception:
            pass

        # Count per locale
        per_locale = {}
        for code, name in TARGET_LANGUAGES.items():
            per_locale[code] = {
                'code': code,
                'name': name,
                'translated': 0,
                'pushed': 0,
                'outdated': 0,
                'failed': 0,
                'total': total_articles,
            }

        for t in translations:
            locale = t.get('target_locale', '')
            status = (t.get('status') or '').lower()
            if locale not in per_locale:
                continue
            if status in ('translated', 'pushed'):
                per_locale[locale]['translated'] += 1
            if status == 'pushed':
                per_locale[locale]['pushed'] += 1
            if status == 'outdated':
                per_locale[locale]['outdated'] += 1
            if status == 'failed':
                per_locale[locale]['failed'] += 1

        return jsonify({
            'success': True,
            'total_articles': total_articles,
            'base_language': BASE_LANGUAGE,
            'languages': per_locale,
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _make_json_serializable(obj):
    """Convert dict values to JSON-serializable types (e.g. datetime, uuid -> str)."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {k: _make_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_make_json_serializable(v) for v in obj]
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    if hasattr(obj, 'hex'):
        return str(obj)
    return obj


@app.route('/api/article-translations', methods=['GET', 'POST'])
def article_translations_api():
    """
    GET: List saved translations.
    POST: Save (upsert) a translation. Body: parent_intercom_article_id, target_locale, translated_title, translated_body_html, status.
    """
    if request.method == 'GET':
        try:
            from translation_supabase import list_article_translations as list_translations
            rows = list_translations()
            return jsonify({
                'success': True,
                'translations': rows,
                'count': len(rows)
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    if request.method == 'POST':
        try:
            data = request.get_json(silent=True) or {}
            parent_id = data.get('parent_intercom_article_id')
            target_locale = data.get('target_locale')
            translated_title = data.get('translated_title', '')
            translated_body_html = data.get('translated_body_html', '')
            status = (data.get('status') or 'draft').lower()
            if status not in ('draft', 'ready'):
                status = 'draft'
            if not parent_id or not target_locale:
                return jsonify({
                    'success': False,
                    'error': 'parent_intercom_article_id and target_locale are required'
                }), 400
            from translation_supabase import upsert_article_translation
            row = upsert_article_translation(
                parent_intercom_article_id=str(parent_id),
                target_locale=str(target_locale),
                translated_title=translated_title,
                translated_body_html=translated_body_html,
                status=status,
                source_locale=data.get('source_locale') or 'en',
                engine=data.get('engine'),
                model=data.get('model'),
                source_checksum=data.get('source_checksum'),
            )
            return jsonify({
                'success': True,
                'translation': _make_json_serializable(row),
                'message': 'Translation saved',
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    return jsonify({'success': False, 'error': 'Method not allowed'}), 405


@app.route('/api/article-translations/<translation_id>', methods=['GET'])
def get_article_translation(translation_id):
    """Get one saved translation by id (for viewing saved HTML)."""
    try:
        from translation_supabase import get_article_translation_by_id
        row = get_article_translation_by_id(translation_id)
        if not row:
            return jsonify({
                'success': False,
                'error': 'Translation not found'
            }), 404
        return jsonify({
            'success': True,
            'translation': row
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ── Daily API Cost Caching (Vercel → Supabase) ──
COST_API_URL = os.getenv('COST_API_URL', '').rstrip('/')
_cost_keys_raw = os.getenv('COST_TARGET_KEYS', '')
COST_TARGET_KEYS = [k.strip() for k in _cost_keys_raw.split(',') if k.strip()]

# Cost data is product-agnostic (one shared analyzer + key set), so every product
# reads/writes the SAME rows in `public.daily_api_costs` — never the active
# product's isolated schema. This keeps FN Market's Cost Analysis chart identical
# to FundedNext's, with no per-schema duplication or first-load populate gap.
COST_SCHEMA = 'public'

def _fetch_and_upsert_dates(dates_to_fetch):
    """Fetch per-key costs for a list of dates from Vercel API and upsert to Supabase."""
    import datetime
    import requests as _req
    _pctx = product_context.current_product(); SUPABASE_URL, SUPABASE_SERVICE_KEY = _pctx["supabase_url"], _pctx["supabase_key"]

    if not dates_to_fetch:
        return

    rows_to_upsert = []
    for d in dates_to_fetch:
        ds = d.isoformat()
        try:
            api_resp = _req.get(
                f'{COST_API_URL}/openai-usage',
                params={'start_date': ds, 'end_date': ds},
                timeout=15
            )
            if api_resp.status_code == 200:
                data = api_resp.json()
                api_keys = data.get('apiKeys', [])
                if not isinstance(api_keys, list):
                    api_keys = list(api_keys.values())
                found_keys = set()
                for key in api_keys:
                    if key.get('keyId') in COST_TARGET_KEYS:
                        found_keys.add(key['keyId'])
                        rows_to_upsert.append({
                            'date': ds,
                            'key_id': key['keyId'],
                            'cost': round(key.get('cost', 0), 6),
                            'requests': key.get('requests', 0),
                            'updated_at': datetime.datetime.utcnow().isoformat() + 'Z',
                        })
                # Store $0 rows for target keys not found, so this date
                # is marked as "checked" and won't be re-fetched every load.
                for missing_key in set(COST_TARGET_KEYS) - found_keys:
                    rows_to_upsert.append({
                        'date': ds,
                        'key_id': missing_key,
                        'cost': 0,
                        'requests': 0,
                        'updated_at': datetime.datetime.utcnow().isoformat() + 'Z',
                    })
        except Exception:
            continue

    if rows_to_upsert:
        headers = product_context.supabase_headers({'Prefer': 'resolution=merge-duplicates'}, schema=COST_SCHEMA)
        _req.post(
            f'{SUPABASE_URL}/rest/v1/daily_api_costs',
            headers=headers,
            json=rows_to_upsert,
            timeout=15
        )


def _get_missing_dates():
    """Return list of missing dates (excluding today) since 2025-01-01."""
    import datetime
    import requests as _req
    _pctx = product_context.current_product(); SUPABASE_URL, SUPABASE_SERVICE_KEY = _pctx["supabase_url"], _pctx["supabase_key"]

    today = datetime.date.today()
    start_date = datetime.date(2026, 1, 1)

    resp = _req.get(
        f'{SUPABASE_URL}/rest/v1/daily_api_costs',
        headers=product_context.supabase_headers(schema=COST_SCHEMA),
        params={
            'select': 'date',
            'date': f'gte.{start_date.isoformat()}',
            'order': 'date.asc',
        },
        timeout=15
    )
    existing_dates = set()
    if resp.status_code == 200 and resp.text:
        for row in resp.json():
            existing_dates.add(row['date'])

    missing = []
    d = start_date
    while d < today:  # exclude today
        if d.isoformat() not in existing_dates:
            missing.append(d)
        d += datetime.timedelta(days=1)
    return missing


def _sync_past_costs():
    """Sync missing past days (synchronous). These are finalized and won't change."""
    missing = _get_missing_dates()
    if missing:
        _fetch_and_upsert_dates(missing)


def _sync_today_cost():
    """Refresh today's cost (background). Today is still accumulating."""
    import datetime
    _fetch_and_upsert_dates([datetime.date.today()])


def _get_cached_daily_costs(days=None, start_date=None, end_date=None):
    """Read cached daily costs from Supabase.
    If days is given, only return last N days.
    If start_date/end_date are given (YYYY-MM-DD strings), filter to that range.
    Otherwise return all cached data.
    Returns list of {date, cost} dicts (summed across target keys per day).
    """
    import datetime
    import requests as _req
    _pctx = product_context.current_product(); SUPABASE_URL, SUPABASE_SERVICE_KEY = _pctx["supabase_url"], _pctx["supabase_key"]

    params = {
        'select': 'date,cost,key_id',
        'key_id': f'in.({",".join(COST_TARGET_KEYS)})',
        'order': 'date.asc',
    }
    if start_date:
        params['date'] = f'gte.{start_date}'
    elif days:
        sd = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
        params['date'] = f'gte.{sd}'

    if end_date:
        if 'date' in params:
            # PostgREST: use 'and' filter for range
            params['and'] = f'(date.gte.{start_date},date.lte.{end_date})'
            del params['date']
        else:
            params['date'] = f'lte.{end_date}'

    resp = _req.get(
        f'{SUPABASE_URL}/rest/v1/daily_api_costs',
        headers=product_context.supabase_headers(schema=COST_SCHEMA),
        params=params,
        timeout=15
    )
    if resp.status_code != 200:
        return []

    # Sum costs per day across keys
    daily = {}
    for row in resp.json():
        d = row['date']
        daily[d] = daily.get(d, 0) + (row.get('cost') or 0)

    return [{'date': d, 'cost': round(c, 4)} for d, c in sorted(daily.items())]


@app.route('/api/dashboard/stats', methods=['GET'])
def dashboard_stats():
    """
    Dashboard statistics: total articles, translations, cost analysis,
    top changed articles, and recent activity.
    Optional query params: start_date, end_date (YYYY-MM-DD) for source changes filter.
    """
    import datetime, time as _time
    from concurrent.futures import ThreadPoolExecutor
    try:
        _t0 = _time.time()
        now = datetime.datetime.utcnow()
        week_ago = now - datetime.timedelta(days=7)
        month_ago = now - datetime.timedelta(days=30)


        import re as _re
        _LOCALE_PREFIX = _re.compile(r'^\[[A-Z]{2}(?:-[A-Z]{1,4})?\]\s+', _re.IGNORECASE)

        _pctx = product_context.current_product()
        SUPABASE_URL, SUPABASE_SERVICE_KEY = _pctx["supabase_url"], _pctx["supabase_key"]
        from config import TARGET_LANGUAGES as _TL
        import requests as _req_pr

        _SB_HEADERS = product_context.supabase_headers()

        # Dashboard-specific translation fetcher: only the activity feed uses
        # this result (total_translated now comes from list_translate_articles),
        # and the feed renders at most 20 entries, so 50 rows is plenty. The
        # explicit low cap also keeps us well under Supabase's 1000-row default.
        def _fetch_translations_for_dashboard():
            try:
                resp = _req_pr.get(
                    f"{SUPABASE_URL}/rest/v1/article_translations",
                    headers=_SB_HEADERS,
                    params={
                        "select": "parent_intercom_article_id,translated_title,created_at,updated_at,pushed_at",
                        "order": "updated_at.desc",
                        "limit": 50,
                    },
                    timeout=15,
                )
                if resp.status_code != 200:
                    return []
                data = resp.json()
                return data if isinstance(data, list) else []
            except Exception:
                return []

        def _fetch_all_pull_rows():
            rows = []
            offset = 0
            try:
                while True:
                    resp = _req_pr.get(
                        f"{SUPABASE_URL}/rest/v1/pull_registry",
                        headers=_SB_HEADERS,
                        params={
                            "select": "intercom_id,title,source_updated_at,pulled_at",
                            "limit": 1000,
                            "offset": offset,
                        },
                        timeout=15,
                    )
                    if resp.status_code != 200:
                        break
                    batch = resp.json()
                    if not batch:
                        break
                    rows.extend(batch)
                    if len(batch) < 1000:
                        break
                    offset += 1000
            except Exception:
                pass
            return rows

        def _fetch_last_sync_str():
            try:
                from pull_service import get_last_sync_time
                return get_last_sync_time()
            except Exception:
                return None

        # Worker threads don't inherit Flask's g → rebind the active product so
        # dashboard reads hit the active tenant's schema, not the default's.
        _wcp = product_context.with_current_product
        with ThreadPoolExecutor(max_workers=3) as _ex:
            _f_trans = _ex.submit(_wcp(_fetch_translations_for_dashboard))
            _f_pull = _ex.submit(_wcp(_fetch_all_pull_rows))
            _f_sync = _ex.submit(_wcp(_fetch_last_sync_str))
            all_translations = _f_trans.result()
            all_pull_rows = _f_pull.result()
            last_sync_str = _f_sync.result()
        print(f"[TIMING] parallel fetch: {_time.time()-_t0:.1f}s", flush=True)

        # ---------- Total articles (from pull_registry, excluding [LOCALE] prefixed) ----------
        # Same logic as Control Tower so both counts always match
        total_articles = len([r for r in all_pull_rows
                              if not _LOCALE_PREFIX.match(r.get('title') or '')])

        # ---------- Fully translated count (same logic as Translate page) ----------
        # Reuse translate_service so both pages always agree
        from translate_service import list_translate_articles as _list_ta
        try:
            _ta_result = _list_ta(page=1, page_size=1)  # counts cover all articles
            _ta_counts = _ta_result.get("counts", {})
            total_translated = (_ta_counts.get("TRANSLATED", 0)
                                + _ta_counts.get("APPROVED", 0))
        except Exception:
            total_translated = 0

        def _parse_ts(s):
            if not s:
                return None
            try:
                return datetime.datetime.fromisoformat(s.replace('Z', '+00:00').replace('+00:00', ''))
            except Exception:
                try:
                    return datetime.datetime.strptime(s[:19], '%Y-%m-%dT%H:%M:%S')
                except Exception:
                    return None

        # Count unique source articles changed in week/month
        changed_week = 0
        changed_month = 0
        for row in all_pull_rows:
            ts = _parse_ts(row.get('source_updated_at'))
            if ts:
                if ts >= week_ago:
                    changed_week += 1
                if ts >= month_ago:
                    changed_month += 1

        # ---------- Weekly breakdown (per day of week) — source article changes ----------
        changes_weekly = [0] * 7  # Mon-Sun
        for row in all_pull_rows:
            ts = _parse_ts(row.get('source_updated_at'))
            if ts and ts >= week_ago:
                day_idx = ts.weekday()  # 0=Mon
                changes_weekly[day_idx] += 1

        # ---------- Monthly breakdown (per week) — source article changes ----------
        changes_monthly = [0] * 5
        changes_monthly_labels = [f'W{j}' for j in range(1, 6)]
        for i in range(4, -1, -1):
            wk_start = now - datetime.timedelta(days=i * 7 + 7)
            wk_end = now - datetime.timedelta(days=i * 7)
            for row in all_pull_rows:
                ts = _parse_ts(row.get('source_updated_at'))
                if ts and wk_start <= ts < wk_end:
                    changes_monthly[4 - i] += 1

        # ---------- Build English titles lookup from pull_registry ----------
        english_titles = {}
        for row in all_pull_rows:
            iid = row.get('intercom_id', '')
            if iid and row.get('title'):
                english_titles[iid] = row['title']

        # ---------- Recently updated source articles (from pull_registry) ----------
        # Sorted by source_updated_at desc — shows which Intercom articles were
        # most recently edited, so user knows what needs re-translation.
        recently_updated = []
        for row in all_pull_rows:
            ts = _parse_ts(row.get('source_updated_at'))
            if ts:
                recently_updated.append({
                    'title': row.get('title') or 'Untitled',
                    'source_updated_at': row.get('source_updated_at'),
                    'ts': ts,
                })

        recently_updated.sort(key=lambda x: x['ts'], reverse=True)
        top_articles = []
        for a in recently_updated[:20]:
            top_articles.append({
                'title': a['title'],
                'last_updated': a['ts'].strftime('%b %d, %Y'),
            })

        # ---------- Recent activities ----------
        # Group by article (one entry per article per action type)
        # 1. Pulled articles — from pull_registry.pulled_at
        # 2. Translated articles — from article_translations.updated_at (grouped by article)
        # 3. Pushed articles — from article_translations.pushed_at (grouped by article)

        def _time_ago(ts):
            delta = now - ts
            if delta.days > 0:
                return f'{delta.days}d ago'
            elif delta.seconds > 3600:
                return f'{delta.seconds // 3600}h ago'
            elif delta.seconds > 60:
                return f'{delta.seconds // 60}m ago'
            else:
                return 'Just now'

        activity_entries = []  # list of (timestamp, type, title)

        # --- Pulled: group by article from pull_registry ---
        for row in all_pull_rows:
            pulled_at_str = row.get('pulled_at') or ''
            ts = _parse_ts(pulled_at_str)
            if ts:
                title = row.get('title') or 'Untitled'
                activity_entries.append((ts, 'pull', title))

        # --- Translated: group by article (most recent updated_at per article) ---
        translate_by_article = {}
        for t in all_translations:
            aid = t.get('parent_intercom_article_id', '')
            if not aid:
                continue
            ts = _parse_ts(t.get('updated_at') or t.get('created_at'))
            if ts:
                if aid not in translate_by_article or ts > translate_by_article[aid]['ts']:
                    title = english_titles.get(aid) or t.get('translated_title', 'Untitled')
                    translate_by_article[aid] = {'ts': ts, 'title': title}

        for info in translate_by_article.values():
            activity_entries.append((info['ts'], 'translate', info['title']))

        # --- Pushed: group by article (most recent pushed_at per article) ---
        push_by_article = {}
        for t in all_translations:
            aid = t.get('parent_intercom_article_id', '')
            if not aid:
                continue
            ts = _parse_ts(t.get('pushed_at'))
            if ts:
                if aid not in push_by_article or ts > push_by_article[aid]['ts']:
                    title = english_titles.get(aid) or t.get('translated_title', 'Untitled')
                    push_by_article[aid] = {'ts': ts, 'title': title}

        for info in push_by_article.values():
            activity_entries.append((info['ts'], 'push', info['title']))

        # Inject automation task runs so they appear alongside article events
        import automation_service as _auto_svc
        _AUTO_TASKS = [
            ('auto_sync_pull',                 'auto_sync',  'Auto Sync completed'),
            ('auto_pull_articles',             'auto_pull',  'Auto Pull completed'),
            ('auto_sweep_leaked_translations', 'auto_sweep', 'Auto Sweep completed'),
        ]
        for _key, _atype, _label in _AUTO_TASKS:
            try:
                _s = _auto_svc.get_settings(_key)
                _ts = _parse_ts(_s.get('last_run_at') or '')
                if _ts and _s.get('last_run_status'):
                    _msg = _s.get('last_run_message') or ''
                    activity_entries.append((_ts, _atype, f'{_label} — {_msg}' if _msg else _label))
            except Exception:
                pass

        # Sort all entries by timestamp desc, take top 20
        activity_entries.sort(key=lambda x: x[0], reverse=True)

        type_labels = {
            'pull': 'Pulled',
            'translate': 'Translated',
            'push': 'Pushed',
        }
        # Automation types render their message directly (no article title wrapping)
        _auto_types = {'auto_sync', 'auto_pull', 'auto_sweep'}

        recent_activities = []
        for ts, atype, title in activity_entries[:20]:
            if atype in _auto_types:
                recent_activities.append({
                    'type': atype,
                    'text': escapeHtml(title),
                    'time': _time_ago(ts)
                })
            else:
                label = type_labels.get(atype, atype.capitalize())
                recent_activities.append({
                    'type': atype,
                    'text': f'{label} <strong>{escapeHtml(title)}</strong>',
                    'time': _time_ago(ts)
                })

        # last_sync_str was fetched in parallel above. Send the raw ISO to the
        # frontend so it can format with the user's local timezone.
        last_synced_iso = last_sync_str or None

        print(f"[TIMING] TOTAL: {_time.time()-_t0:.1f}s", flush=True)
        return jsonify({
            'success': True,
            'total_articles': total_articles,
            'total_translated': total_translated,
            'last_synced': last_synced_iso,
            'changed_this_week': changed_week,
            'changed_this_month': changed_month,
            'changes_weekly': changes_weekly,
            'changes_monthly': changes_monthly,
            'changes_monthly_labels': changes_monthly_labels,
            'top_articles': top_articles,
            'recent_activities': recent_activities
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def escapeHtml(text):
    """Server-side HTML escape for activity feed text."""
    if not text:
        return ''
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


@app.route('/api/dashboard/costs', methods=['GET'])
def dashboard_costs():
    """
    Dashboard cost data: API cost (all time), weekly/monthly breakdowns.
    Syncs missing past days in background, returns cached data immediately.
    Optional query params: start_date, end_date (YYYY-MM-DD) for filtered cost.
    """
    import datetime, threading
    try:
        # Sync missing past days and today in background (non-blocking)
        threading.Thread(target=_sync_past_costs, daemon=True).start()
        threading.Thread(target=_sync_today_cost, daemon=True).start()

        # Check for date filter params
        q_start = request.args.get('start_date')  # YYYY-MM-DD or None
        q_end = request.args.get('end_date')       # YYYY-MM-DD or None

        # Return whatever is already cached
        cached_costs = _get_cached_daily_costs(start_date=q_start, end_date=q_end)
        _cost_by_date = {row['date']: row['cost'] for row in cached_costs}

        today = datetime.date.today()
        _weekday = today.weekday()
        this_monday = today - datetime.timedelta(days=_weekday)
        last_monday = this_monday - datetime.timedelta(days=7)

        cost_weekly = [0.0] * 7
        cost_prev_weekly = [0.0] * 7
        for i in range(7):
            d_this = (this_monday + datetime.timedelta(days=i)).isoformat()
            d_last = (last_monday + datetime.timedelta(days=i)).isoformat()
            cost_weekly[i] = round(_cost_by_date.get(d_this, 0), 4)
            cost_prev_weekly[i] = round(_cost_by_date.get(d_last, 0), 4)

        cost_week = round(sum(cost_weekly), 4)

        cost_monthly = [0.0] * 5
        cost_monthly_labels = [f'W{j}' for j in range(1, 6)]
        for i in range(4, -1, -1):
            wk_start = today - datetime.timedelta(days=i * 7 + 7)
            wk_end = today - datetime.timedelta(days=i * 7)
            d = wk_start
            while d < wk_end:
                cost_monthly[4 - i] += _cost_by_date.get(d.isoformat(), 0)
                d += datetime.timedelta(days=1)
            cost_monthly[4 - i] = round(cost_monthly[4 - i], 4)

        cost_month = round(sum(cost_monthly), 4)

        return jsonify({
            'success': True,
            'cost_all_time': round(sum(row['cost'] for row in cached_costs), 2),
            'cost_week': round(cost_week, 4),
            'cost_month': round(cost_month, 4),
            'cost_weekly': [round(c, 4) for c in cost_weekly],
            'cost_prev_weekly': [round(c, 4) for c in cost_prev_weekly],
            'cost_monthly': [round(c, 4) for c in cost_monthly],
            'cost_monthly_labels': cost_monthly_labels,
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/dashboard/articles', methods=['GET'])
def dashboard_articles():
    """
    Get all articles stored in Supabase (back-office storage), sorted by title (A–Z).
    Merges from: intercom_articles (sync mirror) and intercom_content_items/versions
    (from fetch_and_dump). So articles copied from Intercom via either path are visible.
    """
    try:
        from sync_service import get_dashboard_articles
        from content_supabase import list_articles_from_content

        collection_name = request.args.get('collection_name')
        # 1) Articles in intercom_articles (Sync About FundedNext) – optional table
        try:
            mirror = get_dashboard_articles(collection_name=collection_name)
        except Exception:
            mirror = []
        for a in mirror:
            a.setdefault('intercom_id', a.get('intercom_id') or a.get('id'))

        # 2) Articles in content tables (fetch_and_dump_10_articles)
        content = list_articles_from_content()

        # Merge by intercom_id (prefer mirror title if both exist)
        by_id = {}
        for a in content:
            eid = (a.get('intercom_id') or a.get('id')) or ''
            if eid:
                by_id[str(eid)] = dict(a)
        for a in mirror:
            eid = (a.get('intercom_id') or a.get('id')) or ''
            if eid:
                by_id[str(eid)] = dict(a)

        articles = list(by_id.values())

        # 3) When no stored articles, show Intercom Help Center articles so dashboard always has a list
        if not articles:
            try:
                init_clients()
                intercom_list = []
                try:
                    intercom_list = get_intercom().get_fundednext_help_center_articles(limit=50, fetch_full=False)
                except Exception:
                    pass
                if not intercom_list:
                    seen = set()
                    for a in get_intercom().get_all_help_center_articles():
                        aid = a.get('id')
                        if aid is not None and str(aid) not in seen:
                            seen.add(str(aid))
                            intercom_list.append(a)
                    for a in get_intercom().get_articles():
                        aid = a.get('id')
                        if aid is not None and str(aid) not in seen:
                            seen.add(str(aid))
                            intercom_list.append(a)
                for a in intercom_list[:50]:
                    eid = str(a.get('id', ''))
                    if eid:
                        by_id[eid] = {
                            'intercom_id': eid,
                            'title': (a.get('title') or '').strip() or 'Untitled',
                            'collection_name': 'Intercom Help Center',
                        }
                articles = list(by_id.values())
            except Exception:
                pass

        articles = sorted(articles, key=lambda a: (a.get('title') or '').lower())
        return jsonify({
            'success': True,
            'articles': articles,
            'count': len(articles)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/sync', methods=['POST'])
def sync_from_intercom():
    """
    Sync articles from Intercom into Supabase.
    Body: { "collection_name": "About FundedNext" } or { "collection_id": "...", "collection_name": "..." }
    """
    try:
        init_clients()
        from sync_service import sync_collection_from_intercom, sync_by_collection_id
        data = request.json or {}
        collection_name = data.get('collection_name')
        collection_id = data.get('collection_id')
        if collection_id and collection_name:
            result = sync_by_collection_id(collection_id, collection_name, get_intercom())
        elif collection_name:
            result = sync_collection_from_intercom(collection_name, get_intercom())
        else:
            return jsonify({
                'success': False,
                'error': 'Provide collection_name (e.g. "About FundedNext") or collection_id and collection_name'
            }), 400
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/fetch-and-store', methods=['POST'])
def fetch_and_store():
    """
    Fetch articles from Intercom (FundedNext Help Center) and store them in Supabase
    (intercom_content_items + intercom_content_versions). This is the main flow for
    copying Intercom articles into the dashboard back-office storage.
    """
    try:
        init_clients()
        from content_supabase import dump_articles_to_supabase

        limit = 20
        all_articles = []

        try:
            all_articles = get_intercom().get_fundednext_help_center_articles(limit=limit * 2, fetch_full=True)
        except Exception:
            pass

        if not all_articles:
            seen = set()
            for a in get_intercom().get_all_help_center_articles():
                aid = a.get('id')
                if aid is not None and str(aid) not in seen:
                    seen.add(str(aid))
                    all_articles.append(a)
            for a in get_intercom().get_articles():
                aid = a.get('id')
                if aid is not None and str(aid) not in seen:
                    seen.add(str(aid))
                    all_articles.append(a)
            try:
                for hc in get_intercom().get_help_centers():
                    hc_id = hc.get('id')
                    if hc_id is None:
                        continue
                    try:
                        hc_id_int = int(hc_id)
                    except (TypeError, ValueError):
                        continue
                    for a in get_intercom().search_articles(help_center_id=hc_id_int, state='published', limit=50):
                        aid = a.get('id')
                        if aid is not None and str(aid) not in seen:
                            seen.add(str(aid))
                            all_articles.append(a)
                    if len(all_articles) >= limit:
                        break
            except Exception:
                pass

        if not all_articles:
            return jsonify({
                'success': False,
                'error': 'No articles found from Intercom. Check INTERCOM_ACCESS_TOKEN and Help Center access.',
                'stored': 0,
                'total': 0,
            }), 400

        articles = all_articles[:limit]
        for i, a in enumerate(articles):
            if not (a.get('body') or a.get('title')):
                try:
                    full = get_intercom().get_article(str(a.get('id', '')))
                    if full:
                        articles[i] = full
                except Exception:
                    pass

        stored = dump_articles_to_supabase(articles)
        return jsonify({
            'success': True,
            'stored': stored,
            'total': len(articles),
            'message': f'Stored {stored} new article(s) in Supabase. Total fetched: {len(articles)}.',
        })
    except Exception as e:
        err = str(e)
        if 'external_id' in err.lower() or 'column' in err.lower():
            err = f'{err} Ensure Supabase table intercom_content_items has columns: id, workspace, project, external_id, external_type.'
        return jsonify({
            'success': False,
            'error': err,
            'stored': 0,
            'total': 0,
        }), 500

@app.route('/api/test-connection', methods=['GET'])
def test_connection():
    """Quick connection check using Supabase pull_registry count."""
    try:
        import re as _re
        import requests as _req
        _pctx = product_context.current_product(); SUPABASE_URL, SUPABASE_SERVICE_KEY = _pctx["supabase_url"], _pctx["supabase_key"]
        _LP = _re.compile(r'^\[[A-Z]{2}(?:-[A-Z]{1,4})?\]\s+', _re.IGNORECASE)
        _headers = product_context.supabase_headers()
        rows = []
        _offset = 0
        while True:
            resp = _req.get(
                f"{SUPABASE_URL}/rest/v1/pull_registry",
                headers=_headers,
                params={"select": "title", "limit": "1000", "offset": str(_offset)},
                timeout=10,
            )
            if not resp.ok:
                break
            batch = resp.json() or []
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < 1000:
                break
            _offset += 1000
        if rows:
            articles_count = len([r for r in rows if not _LP.match(r.get('title') or '')])
            return jsonify({
                'success': True,
                'intercom': True,
                'openai': True,
                'articles_count': articles_count
            })
        return jsonify({'success': False, 'error': 'Supabase connection failed'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# =====================================================================
# Translate Module API Endpoints
# =====================================================================

@app.route('/api/translate-hub/articles', methods=['GET'])
def translate_hub_articles():
    """
    List pulled articles with per-language translation status matrix.
    Query params: search, page, page_size, status, language, sort
    """
    import language_service
    language_service.load_active_languages()
    from translate_service import list_translate_articles
    try:
        search = request.args.get('search', '').strip()
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 25))
        status_filter = request.args.get('status', '').strip().upper()
        language_filter = request.args.get('language', '').strip()
        sort_by = request.args.get('sort', 'attention').strip()

        if page_size not in (10, 25, 50, 100):
            page_size = 25
        if page < 1:
            page = 1

        result = list_translate_articles(
            search=search,
            page=page,
            page_size=page_size,
            status_filter=status_filter,
            language_filter=language_filter,
            sort_by=sort_by,
        )
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/translate-hub/article/<intercom_id>', methods=['GET'])
def translate_hub_article_detail(intercom_id):
    """Get article detail with source preview + translation previews for drawer."""
    from translate_service import get_translate_article_detail
    try:
        detail = get_translate_article_detail(intercom_id)
        if detail:
            return jsonify({'success': True, 'article': detail})
        return jsonify({'success': False, 'error': 'Article not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/translate-hub/bulk', methods=['POST'])
def translate_hub_bulk():
    """
    Bulk translate selected articles × languages.
    Body: { "intercom_ids": ["123", ...], "locales": ["fr", "de", ...] }
    """
    from translate_service import bulk_translate
    try:
        init_clients()
        data = request.get_json(silent=True) or {}
        intercom_ids = data.get('intercom_ids', [])
        locales = data.get('locales', [])

        if not intercom_ids:
            return jsonify({'success': False, 'error': 'No article IDs provided.'}), 400
        if not locales:
            return jsonify({'success': False, 'error': 'No languages provided.'}), 400

        # Block translation of outdated articles (source changed since last pull)
        from pull_service import get_pull_article
        outdated_titles = []
        for iid in intercom_ids:
            row = get_pull_article(str(iid))
            if row:
                pulled_at = row.get('pulled_at')
                source_updated = row.get('source_updated_at')
                if pulled_at and source_updated and source_updated > pulled_at:
                    outdated_titles.append(row.get('title', iid))
        if outdated_titles:
            names = ', '.join(outdated_titles[:3])
            more = f' and {len(outdated_titles) - 3} more' if len(outdated_titles) > 3 else ''
            return jsonify({
                'success': False,
                'error': f'Cannot translate {len(outdated_titles)} outdated article(s): {names}{more}. Please re-pull from the Pull page first.'
            }), 400

        # glossary_id is no longer manually selected; all active glossaries
        # are automatically applied during translation.
        result = bulk_translate(
            intercom_ids=intercom_ids,
            locales=locales,
            translator_instance=get_translator(),
            concurrency=8,
            glossary_id=None,  # Auto-uses all active glossaries
        )
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/translate-hub/missing', methods=['POST'])
def translate_hub_missing():
    """
    Get all article × language combinations that need translation.
    Body: { "locales": ["fr", "de", ...] }
    Returns list of missing items for confirmation modal.
    """
    from translate_service import get_missing_translations
    try:
        data = request.get_json(silent=True) or {}
        locales = data.get('locales', list(TARGET_LANGUAGES.keys()))
        missing = get_missing_translations(locales)
        # Group by article
        by_article: Dict[str, Dict] = {}
        for m in missing:
            iid = m["intercom_id"]
            if iid not in by_article:
                by_article[iid] = {"intercom_id": iid, "title": m["title"], "locales": []}
            by_article[iid]["locales"].append(m["locale"])

        return jsonify({
            'success': True,
            'missing': list(by_article.values()),
            'total_combinations': len(missing),
            'total_articles': len(by_article),
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# =====================================================================
# Content Hub API Endpoints
# =====================================================================

@app.route('/api/content-hub/articles', methods=['GET'])
def content_hub_articles():
    """
    List articles with computed health status for Content Hub.
    Query params: search, page, page_size, health_filter, sort_by
    """
    from content_hub_service import list_content_hub_articles
    try:
        search = request.args.get('search', '').strip()
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 25))
        health_filter = request.args.get('health', '').strip().upper()
        sort_by = request.args.get('sort', 'attention').strip()

        if page_size not in (10, 25, 50, 100):
            page_size = 25
        if page < 1:
            page = 1

        result = list_content_hub_articles(
            search=search,
            page=page,
            page_size=page_size,
            health_filter=health_filter,
            sort_by=sort_by,
        )
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/content-hub/collections', methods=['GET'])
def content_hub_collections():
    """List collections with article counts and health summary."""
    from content_hub_service import list_collections
    try:
        collections = list_collections()
        return jsonify({'success': True, 'collections': collections})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/content-hub/article/<intercom_id>', methods=['GET'])
def content_hub_article_detail(intercom_id):
    """Get detailed metadata for one article (for details drawer)."""
    from content_hub_service import get_article_detail
    try:
        detail = get_article_detail(intercom_id)
        if detail:
            return jsonify({'success': True, 'article': detail})
        return jsonify({'success': False, 'error': 'Article not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/content-hub/archive', methods=['POST'])
def content_hub_archive():
    """Archive selected articles so they are hidden from the app."""
    from content_hub_service import archive_articles
    try:
        data = request.get_json(force=True)
        ids = data.get('intercom_ids', [])
        if not ids:
            return jsonify({'success': False, 'error': 'No intercom_ids provided'}), 400
        result = archive_articles(ids)
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/content-hub/unarchive', methods=['POST'])
def content_hub_unarchive():
    """Unarchive articles to make them visible again."""
    from content_hub_service import unarchive_articles
    try:
        data = request.get_json(force=True)
        ids = data.get('intercom_ids', [])
        if not ids:
            return jsonify({'success': False, 'error': 'No intercom_ids provided'}), 400
        result = unarchive_articles(ids)
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# =====================================================================
# Pull Module API Endpoints
# =====================================================================

@app.route('/api/pull/status', methods=['GET'])
def pull_table_status():
    """Check if pull_registry table exists in Supabase."""
    from pull_service import table_exists, SETUP_SQL
    exists = table_exists()
    return jsonify({
        'success': True,
        'table_exists': exists,
        'setup_sql': SETUP_SQL if not exists else None,
    })


@app.route('/api/pull/create-table', methods=['POST'])
def pull_create_table():
    """
    Auto-create pull_registry table in Supabase.
    Uses pg8000 direct connection if SUPABASE_DB_URL is set,
    otherwise tries Supabase Management API with SUPABASE_PAT.
    """
    from pull_service import table_exists, SETUP_SQL
    if table_exists():
        return jsonify({'success': True, 'message': 'Table already exists.'})

    # Try creating via direct DB
    db_url = os.getenv('SUPABASE_DB_URL', '').strip()
    if db_url:
        try:
            from urllib.parse import urlparse, unquote
            from pg8000.native import Connection
            u = urlparse(db_url)
            conn = Connection(
                user=unquote(u.username) if u.username else 'postgres',
                password=unquote(u.password) if u.password else '',
                host=u.hostname or 'localhost',
                port=u.port or 5432,
                database=(u.path or '/postgres').lstrip('/') or 'postgres',
            )
            for stmt in [s.strip() for s in SETUP_SQL.split(';') if s.strip()]:
                conn.run(stmt)
            conn.close()
            return jsonify({'success': True, 'method': 'pg8000', 'message': 'Table created successfully.'})
        except Exception as e:
            pass

    # Try Management API
    pat = os.getenv('SUPABASE_PAT', '').strip() or os.getenv('SUPABASE_ACCESS_TOKEN', '').strip()
    supabase_url = product_context.current_product()["supabase_url"].strip()
    ref = supabase_url.rstrip('/').split('//')[-1].replace('.supabase.co', '') if supabase_url else ''
    if pat and ref:
        try:
            import requests as _req
            api_url = f'https://api.supabase.com/v1/projects/{ref}/database/query'
            headers = {'Authorization': f'Bearer {pat}', 'Content-Type': 'application/json'}
            r = _req.post(api_url, json={'query': SETUP_SQL, 'read_only': False}, headers=headers, timeout=30)
            if r.status_code in (200, 201):
                return jsonify({'success': True, 'method': 'management_api', 'message': 'Table created successfully.'})
        except Exception:
            pass

    return jsonify({
        'success': False,
        'error': 'Could not auto-create table. Please run the SQL manually in Supabase Dashboard > SQL Editor.',
        'setup_sql': SETUP_SQL,
    }), 400


@app.route('/api/pull/articles', methods=['GET'])
def pull_articles_list():
    """
    List articles from pull_registry (paginated, searchable).
    Query params: search, page (1-based), page_size (10|25|50), status_filter
    """
    from pull_service import list_pull_articles, table_exists
    if not table_exists():
        return jsonify({
            'success': False,
            'error': 'pull_registry table does not exist. Please run the setup SQL first.',
            'table_missing': True,
        }), 400
    try:
        search = request.args.get('search', '').strip()
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 25))
        status_filter = request.args.get('status_filter', '').strip()

        if page_size not in (10, 25, 50):
            page_size = 25
        if page < 1:
            page = 1

        result = list_pull_articles(
            search=search,
            page=page,
            page_size=page_size,
            status_filter=status_filter,
        )
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/pull/sync-source', methods=['POST'])
def pull_sync_source():
    """
    Sync article listing from Intercom into pull_registry
    (metadata only, no full body). This populates the table.
    """
    from pull_service import sync_source_list, table_exists
    if not table_exists():
        return jsonify({
            'success': False,
            'error': 'pull_registry table does not exist.',
            'table_missing': True,
        }), 400
    try:
        init_clients()
        result = sync_source_list(get_intercom())
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/pull/execute', methods=['POST'])
def pull_execute():
    """
    Pull full content for selected articles.
    Body: { "intercom_ids": ["123", "456", ...] }
    """
    from pull_service import pull_articles as do_pull, table_exists
    if not table_exists():
        return jsonify({
            'success': False,
            'error': 'pull_registry table does not exist.',
            'table_missing': True,
        }), 400
    try:
        init_clients()
        data = request.get_json(silent=True) or {}
        intercom_ids = data.get('intercom_ids', [])
        if not intercom_ids:
            return jsonify({'success': False, 'error': 'No article IDs provided.'}), 400

        # Soft cap per request — even with parallel + bulk writes, a single
        # invocation has to fit Vercel's function timeout. The client
        # auto-chunks selections larger than this.
        PULL_BATCH_LIMIT = 100
        if len(intercom_ids) > PULL_BATCH_LIMIT:
            return jsonify({
                'success': False,
                'error': f'Too many IDs in one request (max {PULL_BATCH_LIMIT}).',
                'batch_limit': PULL_BATCH_LIMIT,
            }), 413

        results = do_pull(intercom_ids, get_intercom())
        success_count = sum(1 for r in results if r.get('status') == 'success')
        fail_count = sum(1 for r in results if r.get('status') == 'failed')

        return jsonify({
            'success': True,
            'results': results,
            'pulled': success_count,
            'failed': fail_count,
            'total': len(results),
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/pull/stats', methods=['GET'])
def pull_stats():
    """Get aggregate stats for pull registry."""
    from pull_service import get_pull_stats, table_exists
    if not table_exists():
        return jsonify({'success': True, 'total': 0, 'table_exists': False})
    try:
        stats = get_pull_stats()
        stats['table_exists'] = True
        return jsonify({'success': True, **stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# =====================================================================
# Glossary API Endpoints
# =====================================================================

@app.route('/api/glossary/status', methods=['GET'])
def glossary_status():
    """Check if glossary tables exist in Supabase."""
    from glossary_service import tables_exist, SETUP_SQL
    exists = tables_exist()
    return jsonify({
        'success': True,
        'tables_exist': exists,
        'setup_sql': SETUP_SQL if not exists else None,
    })


@app.route('/api/glossary/create-tables', methods=['POST'])
def glossary_create_tables():
    """Auto-create glossary tables in Supabase."""
    from glossary_service import tables_exist, SETUP_SQL
    if tables_exist():
        return jsonify({'success': True, 'message': 'Tables already exist.'})

    import requests as _req
    db_url = os.getenv('SUPABASE_DB_URL', '').strip()
    if db_url:
        try:
            from urllib.parse import urlparse, unquote
            from pg8000.native import Connection
            u = urlparse(db_url)
            conn = Connection(
                user=unquote(u.username) if u.username else 'postgres',
                password=unquote(u.password) if u.password else '',
                host=u.hostname or 'localhost',
                port=u.port or 5432,
                database=(u.path or '/postgres').lstrip('/') or 'postgres',
            )
            for stmt in [s.strip() for s in SETUP_SQL.split(';') if s.strip()]:
                conn.run(stmt)
            conn.close()
            return jsonify({'success': True, 'method': 'pg8000', 'message': 'Glossary tables created successfully.'})
        except Exception:
            pass

    pat = os.getenv('SUPABASE_PAT', '').strip() or os.getenv('SUPABASE_ACCESS_TOKEN', '').strip()
    supabase_url = product_context.current_product()["supabase_url"].strip()
    ref = supabase_url.rstrip('/').split('//')[-1].replace('.supabase.co', '') if supabase_url else ''
    if pat and ref:
        try:
            api_url = f'https://api.supabase.com/v1/projects/{ref}/database/query'
            headers = {'Authorization': f'Bearer {pat}', 'Content-Type': 'application/json'}
            r = _req.post(api_url, json={'query': SETUP_SQL, 'read_only': False}, headers=headers, timeout=30)
            if r.status_code in (200, 201):
                return jsonify({'success': True, 'method': 'management_api', 'message': 'Glossary tables created successfully.'})
        except Exception:
            pass

    return jsonify({
        'success': False,
        'error': 'Could not auto-create tables. Please run the SQL manually in Supabase Dashboard > SQL Editor.',
        'setup_sql': SETUP_SQL,
    }), 400


@app.route('/api/glossary/glossaries', methods=['GET'])
def glossary_list():
    """List glossaries with filtering, search, sort, and pagination."""
    from glossary_service import list_glossaries
    try:
        search = request.args.get('search', '').strip()
        status_filter = request.args.get('status', 'ALL')
        sort_by = request.args.get('sort', 'name_asc')
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 25))
        if page_size not in (10, 25, 50, 100):
            page_size = 25
        if page < 1:
            page = 1
        result = list_glossaries(
            search=search,
            status_filter=status_filter,
            sort_by=sort_by,
            page=page,
            page_size=page_size,
        )
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/glossary/glossaries', methods=['POST'])
def glossary_create():
    """Create a new glossary."""
    from glossary_service import create_glossary
    try:
        data = request.get_json(silent=True) or {}
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'success': False, 'error': 'Glossary name is required.'}), 400
        source_locale = data.get('source_locale', BASE_LANGUAGE)
        target_locales = data.get('target_locales', list(TARGET_LANGUAGES.keys()))
        created_by = data.get('created_by', 'user')
        glossary = create_glossary(name, source_locale, target_locales, created_by)
        return jsonify({'success': True, 'glossary': _make_json_serializable(glossary)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/glossary/glossaries/<glossary_id>', methods=['GET'])
def glossary_get(glossary_id):
    """Get a single glossary."""
    from glossary_service import get_glossary
    try:
        g = get_glossary(glossary_id)
        if g:
            return jsonify({'success': True, 'glossary': g})
        return jsonify({'success': False, 'error': 'Glossary not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/glossary/glossaries/<glossary_id>', methods=['PATCH'])
def glossary_update(glossary_id):
    """Update a glossary."""
    from glossary_service import update_glossary
    try:
        data = request.get_json(silent=True) or {}
        result = update_glossary(glossary_id, data)
        return jsonify({'success': True, 'glossary': _make_json_serializable(result)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/glossary/glossaries/<glossary_id>', methods=['DELETE'])
def glossary_delete(glossary_id):
    """Soft-delete a glossary."""
    from glossary_service import delete_glossary
    try:
        ok = delete_glossary(glossary_id)
        return jsonify({'success': ok})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/glossary/glossaries/<glossary_id>/terms', methods=['GET'])
def glossary_terms_list(glossary_id):
    """List terms in a glossary (paginated, searchable)."""
    from glossary_service import list_terms
    try:
        search = request.args.get('search', '').strip()
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 25))
        if page_size not in (10, 25, 50, 100):
            page_size = 25
        if page < 1:
            page = 1
        result = list_terms(glossary_id, search=search, page=page, page_size=page_size)
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/glossary/glossaries/<glossary_id>/terms', methods=['POST'])
def glossary_term_create(glossary_id):
    """Create a new term in a glossary."""
    from glossary_service import create_term
    try:
        data = request.get_json(silent=True) or {}
        source_term = (data.get('source_term') or '').strip()
        if not source_term:
            return jsonify({'success': False, 'error': 'Source term is required.'}), 400
        translations = data.get('translations', {})
        term = create_term(
            glossary_id=glossary_id,
            source_term=source_term,
            translations=translations,
            part_of_speech=data.get('part_of_speech', ''),
            description=data.get('description', ''),
            image_url=data.get('image_url', ''),
        )
        return jsonify({'success': True, 'term': _make_json_serializable(term)})
    except Exception as e:
        err = str(e)
        # Duplicate key / unique constraint violation
        if '23505' in err or 'already exists' in err.lower() or 'duplicate' in err.lower():
            return jsonify({'success': False, 'error': f'A term "{source_term}" already exists in this glossary.'}), 409
        return jsonify({'success': False, 'error': err}), 500


@app.route('/api/glossary/terms/<term_id>', methods=['PATCH'])
def glossary_term_update(term_id):
    """Update a term."""
    from glossary_service import update_term
    try:
        data = request.get_json(silent=True) or {}
        translations = data.pop('translations', None)
        term = update_term(term_id, data, translations)
        return jsonify({'success': True, 'term': _make_json_serializable(term)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/glossary/terms/bulk-delete', methods=['POST'])
def glossary_terms_bulk_delete():
    """Bulk soft-delete terms."""
    from glossary_service import delete_terms
    try:
        data = request.get_json(silent=True) or {}
        term_ids = data.get('term_ids', [])
        if not term_ids:
            return jsonify({'success': False, 'error': 'No term IDs provided.'}), 400
        count = delete_terms(term_ids)
        return jsonify({'success': True, 'deleted': count})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/glossary/glossaries/<glossary_id>/usage', methods=['GET'])
def glossary_usage(glossary_id):
    """Get usage analytics for terms in a glossary."""
    from glossary_service import compute_term_usage
    try:
        usage = compute_term_usage(glossary_id)
        return jsonify({'success': True, 'usage': usage})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/glossary/glossaries/<glossary_id>/export', methods=['GET'])
def glossary_export(glossary_id):
    """Export a glossary as XLSX."""
    from glossary_service import export_glossary_xlsx
    try:
        xlsx_bytes = export_glossary_xlsx(glossary_id)
        buf = BytesIO(xlsx_bytes)
        buf.seek(0)
        return send_file(
            buf,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'glossary_{glossary_id[:8]}.xlsx',
        )
    except ImportError as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/glossary/glossaries/<glossary_id>/import', methods=['POST'])
def glossary_import(glossary_id):
    """Import terms from XLSX into a glossary."""
    from glossary_service import import_glossary_xlsx
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded.'}), 400
        f = request.files['file']
        if not f.filename:
            return jsonify({'success': False, 'error': 'No file selected.'}), 400
        if not f.filename.lower().endswith('.xlsx'):
            return jsonify({'success': False, 'error': 'File must be an XLSX file (.xlsx).'}), 400
        file_bytes = f.read()
        if not file_bytes or len(file_bytes) == 0:
            return jsonify({'success': False, 'error': 'File is empty.'}), 400
        result = import_glossary_xlsx(glossary_id, file_bytes)
        # Always return success=True if we got a result, even if there were errors
        return jsonify({'success': True, **result})
    except ImportError as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        import traceback
        return jsonify({'success': False, 'error': f'Import failed: {str(e)}', 'traceback': traceback.format_exc()}), 500


# ============================================================
# PUSH MODULE API
# ============================================================

@app.route('/api/push/ensure-columns', methods=['POST'])
def push_ensure_columns():
    """Ensure pushed_at and push_error columns exist in article_translations."""
    try:
        import requests as req
        _pctx = product_context.current_product(); SUPABASE_URL, SUPABASE_SERVICE_KEY = _pctx["supabase_url"], _pctx["supabase_key"]
        rest_base = f"{SUPABASE_URL.rstrip('/')}/rest/v1" if SUPABASE_URL else ""
        if not rest_base:
            return jsonify({'success': False, 'error': 'SUPABASE_URL not set'}), 500

        # Try to query pushed_at - if it fails, run the ALTER TABLE
        h = product_context.supabase_headers()
        resp = req.get(
            f"{rest_base}/article_translations?select=pushed_at&limit=1",
            headers=h, timeout=10,
        )
        if resp.status_code == 200:
            return jsonify({'success': True, 'message': 'Columns already exist'})

        # Columns don't exist; instruct user to run migration
        return jsonify({
            'success': False,
            'error': 'Please run the following SQL in Supabase SQL Editor:\n\nALTER TABLE public.article_translations ADD COLUMN IF NOT EXISTS pushed_at timestamptz DEFAULT NULL;\nALTER TABLE public.article_translations ADD COLUMN IF NOT EXISTS push_error text DEFAULT \'\';',
            'needs_migration': True,
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/push/articles', methods=['GET'])
def push_articles_list():
    """
    List articles for push deployment.
    Query params: locale (optional), search, status_filter, page, page_size
    If locale is omitted, articles load with basic info (no translation status).
    """
    from push_service import list_push_articles
    try:
        locale = request.args.get('locale', '').strip()
        search = request.args.get('search', '').strip()
        status_filter = request.args.get('status_filter', '').strip()
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 25))
        if page_size not in (10, 25, 50, 100, 5000):
            page_size = 25
        if page < 1:
            page = 1
        result = list_push_articles(
            locale=locale,
            search=search,
            status_filter=status_filter,
            page=page,
            page_size=page_size,
        )
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/push/articles-multi', methods=['GET'])
def push_articles_multi():
    """
    List articles with push status for multiple locales simultaneously.
    Query params: locales (comma-separated, required), search, page, page_size
    """
    from push_service import list_push_articles_multi
    try:
        locales_str = request.args.get('locales', '').strip()
        locales = [l.strip() for l in locales_str.split(',') if l.strip()]
        if not locales:
            return jsonify({'success': False, 'error': 'locales is required (comma-separated)'}), 400
        search = request.args.get('search', '').strip()
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 25))
        if page_size not in (10, 25, 50, 100, 5000):
            page_size = 25
        if page < 1:
            page = 1
        result = list_push_articles_multi(
            locales=locales,
            search=search,
            page=page,
            page_size=page_size,
        )
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/push/preview', methods=['GET'])
def push_preview():
    """
    Get preview data for push drawer (source + translation side by side).
    Query params: intercom_id (required), locale (required)
    """
    from push_service import get_push_preview
    try:
        intercom_id = request.args.get('intercom_id', '').strip()
        locale = request.args.get('locale', '').strip()
        if not intercom_id or not locale:
            return jsonify({'success': False, 'error': 'intercom_id and locale are required'}), 400
        preview = get_push_preview(intercom_id, locale)
        if not preview:
            return jsonify({'success': False, 'error': 'Article not found'}), 404
        return jsonify({'success': True, 'preview': _make_json_serializable(preview)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/push/execute', methods=['POST'])
def push_execute():
    """
    Push one translation to Intercom.
    Body: { intercom_id, locale }
    """
    from push_service import push_single
    try:
        init_clients()
        data = request.get_json(silent=True) or {}
        intercom_id = (data.get('intercom_id') or '').strip()
        locale = (data.get('locale') or '').strip()
        if not intercom_id or not locale:
            return jsonify({'success': False, 'error': 'intercom_id and locale are required'}), 400
        result = push_single(intercom_id, locale, get_intercom())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/push/bulk', methods=['POST'])
def push_bulk():
    """
    Bulk push translations to Intercom.
    Body: { intercom_ids: [...], locale: "fr" }
    """
    from push_service import bulk_push
    try:
        init_clients()
        data = request.get_json(silent=True) or {}
        intercom_ids = data.get('intercom_ids', [])
        locale = (data.get('locale') or '').strip()
        if not intercom_ids:
            return jsonify({'success': False, 'error': 'No article IDs provided'}), 400
        if not locale:
            return jsonify({'success': False, 'error': 'locale is required'}), 400
        result = bulk_push(
            intercom_ids=intercom_ids,
            locale=locale,
            intercom_client=get_intercom(),
            concurrency=3,
        )
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# CLEANUP: Remove [LOCALE] duplicate articles from Intercom
# ============================================================

@app.route('/api/push/cleanup-locale-duplicates', methods=['POST'])
def cleanup_locale_duplicates():
    """
    Find and delete [LOCALE]-prefixed duplicate articles from Intercom.
    These are orphan articles created by the push fallback that inflate
    collection article counts on the live Help Center.
    """
    from pull_service import cleanup_locale_articles_from_intercom
    try:
        init_clients()
        result = cleanup_locale_articles_from_intercom(get_intercom())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# AUTOMATION MODULE API
# ============================================================

@app.route('/api/automation/recent-activity', methods=['GET'])
def automation_recent_activity():
    """Return last-run summary for all automation tasks, sorted newest first."""
    import automation_service
    TASKS = [
        {
            'key': 'auto_sync_pull',
            'label': 'Auto Sync Source List',
            'icon': 'sync-alt',
            'color': 'indigo',
        },
        {
            'key': 'auto_pull_articles',
            'label': 'Auto Pull Articles',
            'icon': 'cloud-download-alt',
            'color': 'emerald',
        },
        {
            'key': 'auto_sweep_leaked_translations',
            'label': 'Auto Sweep Leaked Translations',
            'icon': 'shield-alt',
            'color': 'rose',
        },
    ]
    try:
        entries = []
        for task in TASKS:
            s = automation_service.get_settings(task['key'])
            if not s.get('last_run_at'):
                continue
            entries.append({
                'key': task['key'],
                'label': task['label'],
                'icon': task['icon'],
                'color': task['color'],
                'ran_at': s['last_run_at'],
                'status': s.get('last_run_status') or '',
                'message': s.get('last_run_message') or '',
                'enabled': bool(s.get('enabled')),
            })
        entries.sort(key=lambda x: x['ran_at'], reverse=True)
        return jsonify({'success': True, 'entries': entries})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/automation/settings', methods=['GET'])
def automation_get_settings():
    """Get automation settings. Query param: key (default: auto_sync_pull)."""
    import automation_service
    try:
        key = request.args.get('key', 'auto_sync_pull')
        settings = automation_service.get_settings(key)
        return jsonify({'success': True, 'settings': settings})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/automation/toggle', methods=['POST'])
def automation_toggle():
    """Toggle an automation task on or off."""
    import automation_service
    try:
        data = request.get_json(silent=True) or {}
        key = data.get('key', 'auto_sync_pull')
        enabled = bool(data.get('enabled', False))
        result = automation_service.set_enabled(key, enabled)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/automation/logs', methods=['GET'])
def automation_logs():
    """Get recent automation run logs."""
    import automation_service
    try:
        logs = automation_service.get_logs("auto_sync_pull")
        return jsonify({'success': True, 'logs': logs})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/automation/table-status', methods=['GET'])
def automation_table_status():
    """Check if automation_settings table exists."""
    import automation_service
    exists = automation_service.table_exists()
    return jsonify({
        'success': True,
        'table_exists': exists,
        'setup_sql': automation_service.SETUP_SQL if not exists else None,
    })


@app.route('/api/automation/create-table', methods=['POST'])
def automation_create_table():
    """Auto-create automation_settings table."""
    import automation_service
    result = automation_service.auto_create_table()
    return jsonify(result)


@app.route('/api/automation/run-now', methods=['POST'])
def automation_run_now():
    """Manually trigger an automation task (for testing)."""
    import automation_service
    try:
        data = request.get_json(silent=True) or {}
        key = data.get('key', 'auto_sync_pull')
        init_clients()
        if key == 'auto_pull_articles':
            result = automation_service.run_auto_pull(get_intercom())
        elif key == 'auto_sweep_leaked_translations':
            # Ensure row exists, then run regardless of enabled flag
            automation_service.get_settings(key)
            result = automation_service.run_auto_sweep(get_intercom())
        else:
            result = automation_service.run_auto_sync(get_intercom())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/sweep/run', methods=['POST'])
def sweep_run_manual():
    """Manual sweep trigger from the UI — always runs regardless of enabled flag."""
    import automation_service
    from sweep_service import scan_and_demote
    key = 'auto_sweep_leaked_translations'
    try:
        init_clients()
        # Ensure the settings row exists before we try to record into it
        automation_service.get_settings(key)
        result = scan_and_demote(get_intercom())
        articles = result.get('articles_demoted', 0)
        locales = result.get('locales_demoted', 0)
        leaks = result.get('leaks_found', 0)
        if leaks == 0:
            message = f"No leaks found ({result.get('articles_checked', 0)} articles checked)"
        else:
            message = (
                f"Demoted {articles} article(s), {locales} locale(s) "
                f"({result.get('articles_checked', 0)} checked, "
                f"{len(result.get('errors', []))} errors)"
            )
        automation_service.record_run(key, 'success', message)
        return jsonify({'success': True, 'message': message, **result})
    except Exception as e:
        automation_service.record_run(key, 'error', str(e))
        return jsonify({'success': False, 'error': str(e)}), 500


def _run_for_all_products(label, fn):
    """Run fn() once per registered product, each with that product's context.

    A single Vercel cron trigger has no active product, so we loop the registry
    and set g.product per iteration; get_intercom()/services rebind automatically
    (their g-cache is keyed by product id). Each product's own automation_settings
    (in its own DB) still governs whether the run actually does anything.

    NOTE: Vercel Hobby caps a function at 10s. With several products, prefer
    per-product cron paths or chunking rather than one long loop.
    """
    import config as _config
    results = {}
    for pid in _config.PRODUCTS:
        g.product = product_context.resolve_product(pid)
        try:
            results[pid] = fn()
        except Exception as e:
            print(f"[{label}] product={pid} error: {e}", flush=True)
            results[pid] = {'success': False, 'error': str(e)}
    return results


@app.route('/api/cron/sync', methods=['GET', 'POST'])
def cron_sync():
    """
    Cron endpoint called by Vercel Cron at UTC 00:00.
    Checks if auto-sync is enabled, then runs the Pull sync.
    """
    import automation_service

    # Verify cron authorization
    cron_secret = os.getenv('CRON_SECRET', '').strip()
    auth_header = request.headers.get('Authorization', '')
    has_auth = hasattr(request, 'auth_session') and request.auth_session
    has_cron_secret = cron_secret and auth_header == f'Bearer {cron_secret}'

    if not has_auth and not has_cron_secret:
        vercel_cron = request.headers.get('x-vercel-cron')
        if not vercel_cron:
            print(f"[CRON SYNC] Rejected — no auth. Headers: {dict(request.headers)}", flush=True)
            return jsonify({'success': False, 'error': 'Unauthorized cron request'}), 401

    print("[CRON SYNC] Authorized — starting auto sync for all products", flush=True)
    try:
        results = _run_for_all_products("CRON SYNC", lambda: automation_service.run_auto_sync(get_intercom()))
        print(f"[CRON SYNC] Results: {results}", flush=True)
        return jsonify({'success': True, 'products': results})
    except Exception as e:
        print(f"[CRON SYNC] Error: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/cron/pull', methods=['GET', 'POST'])
def cron_pull():
    """
    Cron endpoint called by Vercel Cron at UTC 01:30.
    Auto-pulls all articles with 'Never Pulled' or 'Needs Update' status.
    """
    import automation_service

    # Verify cron authorization
    cron_secret = os.getenv('CRON_SECRET', '').strip()
    auth_header = request.headers.get('Authorization', '')
    has_auth = hasattr(request, 'auth_session') and request.auth_session
    has_cron_secret = cron_secret and auth_header == f'Bearer {cron_secret}'

    if not has_auth and not has_cron_secret:
        vercel_cron = request.headers.get('x-vercel-cron')
        if not vercel_cron:
            print(f"[CRON PULL] Rejected — no auth. Headers: {dict(request.headers)}", flush=True)
            return jsonify({'success': False, 'error': 'Unauthorized cron request'}), 401

    print("[CRON PULL] Authorized — starting auto pull for all products", flush=True)
    try:
        results = _run_for_all_products("CRON PULL", lambda: automation_service.run_auto_pull(get_intercom()))
        print(f"[CRON PULL] Results: {results}", flush=True)
        return jsonify({'success': True, 'products': results})
    except Exception as e:
        print(f"[CRON PULL] Error: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/cron/sweep', methods=['GET', 'POST'])
def cron_sweep():
    """
    Cron endpoint called by Vercel Cron at UTC 03:00.
    Finds articles whose English source is unpublished but have translated
    locales still published, and demotes those locales to draft.
    """
    import automation_service

    cron_secret = os.getenv('CRON_SECRET', '').strip()
    auth_header = request.headers.get('Authorization', '')
    has_auth = hasattr(request, 'auth_session') and request.auth_session
    has_cron_secret = cron_secret and auth_header == f'Bearer {cron_secret}'

    if not has_auth and not has_cron_secret:
        vercel_cron = request.headers.get('x-vercel-cron')
        if not vercel_cron:
            print(f"[CRON SWEEP] Rejected — no auth. Headers: {dict(request.headers)}", flush=True)
            return jsonify({'success': False, 'error': 'Unauthorized cron request'}), 401

    print("[CRON SWEEP] Authorized — starting sweep for all products", flush=True)
    try:
        results = _run_for_all_products("CRON SWEEP", lambda: automation_service.run_auto_sweep(get_intercom()))
        print(f"[CRON SWEEP] Results: {results}", flush=True)
        return jsonify({'success': True, 'products': results})
    except Exception as e:
        print(f"[CRON SWEEP] Error: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()

    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'

    # On Windows the default 'stat' reloader causes [Errno 22] Invalid argument.
    # Use 'watchdog' if installed, otherwise disable the reloader.
    reloader_type = None
    if debug and sys.platform == 'win32':
        try:
            import watchdog  # noqa: F401
            reloader_type = 'watchdog'
        except ImportError:
            reloader_type = None  # disable reloader below

    if reloader_type:
        app.run(host='0.0.0.0', port=port, debug=debug, reloader_type=reloader_type)
    elif debug and sys.platform == 'win32':
        # Run with debug but without reloader to avoid Errno 22
        app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False)
    else:
        app.run(host='0.0.0.0', port=port, debug=debug)
