"""
viibeware Corp. — Corporate Website
Flask application with admin content management backend.
"""

import io
import json
import os
import time
import zipfile
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, jsonify, send_from_directory, send_file
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "viibeware-dev-key-change-in-prod")
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200MB — admin-only uploads, accommodates full-site backup zips
app.config['SESSION_COOKIE_NAME'] = 'viibeware_session'
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)


@app.before_request
def _log_admin_auth():
    """Print cookie + session state for /admin/* POSTs so we can diagnose
    why sessions are getting dropped on upload. Logs go to the container's
    stdout (docker compose logs viibeware-web)."""
    if request.path.startswith("/admin") and request.method == "POST":
        has_cookie = bool(request.cookies.get("session"))
        is_logged_in = bool(session.get("admin_logged_in"))
        print(
            f"[auth] {request.method} {request.path} "
            f"cookie_present={has_cookie} logged_in={is_logged_in} "
            f"ct={request.content_type!r} "
            f"ua={request.headers.get('User-Agent','')[:60]!r}",
            flush=True,
        )

CONTENT_FILE = os.path.join(os.path.dirname(__file__), "data", "content.json")
CONTENT_EXAMPLE = os.path.join(os.path.dirname(__file__), "data", "content.example.json")
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "uploads")
CHROME_DIR = os.path.join(os.path.dirname(__file__), "static", "img")
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}

os.makedirs(UPLOAD_DIR, exist_ok=True)

# Auto-create content.json from example on first run
if not os.path.exists(CONTENT_FILE) and os.path.exists(CONTENT_EXAMPLE):
    import shutil
    shutil.copy2(CONTENT_EXAMPLE, CONTENT_FILE)


def _rewrite_img_refs(node):
    """Walk a nested structure and rewrite any 'img/X' string to 'uploads/X'
    when the file exists in static/uploads/. Returns True if anything changed.

    Leaves references alone when the file only exists as chrome (static/img/) —
    e.g. the default og-image.png or logo.svg shipped with the app."""
    changed = False
    if isinstance(node, dict):
        for k, v in list(node.items()):
            if isinstance(v, str) and v.startswith("img/"):
                basename = v[len("img/"):]
                if "/" in basename or "\\" in basename:
                    continue
                if os.path.exists(os.path.join(UPLOAD_DIR, basename)):
                    node[k] = f"uploads/{basename}"
                    changed = True
            elif isinstance(v, (dict, list)):
                if _rewrite_img_refs(v):
                    changed = True
    elif isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, str) and v.startswith("img/"):
                basename = v[len("img/"):]
                if "/" in basename or "\\" in basename:
                    continue
                if os.path.exists(os.path.join(UPLOAD_DIR, basename)):
                    node[i] = f"uploads/{basename}"
                    changed = True
            elif isinstance(v, (dict, list)):
                if _rewrite_img_refs(v):
                    changed = True
    return changed


