"""Login page: mown-turf background with sports-field markings, the Green Turf logo, and a sign-in form that posts to
/api/login. The page itself is public; everything else is checked on the server by middleware.js."""

from __future__ import annotations

FIELD_SVG = """<svg class="lines" viewBox="0 0 1200 760" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
<g fill="none" stroke="rgba(255,255,255,.55)" stroke-width="4">
<rect x="60" y="60" width="1080" height="640"/><line x1="600" y1="60" x2="600" y2="700"/>
<circle cx="600" cy="380" r="92"/><circle cx="600" cy="380" r="5" fill="rgba(255,255,255,.55)"/>
<rect x="60" y="215" width="165" height="330"/><rect x="60" y="300" width="60" height="160"/>
<rect x="975" y="215" width="165" height="330"/><rect x="1080" y="300" width="60" height="160"/>
<path d="M225 320 A75 75 0 0 1 225 440"/><path d="M975 320 A75 75 0 0 0 975 440"/></g></svg>"""


def page() -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>Sign in | Green Turf 90-Day Plan</title>
<style>
:root{{--g:#1fb43e;--gd:#14813a;--gdd:#0f5f2b;--b:#0194e1;--ink:#17301f;--muted:#566a5c}}
*{{box-sizing:border-box}}html,body{{height:100%}}
body{{margin:0;font:15px/1.5 system-ui,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:var(--ink);background:#2f8a3f;
  display:grid;place-items:center;padding:24px 16px;position:relative;overflow-x:hidden}}
.turf{{position:fixed;inset:0;z-index:0;background:
  radial-gradient(ellipse at 50% 40%,rgba(255,255,255,.10),transparent 60%),
  repeating-linear-gradient(90deg,#2f8f3f 0 90px,#3a9d48 90px 180px)}}
.turf::after{{content:"";position:absolute;inset:0;background:radial-gradient(ellipse at center,transparent 45%,rgba(8,40,18,.55))}}
.lines{{position:fixed;inset:0;width:100%;height:100%;z-index:0}}
.card{{position:relative;z-index:1;width:100%;max-width:400px;background:#fff;border-radius:18px;overflow:hidden;
  box-shadow:0 24px 60px -20px rgba(0,0,0,.55)}}
.card::before{{content:"";display:block;height:6px;background:linear-gradient(90deg,var(--g) 0 45%,var(--b))}}
.inner{{padding:26px 28px 24px}}
.logo{{display:block;height:58px;width:auto;margin:0 auto 6px}}
h1{{font-size:19px;text-align:center;margin:6px 0 2px;color:var(--gdd)}}
.sub{{text-align:center;color:var(--muted);font-size:13px;margin:0 0 18px}}
label{{display:block;font-size:13px;font-weight:600;margin:12px 0 5px}}
input{{width:100%;font:inherit;padding:10px 12px;border:1px solid #cfd8cc;border-radius:10px;background:#fbfdfb}}
input:focus{{outline:none;border-color:var(--g);box-shadow:0 0 0 3px rgba(31,180,62,.2)}}
button{{width:100%;margin-top:18px;font:inherit;font-weight:600;padding:11px;border:0;border-radius:10px;
  background:var(--gd);color:#fff;cursor:pointer}}button:hover{{background:var(--gdd)}}
.msg{{display:none;font-size:13px;border-radius:10px;padding:9px 12px;margin:0 0 6px}}
.msg.err{{background:#fdecea;color:#8f2420}}.msg.ok{{background:#e4f6e8;color:var(--gdd)}}
.secure{{display:flex;gap:8px;align-items:flex-start;font-size:12px;color:var(--muted);margin-top:16px;
  padding-top:14px;border-top:1px solid #e6ece4}}
.secure svg{{flex:none;margin-top:1px}}
.foot{{position:relative;z-index:1;text-align:center;color:rgba(255,255,255,.9);font-size:12px;margin-top:14px}}
</style></head>
<body><div class="turf"></div>{FIELD_SVG}
<main>
<div class="card"><div class="inner">
<img class="logo" src="/brand/greenturf-logo.jpg" alt="Green Turf" width="194" height="58">
<h1>90-Day Plan</h1><p class="sub">Business Operations Director | James Fischer-Myall</p>
<div class="msg err" id="err" role="alert"></div><div class="msg ok" id="ok" role="status"></div>
<form method="post" action="/api/login" autocomplete="on">
<input type="hidden" name="next" id="next" value="/">
<label for="u">Username</label><input id="u" name="username" autocomplete="username" required autofocus>
<label for="p">Password</label><input id="p" name="password" type="password" autocomplete="current-password" required>
<button type="submit">Sign in</button>
</form>
<div class="secure"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#14813a" stroke-width="2"
aria-hidden="true"><rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>
<span>Protected access. Every page and data feed is checked on the server before it loads, and a session lasts 8 hours.</span></div>
</div></div>
<p class="foot">Prepared for Green Turf | Illustrative data only</p>
</main>
<script>
const q = new URLSearchParams(location.search);
const n = q.get('next'); if (n && n.startsWith('/') && !n.startsWith('//')) document.getElementById('next').value = n;
const show = (id, t) => {{ const el = document.getElementById(id); el.textContent = t; el.style.display = 'block'; }};
if (q.get('e') === '1') show('err', "That username and password don't match. Please try again.");
if (q.get('e') === 'setup') show('err', "Sign-in isn't set up yet: the site's username, password and session secret need adding in Vercel.");
if (q.get('out')) show('ok', "You've signed out.");
</script>
</body></html>"""
