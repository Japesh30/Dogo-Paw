// Thin wrapper around the Flask API.
//
// Development: VITE_API_URL is unset, so BASE is '' and requests go to /api/...
// on the Vite dev server, which proxies them to Flask on :5001.
//
// Production: VITE_API_URL is the Render backend origin, baked in at build time
// by Vite. It is not a secret — it ends up in the JavaScript bundle and is
// visible to anyone, which is fine: it is a public API endpoint, and it is
// configuration rather than a credential.
//
// The trailing slash is stripped because a URL is pasted by hand into Vercel's
// dashboard, and "https://api.example.com/" would otherwise build
// "https://api.example.com//api/dogs". Some hosts 404 on the double slash.
const BASE = (import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '')

const TOKEN_KEY = 'dogopaw.token'

export const getToken = () => localStorage.getItem(TOKEN_KEY)
export const setToken = (t) => localStorage.setItem(TOKEN_KEY, t)
export const clearToken = () => localStorage.removeItem(TOKEN_KEY)

// Two audiences, so two messages. In development the reader is the person who
// forgot to start Flask; in production it is a visitor, for whom a port number
// is noise — and there the usual cause is the free backend instance waking from
// sleep, which resolves itself.
const OFFLINE_MESSAGE = import.meta.env.DEV
  ? 'Could not reach the server. Make sure the Flask backend is running on port 5001, then try again.'
  : 'Could not reach the server. It may be waking up after a period of inactivity — please wait a moment and try again.'

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request(path, { method = 'GET', body, auth = false } = {}) {
  const headers = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (auth) {
    const token = getToken()
    if (token) headers.Authorization = `Bearer ${token}`
  }

  let res
  try {
    res = await fetch(`${BASE}/api${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    // Fetch itself failed — no server, DNS, CORS, offline.
    throw new ApiError(OFFLINE_MESSAGE, 0)
  }

  const isJson = res.headers
    .get('content-type')
    ?.includes('application/json')
  const payload = isJson ? await res.json() : null

  // In dev the Vite proxy sits in front of Flask, so a stopped backend comes
  // back as a 502/503/504 from the proxy rather than a thrown network error.
  // Same cause, so it gets the same plain-English message.
  //
  // Checked *after* parsing, because Flask uses 503 itself to say a model
  // artifact is missing. Those replies carry a JSON `error`, a dead proxy does
  // not — so the body is what tells the two apart. Testing the status alone
  // replaced the real reason with "the server is down", which was wrong and
  // sent you looking in the wrong place.
  const unreachable = res.status === 502 || res.status === 503 || res.status === 504
  if (unreachable && !payload?.error) {
    throw new ApiError(OFFLINE_MESSAGE, res.status)
  }

  if (!res.ok) {
    throw new ApiError(
      payload?.error ?? `Something went wrong (error ${res.status}). Please try again.`,
      res.status,
    )
  }
  return payload
}

export const api = {
  register: (data) => request('/auth/register', { method: 'POST', body: data }),
  login: (data) => request('/auth/login', { method: 'POST', body: data }),
  me: () => request('/auth/me', { auth: true }),
  logout: () => request('/auth/logout', { method: 'POST', auth: true }),
  dogs: () => request('/dogs'),
  dog: (id) => request(`/dogs/${id}`),
  volunteer: (data) => request('/volunteer', { method: 'POST', body: data }),
  chatbot: (message) =>
    request('/chatbot', { method: 'POST', body: { message }, auth: true }),
  recommend: (profile) =>
    request('/recommend', { method: 'POST', body: profile, auth: true }),
  adminStats: () => request('/admin/stats', { auth: true }),
  adopterSegments: () => request('/admin/adopter-segments', { auth: true }),
}
