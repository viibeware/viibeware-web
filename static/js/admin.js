/* ============================================================
   viibeware Admin — shared helpers (toast, save, upload, dnd)
   ============================================================ */

// ── Toast / flash helpers ──────────────────────────────
function showToast(message, type = 'success') {
  const area = document.getElementById('flash-area') || document.body;
  const el = document.createElement('div');
  el.className = 'flash ' + (type === 'error' ? 'error' : type === 'success' ? 'success' : '');
  el.innerHTML = `<span></span><button class="flash-dismiss" onclick="this.parentElement.remove()">×</button>`;
  el.querySelector('span').textContent = message;
  area.appendChild(el);
  setTimeout(() => {
    el.style.transition = 'opacity 0.2s';
    el.style.opacity = '0';
    setTimeout(() => el.remove(), 250);
  }, 3800);
}

window.showToast = showToast;

// Auto-dismiss server-rendered flashes
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.flash-area .flash').forEach(el => {
    setTimeout(() => {
      el.style.transition = 'opacity 0.25s';
      el.style.opacity = '0';
      setTimeout(() => el.remove(), 250);
    }, 3800);
  });
});

// ── CSRF helper ────────────────────────────────────────
function csrfToken() {
  const el = document.querySelector('meta[name="csrf-token"]');
  return el ? el.getAttribute('content') : '';
}
window.csrfToken = csrfToken;

// ── JSON save helper ───────────────────────────────────
// Wraps fetch() with the credentials + headers + 401-handling used throughout admin.
async function saveJSON(url, body, opts = {}) {
  try {
    const res = await fetch(url, {
      method: opts.method || 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRF-Token': csrfToken(),
        ...(opts.headers || {})
      },
      body: body != null ? JSON.stringify(body) : undefined
    });
    if (res.status === 401) {
      showToast('Session expired — redirecting to login', 'error');
      setTimeout(() => window.location.href = '/admin/login', 1000);
      return { ok: false, status: 401 };
    }
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try { const j = await res.json(); if (j.message) msg = j.message; } catch (_) {}
      showToast(`✗ ${msg}`, 'error');
      return { ok: false, status: res.status, message: msg };
    }
    const data = await res.json();
    return { ok: true, data };
  } catch (e) {
    showToast(`✗ ${e.message || 'Network error'}`, 'error');
    return { ok: false, status: 0, message: e.message };
  }
}
window.saveJSON = saveJSON;

// ── Image upload helper ────────────────────────────────
async function uploadFile(file) {
  if (!file) return null;
  if (file.size > 200 * 1024 * 1024) {
    showToast(`✗ File too large (${(file.size/1024/1024).toFixed(1)} MB)`, 'error');
    return null;
  }
  const fd = new FormData();
  fd.append('file', file);
  try {
    const res = await fetch('/admin/upload', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest', 'X-CSRF-Token': csrfToken() },
      body: fd
    });
    if (res.status === 401) {
      showToast('Session expired — redirecting to login', 'error');
      setTimeout(() => window.location.href = '/admin/login', 1000);
      return null;
    }
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try { const j = await res.json(); if (j.message) msg = j.message; } catch (_) {}
      showToast(`✗ Upload failed: ${msg}`, 'error');
      return null;
    }
    const data = await res.json();
    return data.path || null;
  } catch (e) {
    showToast(`✗ ${e.message || 'Network error'}`, 'error');
    return null;
  }
}
window.uploadFile = uploadFile;

// ── Drag-reorder for a list ────────────────────────────
// Initializes drag-and-drop on a container whose children are the reorderable rows.
function enableDragReorder(containerSelector, itemSelector = '.list-item') {
  const container = typeof containerSelector === 'string'
    ? document.querySelector(containerSelector)
    : containerSelector;
  if (!container) return;
  let dragEl = null;

  container.addEventListener('dragstart', e => {
    const item = e.target.closest(itemSelector);
    if (!item || !container.contains(item)) return;
    dragEl = item;
    item.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    try { e.dataTransfer.setData('text/plain', ''); } catch (_) {}
  });
  container.addEventListener('dragend', () => {
    if (dragEl) dragEl.classList.remove('dragging');
    container.querySelectorAll(itemSelector).forEach(i => i.classList.remove('drag-over'));
    dragEl = null;
  });
  container.addEventListener('dragover', e => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    const target = e.target.closest(itemSelector);
    if (!target || target === dragEl || !container.contains(target)) return;
    container.querySelectorAll(itemSelector).forEach(i => i.classList.remove('drag-over'));
    target.classList.add('drag-over');
  });
  container.addEventListener('drop', e => {
    e.preventDefault();
    const target = e.target.closest(itemSelector);
    if (!target || target === dragEl || !dragEl) return;
    const items = [...container.querySelectorAll(itemSelector)];
    if (items.indexOf(dragEl) < items.indexOf(target)) target.after(dragEl);
    else target.before(dragEl);
    container.querySelectorAll(itemSelector).forEach(i => i.classList.remove('drag-over'));
  });
}
window.enableDragReorder = enableDragReorder;

