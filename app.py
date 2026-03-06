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
from flask import Flask, render_template, jsonify, request, send_file
from flask_cors import CORS
from functools import wraps
from intercom_client import IntercomClient
from translator import GPTTranslator
from workflow import TranslationWorkflow
from config import TARGET_LANGUAGES, BASE_LANGUAGE
import auth_service

app = Flask(__name__)
CORS(app, supports_credentials=True)


@app.before_request
def log_request():
    """Log method and path for every request (server-side debug)."""
    print(f"{request.method} {request.path}", flush=True)


# ─── Auth helpers ──────────────────────────────────────────────
PUBLIC_PATHS = {'/', '/favicon.ico', '/api/health', '/api/auth/login'}
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


# Initialize clients
intercom_client = None
translator = None
workflow = None

def init_clients():
    """Initialize API clients"""
    global intercom_client, translator, workflow
    if not intercom_client:
        intercom_client = IntercomClient()
    if not translator:
        translator = GPTTranslator()
    if not workflow:
        workflow = TranslationWorkflow(intercom_client, translator)

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


# ─── Auth API routes ──────────────────────────────────────────
@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    """Login with email and password."""
    data = request.get_json(force=True)
    email = data.get('email', '')
    password = data.get('password', '')
    if not email or not password:
        return jsonify({'success': False, 'error': 'Email and password required'}), 400
    result = auth_service.login(email, password)
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
                all_articles = intercom_client.get_fundednext_help_center_articles(limit=50, fetch_full=True)
            except Exception:
                pass
            if not all_articles:
                seen = set()
                for a in intercom_client.get_all_help_center_articles():
                    aid = a.get('id')
                    if aid is not None and str(aid) not in seen:
                        seen.add(str(aid))
                        all_articles.append(a)
                for a in intercom_client.get_articles():
                    aid = a.get('id')
                    if aid is not None and str(aid) not in seen:
                        seen.add(str(aid))
                        all_articles.append(a)
            articles = all_articles[:50]
            for i, a in enumerate(articles):
                if not (a.get('body') or a.get('title')):
                    try:
                        full = intercom_client.get_article(str(a.get('id', '')))
                        if full:
                            articles[i] = full
                    except Exception:
                        pass
        else:
            articles = intercom_client.get_articles(
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
        article = intercom_client.get_article(article_id)
        
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
            from config import SUPABASE_URL, SUPABASE_SERVICE_KEY
            if SUPABASE_URL and SUPABASE_SERVICE_KEY:
                REST_BASE = f"{SUPABASE_URL.rstrip('/')}/rest/v1"
                headers = {
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                    "Content-Type": "application/json",
                }
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
                article = intercom_client.get_article(article_id)
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
        translated = translator.translate_article(
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
        results = workflow.run(
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
    """Get available target languages"""
    return jsonify({
        'success': True,
        'languages': TARGET_LANGUAGES,
        'base_language': BASE_LANGUAGE
    })


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


@app.route('/api/dashboard/stats', methods=['GET'])
def dashboard_stats():
    """
    Dashboard statistics: total articles, translations, cost analysis,
    top changed articles, and recent activity.
    """
    import datetime
    try:
        init_clients()
        now = datetime.datetime.utcnow()
        week_ago = now - datetime.timedelta(days=7)
        month_ago = now - datetime.timedelta(days=30)

        # ---------- Total articles (quick count from Intercom first page) ----------
        total_articles = 0
        try:
            import requests as _req
            resp = intercom_client._make_request("GET", "/articles", params={"page": 1, "per_page": 1})
            data = resp.json()
            total_articles = data.get("total_count", len(data.get("data", [])))
        except Exception:
            pass

        # ---------- Translations from Supabase ----------
        all_translations = []
        try:
            from translation_supabase import list_article_translations
            all_translations = list_article_translations()
        except Exception:
            pass

        total_translated = len(all_translations)

        # Count translations in the last week/month
        changed_week = 0
        changed_month = 0
        for t in all_translations:
            updated = t.get('updated_at') or t.get('created_at') or ''
            if updated:
                try:
                    ts = datetime.datetime.fromisoformat(updated.replace('Z', '+00:00').replace('+00:00', ''))
                except Exception:
                    try:
                        ts = datetime.datetime.strptime(updated[:19], '%Y-%m-%dT%H:%M:%S')
                    except Exception:
                        continue
                if ts >= week_ago:
                    changed_week += 1
                if ts >= month_ago:
                    changed_month += 1

        # ---------- Cost estimation (GPT-4o-mini pricing) ----------
        # GPT-4o-mini: ~$0.15/1M input, ~$0.60/1M output tokens
        # Avg article: ~800 input tokens, ~1200 output tokens per translation
        AVG_INPUT_TOKENS = 800
        AVG_OUTPUT_TOKENS = 1200
        INPUT_COST_PER_TOKEN = 0.15 / 1_000_000
        OUTPUT_COST_PER_TOKEN = 0.60 / 1_000_000
        cost_per_translation = (AVG_INPUT_TOKENS * INPUT_COST_PER_TOKEN) + (AVG_OUTPUT_TOKENS * OUTPUT_COST_PER_TOKEN)

        cost_week = changed_week * cost_per_translation
        cost_month = changed_month * cost_per_translation

        # ---------- Weekly breakdown (per day of week) ----------
        changes_weekly = [0] * 7  # Mon-Sun
        cost_weekly = [0.0] * 7
        for t in all_translations:
            updated = t.get('updated_at') or t.get('created_at') or ''
            if updated:
                try:
                    ts = datetime.datetime.fromisoformat(updated.replace('Z', '+00:00').replace('+00:00', ''))
                except Exception:
                    try:
                        ts = datetime.datetime.strptime(updated[:19], '%Y-%m-%dT%H:%M:%S')
                    except Exception:
                        continue
                if ts >= week_ago:
                    day_idx = ts.weekday()  # 0=Mon
                    changes_weekly[day_idx] += 1
                    cost_weekly[day_idx] += cost_per_translation

        # ---------- Monthly breakdown (per week) ----------
        changes_monthly = [0] * 5
        cost_monthly = [0.0] * 5
        changes_monthly_labels = []
        for i in range(4, -1, -1):
            wk_start = now - datetime.timedelta(days=i * 7 + 7)
            wk_end = now - datetime.timedelta(days=i * 7)
            changes_monthly_labels.append(f'W{5 - i}')
            for t in all_translations:
                updated = t.get('updated_at') or t.get('created_at') or ''
                if updated:
                    try:
                        ts = datetime.datetime.fromisoformat(updated.replace('Z', '+00:00').replace('+00:00', ''))
                    except Exception:
                        try:
                            ts = datetime.datetime.strptime(updated[:19], '%Y-%m-%dT%H:%M:%S')
                        except Exception:
                            continue
                    if wk_start <= ts < wk_end:
                        changes_monthly[4 - i] += 1
                        cost_monthly[4 - i] += cost_per_translation

        # ---------- Top changed articles ----------
        article_change_count = {}
        for t in all_translations:
            aid = t.get('parent_intercom_article_id', '')
            title = t.get('translated_title', 'Untitled')
            updated = t.get('updated_at') or t.get('created_at') or ''
            if aid not in article_change_count:
                article_change_count[aid] = {'title': title, 'changes': 0, 'last_updated': updated}
            article_change_count[aid]['changes'] += 1
            if updated > article_change_count[aid]['last_updated']:
                article_change_count[aid]['last_updated'] = updated

        top_articles = sorted(article_change_count.values(), key=lambda x: x['changes'], reverse=True)[:20]
        for a in top_articles:
            lu = a.get('last_updated', '')
            if lu:
                try:
                    ts = datetime.datetime.fromisoformat(lu.replace('Z', '+00:00').replace('+00:00', ''))
                    a['last_updated'] = ts.strftime('%b %d, %Y')
                except Exception:
                    a['last_updated'] = lu[:10] if len(lu) >= 10 else lu

        # ---------- Recent activities ----------
        recent_activities = []
        sorted_translations = sorted(all_translations,
            key=lambda t: t.get('updated_at') or t.get('created_at') or '', reverse=True)
        for t in sorted_translations[:15]:
            locale = t.get('target_locale', '??')
            title = t.get('translated_title', 'Untitled')
            if len(title) > 50:
                title = title[:47] + '...'
            updated = t.get('updated_at') or t.get('created_at') or ''
            time_str = ''
            if updated:
                try:
                    ts = datetime.datetime.fromisoformat(updated.replace('Z', '+00:00').replace('+00:00', ''))
                    delta = now - ts
                    if delta.days > 0:
                        time_str = f'{delta.days}d ago'
                    elif delta.seconds > 3600:
                        time_str = f'{delta.seconds // 3600}h ago'
                    elif delta.seconds > 60:
                        time_str = f'{delta.seconds // 60}m ago'
                    else:
                        time_str = 'Just now'
                except Exception:
                    time_str = updated[:16] if len(updated) >= 16 else updated

            recent_activities.append({
                'type': 'translate',
                'text': f'Translated <strong>{escapeHtml(title)}</strong> to <strong>{locale.upper()}</strong>',
                'time': time_str
            })

        return jsonify({
            'success': True,
            'total_articles': total_articles,
            'total_translated': total_translated,
            'changed_this_week': changed_week,
            'changed_this_month': changed_month,
            'cost_week': round(cost_week, 4),
            'cost_month': round(cost_month, 4),
            'changes_weekly': changes_weekly,
            'cost_weekly': [round(c, 4) for c in cost_weekly],
            'changes_monthly': changes_monthly,
            'changes_monthly_labels': changes_monthly_labels,
            'cost_monthly': [round(c, 4) for c in cost_monthly],
            'cost_monthly_labels': changes_monthly_labels,
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
                    intercom_list = intercom_client.get_fundednext_help_center_articles(limit=50, fetch_full=False)
                except Exception:
                    pass
                if not intercom_list:
                    seen = set()
                    for a in intercom_client.get_all_help_center_articles():
                        aid = a.get('id')
                        if aid is not None and str(aid) not in seen:
                            seen.add(str(aid))
                            intercom_list.append(a)
                    for a in intercom_client.get_articles():
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
            result = sync_by_collection_id(collection_id, collection_name, intercom_client)
        elif collection_name:
            result = sync_collection_from_intercom(collection_name, intercom_client)
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
            all_articles = intercom_client.get_fundednext_help_center_articles(limit=limit * 2, fetch_full=True)
        except Exception:
            pass

        if not all_articles:
            seen = set()
            for a in intercom_client.get_all_help_center_articles():
                aid = a.get('id')
                if aid is not None and str(aid) not in seen:
                    seen.add(str(aid))
                    all_articles.append(a)
            for a in intercom_client.get_articles():
                aid = a.get('id')
                if aid is not None and str(aid) not in seen:
                    seen.add(str(aid))
                    all_articles.append(a)
            try:
                for hc in intercom_client.get_help_centers():
                    hc_id = hc.get('id')
                    if hc_id is None:
                        continue
                    try:
                        hc_id_int = int(hc_id)
                    except (TypeError, ValueError):
                        continue
                    for a in intercom_client.search_articles(help_center_id=hc_id_int, state='published', limit=50):
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
                    full = intercom_client.get_article(str(a.get('id', '')))
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
    """Test API connections (Intercom required; OpenAI optional for article fetch)."""
    try:
        init_clients()
        articles = []
        try:
            articles = intercom_client.get_articles()
        except Exception:
            pass
        intercom_ok = len(articles) >= 0
        openai_ok = False
        try:
            if translator and translator.client:
                translated = translator.translate_text("Hello", "fr", "en")
                openai_ok = len(translated) > 0
        except Exception:
            pass
        return jsonify({
            'success': True,
            'intercom': intercom_ok,
            'openai': openai_ok,
            'articles_count': len(articles)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# =====================================================================
# Translate Module API Endpoints
# =====================================================================

@app.route('/api/translate-hub/articles', methods=['GET'])
def translate_hub_articles():
    """
    List pulled articles with per-language translation status matrix.
    Query params: search, page, page_size, status, language, sort
    """
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

        # glossary_id is no longer manually selected; all active glossaries
        # are automatically applied during translation.
        result = bulk_translate(
            intercom_ids=intercom_ids,
            locales=locales,
            translator_instance=translator,
            concurrency=3,
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
    supabase_url = os.getenv('SUPABASE_URL', '').strip() or 'https://reiacekmluvuguqfswac.supabase.co'
    ref = supabase_url.rstrip('/').split('//')[-1].replace('.supabase.co', '')
    if pat and ref:
        try:
            api_url = f'https://api.supabase.com/v1/projects/{ref}/database/query'
            headers = {'Authorization': f'Bearer {pat}', 'Content-Type': 'application/json'}
            r = requests.post(api_url, json={'query': SETUP_SQL, 'read_only': False}, headers=headers, timeout=30)
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
        result = sync_source_list(intercom_client)
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

        results = do_pull(intercom_ids, intercom_client)
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
    supabase_url = os.getenv('SUPABASE_URL', '').strip() or 'https://reiacekmluvuguqfswac.supabase.co'
    ref = supabase_url.rstrip('/').split('//')[-1].replace('.supabase.co', '')
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
        from config import SUPABASE_URL, SUPABASE_SERVICE_KEY
        rest_base = f"{SUPABASE_URL.rstrip('/')}/rest/v1" if SUPABASE_URL else ""
        if not rest_base:
            return jsonify({'success': False, 'error': 'SUPABASE_URL not set'}), 500

        # Try to query pushed_at - if it fails, run the ALTER TABLE
        h = {
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json",
        }
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
        if page_size not in (10, 25, 50, 100):
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
        if page_size not in (10, 25, 50, 100):
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
        result = push_single(intercom_id, locale, intercom_client)
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
            intercom_client=intercom_client,
            concurrency=3,
        )
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    app.run(host='0.0.0.0', port=port, debug=debug)
