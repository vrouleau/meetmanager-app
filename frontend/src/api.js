const API = '/api'

const api = {
  async get(path) {
    const res = await fetch(`${API}${path}`)
    if (!res.ok) throw new Error(`${res.status}`)
    return { data: await res.json() }
  },
  async post(path, body) {
    const isFormData = body instanceof FormData
    const res = await fetch(`${API}${path}`, {
      method: 'POST',
      headers: isFormData ? {} : { 'Content-Type': 'application/json' },
      body: isFormData ? body : JSON.stringify(body),
    })
    if (!res.ok) throw new Error(`${res.status}`)
    return { data: await res.json() }
  },
  async delete(path) {
    const res = await fetch(`${API}${path}`, { method: 'DELETE' })
    if (!res.ok) throw new Error(`${res.status}`)
    return { data: await res.json() }
  },
  async put(path, body) {
    const res = await fetch(`${API}${path}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error(`${res.status}`)
    return { data: await res.json() }
  },
}

export default api
