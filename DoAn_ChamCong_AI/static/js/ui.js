/**
 * ui.js — Shared UI utilities for Smart Attendance
 * Dropdown · Toast · Modal helpers
 */

/* =================================================================
   USER DROPDOWN
   ================================================================= */
function initUserDropdown() {
  const menus = document.querySelectorAll('.user-menu');
  menus.forEach(menu => {
    const btn = menu.querySelector('.user-btn');
    if (!btn) return;
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const isOpen = menu.classList.contains('open');
      // Close all
      document.querySelectorAll('.user-menu.open').forEach(m => m.classList.remove('open'));
      if (!isOpen) menu.classList.add('open');
    });
  });
  document.addEventListener('click', () => {
    document.querySelectorAll('.user-menu.open').forEach(m => m.classList.remove('open'));
  });
}

/* =================================================================
   TOAST NOTIFICATIONS
   ================================================================= */
function showToast(msg, type = 'success', durationMs = 3500) {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);
  }
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;

  const icons = {
    success: `<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/></svg>`,
    error:   `<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`,
    info:    `<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`,
  };

  toast.innerHTML = `${icons[type] || icons.info}<span>${msg}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.animation = 'toastOut .25s ease forwards';
    setTimeout(() => toast.remove(), 280);
  }, durationMs);
}

/* =================================================================
   MODAL HELPERS
   ================================================================= */
function openModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add('open');
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove('open');
}

// Close on backdrop click
function initModalBackdrops() {
  document.querySelectorAll('.modal-backdrop').forEach(bd => {
    bd.addEventListener('click', e => {
      if (e.target === bd) {
        bd.classList.remove('open');
        // fire custom event so page can clean up state
        bd.dispatchEvent(new CustomEvent('backdropClose'));
      }
    });
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      document.querySelectorAll('.modal-backdrop.open').forEach(bd => {
        bd.classList.remove('open');
        bd.dispatchEvent(new CustomEvent('backdropClose'));
      });
    }
  });
}

/* =================================================================
   DATE / TIME HELPERS
   ================================================================= */
const VI_DAYS   = ['Chủ nhật','Thứ Hai','Thứ Ba','Thứ Tư','Thứ Năm','Thứ Sáu','Thứ Bảy'];
const VI_MONTHS = ['T1','T2','T3','T4','T5','T6','T7','T8','T9','T10','T11','T12'];

function formatDateVI(d) {
  d = d || new Date();
  return `${VI_DAYS[d.getDay()]}, ${d.getDate()} ${VI_MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

function formatTimeHHMM(str) {
  if (!str) return '--';
  const m = str.match(/(\d{2}):(\d{2})/);
  return m ? `${m[1]}:${m[2]}` : str;
}

function initials(name) {
  if (!name) return '?';
  const parts = name.trim().split(' ');
  return parts.length >= 2
    ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
    : name.substring(0, 2).toUpperCase();
}

/* =================================================================
   CLOCK UPDATER
   ================================================================= */
function startClock(timeEl, dateEl) {
  function tick() {
    const now = new Date();
    const hh = String(now.getHours()).padStart(2,'0');
    const mm = String(now.getMinutes()).padStart(2,'0');
    const ss = String(now.getSeconds()).padStart(2,'0');
    if (timeEl) timeEl.textContent = `${hh}:${mm}:${ss}`;
    if (dateEl) dateEl.textContent = formatDateVI(now);
  }
  tick();
  setInterval(tick, 1000);
}

/* =================================================================
   INIT on DOM ready
   ================================================================= */
document.addEventListener('DOMContentLoaded', () => {
  initUserDropdown();
  initModalBackdrops();
});
