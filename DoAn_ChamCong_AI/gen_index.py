# gen_index.py — write index.html in pieces
import pathlib

OUT = pathlib.Path(r"c:\DoAn_ChamCong_AI\templates\index.html")

PARTS = []

# ── PART 1: HEAD + STYLES ────────────────────────────────────────────────────
PARTS.append(r"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="Tổng quan chấm công — Smart Attendance">
  <title>Tổng quan — Smart Attendance</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="{{ url_for('static', filename='css/app.css') }}">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
  <style>
  /* NO-SIDEBAR LAYOUT */
  .app-shell { display:block; min-height:100vh; }
  .topbar { position:fixed; top:0; left:0; right:0; z-index:100; margin-left:0 !important; padding-right:64px; }
  .main   { margin-left:0 !important; padding-top:calc(var(--topbar-h) + 28px); }

  /* TOGGLE BUTTON */
  #right-menu-toggle {
    position:fixed; top:11px; right:16px; z-index:400;
    width:38px; height:38px; display:flex; align-items:center; justify-content:center;
    background:var(--surface); border:1px solid var(--border);
    border-radius:var(--radius-md); box-shadow:var(--shadow-sm);
    cursor:pointer; color:var(--text-secondary);
    transition:background var(--transition),border-color var(--transition),color var(--transition);
  }
  #right-menu-toggle:hover { background:var(--primary-light); border-color:var(--primary); color:var(--primary); }
  #right-menu-toggle svg { width:18px; height:18px; }

  /* BACKDROP */
  #drawer-backdrop { display:none; position:fixed; inset:0; background:rgba(17,24,39,.25); z-index:300; backdrop-filter:blur(1px); }
  #drawer-backdrop.visible { display:block; }

  /* RIGHT DRAWER */
  #right-drawer {
    position:fixed; top:0; right:0; width:300px; height:100vh;
    background:var(--surface); border-left:1px solid var(--border);
    box-shadow:-4px 0 24px rgba(0,0,0,.10); z-index:350;
    display:flex; flex-direction:column;
    transform:translateX(100%);
    transition:transform .25s cubic-bezier(.4,0,.2,1);
  }
  #right-drawer.open { transform:translateX(0); }
  @media(max-width:600px){ #right-drawer{ width:min(88vw,320px); } }

  .drawer-header { display:flex; align-items:center; justify-content:space-between; padding:0 20px; height:var(--topbar-h); border-bottom:1px solid var(--border); flex-shrink:0; }
  .drawer-brand  { display:flex; align-items:center; gap:10px; font-size:14px; font-weight:600; color:var(--text-primary); }
  .drawer-brand svg { width:18px; height:18px; color:var(--primary); }
  .drawer-close  { width:30px; height:30px; display:flex; align-items:center; justify-content:center; border-radius:var(--radius-sm); color:var(--text-muted); cursor:pointer; transition:background var(--transition),color var(--transition); }
  .drawer-close:hover { background:var(--border-light); color:var(--text-primary); }
  .drawer-close svg { width:16px; height:16px; }
  .drawer-nav  { flex:1; overflow-y:auto; padding:12px 0; }
  .drawer-footer { padding:12px 20px; border-top:1px solid var(--border); font-size:11px; color:var(--text-muted); }
  .drawer-section-label { font-size:10px; font-weight:600; color:var(--text-muted); text-transform:uppercase; letter-spacing:.07em; padding:12px 20px 4px; }
  .drawer-item {
    display:flex; align-items:center; gap:12px; padding:10px 20px;
    font-size:13.5px; font-weight:500; color:var(--text-secondary);
    cursor:pointer; border:none; background:none; width:100%; text-align:left;
    transition:background var(--transition),color var(--transition);
  }
  .drawer-item:hover  { background:var(--primary-light); color:var(--primary); }
  .drawer-item.active { background:var(--primary-light); color:var(--primary); font-weight:600; }
  .drawer-item svg { width:16px; height:16px; flex-shrink:0; opacity:.7; }
  .drawer-item:hover svg, .drawer-item.active svg { opacity:1; }

  /* FEATURE MODAL */
  .feature-modal-backdrop {
    display:none; position:fixed; inset:0; background:rgba(17,24,39,.4); z-index:500;
    backdrop-filter:blur(2px); align-items:center; justify-content:center; padding:24px;
  }
  .feature-modal-backdrop.open { display:flex; }
  .feature-modal {
    background:var(--surface); border-radius:var(--radius-lg); box-shadow:var(--shadow-modal);
    width:90vw; max-width:1300px; max-height:88vh;
    display:flex; flex-direction:column; overflow:hidden;
    animation:modalIn .2s cubic-bezier(.4,0,.2,1);
  }
  @keyframes modalIn { from{opacity:0;transform:scale(.97) translateY(8px)} to{opacity:1;transform:scale(1) translateY(0)} }
  .feature-modal-header { display:flex; align-items:center; justify-content:space-between; padding:0 24px; height:56px; border-bottom:1px solid var(--border); flex-shrink:0; }
  .feature-modal-title  { font-size:15px; font-weight:600; color:var(--text-primary); display:flex; align-items:center; gap:10px; }
  .feature-modal-title svg { width:16px; height:16px; color:var(--primary); }
  .feature-modal-close  { width:32px; height:32px; display:flex; align-items:center; justify-content:center; border-radius:var(--radius-sm); color:var(--text-muted); cursor:pointer; transition:background var(--transition),color var(--transition); }
  .feature-modal-close:hover { background:var(--border-light); color:var(--text-primary); }
  .feature-modal-close svg { width:16px; height:16px; }
  .feature-modal-body   { flex:1; overflow-y:auto; padding:24px; display:flex; flex-direction:column; gap:20px; }

  /* modal specific */
  .modal-cam-wrap  { display:flex; justify-content:center; align-items:flex-start; gap:20px; flex-wrap:wrap; }
  .modal-cam-video { border-radius:var(--radius-md); overflow:hidden; border:1px solid var(--border); flex:1; min-width:280px; max-width:640px; }
  .modal-cam-video img { width:100%; display:block; }
  .modal-cam-info  { min-width:220px; display:flex; flex-direction:column; gap:12px; }
  .modal-charts-grid { display:grid; grid-template-columns:1fr 1fr; gap:20px; }
  .modal-chart-wrap  { height:220px; }
  .modal-table-wrap  { overflow-x:auto; border-radius:var(--radius-md); border:1px solid var(--border); }
  .modal-section-label { font-size:11px; font-weight:600; color:var(--text-muted); text-transform:uppercase; letter-spacing:.06em; padding-bottom:8px; border-bottom:1px solid var(--border-light); }

  /* quick access cards */
  .dash-sum-card { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius-md); padding:14px 16px; display:flex; align-items:center; gap:12px; cursor:pointer; transition:box-shadow var(--transition),border-color var(--transition); }
  .dash-sum-card:hover { box-shadow:var(--shadow-sm); border-color:var(--primary); }
  .dash-sum-icon { width:36px; height:36px; border-radius:var(--radius-sm); display:flex; align-items:center; justify-content:center; flex-shrink:0; }
  .dash-sum-icon svg { width:16px; height:16px; }
  .dash-sum-label { font-size:11px; color:var(--text-muted); }
  .dash-sum-value { font-size:20px; font-weight:700; color:var(--text-primary); }

  @media(max-width:720px){ .modal-charts-grid{ grid-template-columns:1fr; } .feature-modal{ width:98vw; max-height:92vh; } .feature-modal-body{ padding:16px; } }
  @media(max-width:900px){ .content-grid-7030{ grid-template-columns:1fr !important; } }
  @media(max-width:600px){ .main{ padding:20px 12px; } }
  </style>
