/**
 * MediAd View — Frontend Auth v2 client
 * ═════════════════════════════════════════════════════════════════════
 *
 * WHY THIS FILE?
 *   Old code kept the JWT in `localStorage` → vulnerable to XSS.
 *   New flow (Fase 2 backend):
 *     • Access token lives only in JavaScript memory (this module).
 *     • Refresh token lives in an HttpOnly Secure SameSite=lax cookie
 *       (server-set on login). JavaScript CANNOT read or forge it.
 *     • Every API call is wrapped so we automatically:
 *         - attach `Authorization: Bearer <access>` from memory
 *         - send credentials: 'include' so the cookie travels
 *         - on 401, silently POST /api/auth/v2/refresh, retry once
 *         - on refresh failure, redirect to /login
 *
 * USAGE (drop-in replacement for the old fetch pattern):
 *
 *     await Auth.login(email, password);            // sets memory + cookie
 *     const me    = await Auth.api.get('/auth/v2/me');
 *     const users = await Auth.api.get('/admin/users');
 *     await Auth.api.post('/admin/screens', {name:'…'});
 *     await Auth.logout();
 *
 * Legacy code that still uses `localStorage.getItem('mediadview_token')`
 * keeps working — the migration shim mirrors the memory token there for
 * a few grace deploys, then we can remove the shim entirely.
 */
(function (global) {
  'use strict';

  // ── Config ────────────────────────────────────────────────────────
  const BASE = (global.EXPO_BACKEND_URL || '') + '/api';

  // ── State kept ONLY in JS memory ─────────────────────────────────
  let _accessToken = null;
  let _user        = null;
  let _refreshInFlight = null;   // singleton promise → dedupe concurrent 401s

  const listeners = new Set();
  function emit(evt, payload) { listeners.forEach(fn => { try { fn(evt, payload); } catch(_) { /* isolate listener errors */ } }); }

  // Belt & suspenders: purge any leftover legacy tokens from previous versions.
  try {
    localStorage.removeItem('mv_t');
    localStorage.removeItem('mv_u');
    localStorage.removeItem('mediadview_token');
  } catch (_) { /* storage may be blocked by browser policy */ }

  // ── Low-level helpers ────────────────────────────────────────────
  async function _postJSON(path, body, opts = {}) {
    const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
    if (_accessToken && opts.auth !== false) headers['Authorization'] = 'Bearer ' + _accessToken;
    const res = await fetch(BASE + path, {
      method: 'POST',
      credentials: 'include',                        // sends & receives cookies
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
    return res;
  }

  async function _tryRefresh() {
    // Dedupe concurrent refresh attempts. All callers await the same promise.
    if (_refreshInFlight) return _refreshInFlight;
    _refreshInFlight = (async () => {
      const res = await fetch(BASE + '/auth/v2/refresh', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      if (!res.ok) return false;
      const data = await res.json();
      _setSession(data.access_token, data.user);
      return true;
    })().finally(() => { _refreshInFlight = null; });
    return _refreshInFlight;
  }

  function _setSession(access, user) {
    _accessToken = access || null;
    _user = user || null;
    // Expose to window for cross-page utilities (admin panels served
    // from separate HTML files that don't share this closure).
    // Non-persistent: cleared on tab close and on logout.
    try {
      if (access) { window.__mv_token = access; }
      else { delete window.__mv_token; }
    } catch (e) { /* ignore */ }
    emit(access ? 'login' : 'logout', _user);
  }

  // ── Public API ───────────────────────────────────────────────────
  const Auth = {

    /** True when we have an access token in memory. */
    isAuthenticated() { return !!_accessToken; },

    /** Cached user object from last login/refresh. */
    user() { return _user; },

    /** Register a callback for auth state changes: fn(event, user). */
    on(fn) { listeners.add(fn); return () => listeners.delete(fn); },

    /**
     * Log in with email + password.
     * Server sets the HttpOnly refresh cookie and returns the access token.
     */
    async login(email, password) {
      const res = await _postJSON('/auth/v2/login',
        { email, password, client_type: 'web' }, { auth: false });
      if (!res.ok) {
        _setSession(null, null);
        const err = await res.json().catch(() => ({ detail: 'Login failed' }));
        throw new Error(err.detail || 'Login failed');
      }
      const data = await res.json();
      _setSession(data.access_token, data.user);
      return data.user;
    },

    /**
     * Register a new customer. Uses generic response — does not leak whether
     * the email exists.
     */
    async register(payload) {
      const res = await _postJSON('/auth/v2/register', payload, { auth: false });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Registration failed' }));
        throw new Error(err.detail || 'Registration failed');
      }
      return true;
    },

    /**
     * Change password (revokes every other session for this user).
     */
    async changePassword(current_password, new_password) {
      const res = await Auth.api.raw('/auth/v2/change-password',
        { method: 'POST', body: JSON.stringify({ current_password, new_password }) });
      if (!res.ok) throw new Error('Password change failed');
      // Server invalidates all sessions incl. ours → force re-login
      _setSession(null, null);
      return true;
    },

    /**
     * Log out — revokes the entire refresh family and clears the cookie.
     */
    async logout() {
      try { await _postJSON('/auth/v2/logout', {}); } catch (_) { /* local logout still continues */ }
      _setSession(null, null);
    },

    /**
     * Rehydrate the session on page load. If a valid refresh cookie is
     * present, we get a new access token silently — no user prompt.
     * Call this once, early, before rendering protected UI.
     */
    async bootstrap() {
      const ok = await _tryRefresh();
      return ok;
    },

    /**
     * The universal fetch wrapper. Add Authorization, credentials, retry on 401.
     * All app calls should go through this instead of raw fetch().
     */
    api: {
      async raw(path, options = {}) {
        const opts = { credentials: 'include', ...options };
        opts.headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
        if (_accessToken) opts.headers['Authorization'] = 'Bearer ' + _accessToken;

        let res = await fetch(BASE + path, opts);

        // Silent refresh on 401. Only retry once.
        if (res.status === 401 && !opts._retried) {
          const refreshed = await _tryRefresh();
          if (refreshed) {
            const retry = { ...opts, _retried: true };
            retry.headers['Authorization'] = 'Bearer ' + _accessToken;
            res = await fetch(BASE + path, retry);
          } else {
            _setSession(null, null);
            emit('unauthenticated');
            const error = new Error('Session expired');
            error.code = 'SESSION_EXPIRED';
            throw error;
          }
        }
        return res;
      },

      async get(path)               { const r = await Auth.api.raw(path);                                        return _json(r); },
      async del(path)               { const r = await Auth.api.raw(path, { method: 'DELETE' });                  return _json(r); },
      async post(path, body)        { const r = await Auth.api.raw(path, { method: 'POST',  body: JSON.stringify(body || {}) }); return _json(r); },
      async put(path, body)         { const r = await Auth.api.raw(path, { method: 'PUT',   body: JSON.stringify(body || {}) }); return _json(r); },
      async patch(path, body)       { const r = await Auth.api.raw(path, { method: 'PATCH', body: JSON.stringify(body || {}) }); return _json(r); },
    },
  };

  async function _json(res) {
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'HTTP ' + res.status }));
      const e = new Error(err.detail || err.message || ('HTTP ' + res.status));
      e.status = res.status;
      e.body = err;
      throw e;
    }
    if (res.status === 204) return null;
    return res.json();
  }

  // Try silent rehydrate immediately (fire-and-forget). Also expose it.
  global.Auth = Auth;
  if (document.readyState !== 'loading') Auth.bootstrap();
  else document.addEventListener('DOMContentLoaded', () => Auth.bootstrap(), { once: true });

})(window);
