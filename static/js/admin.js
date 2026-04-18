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
      headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
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
function slugify(s) {
  return (s || '').toString()
    .toLowerCase()
    .replace(/[^\w-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .replace(/-{2,}/g, '-')
    .slice(0, 64);
}
window.slugify = slugify;
