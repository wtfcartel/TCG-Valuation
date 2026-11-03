// Server-side sign-in check (Vercel Routing Middleware). Runs before every page and API call except the login page
// and the brand assets it needs. A request needs a valid gt_session cookie, issued by /api/login and signed with
// SESSION_SECRET (HMAC-SHA256). Without SESSION_SECRET set, nothing is served: the site fails closed.

export const config = {
  matcher: ['/((?!login\\.html|api/login|api/logout|brand/|brand\\.css|vendor/pico|favicon).*)'],
};

const enc = new TextEncoder();

async function sign(secret, payload) {
  const key = await crypto.subtle.importKey('raw', enc.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const mac = await crypto.subtle.sign('HMAC', key, enc.encode(payload));
  return [...new Uint8Array(mac)].map(b => b.toString(16).padStart(2, '0')).join('');
}

function same(a, b) {
  if (a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

export async function valid(cookieHeader, secret, now = Date.now()) {
  if (!secret) return false;
  const m = /(?:^|;\s*)gt_session=([^;]+)/.exec(cookieHeader || '');
  if (!m) return false;
  const [user, exp, sig] = decodeURIComponent(m[1]).split('.');
  if (!user || !exp || !sig || Number(exp) * 1000 < now) return false;
  return same(sig, await sign(secret, `${user}.${exp}`));
}

export default async function middleware(request) {
  const secret = process.env.SESSION_SECRET;
  const url = new URL(request.url);
  // demo.logisticsdx.com and greenturf.logisticsdx.com open the consulting-engagement copy (public/c/).
  // The original 90-day version stays at the root of any other address (e.g. tcg-valuation-api.vercel.app).
  const consulting = /^(demo|greenturf)\./.test(url.hostname);
  const home = consulting && (url.pathname === '/' || url.pathname === '/index.html') ? '/c/index.html' : null;
  if (await valid(request.headers.get('cookie'), secret)) {
    return home ? Response.redirect(new URL(home, request.url), 302) : undefined;   // signed in: carry on to the page
  }
  if (url.pathname.startsWith('/api/')) {
    return new Response(JSON.stringify({ error: 'Sign in required' }), { status: 401, headers: { 'Content-Type': 'application/json' } });
  }
  const login = new URL('/login.html', request.url);
  if (!secret) login.searchParams.set('e', 'setup');
  if (home) login.searchParams.set('next', home);
  else if (url.pathname !== '/' && url.pathname !== '/index.html') login.searchParams.set('next', url.pathname + url.search);
  return Response.redirect(login, 302);
}
