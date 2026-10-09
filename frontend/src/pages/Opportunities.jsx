import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, money, qs } from '../api'
import { DaysLeft, EligBadge, useMeta } from '../App.jsx'

// my_naics_only defaults on, so the list opens filtered to your profile's NAICS codes
const DEFAULTS = { q: '', kw: '', source: '', set_aside: '', naics: '', state: '', eligibility: '', notice_type: '', preset: '', my_naics_only: true, hide_expired: true, sort: 'deadline', page: 1 }

export default function Opportunities() {
  const meta = useMeta()
  const nav = useNavigate()
  const [params, setParams] = useSearchParams()
  const f = { ...DEFAULTS, ...Object.fromEntries(params) }
  f.my_naics_only = f.my_naics_only === true || f.my_naics_only === 'true'
  f.hide_expired = !(f.hide_expired === false || f.hide_expired === 'false')
  f.page = Number(f.page) || 1

  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [syncing, setSyncing] = useState(false)
  const [syncMsg, setSyncMsg] = useState('')
  const [days, setDays] = useState(14)
  const [syncOption, setSyncOption] = useState('profile')
  const [saved, setSaved] = useState([])

  const load = () => {
    setErr('')
    api.get('/api/opportunities?' + qs({ ...f, limit: 50 })).then(setData).catch((e) => setErr(e.message))
  }
  useEffect(load, [params.toString()])
  useEffect(() => { api.get('/api/saved-searches').then(setSaved).catch(() => {}) }, [])

  const set = (k, v) => {
    const next = { ...f, [k]: v, page: k === 'page' ? v : 1, preset: k === 'page' || k === 'sort' ? f.preset : '' }
    const clean = Object.fromEntries(Object.entries(next).filter(([key, val]) => val !== DEFAULTS[key] && val !== ''))
    setParams(clean)
  }

  const sync = async () => {
    setSyncing(true); setSyncMsg(''); setErr('')
    try {
      const r = await api.post('/api/sync/sam', { days_back: Number(days), option: syncOption === 'profile' ? null : syncOption })
      setSyncMsg(`SAM.gov: ${r.added} new, ${r.updated} updated, ${r.requests_used} API requests used across ${r.queries} ${r.queries === 1 ? 'query' : 'queries'}.` + (r.errors.length ? ' Errors: ' + r.errors.join('; ') : ''))
      load()
    } catch (e) { setErr(e.message) }
    setSyncing(false)
  }

  const saveSearch = async () => {
    const name = prompt('Name this search')
    if (!name) return
    await api.post('/api/saved-searches', { name, params: Object.fromEntries(params) })
    setSaved(await api.get('/api/saved-searches'))
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / 50)) : 1

  const applyPreset = (p) => setParams({ ...p.params, preset: p.id })
  const syncQueries = (opt) => {
    if (!meta) return 0
    if (opt === 'profile') return Math.max(1, profileNaics)
    const o = (meta.sync_options || []).find((x) => x.id === opt)
    return o ? (o.naics || o.titles || []).length : 0
  }
  const [profileNaics, setProfileNaics] = useState(0)
  useEffect(() => { api.get('/api/profile').then((p) => setProfileNaics(p.naics_codes.length)).catch(() => {}) }, [])

  return (
    <>
      <div className="row spread">
        <div>
          <h1>Opportunities</h1>
          <p className="sub">SAM.gov notices plus anything imported from DIBBS or agency forecasts.</p>
        </div>
        <div className="row">
          <label className="f" style={{ width: 250 }}>Sync
            <select value={syncOption} onChange={(e) => setSyncOption(e.target.value)}>
              {(meta?.sync_options || [{ id: 'profile', label: "My profile's NAICS codes" }]).map((o) => (
                <option key={o.id} value={o.id}>{o.label} ({syncQueries(o.id)} req.)</option>
              ))}
            </select>
          </label>
          <label className="f" style={{ width: 110 }}>Posted in last
            <select value={days} onChange={(e) => setDays(e.target.value)}>
              {[3, 7, 14, 30, 60, 90].map((d) => <option key={d} value={d}>{d} days</option>)}
            </select>
          </label>
          <button className="primary" onClick={sync} disabled={syncing || !meta?.sam_key_configured} style={{ alignSelf: 'flex-end' }}>
            {syncing ? 'Syncing…' : 'Sync SAM.gov'}
          </button>
        </div>
      </div>

      {meta && !meta.sam_key_configured && <div className="notice">Add SAM_API_KEY to backend/.env to enable SAM.gov syncing. You can still import DIBBS and forecast files.</div>}
      {syncMsg && <div className="okmsg">{syncMsg}</div>}
      {err && <div className="err">{err}</div>}

      {meta?.search_presets && (
        <div className="row presets" style={{ marginBottom: 12 }}>
          <span className="small muted">Quick filters:</span>
          {meta.search_presets.map((p) => (
            <button key={p.id} className={`chip ${f.preset === p.id ? 'on' : ''}`} title={p.description} onClick={() => applyPreset(p)}>{p.name}</button>
          ))}
        </div>
      )}
      {f.kw && (
        <div className="small muted" style={{ marginBottom: 8 }}>
          Matching any of: {f.kw.split(',').join(', ')} <button className="link" onClick={() => set('kw', '')}>clear</button>
        </div>
      )}
      {!f.naics && f.my_naics_only && profileNaics === 0 && (
        <div className="notice">Your profile has no NAICS codes yet, so nothing is being filtered. <a href="/profile">Add the recommended codes</a> in one click.</div>
      )}

      <div className="panel">
        <div className="grid g4">
          <label className="f">Search
            <input value={f.q} placeholder="Title, sol #, agency, NSN" onChange={(e) => set('q', e.target.value)} />
          </label>
          <label className="f">Can I bid?
            <select value={f.eligibility} onChange={(e) => set('eligibility', e.target.value)}>
              <option value="">All</option>
              <option value="eligible_now">Can bid now</option>
              <option value="eligible_once_certified">After certification</option>
              <option value="eligible_now,eligible_once_certified">Now or after certification</option>
              <option value="not_eligible">Not eligible</option>
            </select>
          </label>
          <label className="f">Set-aside
            <select value={f.set_aside} onChange={(e) => set('set_aside', e.target.value)}>
              <option value="">Any</option>
              <option value="SDVOSBC,SDVOSBS">SDVOSB (set-aside or sole source)</option>
              <option value="VSA,VSS,SDVOSBC,SDVOSBS">All veteran (SDVOSB + VA VOSB)</option>
              <option value="SBA,SBP">Small business</option>
              <option value="NONE">Unrestricted</option>
              {meta && Object.entries(meta.set_asides).map(([k, v]) => <option key={k} value={k}>{k}: {v}</option>)}
            </select>
          </label>
          <label className="f">Source
            <select value={f.source} onChange={(e) => set('source', e.target.value)}>
              <option value="">All</option>
              <option value="sam">SAM.gov</option>
              <option value="dibbs">DIBBS</option>
              <option value="forecast">Forecasts</option>
              <option value="manual">Manual</option>
            </select>
          </label>
          <label className="f">NAICS
            <input value={f.naics} placeholder="541519, 423490" onChange={(e) => set('naics', e.target.value)} />
          </label>
          <label className="f">Place of performance (state)
            <input value={f.state} maxLength={2} placeholder="NY" onChange={(e) => set('state', e.target.value.toUpperCase())} />
          </label>
          <label className="f">Sort
            <select value={f.sort} onChange={(e) => set('sort', e.target.value)}>
              <option value="deadline">Due soonest</option>
              <option value="posted">Newest posted</option>
              <option value="value">Estimated value</option>
            </select>
          </label>
          <div className="row" style={{ alignSelf: 'flex-end', gap: 14 }}>
            <label className="check"><input type="checkbox" checked={f.my_naics_only} onChange={(e) => set('my_naics_only', e.target.checked)} /> My NAICS only</label>
            <label className="check"><input type="checkbox" checked={f.hide_expired} onChange={(e) => set('hide_expired', e.target.checked)} /> Hide closed</label>
          </div>
        </div>
        <div className="row" style={{ marginTop: 12 }}>
          <button onClick={saveSearch}>Save this search</button>
          {saved.map((s) => (
            <span key={s.id} className="row" style={{ gap: 4 }}>
              <button className="link" onClick={() => setParams(s.params)}>{s.name}</button>
              <button className="link muted" title="Delete" onClick={async () => { await api.del(`/api/saved-searches/${s.id}`); setSaved(saved.filter((x) => x.id !== s.id)) }}>×</button>
            </span>
          ))}
          <button className="link" onClick={() => setParams({})}>Clear filters</button>
        </div>
      </div>

      {data && (
        <div className="row small muted" style={{ marginBottom: 8 }}>
          {data.total} results · {data.counts.eligible_now || 0} can bid now · {data.counts.eligible_once_certified || 0} after certification · {data.counts.not_eligible || 0} not eligible
        </div>
      )}

      <div className="panel" style={{ padding: 0, overflowX: 'auto' }}>
        <table>
          <thead>
            <tr><th>Opportunity</th><th>Set-aside</th><th>Eligibility</th><th>NAICS / NSN</th><th>Type</th><th>Due</th><th>Value</th></tr>
          </thead>
          <tbody>
            {data?.results.map((o) => (
              <tr key={o.id} className="click" onClick={() => nav(`/opportunities/${o.id}`)}>
                <td style={{ maxWidth: 460 }}>
                  <div className="t">{o.title}</div>
                  <div className="small muted">{o.agency}</div>
                  <div className="small mono muted">{o.solicitation_number} · {o.source}{o.pipeline_stage ? ` · in pipeline (${o.pipeline_stage})` : ''}</div>
                  {o.export_controlled && <span className="badge b-eligible_once_certified" title="Export-controlled drawings: JCP certification (DD Form 2345) needed">Export controlled</span>}
                </td>
                <td className="small">{o.set_aside_code ? <span className="tag">{o.set_aside_code}</span> : <span className="muted">none</span>}</td>
                <td><EligBadge status={o.eligibility.status} />{o.eligibility.naics_match === false && <div className="small muted">NAICS outside profile</div>}</td>
                <td className="mono">{o.naics || o.nsn || ''}</td>
                <td className="small">{o.notice_type}</td>
                <td><DaysLeft days={o.days_left} /></td>
                <td className="mono">{money(o.estimated_value)}</td>
              </tr>
            ))}
            {data && data.results.length === 0 && (
              <tr><td colSpan={7} className="muted" style={{ padding: 24 }}>No opportunities match. Run a sync, import a file, or loosen the filters.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {data && totalPages > 1 && (
        <div className="row">
          <button disabled={f.page <= 1} onClick={() => set('page', f.page - 1)}>Previous</button>
          <span className="small muted">Page {f.page} of {totalPages}</span>
          <button disabled={f.page >= totalPages} onClick={() => set('page', f.page + 1)}>Next</button>
        </div>
      )}
    </>
  )
}
