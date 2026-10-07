// Tiny wrapper around fetch for the FastAPI backend.

async function request(method, path, body) {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    const detail = data?.detail
    const message = Array.isArray(detail) ? detail.map((d) => d.msg).join('; ') : detail
    const err = new Error(message || `Request failed (${res.status})`)
    err.status = res.status
    throw err
  }
  return data
}

export const api = {
  health: () => request('GET', '/health'),
  getProfile: () => request('GET', '/profile'),
  saveProfile: (p) => request('PUT', '/profile', p),
  targets: () => request('GET', '/targets'),
  weights: (days = 90) => request('GET', `/weights?days=${days}`),
  addWeight: (weight_kg, day) => request('POST', '/weights', { weight_kg, day }),
  deleteWeight: (id) => request('DELETE', `/weights/${id}`),
  food: (day) => request('GET', `/food${day ? `?day=${day}` : ''}`),
  logFood: (text, day) => request('POST', '/food', { text, day }),
  deleteFood: (id) => request('DELETE', `/food/${id}`),
  intake: (days = 30) => request('GET', `/intake?days=${days}`),
  checkins: () => request('GET', '/checkins'),
  runCheckin: (force = false) => request('POST', `/checkins${force ? '?force=true' : ''}`),
  workoutPlan: () => request('GET', '/workout-plan'),
}

// Local date as YYYY-MM-DD (toISOString would use UTC and can be off by a day).
export function todayISO() {
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function shortDate(iso) {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}