</head>
<body>
<div class="app-shell">
""")

# ── PART 2: TOPBAR ────────────────────────────────────────────────────────────
PARTS.append(r"""<!-- TOPBAR -->
<header class="topbar" role="banner">
  <div style="display:flex;align-items:center;gap:12px;">
    <div style="display:flex;align-items:center;gap:8px;">
      <svg fill="none" stroke="var(--primary)" stroke-width="2" viewBox="0 0 24 24" style="width:20px;height:20px;"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
      <span style="font-weight:700;font-size:14px;color:var(--text-primary);">Smart Attendance</span>
    </div>
    <div id="topbar-date" class="topbar-date" style="font-size:12px;color:var(--text-muted);"></div>
  </div>
  <div style="margin-left:12px;"><span id="ai-status-badge" class="ai-badge none">Khởi động...</span></div>
  <div class="topbar-right">
    <div class="user-menu">
      <button class="user-btn" id="userBtn" aria-label="Tài khoản">
        <div class="user-avatar-sm" id="topbarAvatar">AD</div>
        <div class="user-info-text">
          <span class="user-name-sm" id="topbarName">Admin</span>
          <span class="user-role-sm" id="topbarRole">Quản trị viên</span>
        </div>
        <svg class="user-chevron" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>
      </button>
      <div class="user-dropdown">
        <a class="dropdown-item" href="/me">
          <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.58-7 8-7s8 3 8 7"/></svg>
          Trang cá nhân
        </a>
        <div class="dropdown-divider"></div>
        <a class="dropdown-item danger" href="/logout">
          <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
          Đăng xuất
        </a>
      </div>
    </div>
  </div>
</header>
""")

# ── PART 3: TOGGLE + DRAWER ───────────────────────────────────────────────────
PARTS.append(r"""<!-- TOGGLE -->
<button id="right-menu-toggle" aria-label="Mở menu" title="Menu">
  <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
    <line x1="3" y1="6"  x2="21" y2="6"/>
    <line x1="3" y1="12" x2="21" y2="12"/>
    <line x1="3" y1="18" x2="21" y2="18"/>
  </svg>
</button>
<div id="drawer-backdrop"></div>

<!-- RIGHT DRAWER -->
<aside id="right-drawer" role="navigation" aria-label="Menu chức năng">
  <div class="drawer-header">
    <div class="drawer-brand">
      <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
      Smart Attendance
    </div>
    <button class="drawer-close" id="drawer-close-btn" aria-label="Đóng menu">
      <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
    </button>
  </div>
  <nav class="drawer-nav">
    <div class="drawer-section-label">Tổng quan</div>
    <button class="drawer-item active" id="drawer-item-dashboard" onclick="goToDashboard()">
      <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
      Tổng quan
    </button>
    <div class="drawer-section-label">Quản lý</div>
    <button class="drawer-item" id="drawer-item-employees" onclick="openFeatureModal('employees')">
      <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/></svg>
      Nhân viên
    </button>
    <div class="drawer-section-label">Chấm công</div>
    <button class="drawer-item" id="drawer-item-attendance" onclick="openFeatureModal('attendance')">
      <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>
      Chấm công
    </button>
    <button class="drawer-item" id="drawer-item-statistics" onclick="openFeatureModal('statistics')">
      <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
      Thống kê
    </button>
    <div class="drawer-section-label">Giám sát</div>
    <button class="drawer-item" id="drawer-item-camera" onclick="openFeatureModal('camera')">
      <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2"/></svg>
      Camera AI
    </button>
    <button class="drawer-item" id="drawer-item-alerts" onclick="openFeatureModal('alerts')">
      <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
      Cảnh báo
    </button>
    <div class="drawer-section-label">Hỗ trợ</div>
    <button class="drawer-item" id="drawer-item-health" onclick="openFeatureModal('health')">
      <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78L12 21.23l8.84-8.84a5.5 5.5 0 000-7.78z"/></svg>
      Sức khỏe
    </button>
  </nav>
  <div class="drawer-footer">Smart Attendance v2.0</div>
