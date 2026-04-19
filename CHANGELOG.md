# Changelog

All notable changes to the viibeware Corp. website.

## [0.6.0] — 2026-04-19

### Security
- **CSRF protection.** Per-session token generated server-side and exposed via `<meta name="csrf-token">`. All state-changing admin requests now require the token — either `X-CSRF-Token` header (XHR/JSON) or a `_csrf` form field (native POSTs). Login is exempt (no session yet); everything else is protected.
- **Content Security Policy and strict headers on every response** — `Content-Security-Policy` (allows Cloudflare Turnstile + Google Fonts, blocks third-party script sources), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` locking out camera/microphone/geolocation/payment.
- **Login rate limiting.** Per-IP sliding window — 8 failed logins in 5 minutes triggers a 10-minute lockout. Failures are counted after Turnstile and password verification so an attacker can't probe for the lockout threshold without a valid Turnstile token (when enabled).
- **SVG upload sanitization.** Uploaded SVGs are stripped of `<script>`, `<foreignObject>`, inline `on*=` event handlers, and `javascript:` URLs before being written to disk. Prevents stored-XSS via SVG logos.
- **SECRET_KEY warning.** Loud startup log if the environment variable isn't set and the built-in development secret is in use — sessions are forgeable with the default.
- **Removed `/admin/debug-cookie`** — unauthenticated endpoint that echoed cookies and session state. Useful while debugging session drops in 0.2.x; has no reason to still exist.
- **Removed `/admin/*` before-request auth logger** — it printed user-agent and content-type to stdout on every admin POST.
- **Stale sessions invalidated.** `current_user()` now clears the session if the `user_id` no longer matches a user record (e.g. admin deleted the user while the other device was still logged in).
- **GitHub repo input validation.** Repo strings are now matched against a strict `owner/name` regex before being interpolated into an API URL — blocks any attempt to escape into another host via the version-refresh path.
- **`FORCE_SECURE_COOKIES` env toggle** — set to `1/true/yes` in production to mark the session cookie `Secure`, so it never travels over plain HTTP.

### Added
- **About tab in the settings modal.** App icon + "VIIBEWARE Web" + version + "Built by VIIBEWARE" + short description + AGPLv3 license link + tech-stack icon grid (Python, Flask, Jinja, Gunicorn, JavaScript, Docker, Cloudflare) + scrollable CHANGELOG pulled from `CHANGELOG.md` (file-mtime-cached on the server).
- New endpoint `/admin/app-info` returning app metadata + rendered changelog HTML as JSON, consumed lazily the first time the About tab is opened.
- Tech-stack SVG icons shipped under `static/img/tech/`, rendered via `mask-image` so they pick up the current text color (and the accent color on hover).
- Changelog is rendered as proper markdown (headings, lists, bold, code, links, horizontal rules) using the `Markdown` Python package — not a raw code block.
- Settings modal body now has a `min-height` so the dialog stops resizing as you click between Security / Users / About tabs.

---

## [0.5.4] — 2026-04-18

### Removed
- "Admin" link in the public footer. The admin panel is still at `/admin`; type the URL manually to reach it.

---

## [0.5.3] — 2026-04-18

### Fixed
- Nav brand link now smooth-scrolls to the top of the page instead of targeting `#hero`. Previously, if the Hero section was disabled in Layout, clicking the brand did nothing. `href="#"` is treated as "scroll to top" by the shared anchor handler.

---

## [0.5.2] — 2026-04-18

### Added
- **Startup warning for misconfigured compose** — prints a loud, clear message in the container logs if the Docker volume is mounted at the legacy `/app/static/img` path instead of `/app/static/uploads`. Left unfixed this mismatch causes uploaded files to land in the container's writable layer instead of the persistent volume, so they vanish on every `docker compose up -d`. The warning names the fix and the exact compose line to change.

---

## [0.5.1] — 2026-04-18

(No code changes — version-only release.)

---

## [0.5.0] — 2026-04-18

### Added
- **Branding admin page** (`/admin/branding`, sidebar link under Page Content) — controls the site name and how it's displayed on the public nav, the browser tab title, and the admin chrome. Fields:
  - `name` — the site name shown in the nav and titles.
  - `emphasis_part` — a substring of the name to highlight in an accent color.
  - `transform` — none / lowercase / UPPERCASE / Capitalize Each Word.
  - `page_title_suffix` — text appended to the browser tab title.
  - `font_size_rem` — nav brand font size (rem).
  - `logo_size_px` — nav logo image size (px).
  - `color_primary` and `color_accent` — HTML5 color pickers + sync'd hex inputs.
  - Live preview card at the top of the page.
- Global `branding` context variable available in every template (public, admin, login).
- `render_brand(branding)` Jinja macro that splits the name around the emphasis substring and wraps the accent portion in `<em>`.

### Changed
- Public nav logo, page `<title>`, admin page `<title>`, login brand, and sidebar brand now all pull from `content.branding` instead of hardcoded "viibeware".

---

## [0.4.1] — 2026-04-18

### Fixed
- Sessions started before the 0.4.0 schema change had `admin_logged_in` set but no `user_id`, which caused `current_user()` to return None and hid the settings gear icon and modal. `current_user()` now auto-heals legacy sessions by resolving them to the admin user matching `ADMIN_USER`, so existing logged-in sessions pick up the 0.4.0 admin UI without needing to log out.

---

## [0.4.0] — 2026-04-18

### Added
- **Cloudflare Turnstile on login** — configurable via a new settings modal. Server-side siteverify rejects bad tokens before the password is even checked. Widget only renders when enabled + keyed.
- **Settings modal** — gear icon in the sidebar footer opens a blurred-backdrop popup with tabbed sections for Security (Turnstile) and Users. Close with `×`, Esc, or backdrop click.
- **Multi-user with role-based permissions** — replaces the single-user auth with `users: [{id, username, password_hash, role, ...}]` in `data/auth.json`.
  - Roles: `admin` (full access — users, settings, raw JSON) and `editor` (site content only).
  - Create, update role, reset password, delete users (all via the Users tab).
  - Guards: can't delete your own account, can't demote/delete the last admin.
  - `role_required()` decorator applied to `/admin/settings*`, `/admin/users*`, `/admin/raw`.

### Changed
- `data/auth.json` schema expanded from `{password_hash, password_changed_at}` to `{users: [...], settings: {turnstile: {...}}}`. Automatic migration of the legacy single-user shape on startup.
- First-login bootstrap flow: when no users exist and credentials match the env/default, the change-password step creates the first admin user (rather than storing a loose hash).
- Admin UI: gear icon + settings modal visible only to admins; sidebar footer reorganized.

---

## [0.3.2] — 2026-04-18

### Changed
- **Default admin password changed from `viibeware2026` to `admin`.** Fresh installs must set a new password on first login before the rest of the admin unlocks. Existing deploys with `ADMIN_PASS` already set in `.env` are unaffected — only installs actually using the default password are prompted.

### Added
- **Forced password change on first login** — when a user logs in with the default password, the session is flagged and every admin page redirects to `/admin/change-password` until a new password is set.
- **Voluntary password change** — "Change password" link in the sidebar footer. Requires current password.
- **Strong-password rule** — minimum 12 characters, must include uppercase, lowercase, and a digit. Rejects the default value itself.
- Hashed-password storage in `data/auth.json` (scrypt, via `werkzeug.security`). Once a hash is stored it takes precedence over the `ADMIN_PASS` env var.

---

## [0.3.1] — 2026-04-18

### Added
- **Per-product logo and title sizing** — new `logo_size` (px) and `title_size` (px) fields, editable from the product's Core tab. Title size of 0 keeps the responsive `clamp()` default.
- **Auto-fetched versions from GitHub** — each product can now be configured with `github_repo` and `version_source` (`manual` / `github_release` / `github_tag`). A daemon thread refreshes every 6 hours with a cross-worker cooldown so multiple gunicorn workers don't duplicate requests. Optional `GITHUB_TOKEN` env var raises the rate limit to 5000/hr.
- New admin endpoints: `POST /admin/products/<id>/refresh-version` (single product) and `POST /admin/refresh-versions` (bulk).
- Product edit Core tab: inline "⟳ Refresh" button next to the version field; "Last fetched" timestamp.

### Changed
- **Navigation icon picker** — replaced the free-text "icon" field on the Navigation page with a dropdown (Text link / GitHub icon / Docker Hub icon).

---

## [0.3.0] — 2026-04-18

### Changed
- **Complete admin UI rewrite** — multi-page layout with a persistent sidebar, one URL per editable area. Replaces the prior single-page collapsible admin.
- **Dynamic products** — schema now stores `products` as an array. Add/remove products from the admin; each product gets its own edit page with tabs for Core, Media, Features &amp; tech, Repo links, and Install.
- **Unlimited screenshots, features, repo links, install tabs, and install steps** — all lists support add/remove and drag-to-reorder.
- `repo_links` and `install_tabs` changed from keyed objects to ordered lists of `{id, label, url/icon/..., enabled, ...}`; flat step arrays (`docker_steps`, `quickrun_steps`, `install_steps`) are folded into their corresponding tab's `steps` list.
- `sections` entries now carry `type` (hero / about / product / install) and `product_id` instead of being matched by hardcoded id.
- Public `index.html` now iterates sections generically and looks products up by id — no more hardcoded product blocks.
- Legacy admin endpoints removed: `/admin/update/<section>` (replaced by per-area POST handlers such as `/admin/hero`, `/admin/about`, `/admin/products/<id>`, etc.).

### Added
- Automatic startup migration: `product` + `product3` are reshaped into `products[]`, keyed repo/install structures become lists, and sections gain `type`/`product_id`. Snapshot is saved to `data/content.pre-products-migration-<timestamp>.json` before writing.
- `/admin/products` list view with inline create/delete.
- Login page redesigned to match the new admin visual system.

### Fixed
- Products migration now writes the reshaped JSON back to disk (previously the migration ran in memory without persisting).

---

## [0.2.2] — 2026-04-17

### Changed
- **User content fully decoupled from the container image.** User uploads now live under `static/uploads/` (volume-mounted, `.dockerignore`-excluded, never baked in). `static/img/` is now reserved for chrome assets (`logo.svg`, `og-image.png`) that ship with the app and update on deploy.
- Docker volume `viibeware-uploads` now mounts at `/app/static/uploads` (previously `/app/static/img`).
- Admin footer link goes to `/admin` and redirects to login only if the session has expired.

### Added
- Automatic startup migration: rewrites legacy `img/X` content references to `uploads/X` where the file is present in uploads; snapshots the prior content.json to `data/content.pre-uploads-migration-<timestamp>.json`.
- Import now accepts both `img/` (legacy) and `uploads/` zip entries and normalizes paths on the way in.

---

## [0.2.1] — 2026-04-17

### Added
- **Backup / Restore** — new Backup admin section with Export (downloads `content.json` + all images as a single zip) and Import (restores from a backup zip, validates JSON, snapshots pre-import content)
- **Trusted Servants Pro** product section with Docker Compose and `install.sh` install paths
- `/admin/export` and `/admin/import` routes (admin-only, zip-slip protected)

### Changed
- Session cookie renamed to `viibeware_session` to prevent collision with other Flask apps sharing the same host
- `MAX_CONTENT_LENGTH` bumped to 200 MB to accommodate full-site backup zips
- Admin XHR auth failures return JSON 401 (instead of silent 302 to login) so the UI can surface a clear error
- Install tabs scoped to their own section so switching tabs in one product doesn't collapse another
- Header navigation simplified to four items (Garage Logbook, Trusted Servants Pro, GitHub icon, Docker Hub icon); snarky/sarcastic copy removed
- Removed stats/metrics/testimonials/Warehouse Manager sections

### Fixed
- Session cookie dropped on admin POSTs when another Flask app on the same host set its own `session` cookie

---

## [0.2.0] — 2026-04-05

### Added
- **Docker support** — Dockerfile, docker-compose.yml, and .env configuration
- **Migration script** (`migrate-to-docker.sh`) — automated migration from bare-metal systemd install to Docker with volume-based persistence
- **Warehouse Manager** — full product section with featured image, features, repo links, and tabbed install instructions (Docker Compose, YOLO Mode, Manual)
- **Multi-product architecture** — Jinja2 macros for reusable product and install section rendering
- **Product 2 admin panel** — complete backend editing for Warehouse Manager (name, tagline, description, logo, featured image, features, repo links, install tabs, and all step editors)
- Health check endpoint in Docker container

### Changed
- README rewritten for Docker-first deployment
- Content data and uploaded images now persist in Docker volumes

---

## [0.1.5] — 2026-04-05

### Added
- Warehouse Manager product data and section types (`product2`, `download2`)
- Jinja2 macros (`templates/macros.html`) for DRY product/install rendering
- Product 2 admin sections with full editing (features, install steps, repo links, images)
- `load_content()` migration for `product2` defaults

---

## [0.1.4] — 2026-04-05

### Added
- Open Graph and Twitter Card meta tags for social sharing link previews
- OG image upload and editing in admin panel ("Social Sharing / Open Graph" section)
- `og` data backfill in `load_content()` migration

---

## [0.1.3] — 2026-04-05

### Fixed
- 500 error on `/admin` caused by missing `repo_links` in live `content.json`
- Added comprehensive field migration in `load_content()` — auto-backfills `repo_links`, `featured_image`, `logo`, `screenshots`, `quickrun_steps`, `install_tabs`, `bluesky`, and converts legacy flat-string footer fields to structured objects

---

## [0.1.2] — 2026-04-04

### Added
- Drag-to-reorder for navigation links and product features
- GitHub and Docker Hub repo links on product section frontend with SVG icons
- Repo links editor in admin panel with URL, label, and toggle controls

---

## [0.1.1] — 2026-04-04

### Added
- Product features editable from admin panel (add, remove, reorder)
- Install steps editable from admin panel for all three methods (Docker Compose, YOLO Mode, Manual)
- Version numbering system — displayed in admin header badge

---

## [0.1.0] — 2026-04-04

### Added
- Initial Flask application with JSON-based content management
- Dark neon/cyberpunk aesthetic (cyan #00F2FF + purple #AF00FF)
- Admin dashboard with visual editors for all content sections
- Raw JSON editor for full content control
- JSON API endpoints (`/api/content`, `/api/content/<section>`)
- Dynamic section ordering, visibility, and label editing
- Navigation link editor with add/remove
- Hero, Stats, About, Product, Download, Metrics, and Testimonials sections
- Product section with logo, featured image, screenshot gallery, and lightbox
- Tabbed install instructions (Docker Compose, YOLO Mode, Manual) with toggles
- Code blocks with `<pre><code>` formatting and copy-to-clipboard
- Footer with GitHub, Bluesky, and Email links with per-link toggles
- Scroll-reveal animations, parallax orbs, animated stat counters
- Mobile-responsive layout with hamburger nav
- Auto cache-busting via `CACHE_VERSION` timestamp
- Image upload support for logos, screenshots, featured images, and OG images
- Content persistence — `content.json` excluded from deploy archives
- `content.example.json` auto-copied on fresh installs
