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
import os

import config

try:
    from flask import g, request, has_request_context
except Exception:  # pragma: no cover - allows import in non-Flask contexts
    g = None
    request = None

    def has_request_context():
        return False


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
        },
        "help_center_match": spec["help_center_match"],
        "default_collection": spec["default_collection"],
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
    return resolve_product(config.DEFAULT_PRODUCT)