</aside>
""")

# ── PART 4: MAIN ──────────────────────────────────────────────────────────────
PARTS.append(r"""<!-- MAIN -->
<main class="main" role="main">
  <div class="page-header" id="dashboard">
    <div class="page-header-left">
      <div class="page-title">Tổng quan</div>
      <div class="page-subtitle">Theo dõi tình hình chấm công · cập nhật mỗi 3 giây</div>
    </div>
  </div>

  <!-- KPI -->
  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-label">Tổng nhân viên</div>
      <div class="kpi-value" id="kpi-tong-nv">--</div>
      <div class="kpi-sub">trong hệ thống</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Đã chấm công</div>
      <div class="kpi-value" id="kpi-da-cham">--</div>
      <div class="kpi-sub" id="kpi-da-cham-sub">hôm nay</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Đi trễ</div>
      <div class="kpi-value" id="kpi-di-tre" style="color:var(--warning);">--</div>
      <div class="kpi-sub">so với giờ chuẩn</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Chưa chấm công</div>
      <div class="kpi-value" id="kpi-chua-cham" style="color:var(--danger);">--</div>
      <div class="kpi-sub">vắng mặt hôm nay</div>
    </div>
  </div>

  <!-- hidden KPI for JS -->
  <span id="kpi-dang-lam" style="display:none;"></span>
  <span id="kpi-ve-som"   style="display:none;"></span>
  <span id="kpi-canh-bao" style="display:none;"></span>
  <span id="chamcong-badge" style="display:none;"></span>

  <!-- Quick Access -->
  <div class="panel">
    <div class="panel-header">
      <span class="panel-title">Truy cập nhanh</span>
      <span class="panel-badge">Click để xem chi tiết</span>
    </div>
    <div style="padding:16px;display:grid;grid-template-columns:repeat(4,1fr);gap:12px;">
      <button class="dash-sum-card" onclick="openFeatureModal('attendance')" style="border:none;">
        <div class="dash-sum-icon" style="background:var(--primary-light);"><svg fill="none" stroke="var(--primary)" stroke-width="2" viewBox="0 0 24 24"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg></div>
        <div><div class="dash-sum-label">Chấm công</div><div class="dash-sum-value" id="qa-chamcong">--</div></div>
      </button>
      <button class="dash-sum-card" onclick="openFeatureModal('camera')" style="border:none;">
        <div class="dash-sum-icon" style="background:var(--info-bg);"><svg fill="none" stroke="var(--info)" stroke-width="2" viewBox="0 0 24 24"><path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2"/></svg></div>
        <div><div class="dash-sum-label">Camera AI</div><div class="dash-sum-value" style="font-size:13px;font-weight:600;" id="qa-camera">Live</div></div>
      </button>
      <button class="dash-sum-card" onclick="openFeatureModal('alerts')" style="border:none;">
        <div class="dash-sum-icon" style="background:var(--warning-bg);"><svg fill="none" stroke="var(--warning)" stroke-width="2" viewBox="0 0 24 24"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg></div>
        <div><div class="dash-sum-label">Cảnh báo</div><div class="dash-sum-value" id="qa-canhbao">--</div></div>
      </button>
      <button class="dash-sum-card" onclick="openFeatureModal('health')" style="border:none;">
        <div class="dash-sum-icon" style="background:var(--success-bg);"><svg fill="none" stroke="var(--success)" stroke-width="2" viewBox="0 0 24 24"><path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78L12 21.23l8.84-8.84a5.5 5.5 0 000-7.78z"/></svg></div>
        <div><div class="dash-sum-label">Sức khỏe</div><div class="dash-sum-value" style="font-size:13px;font-weight:600;" id="qa-health">--</div></div>
      </button>
    </div>
  </div>

  <!-- Stat summary + Env + Alerts -->
  <div class="content-grid-7030">
    <div class="panel">
      <div class="panel-header">
        <span class="panel-title">Tình trạng hôm nay</span>
        <button onclick="openFeatureModal('attendance')" style="font-size:11px;color:var(--primary);border:none;background:none;font-family:inherit;font-weight:500;cursor:pointer;">Xem chi tiết →</button>
      </div>
      <div class="stat-list">
        <div class="stat-list-item"><span class="stat-list-label"><span class="stat-list-dot" style="background:var(--success);"></span>Đúng giờ</span><span class="stat-list-value" id="leg-dung-gio">--</span></div>
        <div class="stat-list-item"><span class="stat-list-label"><span class="stat-list-dot" style="background:var(--warning);"></span>Đi trễ</span><span class="stat-list-value" id="leg-di-tre">--</span></div>
        <div class="stat-list-item"><span class="stat-list-label"><span class="stat-list-dot" style="background:var(--primary);"></span>Đang làm việc</span><span class="stat-list-value" id="leg-dang-lam">--</span></div>
        <div class="stat-list-item"><span class="stat-list-label"><span class="stat-list-dot" style="background:var(--danger);"></span>Về sớm</span><span class="stat-list-value" id="leg-ve-som">--</span></div>
        <div class="stat-list-item"><span class="stat-list-label"><span class="stat-list-dot" style="background:var(--text-muted);"></span>Chưa chấm công</span><span class="stat-list-value" id="leg-chua-cham">--</span></div>
      </div>
    </div>
    <div class="right-col">
      <div class="panel">
        <div class="panel-header">
          <span class="panel-title">Cảnh báo gần đây</span>
          <button onclick="openFeatureModal('alerts')" style="font-size:11px;color:var(--primary);border:none;background:none;font-family:inherit;font-weight:500;cursor:pointer;">Tất cả →</button>
        </div>
        <div id="cam-alerts-body"><div class="alert-list-item" style="padding:12px 16px;color:var(--text-muted);font-size:12.5px;">Đang tải...</div></div>
      </div>
    </div>
  </div>

  <!-- hidden chart legend spans for JS compatibility -->
  <div style="display:none;" aria-hidden="true">
    <span id="leg-dung-gio-chart"></span><span id="leg-dang-lam-chart"></span>
    <span id="leg-di-tre-chart"></span><span id="leg-ve-som-chart"></span>
    <span id="leg-chua-cham-chart"></span>
  </div>
