"""
Per-request product (tenant) context.

The hub serves multiple products (FundedNext, FN Market, ...) from a single
deployment. Each request resolves an "active product" whose secrets are read
from the environment variables named in ``config.PRODUCTS``. Downstream code
reads the active product's Intercom token, Supabase URL/key, OpenAI key,
languages and branding from here instead of from module-global ``config``.

Design notes
------------
* Secrets are read from the environment at resolve time, never stored in code.
* ``current_product()`` is safe to call outside a request (cron jobs, scripts,
  CLI): it falls back to the default product so existing non-request code paths
  keep working unchanged.
* This module is intentionally free of any global mutable state so two products
  can never bleed into each other through a shared singleton.
"""
import functools
import os
import threading

import config

try:
    from flask import g, request, has_request_context
except Exception:  # pragma: no cover - allows import in non-Flask contexts
    g = None
    request = None

    def has_request_context():
        return False


# Thread-local active-product override. Flask's ``g`` is request/thread-local, so
# worker threads spawned from a request (ThreadPoolExecutor in bulk translate /
# push) do NOT see the request's active product and would otherwise fall back to
# the default product — reading/writing the WRONG tenant's schema. Workers set
# this override (via ``with_current_product``) so ``current_product()`` resolves
# the correct product inside the thread.
_thread_ctx = threading.local()


def bind_thread_product(product_id: str) -> None:
    """Force the active product for the CURRENT thread (worker threads only)."""
    _thread_ctx.product_id = product_id


def clear_thread_product() -> None:
    """Clear this thread's product override."""
    if hasattr(_thread_ctx, "product_id"):
        del _thread_ctx.product_id


def with_current_product(fn):
    """Wrap ``fn`` so it runs under the caller's active product inside a worker
    thread. Capture the active product id NOW (main/request thread), then rebind
    it on the worker thread for the duration of the call.

    Usage: ``executor.submit(with_current_product(job), *args)`` — the wrap must
    happen on the thread that has the request context (the submit loop).
    """
    pid = current_product()["id"]

    @functools.wraps(fn)
    def _wrapped(*args, **kwargs):
        bind_thread_product(pid)
        try:
            return fn(*args, **kwargs)
        finally:
            clear_thread_product()

    return _wrapped


def resolve_product(product_id: str) -> dict:
    """Build a fully-resolved context for ``product_id`` (secrets from env).

    Unknown or missing ids fall back to the default product so a bad ``X-Product``
    header can never crash a request — worst case it serves the default product,
    which is the current single-tenant behavior.
    """
    spec = config.PRODUCTS.get(product_id)
    if not spec:
        product_id = config.DEFAULT_PRODUCT
        spec = config.PRODUCTS[product_id]

    return {
        "id": product_id,
        "name": spec["name"],
        "brand": {
            "name": spec["name"],
            "short": spec["short"],
            "company": spec["company"],
            "domain": spec["domain"],
            "support_email": spec["support_email"],
            "logo_file": spec["logo_file"],
            "theme": spec["theme"],
            # Optional external cost analyzer (url + target_keys). None when the
            # product has no analyzer → template hides the cost panel entirely.
            "cost_analyzer": spec.get("cost_analyzer"),
        },
        "help_center_match": spec["help_center_match"],
        "default_collection": spec["default_collection"],
        "schema": spec.get("schema", "public"),
        "intercom_token": os.getenv(spec["intercom_token_env"], ""),
        "supabase_url": os.getenv(spec["supabase_url_env"], ""),
        "supabase_key": os.getenv(spec["supabase_key_env"], ""),
        "supabase_db_url": os.getenv(spec.get("supabase_db_url_env", ""), ""),
        "openai_key": os.getenv(spec["openai_key_env"], ""),
        "default_languages": spec["default_languages"],
    }


def pick_product_id() -> str:
    """Determine the active product id for the current request.

    Priority: ``X-Product`` header -> ``?product=`` query -> ``active_product``
    cookie -> default. Anything not in the registry resolves to the default.
    """
    pid = config.DEFAULT_PRODUCT
    if has_request_context():
        pid = (
            request.headers.get("X-Product")
            or request.args.get("product")
            or request.cookies.get("active_product")
            or config.DEFAULT_PRODUCT
        )
    if pid not in config.PRODUCTS:
        pid = config.DEFAULT_PRODUCT
    return pid


def load_active_product() -> None:
    """``before_request`` hook: resolve and stash the active product on ``g``."""
    if g is not None:
        g.product = resolve_product(pick_product_id())


def current_product() -> dict:
    """Return the active product context.

    Inside a request this is whatever ``load_active_product`` stashed on ``g``.
    Outside a request (cron/scripts) it resolves the default product lazily.
    """
    if g is not None and has_request_context():
        prod = getattr(g, "product", None)
        if prod is None:
            prod = resolve_product(pick_product_id())
            g.product = prod
        return prod
    # Worker thread (no request context): honor an explicit per-thread override
    # before falling back to the default product.
    pid = getattr(_thread_ctx, "product_id", None)
    if pid:
        return resolve_product(pid)
    return resolve_product(config.DEFAULT_PRODUCT)


