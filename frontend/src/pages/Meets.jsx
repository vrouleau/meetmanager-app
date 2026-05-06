import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { fetchJson } from '../api'

export default function Meets() {
  const [meets, setMeets] = useState([])
  const [form, setForm] = useState({ name: '', city: '', date_start: '', age_date: '' })
  const [mdbFile, setMdbFile] = useState(null)
  const [creating, setCreating] = useState(false)

  useEffect(() => { load() }, [])
  const load = () => fetchJson('/meets').then(setMeets)

  const submit = async (e) => {
    e.preventDefault()
    if (!mdbFile) return alert("Sélectionnez un fichier .mdb")
    setCreating(true)
    const fd = new FormData()
    fd.append('name', form.name)
    fd.append('city', form.city)
    fd.append('date_start', form.date_start)
    fd.append('age_date', form.age_date)
    fd.append('mdb', mdbFile)
    const res = await fetch('/api/meets', { method: 'POST', body: fd })
    const data = await res.json()
    setCreating(false)
    if (res.ok) {
      alert(`Compétition créée: ${data.events_created} épreuves importées`)
      setForm({ name: '', city: '', date_start: '', age_date: '' })
      setMdbFile(null)
      load()
    } else {
      alert(data.detail || 'Erreur')
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Compétitions</h1>
      <form onSubmit={submit} className="flex flex-wrap gap-2 mb-4 items-end">
        <div><label className="text-sm">Nom</label>
          <input className="border p-2 rounded block" required
            value={form.name} onChange={e => setForm({...form, name: e.target.value})} /></div>
        <div><label className="text-sm">Ville</label>
          <input className="border p-2 rounded block"
            value={form.city} onChange={e => setForm({...form, city: e.target.value})} /></div>
        <div><label className="text-sm">Date début</label>
          <input className="border p-2 rounded block" type="date" required
            value={form.date_start} onChange={e => setForm({...form, date_start: e.target.value})} /></div>
        <div><label className="text-sm">Date âge</label>
          <input className="border p-2 rounded block" type="date" required
            value={form.age_date} onChange={e => setForm({...form, age_date: e.target.value})} /></div>
        <div><label className="text-sm">Template .mdb</label>
          <input className="border p-2 rounded block" type="file" accept=".mdb"
            onChange={e => setMdbFile(e.target.files[0])} /></div>
        <button type="submit" disabled={creating}
          className="bg-blue-600 text-white px-4 py-2 rounded disabled:opacity-50">
          {creating ? 'Création...' : 'Créer'}
        </button>
      </form>
      <table className="w-full border-collapse">
        <thead><tr className="bg-gray-100">
          <th className="border p-2 text-left">Nom</th>
          <th className="border p-2 text-left">Ville</th>
          <th className="border p-2 text-left">Date</th>
          <th className="border p-2 text-left">Actions</th>
        </tr></thead>
        <tbody>
          {meets.map(m => (
            <tr key={m.id}>
              <td className="border p-2"><Link to={`/meets/${m.id}`} className="text-blue-600 hover:underline">{m.name}</Link></td>
              <td className="border p-2">{m.city}</td>
              <td className="border p-2">{m.date_start}</td>
              <td className="border p-2">
                <Link to={`/meets/${m.id}`} className="text-blue-600">Gérer →</Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