</main>
</div><!-- /app-shell -->

<div id="toast-container"></div>
""")

# ── PART 5: MODAL SHELL ───────────────────────────────────────────────────────
PARTS.append(r"""<!-- FEATURE MODAL -->
<div class="feature-modal-backdrop" id="feature-modal-backdrop" role="dialog" aria-modal="true">
  <div class="feature-modal" id="feature-modal">
    <div class="feature-modal-header">
      <div class="feature-modal-title" id="feature-modal-title-wrap">
        <svg id="feature-modal-icon" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"></svg>
        <span id="feature-modal-title">Chức năng</span>
      </div>
      <button class="feature-modal-close" id="feature-modal-close" aria-label="Đóng">
        <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
    </div>
    <div class="feature-modal-body" id="feature-modal-body"></div>
  </div>
</div>
""")

# ── PART 6: JS ────────────────────────────────────────────────────────────────
PARTS.append(r"""<script src="{{ url_for('static', filename='js/ui.js') }}"></script>
<script>
/* CLOCK */
(function(){
  const el=document.getElementById('topbar-date');
  const D=['Chủ nhật','Thứ Hai','Thứ Ba','Thứ Tư','Thứ Năm','Thứ Sáu','Thứ Bảy'];
  function tick(){const n=new Date();if(el)el.textContent=`${D[n.getDay()]}, ${n.getDate()} tháng ${n.getMonth()+1} năm ${n.getFullYear()}`;}
  tick();setInterval(tick,60000);
})();

/* DRAWER */
function openRightDrawer(){
  document.getElementById('right-drawer').classList.add('open');
  document.getElementById('drawer-backdrop').classList.add('visible');
  document.body.style.overflow='hidden';
}
function closeRightDrawer(){
  document.getElementById('right-drawer').classList.remove('open');
  document.getElementById('drawer-backdrop').classList.remove('visible');
  document.body.style.overflow='';
}
function goToDashboard(){
  closeRightDrawer(); closeFeatureModal();
  document.querySelectorAll('.drawer-item').forEach(e=>e.classList.remove('active'));
  document.getElementById('drawer-item-dashboard').classList.add('active');
  window.scrollTo({top:0,behavior:'smooth'});
}
document.getElementById('right-menu-toggle').addEventListener('click',openRightDrawer);
document.getElementById('drawer-close-btn').addEventListener('click',closeRightDrawer);
document.getElementById('drawer-backdrop').addEventListener('click',closeRightDrawer);

/* MODAL */
let activeModal=null, chartsInModal={};

const MODAL_ICONS={
  employees:'<path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/>',
  attendance:'<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/>',
  statistics:'<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
  camera:'<path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2"/>',
  alerts:'<path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
  health:'<path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78L12 21.23l8.84-8.84a5.5 5.5 0 000-7.78z"/>',
};
const MODAL_TITLES={
  employees:'Quản lý nhân viên',attendance:'Chấm công',statistics:'Thống kê',
  camera:'Camera AI',alerts:'Cảnh báo AI',health:'Sức khỏe nhân viên'
};

function openFeatureModal(feature){
  closeRightDrawer();
  document.querySelectorAll('.drawer-item').forEach(e=>e.classList.remove('active'));
  const di=document.getElementById('drawer-item-'+feature);
  if(di) di.classList.add('active');
  document.getElementById('feature-modal-title').textContent=MODAL_TITLES[feature]||feature;
  document.getElementById('feature-modal-icon').innerHTML=MODAL_ICONS[feature]||'';
  Object.values(chartsInModal).forEach(c=>{try{c.destroy();}catch(e){}});
  chartsInModal={};
  document.getElementById('feature-modal-body').innerHTML=buildModalContent(feature);
  document.getElementById('feature-modal-backdrop').classList.add('open');
  document.body.style.overflow='hidden';
  activeModal=feature;
  setTimeout(()=>initModalContent(feature),60);
}
function closeFeatureModal(){
  document.getElementById('feature-modal-backdrop').classList.remove('open');
  document.body.style.overflow='';
  activeModal=null;
  document.querySelectorAll('.drawer-item').forEach(e=>e.classList.remove('active'));
  document.getElementById('drawer-item-dashboard').classList.add('active');
}
document.getElementById('feature-modal-backdrop').addEventListener('click',function(e){if(e.target===this)closeFeatureModal();});
document.getElementById('feature-modal-close').addEventListener('click',closeFeatureModal);
document.addEventListener('keydown',e=>{if(e.key==='Escape'){if(activeModal){closeFeatureModal();return;}closeRightDrawer();}});