// ── Generic helpers ────────────────────────────────────
// ── Settings modal ─────────────────────────────────────
// Lazy-loaded when the user opens the modal. Tabs: Security (Turnstile) and Users.
let _settingsLoaded = false;
let _settingsState = null;

let _aboutLoaded = false;

async function openSettings() {
  const modal = document.getElementById('settings-modal');
  if (!modal) return;
  modal.hidden = false;
  document.body.style.overflow = 'hidden';
  // Backdrop-click to close
  modal.onclick = () => closeSettings();
  // Tab switching inside modal (lazy-load About on first view)
  modal.querySelectorAll('.tabs button').forEach(b => {
    b.onclick = async () => {
      modal.querySelectorAll('.tabs button').forEach(x => x.classList.remove('active'));
      modal.querySelectorAll('.tab-panel').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      modal.querySelector('#' + b.dataset.tab).classList.add('active');
      if (b.dataset.tab === 'settings-about' && !_aboutLoaded) {
        await loadAbout();
        _aboutLoaded = true;
      }
    };
  });
  if (!_settingsLoaded) {
    await loadSettings();
    _settingsLoaded = true;
  }
}

async function loadAbout() {
  try {
    const res = await fetch('/admin/app-info', {
      credentials: 'same-origin',
      headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    });
    if (!res.ok) return;
    const data = await res.json();
    const nameEl = document.getElementById('about-name');
    if (nameEl) nameEl.textContent = data.name || 'VIIBEWARE Web';
    const versionEl = document.getElementById('about-version');
    if (versionEl) versionEl.textContent = data.version || '';
    const descEl = document.getElementById('about-desc');
    if (descEl) descEl.textContent = data.description || '';
    const logEl = document.getElementById('about-changelog-text');
    if (logEl) {
      if (data.changelog_html) logEl.innerHTML = data.changelog_html;
      else logEl.textContent = '(changelog unavailable)';
    }
  } catch (_) {
    // silent; About tab is informational
  }
}

function closeSettings() {
  const modal = document.getElementById('settings-modal');
  if (!modal) return;
  modal.hidden = true;
  document.body.style.overflow = '';
}

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    const modal = document.getElementById('settings-modal');
    if (modal && !modal.hidden) closeSettings();
  }
});

async function loadSettings() {
  const res = await fetch('/admin/settings', {
    credentials: 'same-origin',
    headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
  });
  if (!res.ok) { showToast('Could not load settings', 'error'); return; }
  const data = await res.json();
  _settingsState = data;
  // Turnstile
  document.getElementById('ts-enabled').checked = !!data.turnstile.enabled;
  document.getElementById('ts-site-key').value = data.turnstile.site_key || '';
  const hint = document.getElementById('ts-secret-hint');
  if (data.turnstile.secret_key_set) {
    document.getElementById('ts-secret-key').placeholder = '•••••••• (stored) — leave blank to keep';
    hint.textContent = 'A secret is stored. Enter a new value to replace, or blank to keep the existing one.';
  } else {
    document.getElementById('ts-secret-key').placeholder = '0x4AAAA...';
    hint.textContent = 'Private — used only server-side for siteverify.';
  }
  renderUsers(data.users, data.current_user_id);
}

async function saveTurnstile() {
  const payload = {
    enabled: document.getElementById('ts-enabled').checked,
    site_key: document.getElementById('ts-site-key').value.trim(),
    secret_key: document.getElementById('ts-secret-key').value.trim(),
  };
  const res = await saveJSON('/admin/settings/turnstile', payload);
  if (res.ok) {
    showToast('✓ Turnstile settings saved');
    document.getElementById('ts-secret-key').value = '';
    _settingsLoaded = false;
    await loadSettings();
    _settingsLoaded = true;
  }
}

