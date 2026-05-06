import { useState, useEffect } from 'react'
import { fetchJson } from '../api'

export default function Clubs() {
  const [clubs, setClubs] = useState([])
  const [form, setForm] = useState({ name: '', code: '', city: '', contact_email: '' })

  useEffect(() => { load() }, [])
  const load = () => fetchJson('/clubs').then(setClubs)

  const submit = async (e) => {
    e.preventDefault()
    await fetchJson('/clubs', { method: 'POST', body: JSON.stringify(form) })
    setForm({ name: '', code: '', city: '', contact_email: '' })
    load()
  }

  const remove = async (id) => {
    await fetchJson(`/clubs/${id}`, { method: 'DELETE' })
    load()
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Clubs</h1>
      <form onSubmit={submit} className="flex gap-2 mb-4">
        <input className="border p-2 rounded" placeholder="Nom" required
          value={form.name} onChange={e => setForm({...form, name: e.target.value})} />
        <input className="border p-2 rounded w-20" placeholder="Code"
          value={form.code} onChange={e => setForm({...form, code: e.target.value})} />
        <input className="border p-2 rounded" placeholder="Ville"
          value={form.city} onChange={e => setForm({...form, city: e.target.value})} />
        <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded">Ajouter</button>
      </form>
      <table className="w-full border-collapse">
        <thead><tr className="bg-gray-100">
          <th className="border p-2 text-left">Nom</th>
          <th className="border p-2 text-left">Code</th>
          <th className="border p-2 text-left">Ville</th>
          <th className="border p-2 w-20"></th>
        </tr></thead>
        <tbody>
          {clubs.map(c => (
            <tr key={c.id}>
              <td className="border p-2">{c.name}</td>
              <td className="border p-2">{c.code}</td>
              <td className="border p-2">{c.city}</td>
              <td className="border p-2">
                <button onClick={() => remove(c.id)} className="text-red-600">✕</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