/* MODAL BUILDERS */
function buildModalContent(f){
  if(f==='employees') return `
    <div style="text-align:center;padding:40px 20px;color:var(--text-muted);">
      <svg fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24" style="width:48px;height:48px;margin:0 auto 16px;opacity:.4;"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/></svg>
      <div style="font-size:15px;font-weight:600;color:var(--text-primary);margin-bottom:8px;">Quản lý nhân viên</div>
      <div style="font-size:13px;margin-bottom:20px;">Truy cập trang quản lý nhân viên để xem toàn bộ chức năng CRUD</div>
      <a href="/employees" style="display:inline-flex;align-items:center;gap:8px;padding:10px 20px;background:var(--primary);color:#fff;border-radius:var(--radius-md);font-size:13px;font-weight:600;">
        <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" style="width:14px;height:14px;"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
        Mở trang Nhân viên
      </a>
    </div>`;

  if(f==='attendance') return `
    <div class="modal-section-label">Bộ lọc</div>
    <div class="attendance-toolbar" style="border:none;padding:0;">
      <div class="search-wrap" style="flex:1;max-width:300px;">
        <span class="search-icon"><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2"><circle cx="8.5" cy="8.5" r="5.5"/><path d="M15 15l-3.5-3.5"/></svg></span>
        <input type="text" id="attendance-search" class="search-input" placeholder="Tìm tên hoặc mã nhân viên..." autocomplete="off">
      </div>
      <div class="attendance-date-wrap">
        <input type="date" id="attendance-date" class="attendance-date-input">
        <button id="attendance-today-btn" class="attendance-today-btn">Hôm nay</button>
      </div>
    </div>
    <div class="panel" style="margin:0;">
      <div class="panel-header">
        <span class="panel-title" id="attendance-panel-title">Chấm công hôm nay</span>
        <span class="panel-badge" id="attendance-count">Đang tải...</span>
      </div>
      <div class="modal-table-wrap">
        <table class="data-table" id="chamcong-table">
          <thead><tr><th>Nhân viên</th><th>Ca làm việc</th><th>Giờ vào</th><th>Trạng thái vào</th><th>Giờ ra</th><th>Trạng thái ra</th></tr></thead>
          <tbody id="chamcong-tbody"><tr><td colspan="6" class="td-empty">Đang tải dữ liệu...</td></tr></tbody>
        </table>
      </div>
    </div>`;

  if(f==='statistics') return `
    <div class="modal-section-label">Cơ cấu chấm công hôm nay</div>
    <div class="modal-charts-grid">
      <div class="panel" style="margin:0;">
        <div class="panel-header"><span class="panel-title">Donut</span></div>
        <div class="panel-body">
          <div class="modal-chart-wrap"><canvas id="chart-donut"></canvas></div>
          <div class="donut-legend" style="margin-top:8px;">
            <div class="legend-row"><span class="legend-left"><span class="legend-dot" style="background:#16A34A;"></span>Đúng giờ</span><span class="legend-count" id="leg-dung-gio-chart">--</span></div>
            <div class="legend-row"><span class="legend-left"><span class="legend-dot" style="background:#2563EB;"></span>Đang làm</span><span class="legend-count" id="leg-dang-lam-chart">--</span></div>
            <div class="legend-row"><span class="legend-left"><span class="legend-dot" style="background:#D97706;"></span>Đi trễ</span><span class="legend-count" id="leg-di-tre-chart">--</span></div>
            <div class="legend-row"><span class="legend-left"><span class="legend-dot" style="background:#DC2626;"></span>Về sớm</span><span class="legend-count" id="leg-ve-som-chart">--</span></div>
            <div class="legend-row"><span class="legend-left"><span class="legend-dot" style="background:#9CA3AF;"></span>Chưa chấm</span><span class="legend-count" id="leg-chua-cham-chart">--</span></div>
          </div>
        </div>
      </div>
      <div class="panel" style="margin:0;">
        <div class="panel-header"><span class="panel-title">7 ngày gần nhất</span></div>
        <div class="panel-body"><div class="modal-chart-wrap"><canvas id="chart-weekly"></canvas></div></div>
      </div>
    </div>
    `;

  if(f==='camera') return `
    <div class="modal-cam-wrap">
      <div class="modal-cam-video"><img id="camera-feed" src="{{ url_for('video_feed') }}" alt="Camera stream AI"></div>
      <div class="modal-cam-info">
        <div class="panel" style="margin:0;">
          <div class="panel-header"><span class="panel-title">AI Status</span></div>
          <div style="padding:16px;display:flex;flex-direction:column;gap:12px;">
            <div><div style="font-size:10px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px;">Trạng thái</div><span id="ai-status-badge-modal" class="ai-badge none">--</span></div>
            <div><div style="font-size:10px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px;">EAR Score</div><span id="ear-display" class="ai-badge none" style="font-size:10.5px;">EAR --</span></div>
          </div>
        </div>
        <div class="panel" style="margin:0;">
          <div class="panel-header"><span class="panel-title">Cảnh báo gần đây</span></div>
          <div id="cam-alerts-body-modal" style="max-height:200px;overflow-y:auto;"><div style="padding:12px 16px;color:var(--text-muted);font-size:12px;">Đang tải...</div></div>
        </div>
      </div>
    </div>`;

  if(f==='alerts') return `
    <div class="modal-section-label">10 cảnh báo gần nhất</div>
    <div class="modal-table-wrap">
      <table class="data-table" id="alert-table">
        <thead><tr><th>Nhân viên</th><th>Loại</th><th>Mô tả</th><th>Thời gian</th></tr></thead>
        <tbody id="alert-tbody"><tr><td colspan="4" class="td-empty">Đang tải...</td></tr></tbody>
      </table>
    </div>`;

  if(f==='health') return `
    <div class="modal-section-label">Dữ liệu sức khỏe nhân viên</div>
    <div class="modal-table-wrap">
      <table class="data-table" id="health-table">
        <thead><tr><th>Nhân viên</th><th>Nhịp tim</th><th>SpO₂</th><th>Thời gian</th></tr></thead>
        <tbody id="health-tbody"><tr><td colspan="4" class="td-empty">Đang tải...</td></tr></tbody>
      </table>
    </div>`;

  return '<p>Đang phát triển.</p>';
}

