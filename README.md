# viibeware Corp. — Corporate Website

A dark-neon corporate website built with Flask. Features a full admin CMS backend, multi-product showcases, and an aesthetic that screams "we let an AI build this and we're proud of it."

## Quick Start (Docker)

```bash
# Clone the repo
git clone https://github.com/viibeware/viibeware-website.git
cd viibeware-website

# Create your environment file
cp .env.example .env
# Edit .env — at minimum, change SECRET_KEY and ADMIN_PASS

# Launch
docker compose up -d
```

The site will be available at **http://localhost:8899**

Admin panel: **http://localhost:8899/admin** (default: `admin` / `viibeware2026`)

## Migrating from Bare-Metal

If you have an existing systemd-based install at `/opt/viibeware`, the migration script handles everything:

```bash
cd viibeware-website
chmod +x migrate-to-docker.sh
./migrate-to-docker.sh /opt/viibeware
```

This will stop the old systemd service, start the Docker container, copy your `content.json` and uploaded images into the Docker volumes, and verify the container is healthy. Your old install is left untouched until you manually remove it.

## Project Structure

```
viibeware/
├── app.py                     # Flask application + content migration layer
├── Dockerfile                 # Container image definition
├── docker-compose.yml         # Docker Compose (dev — builds from source)
├── requirements.txt           # Python dependencies (Flask)
├── migrate-to-docker.sh       # Bare-metal → Docker migration script
├── .env.example               # Environment variable template
├── CHANGELOG.md               # Version history
├── data/
│   ├── content.json           # Live site content (excluded from deploys)
│   └── content.example.json   # Default content (copied on first run)
├── static/
│   ├── css/
│   │   ├── style.css          # Frontend styles (dark neon / cyberpunk)
│   │   └── admin.css          # Admin panel styles
│   ├── js/
│   │   └── main.js            # Frontend interactions
│   └── img/                   # Logos, screenshots, OG images
└── templates/
    ├── index.html             # Homepage (dynamic section rendering)
    ├── macros.html            # Jinja2 macros for product/install sections
    ├── admin_dashboard.html   # Admin CMS dashboard
    ├── admin_login.html       # Admin login page
    └── admin_raw.html         # Raw JSON content editor
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `change-me-in-production` | Flask session secret — generate with `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `ADMIN_USER` | `admin` | Admin login username |
| `ADMIN_PASS` | `viibeware2026` | Admin login password |
| `GUNICORN_WORKERS` | `2` | Number of gunicorn worker processes |
| `GUNICORN_PORT` | `8899` | Port the app listens on |

## Admin Panel

Access at `/admin/login`. The dashboard provides visual editors for every section of the site.

**Page Layout** — Drag-and-drop section reordering, visibility toggles, label and subtitle editing for all sections.

**Navigation** — Add, remove, and reorder nav links with drag handles.

**Hero** — Edit headline, subheadline, and CTA button text.

**About** — Edit title, body text, and the four principle cards.

**Stats** — Edit the stat values and labels in the counters grid.

**Products** (Garage Logbook & Warehouse Manager) — Each product has editors for name, version, tagline, description, logo upload, featured image upload, draggable feature list, repository links (GitHub / Docker Hub) with toggles, and screenshot gallery uploads.

**Install Sections** — Per-product tabbed install instructions with tab visibility/label toggles and full step editors (title, description, command) for Docker Compose, YOLO Mode, and Manual install methods.

**Metrics** — Edit the metrics dashboard title and individual metric cards (label, value, change, direction).

**Social / Open Graph** — Edit the title, description, URL, and image used for social sharing link previews.

**Footer** — Edit tagline and toggle/configure GitHub, Bluesky, and Email links.

**Raw JSON Editor** — Full access to `content.json` for advanced edits.

## Content Persistence

`content.json` stores all site content and is excluded from deploy archives. Code updates never overwrite your content. The `load_content()` function in `app.py` includes a migration layer that auto-backfills any missing fields with sensible defaults, so new features never cause 500 errors on existing installs.

## API Endpoints

| Route | Description |
|---|---|
| `/api/content` | Full site content as JSON |
| `/api/content/<section>` | Single section (e.g., `/api/content/product`) |

## Tech Stack

Built with Flask, Jinja2, vanilla JS, and a lot of conversations with Claude. No frontend framework, no build step, no node_modules. Just HTML, CSS, and vibes.

## License

© 2026 viibeware Corp. All rights reserved.
