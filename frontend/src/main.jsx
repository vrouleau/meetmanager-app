import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import './index.css'
import Athletes from './pages/Athletes'
import Register from './pages/Register'
import Admin from './pages/Admin'

function App() {
  return (
    <BrowserRouter>
      <nav className="bg-gray-800 text-white p-3 flex gap-4">
        <Link to="/" className="hover:underline">Athletes</Link>
        <Link to="/admin" className="hover:underline">Admin / Export</Link>
      </nav>
      <Routes>
        <Route path="/" element={<Athletes />} />
        <Route path="/athletes/:id/register" element={<Register />} />
        <Route path="/admin" element={<Admin />} />
      </Routes>
    </BrowserRouter>
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />)