async function clearTurnstileSecret() {
  if (!confirm('Clear the stored Turnstile secret? The login page will fall back to password-only until you save a new secret.')) return;
  const res = await saveJSON('/admin/settings/turnstile', { clear_secret_key: true });
  if (res.ok) {
    showToast('Secret cleared');
    _settingsLoaded = false;
    await loadSettings();
    _settingsLoaded = true;
  }
}

// ── Users CRUD ──────────────────────────────────────────
function renderUsers(users, currentUserId) {
  const tbody = document.getElementById('users-tbody');
  tbody.innerHTML = '';
  if (!users || !users.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="text-muted" style="text-align:center; padding: 1.5rem;">No users yet.</td></tr>';
    return;
  }
  for (const u of users) {
    const isMe = u.id === currentUserId;
    const tr = document.createElement('tr');
    tr.dataset.userId = u.id;
    const lastChanged = u.password_changed_at ? u.password_changed_at.replace('T', ' ').replace('Z', ' UTC') : '—';
    tr.innerHTML = `
      <td>
        <strong>${escapeHtml(u.username)}</strong>
        ${isMe ? '<span class="chip" style="margin-left: 0.4rem;">you</span>' : ''}
        <div class="text-muted mono" style="font-size: 0.72rem;">${u.id}</div>
      </td>
      <td>
        <select class="user-role" ${isMe ? 'disabled title="You cannot change your own role"' : ''}>
          <option value="admin" ${u.role === 'admin' ? 'selected' : ''}>Admin</option>
          <option value="editor" ${u.role === 'editor' ? 'selected' : ''}>Editor</option>
        </select>
      </td>
      <td class="mono" style="font-size: 0.78rem;">${escapeHtml(lastChanged)}</td>
      <td class="actions">
        <button class="btn btn-sm" onclick="saveUserRole('${u.id}', this)">Save role</button>
        <button class="btn btn-sm" onclick="resetUserPassword('${u.id}', '${escapeHtml(u.username)}')">Reset password</button>
        ${isMe ? '' : `<button class="btn btn-sm btn-danger" onclick="deleteUser('${u.id}', '${escapeHtml(u.username)}')">Delete</button>`}
      </td>
    `;
    tbody.appendChild(tr);
  }
}

function escapeHtml(s) {
  return String(s || '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

function showAddUserForm() { document.getElementById('add-user-form').classList.remove('hidden'); }
function hideAddUserForm() {
  document.getElementById('add-user-form').classList.add('hidden');
  document.getElementById('new-user-username').value = '';
  document.getElementById('new-user-password').value = '';
  document.getElementById('new-user-role').value = 'editor';
}

async function createUser() {
  const payload = {
    username: document.getElementById('new-user-username').value.trim(),
    password: document.getElementById('new-user-password').value,
    role: document.getElementById('new-user-role').value,
  };
  if (!payload.username) { showToast('Enter a username', 'error'); return; }
  const res = await saveJSON('/admin/users', payload);
  if (res.ok) {
    showToast('✓ User created');
    hideAddUserForm();
    _settingsLoaded = false;
    await loadSettings();
    _settingsLoaded = true;
  }
}

async function saveUserRole(userId, btn) {
  const row = btn.closest('tr');
  const role = row.querySelector('.user-role').value;
  const res = await saveJSON(`/admin/users/${userId}`, { role });
  if (res.ok) showToast('✓ Role updated');
}

async function resetUserPassword(userId, username) {
  const pw = prompt(`New password for "${username}" (≥12 chars, with upper/lower/digit):`);
  if (!pw) return;
  const res = await saveJSON(`/admin/users/${userId}`, { password: pw });
  if (res.ok) showToast('✓ Password reset');
}

async function deleteUser(userId, username) {
  if (!confirm(`Delete user "${username}"?`)) return;
  const res = await saveJSON(`/admin/users/${userId}/delete`, {});
  if (res.ok) {
    showToast('✓ Deleted');
    _settingsLoaded = false;
    await loadSettings();
    _settingsLoaded = true;
  }
}

window.openSettings = openSettings;
window.closeSettings = closeSettings;
window.saveTurnstile = saveTurnstile;
window.clearTurnstileSecret = clearTurnstileSecret;
window.showAddUserForm = showAddUserForm;
window.hideAddUserForm = hideAddUserForm;
window.createUser = createUser;
window.saveUserRole = saveUserRole;
window.resetUserPassword = resetUserPassword;
window.deleteUser = deleteUser;

function slugify(s) {
  return (s || '').toString()
    .toLowerCase()
    .replace(/[^\w-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .replace(/-{2,}/g, '-')
    .slice(0, 64);
}
window.slugify = slugify;
