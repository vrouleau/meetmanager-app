import React, { useState, useEffect } from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import './index.css'
import { LangProvider, useLang } from './i18n'
import Login from './pages/Login'
import Athletes from './pages/Athletes'
import Register from './pages/Register'
import Admin from './pages/Admin'
import Organizer from './pages/Organizer'
import Secret from './pages/Secret'

function AppInner() {
  const [auth, setAuth] = useState(null)
  const [meetName, setMeetName] = useState('')
  const { t, lang, toggle } = useLang()

  useEffect(() => {
    const pin = localStorage.getItem('pin')
    const role = localStorage.getItem('role')
    if (pin && role) {
      setAuth({ role, club_id: localStorage.getItem('club_id'), club_name: localStorage.getItem('club_name') })
    }
    import('./api').then(m => m.default.get('/meet-info').then(r => setMeetName(r.data.meet_name || '')).catch(() => {}))
  }, [])

  function logout() {
    localStorage.removeItem('pin')
    localStorage.removeItem('role')
    localStorage.removeItem('club_id')
    localStorage.removeItem('club_name')
    setAuth(null)
  }

  if (!auth) return (
    <BrowserRouter>
      <Routes>
        <Route path="/secret/:token" element={<Secret />} />
        <Route path="*" element={<Login onLogin={setAuth} />} />
      </Routes>
    </BrowserRouter>
  )

  const canOrganizer = auth.role === 'admin' || auth.role === 'organizer'
  const canAdmin = auth.role === 'admin'

  return (
    <BrowserRouter>
      <nav className="bg-gray-800 text-white p-3 flex gap-4 items-center">
        <Link to="/" className="hover:underline">{t.athletes}</Link>
        {canOrganizer && <Link to="/organizer" className="hover:underline">{t.organizer}</Link>}
        {canAdmin && <Link to="/admin" className="hover:underline">{t.admin}</Link>}
        <div className="flex-1" />
        {meetName && <span className="font-semibold bg-blue-600 px-2 py-1 rounded text-sm">{meetName}</span>}
        <button onClick={toggle} className="text-xs bg-gray-600 px-2 py-1 rounded">
          {lang === 'fr' ? 'EN' : 'FR'}
        </button>
        <span className="text-sm text-gray-300">{auth.club_name}</span>
        <button onClick={logout} className="text-sm text-red-300 hover:underline">{t.logout}</button>
      </nav>
      <Routes>
        <Route path="/" element={<Athletes role={auth.role} clubId={auth.club_id} />} />
        <Route path="/athletes/:id/register" element={<Register />} />
        {canOrganizer && <Route path="/organizer" element={<Organizer />} />}
        {canAdmin && <Route path="/admin" element={<Admin />} />}
        <Route path="/secret/:token" element={<Secret />} />
      </Routes>
    </BrowserRouter>
  )
}

function App() {
  return (
    <LangProvider>
      <AppInner />
    </LangProvider>
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />)