# ─── Supabase helpers (resolve the ACTIVE product's DB per call) ──────────────
# Service modules must call these at request time — never bind SUPABASE_URL /
# REST_BASE at import, or they freeze to whichever product was default at import
# and leak across tenants on a warm serverless instance.

def supabase_rest_base() -> str:
    """PostgREST base URL for the active product's database.

    Returns "" when the product has no Supabase URL configured, preserving the
    original modules' graceful-skip behavior (their own guards raise/return).
    """
    url = current_product()["supabase_url"]
    return f"{url.rstrip('/')}/rest/v1" if url else ""


class LazyStr:
    """A string-like proxy whose value is recomputed on every access.

    Lets a service module keep a module-level name like ``REST_BASE`` while its
    value follows the ACTIVE product per call. f-strings, concatenation,
    truthiness, len, equality and all str methods delegate to the freshly
    resolved string, so existing call sites need no changes.
    """
    __slots__ = ("_fn",)

    def __init__(self, fn):
        object.__setattr__(self, "_fn", fn)

    def __str__(self):
        return self._fn()

    def __repr__(self):
        return self._fn()

    def __format__(self, spec):
        return format(self._fn(), spec)

    def __bool__(self):
        return bool(self._fn())

    def __len__(self):
        return len(self._fn())

    def __eq__(self, other):
        return self._fn() == other

    def __hash__(self):
        return hash(self._fn())

    def __add__(self, other):
        return self._fn() + other

    def __radd__(self, other):
        return other + self._fn()

    def __getitem__(self, item):
        return self._fn()[item]

    def __getattr__(self, name):
        return getattr(self._fn(), name)


def supabase_headers(extra: dict = None, schema: str = None) -> dict:
    """Auth + schema headers for the active product's Supabase (service role).

    Shared-DB isolation: PostgREST selects the target Postgres schema from
    Accept-Profile (reads) / Content-Profile (writes). We set both to the active
    product's schema, so FundedNext hits `public` (its existing tables) and
    FN Market hits `fnmarket` — same project, physically separate tables.

    Pass ``schema`` to force a specific schema regardless of the active product —
    used for genuinely shared, product-agnostic data (e.g. the cost analyzer's
    ``daily_api_costs``, which every product reports identically from `public`).
    """
    prod = current_product()
    key = prod["supabase_key"]
    if not key:
        raise ValueError("SUPABASE_SERVICE_KEY must be set for the active product")
    schema = schema or prod.get("schema", "public")
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept-Profile": schema,
        "Content-Profile": schema,
    }
    if extra:
        headers.update(extra)
    return headers


def supabase_url_value() -> str:
    """Active product's Supabase URL (for module-level guard proxies)."""
    return current_product()["supabase_url"]


def supabase_key_value() -> str:
    """Active product's Supabase service key (for module-level guard proxies)."""
    return current_product()["supabase_key"]


# Per-product active-language cache. Module-level so it persists across requests
# on a warm instance (matching the original global config.TARGET_LANGUAGES), but
# keyed by product id so products never share a language set. language_service
# populates a product's entry from its own DB via the TARGET_LANGUAGES proxy.
_LANG_CACHE: dict = {}


def active_languages_dict() -> dict:
    """The mutable language dict for the active product.

    Seeded from the product's registry defaults on first access; language_service
    overwrites it (clear/update via the proxy) with the set loaded from that
    product's database.
    """
    pid = current_product()["id"]
    d = _LANG_CACHE.get(pid)
    if d is None:
        d = dict(current_product()["default_languages"])
        _LANG_CACHE[pid] = d
    return d


def active_languages() -> dict:
    """Alias — target languages for the active product."""
    return active_languages_dict()


class LazyDict:
    """A dict-like proxy resolving to the active product's dict on every access.

    Lets ``config.TARGET_LANGUAGES`` stay a single importable name while it
    follows the active product. Reads, iteration, membership, len and the mutating
    dict methods (clear/update/get/items/keys/values) all delegate to the freshly
    resolved dict, so existing call sites and language_service need no changes.
    """
    __slots__ = ("_fn",)

    def __init__(self, fn):
        object.__setattr__(self, "_fn", fn)

    def __getitem__(self, key):
        return self._fn()[key]

    def __setitem__(self, key, value):
        self._fn()[key] = value

    def __delitem__(self, key):
        del self._fn()[key]

    def __contains__(self, key):
        return key in self._fn()

    def __iter__(self):
        return iter(self._fn())

    def __len__(self):
        return len(self._fn())

    def __bool__(self):
        return bool(self._fn())

    def __eq__(self, other):
        return self._fn() == other

    def __repr__(self):
        return repr(self._fn())

    def __getattr__(self, name):
        return getattr(self._fn(), name)
