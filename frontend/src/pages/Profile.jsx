import { useEffect, useState } from 'react'
import { api } from '../api'
import { useMeta } from '../App.jsx'

const CERT_ORDER = ['SB', 'SDVOSB', 'VOSB', '8A', 'HUBZONE', 'WOSB', 'EDWOSB']
const list = (s) => s.split(/[,\n]/).map((x) => x.trim()).filter(Boolean)

export default function Profile() {
  const meta = useMeta()
  const [p, setP] = useState(null)
  const [text, setText] = useState({ naics: '', psc: '', keywords: '', nsn: '' })
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  useEffect(() => {
    api.get('/api/profile').then((d) => {
      setP(d)
      setText({ naics: d.naics_codes.join(', '), psc: d.psc_codes.join(', '), keywords: d.keywords.join(', '), nsn: d.nsn_watchlist.join(', ') })
    }).catch((e) => setErr(e.message))
  }, [])

  if (err && !p) return <div className="err">{err}</div>
  if (!p || !meta) return <p className="muted">Loading…</p>

  const set = (k) => (e) => setP({ ...p, [k]: e.target.value })
  const naics = list(text.naics)

  const applyRecommended = async () => {
    setMsg(''); setErr('')
    try {
      const d = await api.post('/api/profile/apply-recommended', {})
      setP(d)
      setText({ naics: d.naics_codes.join(', '), psc: d.psc_codes.join(', '), keywords: d.keywords.join(', '), nsn: d.nsn_watchlist.join(', ') })
      setMsg(`Added the recommended codes. ${d.naics_codes.length} NAICS codes and ${d.nsn_watchlist.length} watchlist entries are on your profile, with ${d.naics_codes[0]} as primary.`)
    } catch (e) { setErr(e.message) }
  }

  const save = async () => {
    setMsg(''); setErr('')
    try {
      const body = {
        ...p,
        naics_codes: naics,
        psc_codes: list(text.psc),
        keywords: list(text.keywords),
        nsn_watchlist: list(text.nsn),
        small_under_naics: Object.fromEntries(naics.map((n) => [n, p.small_under_naics[n] ?? true])),
      }
      setP(await api.put('/api/profile', body))
      setMsg('Profile saved. Eligibility updates everywhere immediately.')
    } catch (e) { setErr(e.message) }
  }

  return (
    <>
      <h1>Company profile</h1>
      <p className="sub">Drives SAM.gov syncing (one query per NAICS code) and the eligibility check on every opportunity.</p>
      {msg && <div className="okmsg">{msg}</div>}
      {err && <div className="err">{err}</div>}

      <div className="panel">
        <h2>Business</h2>
        <div className="grid g4">
          <label className="f">Legal name<input value={p.name} onChange={set('name')} /></label>
          <label className="f">UEI<input value={p.uei} onChange={set('uei')} className="mono" /></label>
          <label className="f">CAGE<input value={p.cage} onChange={set('cage')} className="mono" /></label>
          <label className="f">State<input value={p.state} maxLength={2} onChange={set('state')} /></label>
          <label className="f">SAM.gov registration
            <select value={p.sam_status} onChange={set('sam_status')}>
              <option value="active">Active</option>
              <option value="pending">Submitted, pending</option>
              <option value="expired">Expired</option>
              <option value="not_registered">Not registered</option>
            </select>
          </label>
          <label className="f">SAM expiration<input type="date" value={p.sam_expiration} onChange={set('sam_expiration')} /></label>
        </div>
      </div>

      <div className="panel">
        <h2>Export-controlled drawings (JCP)</h2>
        <p className="small muted">Many DLA and Navy drawings are export controlled. To download them you need an approved Joint Certification Program certification: submit DD Form 2345 through the JCP office. It is free, and approval takes a few weeks, so apply before you need it.</p>
        <div className="grid g3">
          <label className="f">JCP status
            <select value={p.jcp_status || 'none'} onChange={set('jcp_status')}>
              <option value="none">Not applied</option>
              <option value="applied">Applied, pending</option>
              <option value="approved">Approved</option>
              <option value="expired">Expired</option>
            </select>
          </label>
          <label className="f">Certification number<input value={p.jcp_cert_number || ''} onChange={set('jcp_cert_number')} /></label>
          <label className="f">Expiration<input type="date" value={p.jcp_expiration || ''} onChange={set('jcp_expiration')} /></label>
        </div>
      </div>

      <div className="panel">
        <h2>Certifications</h2>
        <p className="small muted">Set SDVOSB to Pending while your VetCert application is in review. SDVOSB set-asides will show as "After certification" until you switch it to Certified.</p>
        <div className="grid g4">
          {CERT_ORDER.map((c) => (
            <label className="f" key={c}>{meta.certifications[c] || c}
              <select value={p.certifications[c] || 'none'} onChange={(e) => setP({ ...p, certifications: { ...p.certifications, [c]: e.target.value } })}>
                <option value="none">{c === 'SB' ? 'No' : 'None'}</option>
                {c !== 'SB' && <option value="pending">Applied, pending</option>}
                <option value="certified">{c === 'SB' ? 'Yes, small' : 'Certified'}</option>
              </select>
            </label>
          ))}
        </div>
      </div>

      <div className="panel">
        <div className="row spread">
          <h2 style={{ margin: 0 }}>Recommended target market</h2>
          <button className="primary" onClick={applyRecommended}>Add all to my profile</button>
        </div>
        <p className="small muted">Custom control panels, instruments, test equipment and training equipment you design, build and test in-house. Adding them keeps anything already on your profile, makes {meta.primary_naics} primary, and fills the DIBBS watchlist with the matching supply classes. Opportunities then open filtered to these codes.</p>
        <div className="grid g2">
          {Object.entries(meta.naics_groups || {}).map(([k, g]) => (
            <div key={k}>
              <h3>{g.label}</h3>
              <table><tbody>
                {g.codes.map((c) => (
                  <tr key={c}>
                    <td className="mono" style={{ width: 70 }}>{c}{c === meta.primary_naics && <div className="small muted">primary</div>}</td>
                    <td className="small">{meta.naics_titles[c]}</td>
                    <td style={{ width: 30 }}>{naics.includes(c) ? <span className="badge b-eligible_now">on</span> : ''}</td>
                  </tr>
                ))}
              </tbody></table>
            </div>
          ))}
        </div>
        <h3>DLA supply classes (DIBBS watchlist)</h3>
        <div className="row" style={{ gap: 6 }}>
          {Object.entries(meta.fsc_titles || {}).map(([c, t]) => (
            <span key={c} className="tag" title={t}>{c} {t}</span>
          ))}
        </div>
      </div>

      <div className="panel">
        <h2>What you sell</h2>
        <div className="grid g2">
          <label className="f">NAICS codes (comma separated)<textarea value={text.naics} onChange={(e) => setText({ ...text, naics: e.target.value })} placeholder="541511, 541519, 423490" /></label>
          <label className="f">PSC codes (optional)<textarea value={text.psc} onChange={(e) => setText({ ...text, psc: e.target.value })} placeholder="DA01, 6910" /></label>
          <label className="f">Keywords (optional)<textarea value={text.keywords} onChange={(e) => setText({ ...text, keywords: e.target.value })} placeholder="training equipment, help desk" /></label>
          <label className="f">DIBBS NSN / FSC watchlist<textarea value={text.nsn} onChange={(e) => setText({ ...text, nsn: e.target.value })} placeholder="6910 (FSC) or 5340-01-396-5472 (NSN)" /></label>
        </div>
        {naics.length > 0 && (
          <>
            <h3>Small under each NAICS size standard?</h3>
            <p className="small muted">Check the SBA size standards table for each code. Uncheck any code where you exceed the standard.</p>
            <div className="row">
              {naics.map((n) => (
                <label key={n} className="check mono">
                  <input type="checkbox" checked={p.small_under_naics[n] ?? true} onChange={(e) => setP({ ...p, small_under_naics: { ...p.small_under_naics, [n]: e.target.checked } })} /> {n}
                </label>
              ))}
            </div>
          </>
        )}
      </div>

      <div className="panel">
        <h2>Notes</h2>
        <textarea value={p.notes} onChange={set('notes')} placeholder="Capabilities, past performance highlights, teaming partners" />
      </div>
      <button className="primary" onClick={save}>Save profile</button>
    </>
  )
}