def _migrate_img_to_uploads_once():
    """One-shot path migration after split of chrome (static/img/) from user
    uploads (static/uploads/). On environments upgrading from a layout where
    uploads lived under static/img/, Docker volume remap means the files are
    already in static/uploads/ — we just need to rewrite any 'img/X' refs in
    content.json to 'uploads/X'. Snapshots content.json before writing."""
    if not os.path.exists(CONTENT_FILE):
        return
    try:
        with open(CONTENT_FILE, "r") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return
    if not _rewrite_img_refs(data):
        return
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    snapshot = os.path.join(
        os.path.dirname(CONTENT_FILE),
        f"content.pre-uploads-migration-{stamp}.json",
    )
    try:
        with open(CONTENT_FILE, "rb") as src, open(snapshot, "wb") as dst:
            dst.write(src.read())
    except OSError:
        pass
    with open(CONTENT_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[migrate] Rewrote img/X → uploads/X in content.json; snapshot: {snapshot}", flush=True)


_migrate_img_to_uploads_once()

# Cache bust key — changes on every app restart
CACHE_VERSION = str(int(time.time()))

# Site version — displayed in admin panel only
SITE_VERSION = "0.5.0"


@app.context_processor
def inject_globals():
    """Make cache version, site version, and branding available in all
    templates (public site, admin pages, login page)."""
    try:
        branding = load_content().get("branding", {})
    except Exception:
        branding = {}
    return {
        "cache_v": CACHE_VERSION,
        "site_version": SITE_VERSION,
        "branding": branding,
    }

# --- Admin credentials ---
# DEFAULT_ADMIN_PASS is the "fresh install" password; first login with this
# value triggers a mandatory password change. Once the user sets a custom
# password via the admin UI, the hash is stored in data/auth.json and takes
# precedence over this default (and the ADMIN_PASS env var).
DEFAULT_ADMIN_PASS = "admin"
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", DEFAULT_ADMIN_PASS)
AUTH_FILE = os.path.join(os.path.dirname(__file__), "data", "auth.json")

ROLES = ("admin", "editor")


def _empty_auth():
    return {
        "users": [],
        "settings": {
            "turnstile": {"enabled": False, "site_key": "", "secret_key": ""},
        },
    }


def load_auth():
    """Read the admin auth config, migrating legacy shapes to the current
    schema. Returns a dict with `users` (list) and `settings` (dict) keys."""
    if not os.path.exists(AUTH_FILE):
        return _empty_auth()
    try:
        with open(AUTH_FILE, "r") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return _empty_auth()

    # Legacy single-user shape: {password_hash, password_changed_at}
    if "users" not in data and "password_hash" in data:
        data = {
            "users": [{
                "id": "user-admin",
                "username": ADMIN_USER,
                "password_hash": data.get("password_hash", ""),
                "role": "admin",
                "created_at": data.get("password_changed_at", datetime.utcnow().isoformat(timespec="seconds") + "Z"),
                "password_changed_at": data.get("password_changed_at", ""),
            }],
            "settings": {
                "turnstile": {"enabled": False, "site_key": "", "secret_key": ""},
            },
        }
        try:
            save_auth(data)
            print("[migrate] auth.json reshaped: legacy → users[]+settings", flush=True)
        except OSError:
            pass

    data.setdefault("users", [])
    data.setdefault("settings", {})
    data["settings"].setdefault(
        "turnstile",
        {"enabled": False, "site_key": "", "secret_key": ""},
    )
    return data


def save_auth(data):
    with open(AUTH_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _new_user_id(existing_ids):
    n = 1
    while f"user-{n}" in existing_ids:
        n += 1
    return f"user-{n}"


def get_user_by_username(username):
    for u in load_auth().get("users", []):
        if u.get("username") == username:
            return u
    return None


def get_user_by_id(user_id):
    for u in load_auth().get("users", []):
        if u.get("id") == user_id:
            return u
    return None


def verify_user_credentials(username, password):
    """Return the matching user dict (for a stored user) or a synthetic
    bootstrap user dict if no users exist yet and credentials match the
    env/default. Returns None on failure."""
    if not username or not password:
        return None
    auth = load_auth()
    users = auth.get("users", [])
    for u in users:
        if u.get("username") != username:
            continue
        h = u.get("password_hash", "")
        try:
            if h and check_password_hash(h, password):
                return u
        except Exception:
            pass
        return None  # username matched but password didn't
    # Bootstrap path: no users yet, fall through to env credentials
    if not users and username == ADMIN_USER and password == ADMIN_PASS:
        return {
            "id": "bootstrap",
            "username": ADMIN_USER,
            "role": "admin",
            "password_hash": "",
            "bootstrap": True,
        }
    return None


def current_user():
    """Return the logged-in user dict for the current session, or None."""
    uid = session.get("user_id")
    if uid:
        u = get_user_by_id(uid)
        if u:
            return u
    # Pre-bootstrap session (first login before a user record exists)
    if session.get("bootstrap_admin"):
        return {"id": "bootstrap", "username": ADMIN_USER, "role": "admin", "bootstrap": True}
    # Legacy session recovery — sessions started before the 0.4.0 schema
    # change have `admin_logged_in` set but no `user_id`. If an admin user
    # matching ADMIN_USER exists, promote them onto this session so the
    # user doesn't need to log out + back in to see admin UI.
    if session.get("admin_logged_in"):
        u = get_user_by_username(ADMIN_USER)
        if u:
            session["user_id"] = u["id"]
            return u
    return None


def is_using_default_password():
    """True if the currently logged-in session is a bootstrap session (no
    user record yet, signed in via default env credentials)."""
    return bool(session.get("bootstrap_admin"))


def validate_password_strength(pw):
    """Return a human-readable error message if the password is too weak,
    else None. Rules: ≥12 chars, must include upper, lower, and digit."""
    if len(pw) < 12:
        return "Password must be at least 12 characters long."
    if not any(c.isupper() for c in pw):
        return "Password must include an uppercase letter."
    if not any(c.islower() for c in pw):
        return "Password must include a lowercase letter."
    if not any(c.isdigit() for c in pw):
        return "Password must include a digit."
    if pw == DEFAULT_ADMIN_PASS:
        return "Please choose a password different from the default."
    return None


# ─── Turnstile ─────────────────────────────────────────────────

def turnstile_settings():
    return load_auth().get("settings", {}).get("turnstile", {}) or {}


def turnstile_enabled():
    s = turnstile_settings()
    return bool(s.get("enabled") and s.get("site_key") and s.get("secret_key"))


def verify_turnstile(token, remote_ip=""):
    """Server-side verification with Cloudflare. Returns True on success."""
    s = turnstile_settings()
    secret = (s.get("secret_key") or "").strip()
    if not secret:
        return False
    if not token:
        return False
    try:
        import urllib.parse
        payload = {"secret": secret, "response": token}
        if remote_ip:
            payload["remoteip"] = remote_ip
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            body = json.loads(r.read().decode("utf-8"))
        return bool(body.get("success"))
    except Exception as e:
        print(f"[turnstile] verify failed: {e}", flush=True)
        return False


_DEFAULT_INSTALL_TABS = [
    {"id": "docker", "label": "Docker Compose", "enabled": True, "steps": []},
    {"id": "quickrun", "label": "Quick Run", "enabled": False, "steps": []},
    {"id": "manual", "label": "Manual", "enabled": False, "steps": []},
]


def _backfill_product(p):
    """Ensure a product dict has every expected field."""
    p.setdefault("id", "product")
    p.setdefault("name", "New Product")
    p.setdefault("version", "")
    p.setdefault("github_repo", "")
    p.setdefault("version_source", "manual")
    p.setdefault("version_fetched_at", "")
    p.setdefault("tagline", "")
    p.setdefault("description", "")
    p.setdefault("logo", "")
    p.setdefault("logo_size", 80)
    p.setdefault("title_size", 0)  # 0 = use the CSS default (responsive clamp)
    p.setdefault("featured_image", "")
    p.setdefault("screenshots", [])
    p.setdefault("features", [])
    p.setdefault("tech_stack", [])
    p.setdefault("repo_links", [])
    p.setdefault("install_tabs", [
        {"id": tab["id"], "label": tab["label"], "enabled": tab["enabled"], "steps": []}
        for tab in _DEFAULT_INSTALL_TABS
    ])
    # Normalize each install tab
    for tab in p["install_tabs"]:
        tab.setdefault("id", "tab")
        tab.setdefault("label", tab["id"].title())
        tab.setdefault("enabled", False)
        tab.setdefault("steps", [])
    # Normalize each repo link
    for link in p["repo_links"]:
        link.setdefault("id", "")
        link.setdefault("label", "Link")
        link.setdefault("url", "")
        link.setdefault("icon", "")
        link.setdefault("enabled", False)
    return p


def _migrate_products_schema(data):
    """Reshape legacy `product` + `product3` keys into a `products` array, with
    repo_links + install_tabs as lists and step arrays folded into their tab.

    Also upgrades `sections` entries to include `type` (hero/about/product/install)
    and `product_id` where applicable. Runs exactly once — detected by the
    presence of a top-level `products` key."""
    if "products" in data and isinstance(data["products"], list):
        return False

    products = []
    # Preserve order: product, then product3 (legacy keys we know of)
    for legacy_key in ("product", "product3"):
        if legacy_key not in data:
            continue
        p = data.pop(legacy_key)
        if not isinstance(p, dict):
            continue
        p["id"] = legacy_key

        # repo_links: dict → list
        rl = p.get("repo_links")
        if isinstance(rl, dict):
            links = []
            for link_id, link in rl.items():
                if not isinstance(link, dict):
                    continue
                links.append({
                    "id": link_id,
                    "label": link.get("label", link_id.title()),
                    "url": link.get("url", ""),
                    "icon": link_id if link_id in ("github", "dockerhub") else "",
                    "enabled": bool(link.get("enabled", False)),
                })
            p["repo_links"] = links
        elif not isinstance(rl, list):
            p["repo_links"] = []

        # install_tabs: dict → list, merging flat step arrays
        it = p.get("install_tabs")
        step_map = {
            "docker": "docker_steps",
            "quickrun": "quickrun_steps",
            "manual": "install_steps",
        }
        if isinstance(it, dict):
            tabs = []
            for tab_id in ("docker", "quickrun", "manual"):
                tab = it.get(tab_id, {}) if isinstance(it.get(tab_id), dict) else {}
                step_field = step_map[tab_id]
                steps = p.get(step_field) or []
                tabs.append({
                    "id": tab_id,
                    "label": tab.get("label", tab_id.title()),
                    "enabled": bool(tab.get("enabled", False)),
                    "steps": steps if isinstance(steps, list) else [],
                })
            # Include any additional tabs from the old dict
            for tab_id, tab in it.items():
                if tab_id in ("docker", "quickrun", "manual"):
                    continue
                if not isinstance(tab, dict):
                    continue
                tabs.append({
                    "id": tab_id,
                    "label": tab.get("label", tab_id.title()),
                    "enabled": bool(tab.get("enabled", False)),
                    "steps": [],
                })
            p["install_tabs"] = tabs
        elif not isinstance(it, list):
            p["install_tabs"] = []

        # Drop now-migrated flat step arrays
        for flat in ("docker_steps", "quickrun_steps", "install_steps"):
            p.pop(flat, None)

        products.append(p)

    data["products"] = products

    # Upgrade sections: infer type + product_id from legacy ids
    sections = data.get("sections", [])
    if isinstance(sections, list):
        for sec in sections:
            if not isinstance(sec, dict):
                continue
            if "type" in sec:
                continue
            sid = sec.get("id", "")
            if sid == "hero":
                sec["type"] = "hero"
            elif sid == "about":
                sec["type"] = "about"
            elif sid in ("product", "product3"):
                sec["type"] = "product"
                sec["product_id"] = sid
            elif sid == "download":
                sec["type"] = "install"
                sec["product_id"] = "product"
            elif sid == "download3":
                sec["type"] = "install"
                sec["product_id"] = "product3"
            else:
                sec["type"] = sec.get("type", "custom")
        data["sections"] = sections

    return True


def load_content():
    """Load site content from JSON, applying one-time schema migration and
    backfilling any missing fields. Safe to call on every request."""
    with open(CONTENT_FILE, "r") as f:
        raw_text = f.read()
        data = json.loads(raw_text)

    # One-time schema migration (product/product3 → products[])
    if _migrate_products_schema(data):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        snapshot = os.path.join(
            os.path.dirname(CONTENT_FILE),
            f"content.pre-products-migration-{stamp}.json",
        )
        try:
            with open(snapshot, "w") as out:
                out.write(raw_text)
        except OSError:
            pass
        with open(CONTENT_FILE, "w") as out:
            json.dump(data, out, indent=2)
        print(f"[migrate] Reshaped product/product3 → products[]; snapshot: {snapshot}", flush=True)

    # Ensure top-level structure
    data.setdefault("sections", [])
    data.setdefault("hero", {})
    data.setdefault("about", {})
    data.setdefault("nav", {"links": []})
    data.setdefault("footer", {})
    data.setdefault("og", {})
    data.setdefault("products", [])

    # Backfill each product
    for product in data["products"]:
        _backfill_product(product)

    # Hero backfill
    hero = data["hero"]
    hero.setdefault("headline", "")
    hero.setdefault("subheadline", "")
    hero.setdefault("cta_primary", "")
    hero.setdefault("cta_secondary", "")

    # About backfill
    about = data["about"]
    about.setdefault("title", "")
    about.setdefault("body", "")
    about.setdefault("principles", [])

    # Nav backfill
    nav = data["nav"]
    nav.setdefault("links", [])

    # Footer backfill — normalize legacy string forms
    footer = data["footer"]
    footer.setdefault("tagline", "")
    footer.setdefault("year", datetime.now().year)
    if isinstance(footer.get("github"), str):
        footer["github"] = {"url": footer["github"], "enabled": True}
    footer.setdefault("github", {"url": "", "enabled": False})
    footer.setdefault("bluesky", {"url": "", "enabled": False})
    if isinstance(footer.get("email"), str):
        footer["email"] = {"address": footer["email"], "enabled": True}
    footer.setdefault("email", {"address": "", "enabled": False})

    # OG backfill
    og = data["og"]
    og.setdefault("title", "")
    og.setdefault("description", "")
    og.setdefault("url", "")
    og.setdefault("image", "img/og-image.png")

    # Branding backfill — controls site name and how it's displayed
    data.setdefault("branding", {})
    branding = data["branding"]
    branding.setdefault("name", "viibeware")
    branding.setdefault("emphasis_part", "viibe")
    branding.setdefault("transform", "none")  # none | lowercase | uppercase | capitalize
    branding.setdefault("font_size_rem", 1.15)
    branding.setdefault("logo_size_px", 32)
    branding.setdefault("color_primary", "#e8e8f0")
    branding.setdefault("color_accent", "#00F2FF")
    branding.setdefault("page_title_suffix", "Corp. — We Don't Write Code")

    return data


def save_content(data):
    """Save site content to JSON file."""
    with open(CONTENT_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_product(content, product_id):
    """Look up a product by id within the loaded content."""
    for p in content.get("products", []):
        if p.get("id") == product_id:
            return p
    return None


# ─── GitHub version auto-refresh ───────────────────────────────
import threading
import urllib.request
import urllib.error

VERSION_REFRESH_INTERVAL_SECONDS = 6 * 60 * 60  # 6 hours
VERSION_REFRESH_COOLDOWN_SECONDS = 5 * 60  # Cross-worker: skip if another worker refreshed within 5 min
VERSION_REFRESH_LOCK_FILE = os.path.join(os.path.dirname(__file__), "data", ".version-refresh-lock")


def fetch_github_version(repo, source):
    """Fetch the latest version from GitHub for `owner/repo`.

    `source` is one of "github_release" (uses /releases/latest) or
    "github_tag" (uses /tags and picks the first). Returns the tag string
    with a leading 'v' stripped, or None on failure."""
    repo = (repo or "").strip().strip("/")
    if not repo or "/" not in repo:
        return None

    headers = {
        "User-Agent": "viibeware-web",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    if source == "github_release":
        url = f"https://api.github.com/repos/{repo}/releases/latest"
    elif source == "github_tag":
        url = f"https://api.github.com/repos/{repo}/tags?per_page=1"
    else:
        return None

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            payload = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"[version] {repo} {source}: HTTP {e.code} {e.reason}", flush=True)
        return None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        print(f"[version] {repo} {source}: {e}", flush=True)
        return None

    if source == "github_release":
        tag = (payload.get("tag_name") or "").strip()
    else:
        tag = (payload[0].get("name") or "").strip() if isinstance(payload, list) and payload else ""

    if tag.startswith("v") and len(tag) > 1 and tag[1].isdigit():
        tag = tag[1:]
    return tag or None


def refresh_all_versions(force=False):
    """Walk every product configured for auto-version, fetch the latest
    version from GitHub, and write the updated content.json if any changes.

    Returns a list of dicts describing what was checked: `{id, repo, source,
    old, new, updated, error?}`. A lock file is used for cross-worker
    cooldown so multiple gunicorn workers don't hammer the GitHub API."""
    now = time.time()
    if not force:
        try:
            if os.path.exists(VERSION_REFRESH_LOCK_FILE):
                age = now - os.path.getmtime(VERSION_REFRESH_LOCK_FILE)
                if age < VERSION_REFRESH_COOLDOWN_SECONDS:
                    return []
        except OSError:
            pass
    try:
        with open(VERSION_REFRESH_LOCK_FILE, "w") as f:
            f.write(str(int(now)))
    except OSError:
        pass

    try:
        with open(CONTENT_FILE, "r") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []

    results = []
    dirty = False
    for product in data.get("products", []):
        source = product.get("version_source") or "manual"
        repo = (product.get("github_repo") or "").strip()
        if source == "manual" or not repo:
            continue
        new_version = fetch_github_version(repo, source)
        old_version = product.get("version", "")
        entry = {
            "id": product.get("id"),
            "repo": repo,
            "source": source,
            "old": old_version,
            "new": new_version,
            "updated": False,
        }
        if new_version is None:
            entry["error"] = "fetch failed"
            results.append(entry)
            continue
        product["version_fetched_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        dirty = True  # timestamp always changes
        if new_version != old_version:
            product["version"] = new_version
            entry["updated"] = True
        results.append(entry)

    if dirty:
        try:
            with open(CONTENT_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except OSError as e:
            print(f"[version] failed to save content.json: {e}", flush=True)

    updated = [r for r in results if r.get("updated")]
    if updated:
        summary = ", ".join(f"{r['id']}: {r['old'] or '∅'} → {r['new']}" for r in updated)
        print(f"[version] refreshed: {summary}", flush=True)
    return results


def _version_refresh_loop():
    """Background thread: periodic version refresh every 6 hours."""
    time.sleep(30)  # stagger startup so workers don't all hit GH at once
    while True:
        try:
            refresh_all_versions()
        except Exception as e:
            print(f"[version] background loop error: {e}", flush=True)
        time.sleep(VERSION_REFRESH_INTERVAL_SECONDS)


def _start_version_refresh_thread():
    """Start the background refresher once per worker. The lock file in
    refresh_all_versions() prevents multiple workers from duplicating work."""
    if os.environ.get("WERKZEUG_RUN_MAIN") == "false":
        return  # Flask reloader parent — skip
    t = threading.Thread(target=_version_refresh_loop, daemon=True, name="version-refresh")
    t.start()


_start_version_refresh_thread()


def _wants_json():
    return (
        request.is_json
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in request.headers.get("Accept", "")
    )


def login_required(f):
    """Decorator to require admin login."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            if _wants_json():
                return jsonify({"status": "error", "message": "Not logged in"}), 401
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


def role_required(*allowed_roles):
    """Decorator to require the logged-in user to have one of the given roles.
    login_required must be applied separately (or use @role_required alone —
    it also checks login). Returns 403 for authenticated users lacking the role."""
    def wrapper(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get("admin_logged_in"):
                if _wants_json():
                    return jsonify({"status": "error", "message": "Not logged in"}), 401
                return redirect(url_for("admin_login"))
            u = current_user()
            if not u or u.get("role") not in allowed_roles:
                if _wants_json():
                    return jsonify({"status": "error", "message": "Forbidden"}), 403
                flash("You don't have permission to access that page.", "error")
                return redirect(url_for("admin_dashboard"))
            return f(*args, **kwargs)
        return decorated
    return wrapper


# ─── Public Routes ─────────────────────────────────────────────

@app.route("/")
def index():
    """Render the main homepage."""
    content = load_content()
    return render_template("index.html", content=content)


# ─── Admin Routes ──────────────────────────────────────────────

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """Admin login page."""
    ts = turnstile_settings()
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if turnstile_enabled():
            token = request.form.get("cf-turnstile-response", "")
            if not verify_turnstile(token, request.remote_addr or ""):
                flash("Turnstile check failed. Please try again.", "error")
                return render_template("admin_login.html", turnstile=ts)
        user = verify_user_credentials(username, password)
        if not user:
            flash("Invalid credentials.", "error")
            return render_template("admin_login.html", turnstile=ts)
        session.permanent = True
        session["admin_logged_in"] = True
        if user.get("bootstrap"):
            session["bootstrap_admin"] = True
            session["must_change_password"] = True
            session.pop("user_id", None)
            flash("You're signed in with the default password. Please set a new one to continue.", "success")
            return redirect(url_for("admin_change_password"))
        session["user_id"] = user["id"]
        session.pop("bootstrap_admin", None)
        session.pop("must_change_password", None)
        flash("Logged in successfully.", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_login.html", turnstile=ts)


@app.before_request
def _enforce_password_change():
    """If the user is logged in with the default password, force them through
    /admin/change-password before they can reach any other admin page."""
    if not session.get("admin_logged_in"):
        return
    if not session.get("must_change_password"):
        return
    # Allow the change-password page itself, logout, and static files
    if request.endpoint in {"admin_change_password", "admin_logout", "static"}:
        return
    # Only intercept admin routes; leave public pages alone
    if request.path.startswith("/admin"):
        if request.method == "POST" and (
            request.is_json
            or request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or "application/json" in request.headers.get("Accept", "")
        ):
            return jsonify({"status": "error", "message": "Password change required"}), 403
        return redirect(url_for("admin_change_password"))


@app.route("/admin/change-password", methods=["GET", "POST"])
@login_required
def admin_change_password():
    must_change = bool(session.get("must_change_password"))
    bootstrap = bool(session.get("bootstrap_admin"))
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")

        # Verify "current password" — for bootstrap it's the env/default value
        if bootstrap:
            current_ok = (current == ADMIN_PASS)
        else:
            u = current_user()
            current_ok = bool(u and u.get("password_hash") and check_password_hash(u["password_hash"], current))
        if not current_ok:
            flash("Current password is incorrect.", "error")
            return render_template("admin/change_password.html", must_change=must_change)

        if new != confirm:
            flash("The two new passwords do not match.", "error")
            return render_template("admin/change_password.html", must_change=must_change)

        err = validate_password_strength(new)
        if err:
            flash(err, "error")
            return render_template("admin/change_password.html", must_change=must_change)

        auth = load_auth()
        now_iso = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        if bootstrap:
            # Create the first admin user
            uid = _new_user_id({u["id"] for u in auth.get("users", [])})
            new_user = {
                "id": uid,
                "username": ADMIN_USER,
                "password_hash": generate_password_hash(new),
                "role": "admin",
                "created_at": now_iso,
                "password_changed_at": now_iso,
            }
            auth.setdefault("users", []).append(new_user)
            save_auth(auth)
            session.pop("bootstrap_admin", None)
            session["user_id"] = uid
        else:
            u = current_user()
            for stored in auth.get("users", []):
                if stored["id"] == u["id"]:
                    stored["password_hash"] = generate_password_hash(new)
                    stored["password_changed_at"] = now_iso
                    break
            save_auth(auth)
        session.pop("must_change_password", None)
        flash("Password updated.", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("admin/change_password.html", must_change=must_change)


@app.route("/admin/logout")
def admin_logout():
    """Log out of admin."""
    for key in ("admin_logged_in", "user_id", "bootstrap_admin", "must_change_password"):
        session.pop(key, None)
    flash("Logged out.", "success")
    return redirect(url_for("index"))


# ─── Settings + Users (admin-only) ─────────────────────────────

def _user_dto(u):
    """Return the safe public fields of a user (no hash)."""
    return {
        "id": u.get("id"),
        "username": u.get("username"),
        "role": u.get("role"),
        "created_at": u.get("created_at", ""),
        "password_changed_at": u.get("password_changed_at", ""),
    }


@app.route("/admin/settings", methods=["GET"])
@role_required("admin")
def admin_settings_get():
    auth = load_auth()
    ts = auth.get("settings", {}).get("turnstile", {}) or {}
    return jsonify({
        "status": "ok",
        "turnstile": {
            "enabled": bool(ts.get("enabled")),
            "site_key": ts.get("site_key", ""),
            "secret_key_set": bool(ts.get("secret_key")),
        },
        "users": [_user_dto(u) for u in auth.get("users", [])],
        "current_user_id": (current_user() or {}).get("id"),
        "roles": list(ROLES),
    })


@app.route("/admin/settings/turnstile", methods=["POST"])
@role_required("admin")
def admin_settings_turnstile():
    data = request.get_json(silent=True) or {}
    auth = load_auth()
    ts = auth.get("settings", {}).setdefault("turnstile", {"enabled": False, "site_key": "", "secret_key": ""})
    if "enabled" in data:
        ts["enabled"] = bool(data["enabled"])
    if "site_key" in data:
        ts["site_key"] = (data.get("site_key") or "").strip()
    # Only overwrite secret if a non-empty value is supplied (so saving with a
    # blank field doesn't clobber the stored secret when it's hidden in the UI)
    sk = data.get("secret_key")
    if sk is not None and str(sk).strip() != "":
        ts["secret_key"] = str(sk).strip()
    if data.get("clear_secret_key"):
        ts["secret_key"] = ""
    save_auth(auth)
    return jsonify({"status": "ok", "message": "Turnstile settings saved"})


@app.route("/admin/users", methods=["POST"])
@role_required("admin")
def admin_user_new():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    role = data.get("role") or "editor"
    if not username:
        return jsonify({"status": "error", "message": "Username is required"}), 400
    if role not in ROLES:
        return jsonify({"status": "error", "message": f"Invalid role (allowed: {', '.join(ROLES)})"}), 400
    if get_user_by_username(username):
        return jsonify({"status": "error", "message": "Username already in use"}), 400
    err = validate_password_strength(password)
    if err:
        return jsonify({"status": "error", "message": err}), 400
    auth = load_auth()
    uid = _new_user_id({u["id"] for u in auth["users"]})
    now_iso = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    user = {
        "id": uid,
        "username": username,
        "password_hash": generate_password_hash(password),
        "role": role,
        "created_at": now_iso,
        "password_changed_at": now_iso,
    }
    auth["users"].append(user)
    save_auth(auth)
    return jsonify({"status": "ok", "message": f"User '{username}' created", "user": _user_dto(user)})


@app.route("/admin/users/<user_id>", methods=["POST"])
@role_required("admin")
def admin_user_update(user_id):
    data = request.get_json(silent=True) or {}
    auth = load_auth()
    target = None
    for u in auth["users"]:
        if u["id"] == user_id:
            target = u
            break
    if not target:
        return jsonify({"status": "error", "message": "User not found"}), 404

    me = current_user() or {}

    if "role" in data:
        new_role = data["role"]
        if new_role not in ROLES:
            return jsonify({"status": "error", "message": "Invalid role"}), 400
        # Don't allow demoting yourself or removing the last admin
        admins = [u for u in auth["users"] if u.get("role") == "admin"]
        if target.get("role") == "admin" and new_role != "admin" and len(admins) <= 1:
            return jsonify({"status": "error", "message": "Cannot demote the last remaining admin"}), 400
        target["role"] = new_role

    if "password" in data and data["password"]:
        err = validate_password_strength(data["password"])
        if err:
            return jsonify({"status": "error", "message": err}), 400
        target["password_hash"] = generate_password_hash(data["password"])
        target["password_changed_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    if "username" in data:
        new_username = (data["username"] or "").strip()
        if not new_username:
            return jsonify({"status": "error", "message": "Username cannot be empty"}), 400
        other = get_user_by_username(new_username)
        if other and other["id"] != target["id"]:
            return jsonify({"status": "error", "message": "Username already in use"}), 400
        target["username"] = new_username

    save_auth(auth)
    return jsonify({"status": "ok", "message": "User updated", "user": _user_dto(target)})


@app.route("/admin/users/<user_id>/delete", methods=["POST"])
@role_required("admin")
def admin_user_delete(user_id):
    auth = load_auth()
    me = current_user() or {}
    if me.get("id") == user_id:
        return jsonify({"status": "error", "message": "You can't delete your own account"}), 400
    target = None
    for u in auth["users"]:
        if u["id"] == user_id:
            target = u
            break
    if not target:
        return jsonify({"status": "error", "message": "User not found"}), 404
    admins = [u for u in auth["users"] if u.get("role") == "admin"]
    if target.get("role") == "admin" and len(admins) <= 1:
        return jsonify({"status": "error", "message": "Cannot delete the last remaining admin"}), 400
    auth["users"] = [u for u in auth["users"] if u["id"] != user_id]
    save_auth(auth)
    return jsonify({"status": "ok", "message": f"Deleted user '{target.get('username','')}'"})


def _render_admin(template, active_section, **ctx):
    """Render an admin page with shared sidebar context."""
    content = ctx.pop("content", None) or load_content()
    return render_template(
        template,
        content=content,
        active_section=active_section,
        sidebar_products=content.get("products", []),
        current_user=current_user(),
        **ctx,
    )


@app.route("/admin")
@login_required
def admin_dashboard():
    """Overview: quick links + at-a-glance content stats."""
    content = load_content()
    stats = {
        "products": len(content.get("products", [])),
        "sections_enabled": sum(1 for s in content.get("sections", []) if s.get("enabled")),
        "sections_total": len(content.get("sections", [])),
        "nav_links": len(content.get("nav", {}).get("links", [])),
    }
    return _render_admin("admin/dashboard.html", "dashboard", content=content, stats=stats)


@app.route("/admin/layout", methods=["GET", "POST"])
@login_required
def admin_layout():
    """Reorder sections, toggle visibility, edit labels/subtitles."""
    content = load_content()
    if request.method == "POST":
        data = request.get_json(silent=True)
        if not isinstance(data, list):
            return jsonify({"status": "error", "message": "Expected a JSON array of sections"}), 400
        content["sections"] = data
        save_content(content)
        return jsonify({"status": "ok", "message": "Layout saved"})
    return _render_admin("admin/layout.html", "layout", content=content)


@app.route("/admin/navigation", methods=["GET", "POST"])
@login_required
def admin_navigation():
    """Edit header nav links."""
    content = load_content()
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        links = data.get("links")
        if not isinstance(links, list):
            return jsonify({"status": "error", "message": "Expected {links: [...]}"}), 400
        content["nav"] = {"links": links}
        save_content(content)
        return jsonify({"status": "ok", "message": "Navigation saved"})
    return _render_admin("admin/navigation.html", "navigation", content=content)


@app.route("/admin/hero", methods=["GET", "POST"])
@login_required
def admin_hero():
    content = load_content()
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        content["hero"] = data
        save_content(content)
        return jsonify({"status": "ok", "message": "Hero saved"})
    return _render_admin("admin/hero.html", "hero", content=content)


@app.route("/admin/about", methods=["GET", "POST"])
@login_required
def admin_about():
    content = load_content()
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        content["about"] = data
        save_content(content)
        return jsonify({"status": "ok", "message": "About saved"})
    return _render_admin("admin/about.html", "about", content=content)


@app.route("/admin/footer", methods=["GET", "POST"])
@login_required
def admin_footer():
    content = load_content()
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        content["footer"] = data
        save_content(content)
        return jsonify({"status": "ok", "message": "Footer saved"})
    return _render_admin("admin/footer.html", "footer", content=content)


@app.route("/admin/branding", methods=["GET", "POST"])
@login_required
def admin_branding():
    content = load_content()
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        content["branding"] = data
        save_content(content)
        return jsonify({"status": "ok", "message": "Branding saved"})
    return _render_admin("admin/branding.html", "branding", content=content)


@app.route("/admin/seo", methods=["GET", "POST"])
@login_required
def admin_seo():
    content = load_content()
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        content["og"] = data
        save_content(content)
        return jsonify({"status": "ok", "message": "SEO saved"})
    return _render_admin("admin/seo.html", "seo", content=content)


# ─── Products ──────────────────────────────────────────────────

def _slugify(text):
    out = []
    for ch in (text or "").lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "_"):
            out.append("-")
    slug = "".join(out).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:64] or "product"


def _unique_product_id(content, base):
    existing = {p.get("id") for p in content.get("products", [])}
    if base not in existing:
        return base
    n = 2
    while f"{base}-{n}" in existing:
        n += 1
    return f"{base}-{n}"


@app.route("/admin/products")
@login_required
def admin_products():
    content = load_content()
    return _render_admin("admin/products_list.html", "products", content=content)


@app.route("/admin/products/new", methods=["POST"])
@login_required
def admin_product_new():
    content = load_content()
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "New Product").strip()
    requested_id = (data.get("id") or "").strip()
    pid = _unique_product_id(content, _slugify(requested_id or name))
    new_product = {
        "id": pid,
        "name": name,
        "version": "",
        "tagline": "",
        "description": "",
        "logo": "",
        "featured_image": "",
        "screenshots": [],
        "features": [],
        "tech_stack": [],
        "repo_links": [],
        "install_tabs": [
            {"id": "docker", "label": "Docker Compose", "enabled": True, "steps": []},
            {"id": "quickrun", "label": "Quick Run", "enabled": False, "steps": []},
            {"id": "manual", "label": "Manual", "enabled": False, "steps": []},
        ],
    }
    content.setdefault("products", []).append(new_product)
    # Also append default Product + Install sections for this product
    content.setdefault("sections", []).append({
        "id": f"product-{pid}",
        "type": "product",
        "product_id": pid,
        "enabled": True,
        "label": f"// {name}",
        "subtitle": "",
    })
    content["sections"].append({
        "id": f"install-{pid}",
        "type": "install",
        "product_id": pid,
        "enabled": True,
        "label": "// Install",
        "subtitle": f"Install {name}",
    })
    save_content(content)
    return jsonify({"status": "ok", "message": "Product created", "id": pid})


@app.route("/admin/products/<product_id>", methods=["GET", "POST"])
@login_required
def admin_product_edit(product_id):
    content = load_content()
    if request.method == "POST":
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"status": "error", "message": "Expected JSON object"}), 400
        # Preserve id, disallow rename via this endpoint
        data["id"] = product_id
        # Replace the product in the list
        found = False
        for i, p in enumerate(content.get("products", [])):
            if p.get("id") == product_id:
                content["products"][i] = data
                found = True
                break
        if not found:
            return jsonify({"status": "error", "message": "Product not found"}), 404
        save_content(content)
        return jsonify({"status": "ok", "message": "Product saved"})

    product = get_product(content, product_id)
    if not product:
        flash(f"Product '{product_id}' not found", "error")
        return redirect(url_for("admin_products"))
    return _render_admin(
        "admin/product_edit.html",
        f"product:{product_id}",
        content=content,
        product=product,
    )


@app.route("/admin/products/<product_id>/refresh-version", methods=["POST"])
@login_required
def admin_product_refresh_version(product_id):
    """Force-refresh the version for a single product from GitHub."""
    content = load_content()
    product = get_product(content, product_id)
    if not product:
        return jsonify({"status": "error", "message": "Product not found"}), 404
    source = product.get("version_source") or "manual"
    repo = (product.get("github_repo") or "").strip()
    if source == "manual":
        return jsonify({"status": "error", "message": "Version source is set to Manual"}), 400
    if not repo:
        return jsonify({"status": "error", "message": "Set a GitHub repo (owner/name) first"}), 400
    new_version = fetch_github_version(repo, source)
    if new_version is None:
        return jsonify({"status": "error", "message": f"Could not fetch from GitHub — check repo and source"}), 502
    old_version = product.get("version", "")
    product["version"] = new_version
    product["version_fetched_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    save_content(content)
    return jsonify({
        "status": "ok",
        "message": f"Version updated: {old_version or '∅'} → {new_version}",
        "version": new_version,
        "fetched_at": product["version_fetched_at"],
    })


@app.route("/admin/refresh-versions", methods=["POST"])
@login_required
def admin_refresh_versions():
    """Force-refresh every auto-version product now."""
    results = refresh_all_versions(force=True)
    updated = sum(1 for r in results if r.get("updated"))
    errored = sum(1 for r in results if r.get("error"))
    return jsonify({
        "status": "ok",
        "message": f"Checked {len(results)} product(s); {updated} updated; {errored} error(s).",
        "results": results,
    })


@app.route("/admin/products/<product_id>/delete", methods=["POST"])
@login_required
def admin_product_delete(product_id):
    content = load_content()
    before = len(content.get("products", []))
    content["products"] = [p for p in content.get("products", []) if p.get("id") != product_id]
    if len(content["products"]) == before:
        return jsonify({"status": "error", "message": "Product not found"}), 404
    # Also remove any sections referencing this product
    content["sections"] = [
        s for s in content.get("sections", [])
        if not (s.get("type") in ("product", "install") and s.get("product_id") == product_id)
    ]
    save_content(content)
    return jsonify({"status": "ok", "message": "Product deleted"})


# ─── Backup / Raw ──────────────────────────────────────────────

@app.route("/admin/backup")
@login_required
def admin_backup():
    return _render_admin("admin/backup.html", "backup")


@app.route("/admin/raw", methods=["GET", "POST"])
@role_required("admin")
def admin_raw():
    """Raw JSON editor for the entire content file."""
    if request.method == "POST":
        try:
            raw = request.form.get("raw_json", "")
            data = json.loads(raw)
            save_content(data)
            flash("Content saved successfully.", "success")
        except json.JSONDecodeError as e:
            flash(f"Invalid JSON: {e}", "error")
        return redirect(url_for("admin_raw"))
    content = load_content()
    raw_json = json.dumps(content, indent=2)
    return _render_admin("admin/raw.html", "raw", content=content, raw_json=raw_json)


# ─── Image Upload ──────────────────────────────────────────────

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/admin/upload", methods=["POST"])
@login_required
def admin_upload():
    """Handle image uploads for product logo/screenshots."""
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file provided"}), 400
    f = request.files['file']
    if f.filename == '':
        return jsonify({"status": "error", "message": "No file selected"}), 400
    if not allowed_file(f.filename):
        return jsonify({"status": "error", "message": "File type not allowed"}), 400

    filename = secure_filename(f.filename)
    filepath = os.path.join(UPLOAD_DIR, filename)
    f.save(filepath)
    return jsonify({"status": "ok", "path": f"uploads/{filename}"})


# ─── Backup: Export / Import ───────────────────────────────────

@app.route("/admin/export")
@login_required
def admin_export():
    """Stream a zip containing content.json and every file in static/img/."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        if os.path.exists(CONTENT_FILE):
            zf.write(CONTENT_FILE, arcname="content.json")
        if os.path.isdir(UPLOAD_DIR):
            for entry in sorted(os.listdir(UPLOAD_DIR)):
                if entry.startswith("."):
                    continue
                full = os.path.join(UPLOAD_DIR, entry)
                if os.path.isfile(full):
                    zf.write(full, arcname=f"uploads/{entry}")
    buf.seek(0)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"viibeware-backup-{stamp}.zip",
    )


@app.route("/admin/import", methods=["POST"])
@login_required
def admin_import():
    """Restore a backup zip: replace content.json and image files.

    The zip must contain `content.json` at its root and optional `img/*` files.
    We validate JSON parses before writing anything, and back up the current
    content.json alongside it so the prior state is recoverable."""
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "No file provided"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"status": "error", "message": "No file selected"}), 400
    if not f.filename.lower().endswith(".zip"):
        return jsonify({"status": "error", "message": "File must be a .zip"}), 400

    try:
        raw = f.read()
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        return jsonify({"status": "error", "message": "Not a valid zip file"}), 400

    # Locate content.json and validate it parses
    names = zf.namelist()
    if "content.json" not in names:
        return jsonify({"status": "error", "message": "Zip is missing content.json"}), 400

    try:
        content_bytes = zf.read("content.json")
        parsed = json.loads(content_bytes.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("content.json root must be an object")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as e:
        return jsonify({"status": "error", "message": f"Invalid content.json: {e}"}), 400

    # Collect image entries from either uploads/ (new) or img/ (legacy backups),
    # rejecting path traversal and unknown extensions
    img_entries = []
    for name in names:
        if name.endswith("/"):
            continue
        if name.startswith("uploads/"):
            relative = name[len("uploads/"):]
        elif name.startswith("img/"):
            relative = name[len("img/"):]
        else:
            continue
        if "/" in relative or "\\" in relative or relative.startswith("."):
            continue
        if not allowed_file(relative):
            continue
        img_entries.append((name, relative))

    # Back up current content.json
    if os.path.exists(CONTENT_FILE):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = os.path.join(
            os.path.dirname(CONTENT_FILE),
            f"content.pre-import-{stamp}.json",
        )
        try:
            with open(CONTENT_FILE, "rb") as src, open(backup_path, "wb") as dst:
                dst.write(src.read())
        except OSError:
            pass

    # Write images first so the subsequent path rewrite can verify their presence
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    restored_images = 0
    for zip_name, relative in img_entries:
        safe_name = secure_filename(relative)
        if not safe_name:
            continue
        dest = os.path.join(UPLOAD_DIR, safe_name)
        with zf.open(zip_name) as src, open(dest, "wb") as dst:
            dst.write(src.read())
        restored_images += 1

    # Rewrite any legacy img/X → uploads/X refs in the imported content
    _rewrite_img_refs(parsed)
    with open(CONTENT_FILE, "w") as out:
        json.dump(parsed, out, indent=2)

    return jsonify({
        "status": "ok",
        "message": f"Imported content.json and {restored_images} image(s).",
        "images": restored_images,
    })


# ─── API (for potential SPA use) ───────────────────────────────

@app.route("/admin/debug-cookie")
def admin_debug_cookie():
    """Diagnostic: shows what cookies and session state the server sees."""
    return jsonify({
        "cookies_received": dict(request.cookies),
        "session_has_admin_logged_in": bool(session.get("admin_logged_in")),
        "session_keys": list(session.keys()),
        "user_agent": request.headers.get("User-Agent", ""),
        "accept": request.headers.get("Accept", ""),
    })


@app.route("/api/content")
def api_content():
    """Return all site content as JSON."""
    return jsonify(load_content())


@app.route("/api/content/<section>")
def api_content_section(section):
    """Return a single content section as JSON."""
    content = load_content()
    if section in content:
        return jsonify(content[section])
    return jsonify({"error": "Section not found"}), 404


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8899)
