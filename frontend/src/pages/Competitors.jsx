import { useState } from 'react'
import { api, money, qs } from '../api'

export default function Competitors() {
  const [f, setF] = useState({ naics: '', set_aside: '', keyword: '', agency: '', years: 3 })
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  const go = async () => {
    setBusy(true); setErr('')
    try { setData(await api.get('/api/competitors?' + qs(f))) } catch (e) { setErr(e.message) }
    setBusy(false)
  }

  return (
    <>
      <h1>Competitor intel</h1>
      <p className="sub">Past federal contract awards from USAspending.gov. See who wins in your NAICS codes, at which agencies, and at what size.</p>
      <div className="panel">
        <div className="grid g4">
          <label className="f">NAICS (blank uses your profile)<input value={f.naics} onChange={set('naics')} placeholder="541519" /></label>
          <label className="f">Set-aside type
            <select value={f.set_aside} onChange={set('set_aside')}>
              <option value="">Any</option>
              <option value="SDVOSBC,SDVOSBS">SDVOSB</option>
              <option value="VSA,VSS">VA VOSB</option>
              <option value="SBA,SBP">Small business</option>
              <option value="NONE">Unrestricted</option>
            </select>
          </label>
          <label className="f">Keyword<input value={f.keyword} onChange={set('keyword')} placeholder="help desk" /></label>
          <label className="f">Awarding agency (exact name)<input value={f.agency} onChange={set('agency')} placeholder="Department of Veterans Affairs" /></label>
          <label className="f">Years back
            <select value={f.years} onChange={set('years')}>{[1, 2, 3, 5].map((y) => <option key={y}>{y}</option>)}</select>
          </label>
          <div style={{ alignSelf: 'flex-end' }}><button className="primary" onClick={go} disabled={busy}>{busy ? 'Searching…' : 'Search awards'}</button></div>
        </div>
        <p className="small muted" style={{ marginTop: 10 }}>Shows the largest 200 matching awards. Set-aside codes in award data follow the same SAM codes used elsewhere in the app.</p>
      </div>
      {err && <div className="err">{err}</div>}
      {data && (
        <div className="grid g2">
          <div className="panel">
            <h2>Top recipients ({money(data.total_value)} across {data.awards.length} awards)</h2>
            <table>
              <thead><tr><th>Company</th><th>Awards</th><th>Total</th></tr></thead>
              <tbody>
                {data.top_competitors.map((c) => (
                  <tr key={c.uei || c.recipient}>
                    <td><div className="t">{c.recipient}</div><div className="small muted">{c.agencies.slice(0, 3).join(', ')}</div></td>
                    <td className="mono">{c.count}</td>
                    <td className="mono">{money(c.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="panel" style={{ maxHeight: 700, overflow: 'auto' }}>
            <h2>Awards</h2>
            <table>
              <tbody>
                {data.awards.map((a) => (
                  <tr key={a.award_id + a.recipient}>
                    <td>
                      <div className="t">{a.recipient}</div>
                      <div className="small">{a.description?.slice(0, 140)}</div>
                      <div className="small muted">{a.sub_agency || a.agency} · {a.start_date} · NAICS {a.naics}</div>
                    </td>
                    <td className="mono">{a.url ? <a href={a.url} target="_blank" rel="noreferrer">{money(a.amount)}</a> : money(a.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  )
}
