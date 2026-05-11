import { useState, useEffect } from 'react'
import { useLang } from '../i18n'
import api from '../api'

export default function Organizer() {
  const [meetInfo, setMeetInfo] = useState(null)
  const [clubs, setClubs] = useState([])
  const [checked, setChecked] = useState({})
  const [msg, setMsg] = useState('')
  const { t, lang } = useLang()

  useEffect(() => { loadMeetInfo(); loadClubs() }, [])

  async function loadMeetInfo() {
    const r = await api.get('/meet-info')
    setMeetInfo(r.data)
  }

  async function loadClubs() {
    const r = await api.get('/clubs')
    setClubs(r.data)
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

  async function sendInvitation(clubId) {
    try {
      const r = await api.post(`/clubs/${clubId}/send-pin`, { lang })
      setMsg(r.data.message || 'Sent!')
    } catch (e) { setMsg(e.detail || e.message || 'Error') }
  }

  async function sendSelected() {
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
    setMsg(`${sent} ${t.invitations_sent}${errors ? ` (${errors} ${lang === 'fr' ? 'erreur(s)' : 'error(s)'})` : ''}`)
  }



  const checkedCount = Object.values(checked).filter(Boolean).length

  return (
    <div className="p-4 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">{t.organizer}</h1>

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

      {/* Closure date */}
      <div className="mb-4 p-3 bg-yellow-50 rounded text-sm flex items-center gap-3">
        <label className="font-semibold whitespace-nowrap">{t.closure_date_label}:</label>
        <input type="date" className="border p-1 rounded"
          defaultValue={meetInfo?.closure_date || ''}
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
        <p className="text-sm text-gray-600 mb-2">{t.upload_meet_desc}</p>
        <input type="file" accept=".lxf" onChange={uploadMeet} />
      </div>

      {/* Team invite management */}
      <div className="border p-4 rounded mb-4">
        <h2 className="font-semibold mb-2">{t.team_invites}</h2>

        <div className="flex gap-2 mb-3">
          <button onClick={sendSelected} disabled={!checkedCount}
            className="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 disabled:opacity-50">
            {t.send_invitation} {checkedCount > 0 && `(${checkedCount})`}
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
            </tr></thead>
            <tbody>
              {clubs.map(c => (
                <tr key={c.id} className="border-b hover:bg-gray-50">
                  <td className="p-2"><input type="checkbox" checked={!!checked[c.id]}
                    onChange={e => setChecked(prev => ({...prev, [c.id]: e.target.checked}))} /></td>
                  <td className="p-2">{c.name}</td>
                  <td className="p-2 text-gray-600">{c.admin_email || <span className="text-red-400">{lang === 'fr' ? 'aucun' : 'none'}</span>}</td>
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
