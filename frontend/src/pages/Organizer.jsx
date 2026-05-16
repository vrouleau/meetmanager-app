import { useState, useEffect } from 'react'
import { useLang } from '../i18n'
import api from '../api'

export default function Organizer() {
  const [meetInfo, setMeetInfo] = useState(null)
  const [clubs, setClubs] = useState([])
  const [checked, setChecked] = useState({})
  const [stripeStatus, setStripeStatus] = useState(null)
  const [msg, setMsg] = useState('')
  const { t, lang } = useLang()

  useEffect(() => { loadMeetInfo(); loadClubs(); loadStripeStatus() }, [])

  async function loadMeetInfo() {
    const r = await api.get('/meet-info')
    setMeetInfo(r.data)
  }

  async function loadClubs() {
    const r = await api.get('/clubs')
    const myId = Number(localStorage.getItem('club_id'))
    setClubs(r.data.filter(c => c.id !== myId))
  }

  async function loadStripeStatus() {
    try {
      const r = await api.get('/stripe/status')
      setStripeStatus(r.data)
    } catch { setStripeStatus({ connected: false }) }
  }

  async function connectStripe() {
    try {
      const r = await api.post('/stripe/connect', {})
      window.location.href = r.data.url
    } catch (e) { setMsg(e.response?.data?.detail || e.message || 'Error') }
  }

  async function disconnectStripe() {
    if (!confirm(lang === 'fr' ? 'Déconnecter Stripe ?' : 'Disconnect Stripe?')) return
    try {
      await api.post('/stripe/disconnect', {})
      setStripeStatus({ connected: false })
      setMsg(lang === 'fr' ? 'Stripe déconnecté' : 'Stripe disconnected')
    } catch (e) { setMsg(e.message || 'Error') }
  }

  function exportLxf() {
    window.open('/api/export', '_blank')
  }

  async function uploadMeet(e) {
    const file = e.target.files[0]
    if (!file) return
    if (meetInfo?.filename && !confirm(t.confirm_replace_meet)) {
      e.target.value = ''
      return
    }
    const fd = new FormData()
    fd.append('file', file)
    setMsg(lang === 'fr' ? 'Téléversement...' : 'Uploading...')
    const r = await api.post('/upload/meet', fd)
    setMsg(`${r.data.events_loaded} ${t.events}`)
    e.target.value = ''
    loadMeetInfo(); loadClubs()
  }

  async function sendSelectedInvites() {
    const ids = Object.entries(checked).filter(([,v]) => v).map(([k]) => k)
    if (!ids.length) return
    setMsg(lang === 'fr' ? 'Envoi en cours...' : 'Sending...')
    let sent = 0, errors = 0
    for (const id of ids) {
      try {
        await api.post(`/clubs/${id}/send-pin`, { lang })
        sent++
      } catch { errors++ }
    }
    setChecked({})
    loadClubs()
    setMsg(`${sent} ${t.invitations_sent}${errors ? ` (${errors} ${lang === 'fr' ? 'erreur(s)' : 'error(s)'})` : ''}`)
  }

  async function sendSelectedStripeInvoices() {
    const ids = Object.entries(checked).filter(([,v]) => v).map(([k]) => k)
    if (!ids.length) return
    const count = ids.length
    const message = lang === 'fr'
      ? `Envoyer les factures Stripe à ${count} club(s) ?`
      : `Send Stripe invoices to ${count} club(s)?`
    if (!confirm(message)) return
    setMsg(lang === 'fr' ? 'Envoi des factures...' : 'Sending invoices...')
    let sent = 0, errors = 0
    for (const id of ids) {
      try {
        await api.post(`/clubs/${id}/invoice`, {})
        sent++
      } catch { errors++ }
    }
    setChecked({})
    loadClubs()
    setMsg(`${sent} ${t.stripe_invoices_sent}${errors ? ` (${errors} ${lang === 'fr' ? 'erreur(s)' : 'error(s)'})` : ''}`)
  }

  async function downloadSelectedPdfZip() {
    const ids = Object.entries(checked).filter(([,v]) => v).map(([k]) => Number(k))
    if (!ids.length) return
    setMsg(lang === 'fr' ? 'Génération des PDF...' : 'Generating PDFs...')
    try {
      const res = await fetch('/api/invoices/pdf-zip', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Club-Pin': localStorage.getItem('pin') || '' },
        body: JSON.stringify({ club_ids: ids })
      })
      if (!res.ok) throw new Error(`${res.status}`)
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = 'invoices.zip'; a.click()
      URL.revokeObjectURL(url)
      setMsg('')
    } catch (e) { setMsg(e.message || 'Error') }
  }

  const checkedCount = Object.values(checked).filter(Boolean).length
  const closurePassed = meetInfo?.closure_date && new Date() > new Date(meetInfo.closure_date + 'T23:59:59')

  // Mode: invite (before closure), stripe (after + connected), pdf (after + not connected)
  const mode = !closurePassed ? 'invite' : stripeStatus?.connected ? 'stripe' : 'pdf'

  function handleMainAction() {
    if (mode === 'invite') sendSelectedInvites()
    else if (mode === 'stripe') sendSelectedStripeInvoices()
    else downloadSelectedPdfZip()
  }

  const buttonLabel = mode === 'invite' ? t.send_invitation
    : mode === 'stripe' ? t.send_stripe_invoice_btn
    : t.download_invoices_btn
  const buttonColor = mode === 'invite' ? 'bg-green-600 hover:bg-green-600/85'
    : mode === 'stripe' ? 'bg-blue-600 hover:bg-blue-600/85'
    : 'bg-gray-600 hover:bg-gray-600/85'

  function statusText(c) {
    const parts = []
    if (c.registered_athlete_count) parts.push(`${c.registered_athlete_count} ${t.athletes_short}`)
    if (c.total_fees_cents) parts.push(formatMoney(c.total_fees_cents, meetInfo?.currency || 'CAD', lang))
    if (mode === 'invite' && c.invite_send_count) parts.push(`${c.invite_send_count}× ${t.invited_short}`)
    if (mode === 'stripe' && c.stripe_send_count) parts.push(`${c.stripe_send_count}× ${t.sent_short}`)
    return parts.join(' · ') || '—'
  }

  return (
    <div className="p-4 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold mb-4 text-balance">{t.organizer}</h1>

      {/* Meet info */}
      {meetInfo && (
        <div className="mb-4 p-3 bg-blue-50 rounded text-sm">
          <strong>{t.meet}:</strong>{' '}
          {meetInfo.filename
            ? <>
                <strong>{meetInfo.meet_name || meetInfo.filename}</strong>
                {' '}— {({'LCM':'50m','SCM':'25m'})[meetInfo.course] || meetInfo.course || '?'} — {meetInfo.masters ? 'Masters' : 'No Masters'}
                {' '}— {meetInfo.events} {t.events}
                <br/><span className="text-gray-500">({meetInfo.filename}, {t.uploaded} {new Date(meetInfo.uploaded_at + 'Z').toLocaleString()})</span>
              </>
            : <span className="text-red-600">{t.no_meet}</span>}
        </div>
      )}

      <FeeSummary meetInfo={meetInfo} t={t} lang={lang} />

      {/* Stripe Connect */}
      <div className="mb-4 p-3 bg-purple-50 rounded text-sm flex items-center gap-3">
        <span className="font-semibold">{t.stripe_connect}:</span>
        {stripeStatus?.connected ? (
          <>
            <span className="text-green-700 font-medium">✓ {t.stripe_connected}</span>
            <button onClick={disconnectStripe}
              className="bg-red-500 text-white px-2 py-1 rounded text-xs hover:bg-red-600">
              {t.stripe_disconnect_btn}
            </button>
          </>
        ) : (
          <button onClick={connectStripe}
            className="bg-purple-600 text-white px-3 py-1 rounded hover:bg-purple-600/85 text-sm">
            {t.stripe_connect_btn}
          </button>
        )}
      </div>

      {/* Closure date */}
      <div className="mb-4 p-3 bg-yellow-50 rounded text-sm flex items-center gap-3">
        <label className="font-semibold whitespace-nowrap">{t.closure_date_label}:</label>
        <input type="date" className="border p-1 rounded"
          defaultValue={meetInfo?.closure_date || ''}
          onKeyDown={e => { if (e.key === 'Enter') e.target.blur() }}
          onBlur={async e => {
            await api.put('/closure-date', { closure_date: e.target.value })
            loadMeetInfo()
            setMsg(t.closure_saved)
          }} />
        {meetInfo?.closure_date && <span className="text-gray-600">{new Date(meetInfo.closure_date + 'T00:00:00').toLocaleDateString()}</span>}
      </div>

      {/* Meet upload */}
      <div className="border p-4 rounded mb-4">
        <h2 className="font-semibold mb-2">{t.upload_meet}</h2>
        <p className="text-sm text-gray-600 mb-1 text-pretty">{t.export_meet_smb_desc}</p>
        <button
          onClick={() => {
            fetch('/api/export/meet-smb', { headers: { 'X-Club-Pin': localStorage.getItem('pin') || '' } })
              .then(r => { if (!r.ok) throw new Error(r.status); return r.blob() })
              .then(blob => {
                const url = URL.createObjectURL(blob)
                const a = document.createElement('a')
                a.href = url; a.download = 'meet.smb'; a.click()
                URL.revokeObjectURL(url)
              })
              .catch(e => setMsg(e.message || 'Error'))
          }}
          className="bg-gray-600 text-white px-3 py-1.5 rounded hover:bg-gray-600/85 text-sm mb-3"
        >
          {t.export_meet_smb}
        </button>
        <p className="text-sm text-gray-600 mb-2 text-pretty">{t.upload_meet_desc}</p>
        <input type="file" accept=".lxf" onChange={uploadMeet} className="file:border file:border-gray-300 file:rounded file:px-3 file:py-1.5 file:text-sm file:bg-white file:cursor-pointer" />
      </div>

      {/* Export */}
      <div className="border p-4 rounded mb-4">
        <h2 className="font-semibold mb-2">{t.export}</h2>
        <p className="text-sm text-gray-600 mb-2 text-pretty">{t.export_desc}</p>
        <button onClick={exportLxf}
                className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-600/85">
          {t.download_lxf}
        </button>
      </div>

      {/* Team invite management */}
      <div className="border p-4 rounded mb-4">
        <h2 className="font-semibold mb-2">{t.team_invites}</h2>

        <div className="flex gap-2 mb-3">
          <button onClick={handleMainAction} disabled={!checkedCount}
            className={`text-white px-4 py-2 rounded disabled:opacity-50 ${buttonColor}`}>
            {buttonLabel} {checkedCount > 0 && `(${checkedCount})`}
          </button>
        </div>

        <div className="max-h-64 overflow-y-auto border rounded">
          <table className="w-full text-sm">
            <thead><tr className="border-b bg-gray-50">
              <th className="p-2 w-8">
                <input type="checkbox"
                  checked={clubs.length > 0 && clubs.every(c => checked[c.id])}
                  onChange={e => {
                    const val = e.target.checked
                    setChecked(Object.fromEntries(clubs.map(c => [c.id, val])))
                  }} />
              </th>
              <th className="p-2 text-left">{t.club}</th>
              <th className="p-2 text-left">Email</th>
              <th className="p-2 text-left">{t.status}</th>
            </tr></thead>
            <tbody>
              {clubs.map(c => (
                <tr key={c.id} className="border-b hover:bg-gray-50">
                  <td className="p-2"><input type="checkbox" checked={!!checked[c.id]}
                    onChange={e => setChecked(prev => ({...prev, [c.id]: e.target.checked}))} /></td>
                  <td className="p-2">{c.name}</td>
                  <td className="p-2 text-gray-600">{c.email || <span className="text-red-400">{lang === 'fr' ? 'aucun' : 'none'}</span>}</td>
                  <td className="p-2 text-gray-600 text-xs">{statusText(c)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {msg && <p className="mt-4 text-green-700">{msg}</p>}
    </div>
  )
}

const FEE_TYPE_LABEL = {
  CLUB: 'fee_per_club', ATHLETE: 'fee_per_athlete', RELAY: 'fee_per_relay',
  TEAM: 'fee_per_team', LATEFEE: 'fee_late', LSCMEETFEE: 'fee_lsc',
}

function formatMoney(cents, currency, lang) {
  const amount = (cents || 0) / 100
  try {
    return new Intl.NumberFormat(lang === 'fr' ? 'fr-CA' : 'en-CA', { style: 'currency', currency: currency || 'CAD' }).format(amount)
  } catch { return `${amount.toFixed(2)} ${currency || ''}`.trim() }
}

function FeeSummary({ meetInfo, t, lang }) {
  if (!meetInfo) return null
  const currency = meetInfo.currency || 'CAD'
  const meetFees = meetInfo.meet_fees || {}
  const eventFees = (meetInfo.event_fees || []).filter(e => (e.fee_cents || 0) > 0)
  const meetFeeEntries = Object.entries(meetFees)
  const hasMeet = !!meetInfo.filename

  return (
    <div className="mb-4 border rounded p-3 bg-gray-50">
      <h2 className="font-semibold mb-2">{t.fee_summary} {currency ? <span className="text-xs text-gray-500">({currency})</span> : null}</h2>
      <div className="h-56 overflow-y-auto border bg-white rounded p-2 text-sm font-mono whitespace-pre">
        {!hasMeet ? (
          <span className="text-gray-500">{t.fee_no_meet}</span>
        ) : (
          <>
            <div className="font-sans font-semibold text-gray-700 mb-1">{t.fee_meet_level}</div>
            {meetFeeEntries.length === 0 ? (
              <div className="font-sans text-gray-500 mb-2">{t.fee_none_meet_level}</div>
            ) : (
              <div className="mb-2">
                {meetFeeEntries.map(([type, cents]) => (
                  <div key={type}>{(t[FEE_TYPE_LABEL[type]] || type).padEnd(22, ' ')}{formatMoney(cents, currency, lang)}</div>
                ))}
              </div>
            )}
            <div className="font-sans font-semibold text-gray-700 mb-1">{t.fee_per_event}</div>
            {eventFees.length === 0 ? (
              <div className="font-sans text-gray-500">{t.fee_none_event}</div>
            ) : (
              eventFees.map((e, i) => (
                <div key={i}>{e.event_number != null ? `#${String(e.event_number).padStart(3,' ')}` : '   '}  {(e.style_name||'').slice(0,40).padEnd(40,' ')}{formatMoney(e.fee_cents, currency, lang)}</div>
              ))
            )}
          </>
        )}
      </div>
    </div>
  )
}
