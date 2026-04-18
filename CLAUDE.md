# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Local development (auto-reload, debug mode)
python3 app.py                              # serves on http://localhost:8899

# Production-style local run
gunicorn --workers 2 --bind 0.0.0.0:8899 app:app

# Docker (primary deploy path)
docker compose up -d --build                # rebuild + start
docker compose logs -f viibeware-web        # tail logs
docker compose restart                      # reload after code changes
docker compose down                         # stop (volumes persist)

# Bare-metal → Docker migration (one-shot)
./migrate-to-docker.sh /opt/viibeware
```

Dependencies: `pip install -r requirements.txt` (Flask + gunicorn — no build step, no node_modules). No test suite or linter is configured.

## Architecture

This is a **single-file Flask CMS**. Everything backend lives in `app.py`; `data/content.json` is the only source of truth for site content.

### Content layer — the important pattern

`load_content()` in `app.py` is a **migration/backfill layer**, not just a file read. On every request it:
1. Loads `data/content.json`
2. Backfills any missing fields (`repo_links`, `featured_image`, `install_tabs`, `og`, `product2`, structured `footer` objects, etc.) with sensible defaults
3. Converts legacy flat-string fields (e.g. `footer.github` as string) into structured objects

**Anytime you add a new content field, add a corresponding backfill in `load_content()`** — otherwise live installs with older `content.json` files will 500 on first render. This is the canonical way the project handles schema evolution without migrations. History in `CHANGELOG.md` 0.1.3/0.1.4/0.1.5 shows each time this pattern was applied.

`content.json` is deliberately excluded from deploys — code updates must never overwrite user content. `content.example.json` is the shipped template, auto-copied on first run if `content.json` is missing.

### Rendering

`templates/index.html` renders sections by iterating `content.sections` (an ordered list of section descriptors with `id`, `label`, `subtitle`, `visible`). Product and install-tab blocks use Jinja macros in `templates/macros.html` (`render_product`, `render_install`) so both products (Garage Logbook as `product`, Warehouse Manager as `product2`) share the same template. Adding a new product means adding a key to `content.json`, backfilling it in `load_content()`, and adding a section entry that points the macros at it.

### Admin API shape

Admin dashboard (`/admin`) is a single page with per-section forms that POST JSON to `/admin/update/<section>`. The server replaces `content[section]` wholesale with the POSTed JSON and saves. There is no field-level validation — the admin UI is trusted. `/admin/raw` edits the full JSON blob. Login is session-based (`login_required` decorator), credentials from `ADMIN_USER`/`ADMIN_PASS` env vars.

### Persistence in Docker

Two named volumes:
- `viibeware-data` → `/app/data` (content.json)
- `viibeware-uploads` → `/app/static/img` (uploaded logos/screenshots/OG images)

The Docker image does **not** bake `content.json` into itself — only `content.example.json`. Rebuilding the image never clobbers live content.

### Cache busting

`CACHE_VERSION` is a timestamp set at import time and injected into all templates via `inject_globals()`. CSS/JS are referenced as `style.css?v={{ cache_v }}`. Restarting the container is what invalidates cached assets; there is no build hash.

## Conventions

- No frontend framework, no bundler. Vanilla JS in `static/js/main.js`, hand-written CSS in `static/css/`.
- SVG icons (GitHub, Docker Hub) live inline in `templates/macros.html` as Jinja `{% set %}` blocks.
- `SITE_VERSION` in `app.py` is displayed in the admin header only — bump it alongside `CHANGELOG.md` entries.
- Uploaded filenames are passed through `secure_filename()` and saved flat into `static/img/`; collisions overwrite.
