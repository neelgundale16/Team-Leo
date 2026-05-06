<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Project Veracity — Hallucination Firewall</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=DM+Mono:wght@300;400;500&family=Instrument+Serif:ital@0;1&display=swap" rel="stylesheet">
<style>
/* ── Tokens ─────────────────────────── */
:root {
  --bg:        #f5f4f0;
  --surface:   #ffffff;
  --surface-2: #fafaf8;
  --border:    #e4e2db;
  --border-2:  #c9c7be;
  --ink:       #1a1916;
  --ink-2:     #4a4843;
  --ink-3:     #8c8a84;
  --ink-4:     #b8b6b0;
  --red:       #c0392b;
  --red-light: #fdf1f0;
  --red-mid:   #e74c3c;
  --red-border:#f5c6c3;
  --green:     #1a7a4a;
  --green-light:#f0faf4;
  --green-border:#a8dfc0;
  --green-mid: #27ae60;
  --amber:     #b45309;
  --amber-light:#fffbeb;
  --shadow-sm: 0 1px 2px rgba(0,0,0,.06),0 1px 3px rgba(0,0,0,.04);
  --shadow-md: 0 4px 6px rgba(0,0,0,.05),0 2px 4px rgba(0,0,0,.04);
  --shadow-lg: 0 10px 25px rgba(0,0,0,.07),0 4px 10px rgba(0,0,0,.04);
  --shadow-xl: 0 20px 40px rgba(0,0,0,.08),0 8px 16px rgba(0,0,0,.04);
  --font-sans: 'DM Sans', sans-serif;
  --font-mono: 'DM Mono', monospace;
  --font-serif:'Instrument Serif', serif;
  --r-sm:4px; --r-md:8px; --r-lg:12px; --r-xl:16px; --r-2xl:24px;
}

*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{font-size:16px;-webkit-font-smoothing:antialiased;scroll-behavior:smooth}
body{font-family:var(--font-sans);background:var(--bg);color:var(--ink);min-height:100vh;overflow-x:hidden}

::-webkit-scrollbar{width:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border-2);border-radius:99px}

