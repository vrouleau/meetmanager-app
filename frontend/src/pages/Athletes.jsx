import { useState, useEffect } from 'react'
import { fetchJson } from '../api'

export default function Athletes() {
  const [athletes, setAthletes] = useState([])
  const [clubs, setClubs] = useState([])
  const [form, setForm] = useState({
    first_name: '', last_name: '', gender: 'M', birthdate: '', nran: '', club_id: '', email: ''
  })

  useEffect(() => {
    fetchJson('/athletes').then(setAthletes)
    fetchJson('/clubs').then(setClubs)
  }, [])
  const load = () => fetchJson('/athletes').then(setAthletes)

  const submit = async (e) => {
    e.preventDefault()
    await fetchJson('/athletes', {
      method: 'POST',
      body: JSON.stringify({ ...form, club_id: parseInt(form.club_id) })
    })
    setForm({ first_name: '', last_name: '', gender: 'M', birthdate: '', nran: '', club_id: '', email: '' })
    load()
  }

  const remove = async (id) => {
    await fetchJson(`/athletes/${id}`, { method: 'DELETE' })
    load()
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Athlètes</h1>
      <form onSubmit={submit} className="flex flex-wrap gap-2 mb-4">
        <input className="border p-2 rounded" placeholder="Prénom" required
          value={form.first_name} onChange={e => setForm({...form, first_name: e.target.value})} />
        <input className="border p-2 rounded" placeholder="Nom" required
          value={form.last_name} onChange={e => setForm({...form, last_name: e.target.value})} />
        <select className="border p-2 rounded" value={form.gender}
          onChange={e => setForm({...form, gender: e.target.value})}>
          <option value="M">M</option><option value="F">F</option>
        </select>
        <input className="border p-2 rounded" type="date" required
          value={form.birthdate} onChange={e => setForm({...form, birthdate: e.target.value})} />
        <input className="border p-2 rounded w-24" placeholder="NRAN"
          value={form.nran} onChange={e => setForm({...form, nran: e.target.value})} />
        <select className="border p-2 rounded" required value={form.club_id}
          onChange={e => setForm({...form, club_id: e.target.value})}>
          <option value="">Club...</option>
          {clubs.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded">Ajouter</button>
      </form>
      <table className="w-full border-collapse text-sm">
        <thead><tr className="bg-gray-100">
          <th className="border p-2 text-left">Nom</th>
          <th className="border p-2 text-left">Sexe</th>
          <th className="border p-2 text-left">DDN</th>
          <th className="border p-2 text-left">NRAN</th>
          <th className="border p-2 text-left">Club</th>
          <th className="border p-2 w-10"></th>
        </tr></thead>
        <tbody>
          {athletes.map(a => (
            <tr key={a.id}>
              <td className="border p-2">{a.first_name} {a.last_name}</td>
              <td className="border p-2">{a.gender}</td>
              <td className="border p-2">{a.birthdate}</td>
              <td className="border p-2">{a.nran}</td>
              <td className="border p-2">{clubs.find(c => c.id === a.club_id)?.name}</td>
              <td className="border p-2">
                <button onClick={() => remove(a.id)} className="text-red-600">✕</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