/* INIT MODAL CONTENT */
const CB={responsive:true,maintainAspectRatio:false,animation:{duration:300},
  plugins:{legend:{display:false},tooltip:{backgroundColor:'#fff',borderColor:'#E5E7EB',borderWidth:1,titleColor:'#111827',bodyColor:'#667085',padding:10,cornerRadius:6}}};

function initModalContent(f){
  if(f==='attendance'){
    const today=getTodayStr(); selectedDate=today;
    const di=document.getElementById('attendance-date'); if(di) di.value=today;
    const si=document.getElementById('attendance-search');
    if(si) si.addEventListener('input',()=>{clearTimeout(searchDebounce);searchDebounce=setTimeout(filterAndRender,250);});
    if(di) di.addEventListener('change',()=>{const v=di.value;if(!v)return;selectedDate=v;if(si)si.value='';fetchDashboard(v);});
    const tb=document.getElementById('attendance-today-btn');
    if(tb) tb.addEventListener('click',()=>{const t=getTodayStr();selectedDate=t;if(di)di.value=t;if(si)si.value='';fetchDashboard(t);});
    fetchDashboard(selectedDate);
  }
  if(f==='statistics'){
    const dc=document.getElementById('chart-donut');
    if(dc){chartsInModal.donut=new Chart(dc,{type:'doughnut',data:{labels:['Đúng giờ','Đang làm','Đi trễ','Về sớm','Chưa chấm'],datasets:[{data:[0,0,0,0,1],backgroundColor:['#16A34A','#2563EB','#D97706','#DC2626','#9CA3AF'],borderColor:'#fff',borderWidth:3,hoverOffset:6}]},options:{...CB,cutout:'70%',plugins:{...CB.plugins,tooltip:{...CB.plugins.tooltip,callbacks:{label:ctx=>` ${ctx.label}: ${ctx.parsed} người`}}}}});donutChart=chartsInModal.donut;}
    const wc=document.getElementById('chart-weekly');
    if(wc){chartsInModal.weekly=new Chart(wc,{type:'bar',data:{labels:[],datasets:[{label:'Người vào',data:[],backgroundColor:'#BFDBFE',borderColor:'#2563EB',borderWidth:1,borderRadius:4,borderSkipped:false},{label:'Người ra',data:[],backgroundColor:'#BBF7D0',borderColor:'#16A34A',borderWidth:1,borderRadius:4,borderSkipped:false}]},options:{...CB,plugins:{...CB.plugins,legend:{display:true,position:'top',labels:{color:'#667085',font:{size:11},boxWidth:10,padding:10}}},scales:{x:{grid:{color:'#F3F4F6'},ticks:{color:'#98A2B3',font:{size:10}}},y:{grid:{color:'#F3F4F6'},ticks:{color:'#98A2B3',font:{size:10},stepSize:1},beginAtZero:true}}}});weeklyChart=chartsInModal.weekly;fetchWeekly();}
    fetchDashboard(selectedDate);
  }
  if(f==='camera'){
    const mb=document.getElementById('ai-status-badge'),mm=document.getElementById('ai-status-badge-modal');
    if(mb&&mm){mm.textContent=mb.textContent;mm.className=mb.className;}
    const ca=document.getElementById('cam-alerts-body'),cm=document.getElementById('cam-alerts-body-modal');
    if(ca&&cm) cm.innerHTML=ca.innerHTML;
  }
  if(f==='alerts') fetchAlerts();
  if(f==='health') fetchHealth();
}

/* HELPERS */
function initials(n){if(!n)return'?';const p=n.trim().split(' ');return p.length>=2?(p[0][0]+p[p.length-1][0]).toUpperCase():n.substring(0,2).toUpperCase();}
function fmtTime(s){if(!s)return'--';const m=s.match(/(\d{2}):(\d{2})(?::(\d{2}))?/);return m?`${m[1]}:${m[2]}`:s;}
function badgeVao(t){if(!t||t==='Chưa chấm công')return`<span class="badge badge-gray">${t||'Chưa chấm công'}</span>`;if(t==='Đúng giờ')return`<span class="badge badge-green">Đúng giờ</span>`;if(t==='Đi trễ')return`<span class="badge badge-orange">Đi trễ</span>`;return`<span class="badge badge-gray">${t}</span>`;}
function badgeRa(t){if(!t||t==='--')return'<span class="text-xs text-muted">--</span>';if(t==='Đang làm việc')return`<span class="badge badge-blue">Đang làm việc</span>`;if(t==='Đúng giờ')return`<span class="badge badge-green">Đúng giờ</span>`;if(t==='Về sớm')return`<span class="badge badge-red">Về sớm</span>`;return`<span class="badge badge-gray">${t}</span>`;}
function badgeAlert(l){if(!l)return`<span class="badge badge-gray">--</span>`;const lc=l.toLowerCase();if(lc.includes('ngu')||lc.includes('buồn'))return`<span class="badge badge-red">${l}</span>`;if(lc.includes('guc')||lc.includes('tilt'))return`<span class="badge badge-orange">${l}</span>`;return`<span class="badge badge-gray">${l}</span>`;}