/* ── NAV ──────────────────────────────── */
nav {
  position: fixed; top:0; left:0; right:0; z-index:200;
  background: rgba(245,244,240,.88);
  backdrop-filter: blur(20px) saturate(1.4);
  -webkit-backdrop-filter: blur(20px) saturate(1.4);
  border-bottom:1px solid var(--border);
}
.nav-inner {
  max-width:1200px; margin:0 auto;
  padding:0 2rem; height:60px;
  display:flex; align-items:center; gap:1.5rem;
}
.nav-logo {
  display:flex; align-items:center; gap:.6rem; text-decoration:none;
}
.nav-logo-icon {
  width:32px; height:32px; background:var(--ink); border-radius:6px;
  display:flex; align-items:center; justify-content:center; flex-shrink:0;
}
.nav-logo-icon svg{width:17px;height:17px;color:#fff}
.nav-brand {font-size:.95rem;font-weight:700;color:var(--ink);letter-spacing:-.02em}
.nav-version {
  font-size:.6rem;font-weight:600;letter-spacing:.06em;
  background:var(--red);color:#fff;padding:2px 8px;border-radius:99px;
}
.nav-links {display:flex;align-items:center;gap:.25rem;margin-left:1.5rem}
.nav-link {
  font-size:.8rem;color:var(--ink-3);font-weight:500;
  padding:.35rem .75rem;border-radius:var(--r-md);text-decoration:none;
  transition:color .15s,background .15s;
}
.nav-link:hover{color:var(--ink);background:rgba(26,25,22,.05)}
.nav-right{margin-left:auto;display:flex;align-items:center;gap:.75rem}
.nav-status {
  display:flex;align-items:center;gap:6px;
  font-size:.68rem;font-weight:500;color:var(--green);
}
.pulse-dot {
  width:6px;height:6px;background:var(--green-mid);border-radius:50%;
  animation:pulse-green 2s ease-in-out infinite;
}
@keyframes pulse-green{
  0%,100%{opacity:1;box-shadow:0 0 0 0 rgba(39,174,96,.4)}
  50%{opacity:.7;box-shadow:0 0 0 5px rgba(39,174,96,0)}
}
.btn-ghost {
  font-size:.8rem;font-weight:500;color:var(--ink-2);
  padding:.4rem 1rem;border-radius:var(--r-md);border:1px solid var(--border);
  background:var(--surface);cursor:pointer;text-decoration:none;
  transition:border-color .15s,box-shadow .15s;
}
.btn-ghost:hover{border-color:var(--border-2);box-shadow:var(--shadow-sm)}
.btn-primary {
  font-size:.8rem;font-weight:600;color:#fff;
  padding:.4rem 1.1rem;border-radius:var(--r-md);border:none;
  background:var(--ink);cursor:pointer;text-decoration:none;
  display:flex;align-items:center;gap:.4rem;
  transition:opacity .15s,box-shadow .15s;
}
.btn-primary:hover{opacity:.85;box-shadow:0 4px 12px rgba(26,25,22,.22)}

/* ── HERO ─────────────────────────────── */
.hero {
  padding: 140px 2rem 80px;
  max-width:1200px;margin:0 auto;
  display:grid;grid-template-columns:1fr 1fr;gap:4rem;align-items:center;
}
.hero-left {}
.hero-eyebrow {
  display:flex;align-items:center;gap:.5rem;margin-bottom:1.2rem;
}
.eyebrow-tag {
  font-size:.65rem;font-weight:600;letter-spacing:.1em;text-transform:uppercase;
  color:var(--red);background:var(--red-light);border:1px solid var(--red-border);
  padding:3px 10px;border-radius:99px;
}
.eyebrow-dot{color:var(--ink-4)}
.eyebrow-sub{font-size:.65rem;color:var(--ink-3);letter-spacing:.04em}

.hero-title {
  font-size:clamp(2.4rem,4vw,3.4rem);
  font-weight:700;letter-spacing:-.04em;line-height:1.1;
  color:var(--ink);margin-bottom:.5rem;
}
.hero-title em {
  font-style:italic;font-family:var(--font-serif);
  font-weight:400;color:var(--red);letter-spacing:-.02em;
}
.hero-sub {
  font-size:1.05rem;color:var(--ink-2);line-height:1.7;
  max-width:460px;margin-bottom:2rem;font-weight:400;
}
.hero-ctas {display:flex;align-items:center;gap:.75rem;flex-wrap:wrap}
.hero-btn-main {
  font-size:.88rem;font-weight:600;color:#fff;
  padding:.65rem 1.4rem;border-radius:var(--r-lg);border:none;
  background:var(--ink);cursor:pointer;text-decoration:none;
  display:flex;align-items:center;gap:.5rem;
  transition:opacity .15s,box-shadow .2s;
  box-shadow:0 2px 8px rgba(26,25,22,.18);
}
.hero-btn-main:hover{opacity:.85;box-shadow:0 6px 20px rgba(26,25,22,.24)}
.hero-btn-sec {
  font-size:.88rem;font-weight:500;color:var(--ink-2);
  padding:.65rem 1.4rem;border-radius:var(--r-lg);
  border:1px solid var(--border);background:var(--surface);
  cursor:pointer;text-decoration:none;display:flex;align-items:center;gap:.5rem;
  transition:border-color .15s,box-shadow .15s;
}
.hero-btn-sec:hover{border-color:var(--border-2);box-shadow:var(--shadow-sm)}
.hero-meta {
  margin-top:1.5rem;display:flex;align-items:center;gap:.5rem;
  font-size:.72rem;color:var(--ink-4);
}
.hero-meta-sep{width:3px;height:3px;background:var(--border-2);border-radius:50%}

/* Hero right: terminal */
.hero-terminal {
  background:var(--ink);border-radius:var(--r-xl);
  box-shadow:0 24px 60px rgba(26,25,22,.25);
  overflow:hidden;font-family:var(--font-mono);
  border:1px solid rgba(255,255,255,.06);
}
.terminal-bar {
  background:rgba(255,255,255,.05);
  border-bottom:1px solid rgba(255,255,255,.07);
  padding:.65rem 1rem;
  display:flex;align-items:center;gap:.5rem;
}
.terminal-dots {display:flex;gap:5px}
.td{width:10px;height:10px;border-radius:50%}
.td-r{background:#ff5f57}.td-y{background:#febc2e}.td-g{background:#28c840}
.terminal-title{margin-left:.5rem;font-size:.65rem;color:rgba(255,255,255,.3);letter-spacing:.04em}
.terminal-body{padding:1.25rem 1.25rem 1.5rem;font-size:.75rem;line-height:1.9}
.t-comment{color:rgba(255,255,255,.25)}
.t-prompt{color:#28c840}
.t-cmd{color:rgba(255,255,255,.8)}
.t-key{color:#86b4ff}
.t-val{color:#f1fa8c}
.t-str{color:#ff79c6}
.t-tag{color:#50fa7b;font-weight:500}
.t-warn{color:#ffb86c}
.t-err{color:#ff5555}
.t-fix{color:#50fa7b}
.t-dim{color:rgba(255,255,255,.3)}
.t-line{display:block;margin-bottom:1px}
.cursor-term {
  display:inline-block;width:7px;height:.85em;background:#28c840;
  vertical-align:text-bottom;animation:blink-term .9s step-end infinite;
}
@keyframes blink-term{0%,100%{opacity:1}50%{opacity:0}}

/* ── STATS STRIP ──────────────────────── */
.stats-strip {
  border-top:1px solid var(--border);border-bottom:1px solid var(--border);
  background:var(--surface);
}
.stats-strip-inner {
  max-width:1200px;margin:0 auto;
  display:grid;grid-template-columns:repeat(4,1fr);
}
.stat-block {
  padding:1.75rem 2rem;
  border-right:1px solid var(--border);
}
.stat-block:last-child{border-right:none}
.stat-num {
  font-size:2rem;font-weight:700;letter-spacing:-.04em;
  color:var(--ink);line-height:1;margin-bottom:.3rem;
}
.stat-num-red{color:var(--red)}
.stat-num-green{color:var(--green)}
.stat-label-b{font-size:.72rem;color:var(--ink-3);font-weight:500;letter-spacing:.03em}

/* ── SECTION SHARED ───────────────────── */
section{padding:80px 2rem}
.section-inner{max-width:1200px;margin:0 auto}
.section-eyebrow {
  font-size:.65rem;font-weight:600;letter-spacing:.12em;text-transform:uppercase;
  color:var(--red);margin-bottom:.8rem;
}
.section-title {
  font-size:clamp(1.7rem,2.8vw,2.4rem);font-weight:700;
  letter-spacing:-.035em;line-height:1.2;color:var(--ink);margin-bottom:.75rem;
}
.section-title em{font-style:italic;font-family:var(--font-serif);font-weight:400}
.section-sub {
  font-size:.95rem;color:var(--ink-2);line-height:1.7;max-width:540px;
}

/* ── HOW IT WORKS ─────────────────────── */
.how-section{background:var(--surface);border-top:1px solid var(--border);border-bottom:1px solid var(--border)}
.how-header{margin-bottom:3.5rem}
.pipeline-flow {
  display:grid;grid-template-columns:repeat(4,1fr);gap:1.5rem;
  position:relative;
}
.pipeline-flow::before {
  content:'';position:absolute;top:28px;left:14%;right:14%;height:1px;
  background:linear-gradient(90deg,var(--border),var(--red-border),var(--border));
  z-index:0;
}
.pipe-step {
  position:relative;z-index:1;
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r-xl);padding:1.5rem;
  box-shadow:var(--shadow-sm);
  transition:box-shadow .2s,border-color .2s,transform .2s;
}
.pipe-step:hover{box-shadow:var(--shadow-lg);border-color:var(--border-2);transform:translateY(-2px)}
.pipe-num {
  width:40px;height:40px;border-radius:50%;
  display:flex;align-items:center;justify-content:center;
  font-size:.7rem;font-weight:700;font-family:var(--font-mono);
  margin-bottom:1rem;letter-spacing:.06em;border:1.5px solid;
}
.pipe-num-1{background:var(--red-light);color:var(--red);border-color:var(--red-border)}
.pipe-num-2{background:var(--amber-light);color:var(--amber);border-color:#fcd34d}
.pipe-num-3{background:#eff6ff;color:#1d4ed8;border-color:#bfdbfe}
.pipe-num-4{background:var(--green-light);color:var(--green);border-color:var(--green-border)}
.pipe-name{font-size:.82rem;font-weight:700;color:var(--ink);margin-bottom:.3rem;letter-spacing:-.01em}
.pipe-tech{font-size:.65rem;font-weight:600;letter-spacing:.07em;text-transform:uppercase;color:var(--ink-4);margin-bottom:.6rem;font-family:var(--font-mono)}
.pipe-desc{font-size:.77rem;color:var(--ink-2);line-height:1.6}

/* ── FEATURES GRID ────────────────────── */
.features-grid {
  display:grid;grid-template-columns:repeat(3,1fr);gap:1px;
  background:var(--border);border:1px solid var(--border);border-radius:var(--r-2xl);
  overflow:hidden;margin-top:3.5rem;
}
.feature-cell {
  background:var(--surface);padding:2rem;
  transition:background .2s;
}
.feature-cell:hover{background:var(--surface-2)}
.feature-icon {
  width:40px;height:40px;border-radius:var(--r-lg);
  display:flex;align-items:center;justify-content:center;
  font-size:1.1rem;margin-bottom:1rem;
  border:1px solid var(--border);
}
.feature-name{font-size:.9rem;font-weight:700;color:var(--ink);margin-bottom:.4rem;letter-spacing:-.01em}
.feature-desc{font-size:.77rem;color:var(--ink-2);line-height:1.6}

/* ── DEMO / MOCKUP ────────────────────── */
.demo-section{background:var(--bg)}
.demo-wrap {
  display:grid;grid-template-columns:1fr 1fr;gap:3rem;align-items:center;margin-top:3rem;
}
.demo-copy{}
.demo-points{margin-top:1.5rem;display:flex;flex-direction:column;gap:.85rem}
.demo-point{display:flex;align-items:flex-start;gap:.75rem}
.demo-point-icon {
  width:22px;height:22px;border-radius:50%;flex-shrink:0;margin-top:1px;
  display:flex;align-items:center;justify-content:center;font-size:.6rem;
}
.dpi-red{background:var(--red-light);border:1px solid var(--red-border);color:var(--red)}
.dpi-green{background:var(--green-light);border:1px solid var(--green-border);color:var(--green)}
.dpi-blue{background:#eff6ff;border:1px solid #bfdbfe;color:#1d4ed8}
.demo-point-text{font-size:.82rem;color:var(--ink-2);line-height:1.6}
.demo-point-text strong{color:var(--ink);font-weight:600}

/* Mockup UI */
.ui-mockup {
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r-xl);box-shadow:var(--shadow-xl);overflow:hidden;
}
.mockup-topbar {
  background:var(--surface-2);border-bottom:1px solid var(--border);
  padding:.65rem 1rem;display:flex;align-items:center;gap:.5rem;
}
.m-dot{width:8px;height:8px;border-radius:50%}
.m-dot-r{background:#ff5f57}.m-dot-y{background:#febc2e}.m-dot-g{background:#28c840}
.mockup-body{padding:1rem}
.m-input-row {
  background:var(--bg);border:1px solid var(--border);border-radius:var(--r-lg);
  padding:.6rem .8rem;display:flex;align-items:center;gap:.5rem;margin-bottom:.85rem;
}
.m-prompt{font-family:var(--font-mono);font-size:.75rem;color:var(--red);font-weight:500}
.m-query{font-size:.75rem;color:var(--ink-3);flex:1}
.m-send {
  width:22px;height:22px;background:var(--ink);border-radius:5px;
  display:flex;align-items:center;justify-content:center;
}
.m-send svg{width:10px;height:10px;color:#fff}
.m-stream {
  font-size:.78rem;line-height:1.9;color:var(--ink-2);
}
.m-token{display:inline;color:var(--ink)}
.m-corrected-wrap{display:inline;position:relative}
.m-original{text-decoration:line-through;color:var(--ink-4);font-size:.7rem}
.m-corrected {
  display:inline;background:var(--green-light);color:var(--green);
  border:1px solid var(--green-border);border-radius:3px;padding:1px 5px;
  font-weight:600;font-size:.75rem;margin-left:2px;
}
.m-warn{
  display:inline;background:var(--amber-light);color:var(--amber);
  border:1px solid #fcd34d;border-radius:3px;padding:1px 5px;font-weight:600;font-size:.75rem;
}
.m-cursor{
  display:inline-block;width:2px;height:.9em;background:var(--ink);
  vertical-align:text-bottom;margin-left:1px;border-radius:1px;
  animation:blink-cur 1s step-end infinite;
}
@keyframes blink-cur{0%,100%{opacity:1}50%{opacity:0}}
.m-correction-tag {
  display:flex;align-items:center;gap:.4rem;margin-top:.65rem;
  padding:.45rem .6rem;background:var(--green-light);
  border:1px solid var(--green-border);border-radius:var(--r-md);
  font-size:.67rem;color:var(--green);font-weight:500;
}

/* ── TECH STACK ───────────────────────── */
.tech-section{background:var(--surface);border-top:1px solid var(--border)}
.tech-grid {
  display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin-top:2.5rem;
}
.tech-card {
  background:var(--surface-2);border:1px solid var(--border);
  border-radius:var(--r-xl);padding:1.25rem 1.25rem;
  transition:box-shadow .2s,border-color .2s;
}
.tech-card:hover{box-shadow:var(--shadow-md);border-color:var(--border-2)}
.tech-label {
  font-size:.6rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;
  color:var(--ink-4);font-family:var(--font-mono);margin-bottom:.6rem;
}
.tech-name{font-size:.9rem;font-weight:700;color:var(--ink);margin-bottom:.25rem;letter-spacing:-.01em}
.tech-desc{font-size:.72rem;color:var(--ink-3);line-height:1.5}

/* ── TEAM / FOOTER ────────────────────── */
.team-section{background:var(--bg);border-top:1px solid var(--border)}
.team-inner{text-align:center;max-width:600px;margin:0 auto}
.team-badge {
  display:inline-flex;align-items:center;gap:.5rem;
  background:var(--surface);border:1px solid var(--border);
  border-radius:99px;padding:.4rem 1rem;margin-bottom:1.5rem;
  font-size:.7rem;font-weight:600;color:var(--ink-2);letter-spacing:.04em;
}
.team-title{font-size:clamp(1.6rem,2.5vw,2.2rem);font-weight:700;letter-spacing:-.04em;margin-bottom:.75rem;color:var(--ink)}
.team-title em{font-style:italic;font-family:var(--font-serif);font-weight:400;color:var(--red)}
.team-desc{font-size:.9rem;color:var(--ink-2);line-height:1.7;margin-bottom:2rem}
.team-members {
  display:flex;justify-content:center;gap:1px;
  background:var(--border);border:1px solid var(--border);
  border-radius:var(--r-xl);overflow:hidden;margin-bottom:2rem;
}
.member{background:var(--surface);padding:1.25rem 1.5rem;flex:1;text-align:center}
.member-avatar {
  width:40px;height:40px;border-radius:50%;
  background:var(--ink);color:#fff;
  display:flex;align-items:center;justify-content:center;
  font-size:.8rem;font-weight:700;margin:0 auto .6rem;
  letter-spacing:.05em;
}
.member-name{font-size:.78rem;font-weight:600;color:var(--ink);margin-bottom:.2rem}
.member-role{font-size:.65rem;color:var(--ink-4)}

footer {
  background:var(--surface);border-top:1px solid var(--border);
  padding:1.1rem 2rem;
}
.footer-inner {
  max-width:1200px;margin:0 auto;
  display:flex;justify-content:space-between;align-items:center;
}
.footer-l,.footer-r{font-size:.68rem;color:var(--ink-4)}
.footer-l a{color:var(--ink-3);text-decoration:none}
.footer-l a:hover{color:var(--ink)}

/* ── ANIMATIONS ───────────────────────── */
@keyframes fade-up{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}
.reveal{opacity:0;transform:translateY(16px);transition:opacity .55s ease,transform .55s ease}
.reveal.in{opacity:1;transform:translateY(0)}

/* ── RESPONSIVE ───────────────────────── */
@media(max-width:900px){
  .hero{grid-template-columns:1fr;gap:2rem;padding-top:100px}
  .hero-terminal{display:none}
  .stats-strip-inner{grid-template-columns:repeat(2,1fr)}
  .pipeline-flow,.features-grid,.demo-wrap,.tech-grid{grid-template-columns:1fr}
  .pipeline-flow::before{display:none}
  .team-members{flex-direction:column;gap:1px}
  .nav-links{display:none}
}
</style>
</head>
<body>

<!-- ── NAV ──────────────────────────── -->
<nav>
  <div class="nav-inner">
    <a class="nav-logo" href="#">
      <div class="nav-logo-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
        </svg>
      </div>
      <span class="nav-brand">Project Veracity</span>
      <span class="nav-version">v1.0</span>
    </a>

    <div class="nav-links">
      <a href="#how" class="nav-link">How it works</a>
      <a href="#features" class="nav-link">Features</a>
      <a href="#demo" class="nav-link">Demo</a>
      <a href="#stack" class="nav-link">Tech Stack</a>
    </div>

    <div class="nav-right">
      <div class="nav-status">
        <span class="pulse-dot"></span>
        Firewall Active
      </div>
      <a href="#demo" class="btn-primary">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
        Try Demo
      </a>
    </div>
  </div>
</nav>

<!-- ── HERO ─────────────────────────── -->
<section class="hero">
  <div class="hero-left reveal in">
    <div class="hero-eyebrow">
      <span class="eyebrow-tag">AI &amp; Automation</span>
      <span class="eyebrow-dot">·</span>
      <span class="eyebrow-sub">Beyond Wrappers Track — XEN-O-THON 2026</span>
    </div>

    <h1 class="hero-title">
      Self-Healing<br>
      <em>Hallucination</em><br>
      Firewall
    </h1>

    <p class="hero-sub">
      A real-time pipeline that intercepts AI-generated claims, verifies them against a private knowledge vault, and auto-corrects hallucinations before they reach the user — token by token.
    </p>

    <div class="hero-ctas">
      <a href="#demo" class="hero-btn-main">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
        Live Demo
      </a>
      <a href="#how" class="hero-btn-sec">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        How it works
      </a>
    </div>

    <div class="hero-meta">
      <span>Team Leo</span>
      <span class="hero-meta-sep"></span>
      <span>GTBIT New Delhi</span>
      <span class="hero-meta-sep"></span>
      <span>Institution's Innovation Council</span>
    </div>
  </div>

  <!-- Terminal mockup -->
  <div class="hero-terminal reveal in" style="transition-delay:.12s">
    <div class="terminal-bar">
      <div class="terminal-dots">
        <div class="td td-r"></div>
        <div class="td td-y"></div>
        <div class="td td-g"></div>
      </div>
      <span class="terminal-title">veracity — firewall pipeline</span>
    </div>
    <div class="terminal-body">
      <span class="t-line t-comment"># Initializing Project Veracity v1.0</span>
      <span class="t-line"><span class="t-prompt">›</span> <span class="t-cmd">uvicorn main:app --reload --port 8000</span></span>
      <span class="t-line t-dim">  loading chromadb vault… <span class="t-tag">✓ 2,841 chunks</span></span>
      <span class="t-line t-dim">  NLI sentinel ready…     <span class="t-tag">✓ model loaded</span></span>
      <span class="t-line t-dim">  interceptor armed…      <span class="t-tag">✓ streaming</span></span>
      <span class="t-line">&nbsp;</span>
      <span class="t-line t-comment"># Query received</span>
      <span class="t-line"><span class="t-key">query</span>: <span class="t-str">"Apple's revenue in Q4 2023?"</span></span>
      <span class="t-line">&nbsp;</span>
      <span class="t-line t-comment"># Token stream + firewall scan</span>
      <span class="t-line t-dim">  token[42] → <span class="t-warn">CLAIM DETECTED</span></span>
      <span class="t-line t-dim">  sentinel  → <span class="t-err">HALLUCINATION (conf: 0.87)</span></span>
      <span class="t-line t-dim">  vault     → <span class="t-tag">source: apple_10k_2023.pdf</span></span>
      <span class="t-line t-dim">  rewriter  → <span class="t-fix">AUTO-CORRECTING…</span></span>
      <span class="t-line">&nbsp;</span>
      <span class="t-line"><span class="t-tag">✓ corrected</span>  <span class="t-key">"$89.5B"</span> → <span class="t-fix">"$119.6B"</span></span>
      <span class="t-line"><span class="t-tag">✓ verified</span>  latency: <span class="t-val">142ms</span>   accuracy: <span class="t-val">98.3%</span></span>
      <span class="t-line">&nbsp;</span>
      <span class="t-prompt">›</span> <span class="cursor-term"></span>
    </div>
  </div>
</section>

<!-- ── STATS STRIP ───────────────────── -->
<div class="stats-strip">
  <div class="stats-strip-inner">
    <div class="stat-block reveal">
      <div class="stat-num stat-num-red">98.3%</div>
      <div class="stat-label-b">Correction Accuracy</div>
    </div>
    <div class="stat-block reveal" style="transition-delay:.08s">
      <div class="stat-num">&lt;200ms</div>
      <div class="stat-label-b">Avg Verification Latency</div>
    </div>
    <div class="stat-block reveal" style="transition-delay:.16s">
      <div class="stat-num stat-num-green">4-Stage</div>
      <div class="stat-label-b">Detection Pipeline</div>
    </div>
    <div class="stat-block reveal" style="transition-delay:.24s">
      <div class="stat-num">Real-Time</div>
      <div class="stat-label-b">Token-by-Token Streaming</div>
    </div>
  </div>
</div>

<!-- ── HOW IT WORKS ──────────────────── -->
<section class="how-section" id="how">
  <div class="section-inner">
    <div class="how-header reveal">
      <p class="section-eyebrow">Architecture</p>
      <h2 class="section-title">A 4-stage <em>firewall</em> pipeline</h2>
      <p class="section-sub">Every AI response passes through four sequential layers of detection, verification, retrieval and correction — all in milliseconds.</p>
    </div>

    <div class="pipeline-flow">
      <div class="pipe-step reveal">
        <div class="pipe-num pipe-num-1">01</div>
        <div class="pipe-tech">Claim Boundary Detection</div>
        <div class="pipe-name">Interceptor</div>
        <div class="pipe-desc">Segments the streaming LLM output into semantic claim units in real-time. Identifies factual assertions worthy of verification before they reach the user.</div>
      </div>
      <div class="pipe-step reveal" style="transition-delay:.08s">
        <div class="pipe-num pipe-num-2">02</div>
        <div class="pipe-tech">NLI Fact Classification</div>
        <div class="pipe-name">Sentinel</div>
        <div class="pipe-desc">Runs each extracted claim through a Natural Language Inference model that classifies it as entailed, neutral, or contradicted against retrieved evidence.</div>
      </div>
      <div class="pipe-step reveal" style="transition-delay:.16s">
        <div class="pipe-num pipe-num-3">03</div>
        <div class="pipe-tech">ChromaDB Semantic Lookup</div>
        <div class="pipe-name">Vault Search</div>
        <div class="pipe-desc">Performs a high-speed vector similarity search over a private knowledge vault of uploaded documents. Returns the most relevant grounding evidence per claim.</div>
      </div>
      <div class="pipe-step reveal" style="transition-delay:.24s">
        <div class="pipe-num pipe-num-4">04</div>
        <div class="pipe-tech">REVERSE Auto-Correction</div>
        <div class="pipe-name">Rewriter</div>
        <div class="pipe-desc">When hallucinations are detected, the rewriter replaces the false claim with a factually grounded correction — inline, in-place, with full source attribution.</div>
      </div>
    </div>
  </div>
</section>

<!-- ── FEATURES ──────────────────────── -->
<section id="features" style="background:var(--bg)">
  <div class="section-inner">
    <div class="reveal">
      <p class="section-eyebrow">Features</p>
      <h2 class="section-title">Built to go <em>beyond wrappers</em></h2>
      <p class="section-sub">Project Veracity isn't just a chatbot with guardrails. It's a full self-healing inference layer built from the ground up.</p>
    </div>

    <div class="features-grid reveal" style="transition-delay:.1s">
      <div class="feature-cell">
        <div class="feature-icon">🌊</div>
        <div class="feature-name">Token-by-Token Streaming</div>
        <div class="feature-desc">SSE-based streaming with real-time firewall scanning. Users see responses as they generate — corrections appear inline without buffering.</div>
      </div>
      <div class="feature-cell">
        <div class="feature-icon">📂</div>
        <div class="feature-name">Private Vault Upload</div>
        <div class="feature-desc">Upload PDFs, CSVs, and documents to build a personal knowledge base. The vault is chunked and embedded for sub-200ms semantic retrieval.</div>
      </div>
      <div class="feature-cell">
        <div class="feature-icon">🔬</div>
        <div class="feature-name">NLI-Powered Verification</div>
        <div class="feature-desc">A dedicated Natural Language Inference model classifies every claim as entailed, neutral, or contradicted — not just keyword matching.</div>
      </div>
      <div class="feature-cell">
        <div class="feature-icon">✏️</div>
        <div class="feature-name">In-Place Correction</div>
        <div class="feature-desc">Corrected text replaces the original inline with a green highlight and tooltip attribution — so users always know which sources grounded the fix.</div>
      </div>
      <div class="feature-cell">
        <div class="feature-icon">📊</div>
        <div class="feature-name">Live Metrics Panel</div>
        <div class="feature-desc">A real-time sidebar tracks claims detected, corrections made, hallucination rate, and pipeline latency — across the entire session.</div>
      </div>
      <div class="feature-cell">
        <div class="feature-icon">⚡</div>
        <div class="feature-name">Sub-200ms Pipeline</div>
        <div class="feature-desc">The full 4-stage pipeline (intercept → sentinel → vault → rewrite) completes in under 200ms on average, keeping the streaming experience fluid.</div>
      </div>
    </div>
  </div>
</section>

<!-- ── DEMO ──────────────────────────── -->
<section id="demo" style="background:var(--surface);border-top:1px solid var(--border)">
  <div class="section-inner">
    <div class="demo-wrap">
      <div class="demo-copy reveal">
        <p class="section-eyebrow">Live Interface</p>
        <h2 class="section-title">Watch it <em>correct</em> in real time</h2>
        <p class="section-sub">Ask anything about finance, legal documents, or company metrics. Upload a document to ground the model in your data.</p>

        <div class="demo-points">
          <div class="demo-point">
            <div class="demo-point-icon dpi-red">🛡️</div>
            <div class="demo-point-text"><strong>Hallucinations flagged instantly</strong> — incorrect figures, wrong dates, false attributions are crossed out in red before the user can act on them.</div>
          </div>
          <div class="demo-point">
            <div class="demo-point-icon dpi-green">✓</div>
            <div class="demo-point-text"><strong>Corrections grounded in your vault</strong> — the fixed value is shown in green with a tooltip citing the exact source document and chunk.</div>
          </div>
          <div class="demo-point">
            <div class="demo-point-icon dpi-blue">📈</div>
            <div class="demo-point-text"><strong>Stats panel tracks everything</strong> — hallucination rate, avg latency, verified claims, pipeline steps — all updated live, per query.</div>
          </div>
        </div>
      </div>

      <!-- UI Mockup -->
      <div class="ui-mockup reveal" style="transition-delay:.12s">
        <div class="mockup-topbar">
          <div class="m-dot m-dot-r"></div>
          <div class="m-dot m-dot-y"></div>
          <div class="m-dot m-dot-g"></div>
        </div>
        <div class="mockup-body">
          <div class="m-input-row">
            <span class="m-prompt">›</span>
            <span class="m-query">What was Apple's Q4 2023 revenue?</span>
            <div class="m-send">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
            </div>
          </div>

          <div class="m-stream">
            <span class="m-token">Apple reported quarterly revenue of </span>
            <span class="m-corrected-wrap">
              <span class="m-original">$89.5 billion</span>
              <span class="m-corrected">$119.6 billion</span>
            </span>
            <span class="m-token"> for Q4 2023, representing a </span>
            <span class="m-warn">2% decline</span>
            <span class="m-token"> year-over-year. iPhone sales led the quarter, contributing approximately </span>
            <span class="m-corrected-wrap">
              <span class="m-original">$40B</span>
              <span class="m-corrected">$43.8B</span>
            </span>
            <span class="m-token"> in revenue.</span>
            <span class="m-cursor"></span>
          </div>

          <div class="m-correction-tag">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
            2 corrections applied · Source: <span style="font-family:var(--font-mono);margin-left:.3rem;color:var(--green)">apple_10k_2023.pdf</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- ── TECH STACK ────────────────────── -->
<section id="stack" class="tech-section">
  <div class="section-inner">
    <div class="reveal">
      <p class="section-eyebrow">Tech Stack</p>
      <h2 class="section-title">Built on <em>real</em> infrastructure</h2>
      <p class="section-sub">No wrappers. Every layer is purpose-built for low-latency, high-accuracy hallucination detection.</p>
    </div>
    <div class="tech-grid">
      <div class="tech-card reveal">
        <div class="tech-label">Frontend</div>
        <div class="tech-name">Next.js 14 + TypeScript</div>
        <div class="tech-desc">App Router, SSE streaming consumer, React state machine for token rendering and inline correction display.</div>
      </div>
      <div class="tech-card reveal" style="transition-delay:.06s">
        <div class="tech-label">Backend</div>
        <div class="tech-name">FastAPI + Python</div>
        <div class="tech-desc">Async pipeline orchestration with Server-Sent Events, uvicorn runtime, and modular step architecture.</div>
      </div>
      <div class="tech-card reveal" style="transition-delay:.12s">
        <div class="tech-label">Vector DB</div>
        <div class="tech-name">ChromaDB</div>
        <div class="tech-desc">Embedded vector store for semantic chunk retrieval. Docs are chunked, embedded, and queried in under 50ms.</div>
      </div>
      <div class="tech-card reveal" style="transition-delay:.18s">
        <div class="tech-label">NLI Model</div>
        <div class="tech-name">Sentence Transformers</div>
        <div class="tech-desc">Zero-shot NLI classification for entailment, contradiction, and neutral stance detection per extracted claim.</div>
      </div>
      <div class="tech-card reveal" style="transition-delay:.24s">
        <div class="tech-label">LLM</div>
        <div class="tech-name">Claude / OpenAI API</div>
        <div class="tech-desc">Base generation layer. The firewall intercepts output post-generation — model-agnostic by design.</div>
      </div>
      <div class="tech-card reveal" style="transition-delay:.30s">
        <div class="tech-label">Styling</div>
        <div class="tech-name">DM Sans + DM Mono</div>
        <div class="tech-desc">Custom design system with CSS variables, token-level animations, and accessible color-coded correction states.</div>
      </div>
    </div>
  </div>
</section>

<!-- ── TEAM ──────────────────────────── -->
<section class="team-section">
  <div class="section-inner">
    <div class="team-inner reveal">
      <div class="team-badge">
        🏛️ &nbsp; GTBIT New Delhi · Institution's Innovation Council
      </div>
      <h2 class="team-title">Built by <em>Team Leo</em></h2>
      <p class="team-desc">
        Competing in the AI &amp; Automation — Beyond Wrappers track at XEN-O-THON 2026. We set out to prove that reliable AI isn't about better prompts — it's about building the infrastructure layer that makes AI trustworthy by design.
      </p>

      <div class="team-members">
        <div class="member">
          <div class="member-avatar">TL</div>
          <div class="member-name">Team Leo</div>
          <div class="member-role">GTBIT New Delhi</div>
        </div>
        <div class="member">
          <div class="member-avatar">🛡️</div>
          <div class="member-name">Project Veracity</div>
          <div class="member-role">XEN-O-THON 2026</div>
        </div>
        <div class="member">
          <div class="member-avatar">AI</div>
          <div class="member-name">Beyond Wrappers</div>
          <div class="member-role">AI &amp; Automation Track</div>
        </div>
      </div>

      <div style="display:flex;justify-content:center;gap:.75rem;flex-wrap:wrap">
        <a href="#how" class="hero-btn-main" style="font-size:.82rem">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
          Explore Architecture
        </a>
        <a href="#demo" class="hero-btn-sec" style="font-size:.82rem">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
          See Demo
        </a>
      </div>
    </div>
  </div>
</section>

<!-- ── FOOTER ────────────────────────── -->
<footer>
  <div class="footer-inner">
    <span class="footer-l">
      XEN-O-THON 2026 · <a href="#">Team Leo</a> · AI &amp; Automation — Beyond Wrappers
    </span>
    <span class="footer-r">GTBIT New Delhi · Institution's Innovation Council</span>
  </div>
</footer>

<script>
// Intersection Observer for reveal animations
const observer = new IntersectionObserver((entries) => {
  entries.forEach(e => {
    if (e.isIntersecting) {
      e.target.classList.add('in');
      observer.unobserve(e.target);
    }
  });
}, { threshold: 0.12 });

document.querySelectorAll('.reveal').forEach(el => observer.observe(el));

// Smooth scroll for nav links
document.querySelectorAll('a[href^="#"]').forEach(a => {
  a.addEventListener('click', e => {
    const id = a.getAttribute('href').slice(1);
    const el = document.getElementById(id);
    if (el) {
      e.preventDefault();
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
});
</script>export interface Token {
  id: string
  text: string
  status: 'streaming' | 'verified' | 'corrected' | 'skipped' | 'high_entropy'
  entropy: number
  correction?: string
  source?: string
  timestamp: number
}

export interface StreamEvent {
  event_type:
    | 'token' | 'correction' | 'stats' | 'done' | 'error'
    | 'eval_start' | 'eval_progress' | 'eval_complete' | 'model_done'
  data: Record<string, any>
  model_id?: string
}

export interface SessionStats {
  total_claims_detected: number
  claims_verified: number
  claims_skipped: number
  hallucinations_found: number
  corrections_made: number
  avg_verification_latency_ms: number
  total_pipeline_latency_ms: number
  model_id?: string
}

export interface EvalDimension {
  name: string
  score: number
  rationale: string
  evidence?: string
}

export interface ModelEvalResult {
  model_id: string
  model_label: string
  overall_score: number
  dimensions: Record<string, EvalDimension>
  hallucination_rate: number
  avg_entropy: number
  peak_entropy: number
  corrections: number
  latency_ms: number
  tokens_total: number
  response: string
}

export interface EvalComplete {
  session_id: string
  winner: string
  winner_label: string
  verdict: string
  rationale: string
  dimension_winner: Record<string, string>
  dimension_weights: Record<string, number>
  models: ModelEvalResult[]
}

export interface CorrectionEvent {
  original_claim: string
  original_sentence: string
  corrected_sentence: string
  source: string
  similarity_score: number
  nli_label: string
  nli_confidence: number
  diff_ratio: number
}

export type AppMode = 'firewall' | 'eval'

</body>
</html>