/* ATTENDANCE STATE */
let attendanceRecords=[],selectedDate='',searchDebounce=null;
function normVi(s){return(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\u0111/g,'d').replace(/\u0110/g,'D').toLowerCase();}
function filterAndRender(){
  const si=document.getElementById('attendance-search'),q=si?(si.value||'').trim():'',nq=normVi(q);
  const filtered=q?attendanceRecords.filter(r=>normVi(r.HoTen).includes(nq)||String(r.MaNV).includes(q)):attendanceRecords;
  const ce=document.getElementById('attendance-count');
  if(ce) ce.textContent=q?`${filtered.length} / ${attendanceRecords.length} nhân viên`:`${attendanceRecords.length} nhân viên`;
  const tbody=document.getElementById('chamcong-tbody');
  if(!tbody) return;
  if(!filtered.length){tbody.innerHTML=q?'<tr><td colspan="6" class="td-empty">Không tìm thấy nhân viên phù hợp</td></tr>':'<tr><td colspan="6" class="td-empty">Chưa có dữ liệu chấm công ngày này</td></tr>';return;}
  tbody.innerHTML=filtered.map(r=>`
    <tr>
      <td><div class="emp-cell"><div class="emp-avatar">${initials(r.HoTen)}</div><div><div class="emp-name">${r.HoTen}</div><div class="emp-id">NV${String(r.MaNV||'').padStart(3,'0')}</div></div></div></td>
      <td><div class="shift-name">${r.TenCa||'--'}</div><span class="shift-hours">${r.GioBatDau||'--'} – ${r.GioKetThuc||'--'}</span></td>
      <td class="tabular fw-600" style="color:var(--success);">${r.GioVao?fmtTime(r.GioVao):'<span class="text-muted">--</span>'}</td>
      <td>${badgeVao(r.TrangThaiVao)}</td>
      <td class="tabular text-muted">${r.GioRa?fmtTime(r.GioRa):'<span class="text-muted">--</span>'}</td>
      <td>${badgeRa(r.TrangThaiRa)}</td>
    </tr>`).join('');
}

/* CHART INSTANCES (lazy-init in modal) */
let donutChart=null,weeklyChart=null;

/* FETCH: DASHBOARD */
function fetchDashboard(dateOverride){
  const d=dateOverride!==undefined?dateOverride:selectedDate;
  const url=d?`/api/dashboard/attendance?date=${d}`:'/api/dashboard/attendance';
  fetch(url).then(r=>r.json()).then(data=>{
    const s=data.Summary||{},recs=data.Records||[],sel=data.SelectedDate||selectedDate;
    if(sel) selectedDate=sel;
    document.getElementById('kpi-tong-nv').textContent=s.TongNhanVien??'--';
    document.getElementById('kpi-da-cham').textContent=s.DaChamCong??'--';
    document.getElementById('kpi-dang-lam').textContent=s.DangLamViec??'--';
    document.getElementById('kpi-di-tre').textContent=s.DiTre??'--';
    document.getElementById('kpi-ve-som').textContent=s.VeSom??'--';
    document.getElementById('kpi-chua-cham').textContent=s.ChuaChamCong??'--';
    document.getElementById('kpi-canh-bao').textContent=s.CanhBaoHomNay??'--';
    const cb=document.getElementById('chamcong-badge');if(cb) cb.textContent=`${s.DaChamCong??0}/${s.TongNhanVien??0} người`;
    const qa=document.getElementById('qa-chamcong');if(qa) qa.textContent=`${s.DaChamCong??'--'}/${s.TongNhanVien??'--'}`;
    const sub=document.getElementById('kpi-da-cham-sub');if(sub) sub.textContent=`/ ${s.TongNhanVien??'--'} nhân viên`;
    const dungGio=recs.filter(r=>r.TrangThaiVao==='Đúng giờ'&&r.TrangThaiRa!=='Về sớm').length;
    const dangLam=s.DangLamViec||0,diTre=s.DiTre||0,veSom=s.VeSom||0,chuaCham=s.ChuaChamCong||0;
    ['leg-dung-gio','leg-di-tre','leg-dang-lam','leg-ve-som','leg-chua-cham'].forEach((id,i)=>{const e=document.getElementById(id);if(e) e.textContent=[dungGio,diTre,dangLam,veSom,chuaCham][i];});
    ['leg-dung-gio-chart','leg-dang-lam-chart','leg-di-tre-chart','leg-ve-som-chart','leg-chua-cham-chart'].forEach((id,i)=>{const e=document.getElementById(id);if(e) e.textContent=[dungGio,dangLam,diTre,veSom,chuaCham][i];});
    if(donutChart){donutChart.data.datasets[0].data=[dungGio,dangLam,diTre,veSom,chuaCham];donutChart.update();}
    const today=getTodayStr(),te=document.getElementById('attendance-panel-title');
    if(te){if(selectedDate===today){te.textContent='Chấm công hôm nay';}else{const dd=new Date(selectedDate+'T00:00:00');te.textContent=`Chấm công ngày ${String(dd.getDate()).padStart(2,'0')}/${String(dd.getMonth()+1).padStart(2,'0')}/${dd.getFullYear()}`;}}
    attendanceRecords=recs;filterAndRender();
  }).catch(e=>console.error('[dashboard]',e));
}

/* FETCH: WEEKLY */
function fetchWeekly(){
  fetch('/api/get_chamcong_weekly').then(r=>r.json()).then(data=>{
    if(!weeklyChart) return;
    const D=['CN','T2','T3','T4','T5','T6','T7'];
    weeklyChart.data.labels=data.map(r=>{if(!r.Ngay||r.Ngay==='--')return'--';const d=new Date(r.Ngay);return`${D[d.getDay()]} ${String(d.getDate()).padStart(2,'0')}/${String(d.getMonth()+1).padStart(2,'0')}`;});
    weeklyChart.data.datasets[0].data=data.map(r=>r.SoNguoiVao);
    weeklyChart.data.datasets[1].data=data.map(r=>r.SoNguoiRa);
    weeklyChart.update();
  }).catch(e=>console.error('[weekly]',e));
}

/* FETCH: HEALTH */
function fetchHealth(){
  fetch('/api/get_health').then(r=>r.json()).then(data=>{
    const qa=document.getElementById('qa-health');if(qa&&data.length) qa.textContent=`${data[0].NhipTim} bpm`;
    const tbody=document.getElementById('health-tbody');if(!tbody) return;
    if(!data.length){tbody.innerHTML='<tr><td colspan="4" class="td-empty">Chưa có dữ liệu sức khỏe</td></tr>';return;}
    tbody.innerHTML=data.map(r=>`<tr><td><div class="emp-cell"><div class="emp-avatar" style="width:26px;height:26px;font-size:10px;">${initials(r.HoTen)}</div><span class="fw-600">${r.HoTen}</span></div></td><td><span class="fw-600" style="color:var(--danger);">${r.NhipTim}</span> <span class="text-xs text-muted">bpm</span></td><td><span class="fw-600">${r.SpO2}</span><span class="text-xs text-muted">%</span></td><td class="text-xs text-muted tabular">${r.ThoiGian}</td></tr>`).join('');
  }).catch(e=>console.error('[health]',e));
}

/* FETCH: ALERTS */
function fetchAlerts(){
  fetch('/api/get_alerts?limit=10').then(r=>r.json()).then(data=>{
    const qa=document.getElementById('qa-canhbao');if(qa) qa.textContent=data.length||0;
    const tb=document.getElementById('alert-tbody');
    if(tb){if(!data.length){tb.innerHTML='<tr><td colspan="4" class="td-empty">Chưa có cảnh báo</td></tr>';}else{tb.innerHTML=data.map(r=>`<tr><td class="fw-600">${r.HoTen}</td><td>${badgeAlert(r.LoaiCanhBao)}</td><td class="text-xs text-muted">${r.MoTa||'--'}</td><td class="text-xs text-muted tabular">${r.ThoiGian}</td></tr>`).join('');}}
    const today=new Date().toDateString();
    const ta=data.filter(r=>{if(!r.ThoiGian||r.ThoiGian==='--')return false;try{return new Date(r.ThoiGian).toDateString()===today;}catch{return false;}});
    const cb=document.getElementById('cam-alerts-body');
    if(cb){if(!ta.length){cb.innerHTML='<div class="alert-list-item"><span class="text-xs text-muted">Không có cảnh báo hôm nay</span></div>';}else{cb.innerHTML=ta.slice(0,5).map(r=>{const l=(r.LoaiCanhBao||'').toLowerCase();const dc=l.includes('ngu')||l.includes('buồn')?'alert-dot-red':l.includes('guc')||l.includes('tilt')?'alert-dot-orange':'alert-dot-gray';return`<div class="alert-list-item"><span class="alert-dot ${dc}"></span><div style="flex:1;min-width:0;"><div class="alert-name">${r.HoTen}</div><div class="alert-type">${r.LoaiCanhBao||'--'}</div></div><span class="alert-time">${fmtTime(r.ThoiGian)}</span></div>`;}).join('');}}
    const cm=document.getElementById('cam-alerts-body-modal');if(cm&&cb) cm.innerHTML=cb.innerHTML;
  }).catch(e=>console.error('[alerts]',e));
}

/* FETCH: AI STATUS */
function fetchAiStatus(){
  fetch('/api/ai_status').then(r=>r.json()).then(data=>{
    const badge=document.getElementById('ai-status-badge'),ear=document.getElementById('ear-display');
    const M={binh_thuong:{label:'Bình thường',cls:'normal'},buon_ngu:{label:'Buồn ngủ',cls:'warning'},guc_dau:{label:'Gục đầu',cls:'tilt'},khong_co_khuon_mat:{label:'Không phát hiện',cls:'none'}};
    const info=M[data.state]||{label:data.state||'N/A',cls:'none'};
    if(badge){badge.textContent=info.label;badge.className=`ai-badge ${info.cls}`;}
    if(ear){ear.textContent=`EAR ${data.ear??'--'}`;ear.className=`ai-badge ${data.state==='buon_ngu'?'warning':'none'}`;ear.style.fontSize='10.5px';}
    const mm=document.getElementById('ai-status-badge-modal');if(mm&&badge){mm.textContent=badge.textContent;mm.className=badge.className;}
  }).catch(e=>console.error('[ai_status]',e));
}

function getTodayStr(){const n=new Date();return`${n.getFullYear()}-${String(n.getMonth()+1).padStart(2,'0')}-${String(n.getDate()).padStart(2,'0')}`;}

/* POLLING */
function initPolling(){
  const today=getTodayStr(); selectedDate=today;
  fetchDashboard(today);fetchAlerts();fetchHealth();fetchAiStatus();
  setInterval(()=>{if(selectedDate===getTodayStr()) fetchDashboard(selectedDate);},3000);
  setInterval(fetchAlerts,5000);
  setInterval(fetchHealth,10000);
  setInterval(fetchAiStatus,1500);
}
document.addEventListener('DOMContentLoaded',initPolling);
</script>
</body>
</html>
""")

OUT.write_text(''.join(PARTS), encoding='utf-8')
print(f"Written {OUT.stat().st_size} bytes, {len(OUT.read_text(encoding='utf-8').splitlines())} lines")
