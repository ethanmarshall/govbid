import { Fragment, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, fmtDue, money } from '../api'

const list = (s) => s.split(/[,\s]+/).map((x) => x.trim()).filter(Boolean)
const pct = (x) => (x == null ? 'n/a' : `${(x * 100).toFixed(1)}%`)
const daysUntil = (s) => {
  if (!s) return null
  const [y, m, d] = s.split('-').map(Number)
  const now = new Date(); now.setHours(0, 0, 0, 0)
  return Math.round((new Date(y, m - 1, d) - now) / 86400000)
}
const asOf = (s) => (s ? new Date(s).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '')

function Bar({ value, max }) {
  const w = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0
  return <div className="mkt-bar" title={money(value)}><i style={{ width: `${w}%` }} /></div>
}

export default function Market() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || 'recompetes'
  const go = (t) => setParams({ tab: t })
  const [defs, setDefs] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => { api.get('/api/market/defaults').then(setDefs).catch((e) => setErr(e.message)) }, [])

  return (
    <>
      <h1>Recompetes and buyers</h1>
      <p className="sub">Incumbent contracts ending soon in your codes, and who buys what you sell. Data from USAspending.gov, cached for 24 hours.</p>
      <div className="tabs">
        <button className={tab === 'recompetes' ? 'on' : ''} onClick={() => go('recompetes')}>Recompetes</button>
        <button className={tab === 'tracked' ? 'on' : ''} onClick={() => go('tracked')}>Tracked</button>
        <button className={tab === 'buyers' ? 'on' : ''} onClick={() => go('buyers')}>Buyers</button>
      </div>
      {err && <div className="err">{err}</div>}
      {!defs && !err && <p className="muted">Loading…</p>}
      {defs && tab === 'recompetes' && <Recompetes defs={defs} />}
      {defs && tab === 'tracked' && <Tracked defs={defs} />}
      {defs && tab === 'buyers' && <Buyers defs={defs} />}
    </>
  )
}

// ------------------------------------------------------------------ recompetes
function Recompetes({ defs }) {
  const [f, setF] = useState({
    naics: defs.naics.join(', '), psc: defs.psc.join(', '), months_from: defs.months_from, months_to: defs.months_to,
    agency: '', min_value: '', set_aside: '',
  })
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [quick, setQuick] = useState('')
  const [details, setDetails] = useState({})
  const [trackFor, setTrackFor] = useState(null)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  const search = async (refresh = false) => {
    setBusy(true); setErr('')
    try {
      setData(await api.post('/api/market/recompetes', {
        naics: list(f.naics), psc: list(f.psc), months_from: Number(f.months_from) || 0, months_to: Number(f.months_to) || 0,
        agency: f.agency, min_value: f.min_value ? Number(f.min_value) : null, set_aside: f.set_aside, refresh,
      }))
    } catch (e) { setErr(e.message) }
    setBusy(false)
  }

  const loadDetail = async (gid) => {
    setDetails((d) => ({ ...d, [gid]: { loading: true } }))
    try {
      const d = await api.get(`/api/market/award/${encodeURIComponent(gid)}`)
      setDetails((x) => ({ ...x, [gid]: d }))
    } catch (e) { setDetails((x) => ({ ...x, [gid]: { error: e.message } })) }
  }

  const markTracked = (gid, id) => setData({ ...data, results: data.results.map((r) => (r.generated_internal_id === gid ? { ...r, tracked_id: id } : r)) })

  const q = quick.toLowerCase()
  const rows = (data?.results || []).filter((r) => !q || [r.agency, r.sub_agency, r.recipient, r.description, details[r.generated_internal_id]?.office]
    .some((v) => (v || '').toLowerCase().includes(q)))

  return (
    <>
      <div className="notice">
        When an incumbent contract ends, the work is often recompeted. The time to meet the buyer is before the solicitation posts:
        contact the contracting office and small business specialist now, and check SAM.gov for a presolicitation, sources sought or RFI on the same requirement.
      </div>
      <div className="panel">
        <div className="grid g4">
          <label className="f">NAICS codes<input value={f.naics} onChange={set('naics')} placeholder="332710, 336413" /></label>
          <label className="f">PSC / FSC codes<input value={f.psc} onChange={set('psc')} placeholder="5340, 3020" /></label>
          <label className="f">Ends from (months out)<input type="number" min="0" value={f.months_from} onChange={set('months_from')} /></label>
          <label className="f">Ends to (months out)<input type="number" min="0" value={f.months_to} onChange={set('months_to')} /></label>
          <label className="f">Awarding agency (exact name)<input value={f.agency} onChange={set('agency')} placeholder="Department of Defense" /></label>
          <label className="f">Minimum obligated value ($)<input type="number" min="0" value={f.min_value} onChange={set('min_value')} placeholder="25000" /></label>
          <label className="f">Set-aside used on the incumbent award
            <select value={f.set_aside} onChange={set('set_aside')}>
              <option value="">Any</option>
              {Object.entries(defs.set_aside_groups).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <div style={{ alignSelf: 'flex-end' }} className="row">
            <button className="primary" onClick={() => search(false)} disabled={busy}>{busy ? 'Searching…' : 'Find recompetes'}</button>
            {data && <button onClick={() => search(true)} disabled={busy}>Refresh</button>}
          </div>
        </div>
        <p className="small muted" style={{ marginTop: 10 }}>
          Prefilled from your profile (FSC codes from your NSN watchlist are included). NAICS and PSC lists are searched separately and merged.
          Only contracts with activity in the last 5 years are checked.
        </p>
      </div>
      {err && <div className="err">{err}</div>}
      {data && (
        <div className="panel">
          <div className="row spread">
            <h2>{rows.length} contracts ending {fmtDue(data.window.start)} to {fmtDue(data.window.end)}</h2>
            <span className="small muted">As of {asOf(data.as_of)}</span>
          </div>
          {data.truncated && (
            <p className="due-soon small">Too many matches to scan fully (stopped at contracts ending {fmtDue(data.scanned_to)}). Some contracts ending earlier in the window may be missing. Add a minimum value, an agency or narrower codes.</p>
          )}
          <label className="f" style={{ maxWidth: 360 }}>Filter these results<input value={quick} onChange={(e) => setQuick(e.target.value)} placeholder="agency, sub-agency, office, incumbent" /></label>
          <table style={{ marginTop: 10 }}>
            <thead><tr><th>Ends</th><th>Contract</th><th>Incumbent</th><th>Buyer</th><th>Obligated</th><th>Competition</th><th></th></tr></thead>
            <tbody>
              {rows.map((r) => {
                const d = details[r.generated_internal_id]
                const days = daysUntil(r.end_date)
                return (
                  <Fragment key={r.generated_internal_id}>
                    <tr>
                      <td className="mono"><div>{r.end_date}</div><div className="small muted">{days != null ? `${days} days` : ''}</div></td>
                      <td>
                        <a href={r.url} target="_blank" rel="noreferrer" className="mono">{r.award_id}</a>
                        <div className="small muted">{r.award_type} · NAICS {r.naics} · PSC {r.psc}</div>
                        <div className="small">{r.description}</div>
                      </td>
                      <td>{r.recipient}<div className="small muted mono">{r.recipient_uei}</div></td>
                      <td>{r.sub_agency || r.agency}<div className="small muted">{d?.office || r.agency}</div></td>
                      <td className="mono">{money(r.amount)}<div className="small muted">since {r.start_date}</div></td>
                      <td className="small">
                        {!d && <button className="link" onClick={() => loadDetail(r.generated_internal_id)}>Load details</button>}
                        {d?.loading && <span className="muted">Loading…</span>}
                        {d?.error && <span className="err">{d.error}</span>}
                        {d && !d.loading && !d.error && (
                          <>
                            <div>{d.set_aside || 'Set-aside not reported'}</div>
                            <div className="muted">{d.extent_competed}{d.offers ? `, ${d.offers} offers` : ''}</div>
                            {d.potential_end_date && d.potential_end_date !== d.end_date && <div className="muted">Potential end with options {d.potential_end_date}</div>}
                            {d.parent_piid && <div className="muted">Order under {d.parent_piid}</div>}
                          </>
                        )}
                      </td>
                      <td>
                        {r.tracked_id ? <span className="tag">Tracked</span>
                          : <button onClick={() => setTrackFor(trackFor === r.generated_internal_id ? null : r.generated_internal_id)}>Track</button>}
                      </td>
                    </tr>
                    {trackFor === r.generated_internal_id && (
                      <tr><td colSpan={7}><TrackForm row={r} detail={d} onDone={(id) => { markTracked(r.generated_internal_id, id); setTrackFor(null) }} /></td></tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
          {!rows.length && <p className="muted">No contracts in this window. Try a wider window or more codes.</p>}
        </div>
      )}
    </>
  )
}

function TrackForm({ row, detail, onDone }) {
  const [notes, setNotes] = useState('')
  const [reminder, setReminder] = useState('')
  const [err, setErr] = useState('')
  const save = async () => {
    setErr('')
    const d = detail && !detail.loading && !detail.error ? detail : {}
    try {
      const t = await api.post('/api/market/tracked', {
        ...row, office: d.office || '', set_aside: d.set_aside || '', extent_competed: d.extent_competed || '', offers: d.offers || '',
        notes, reminder_date: reminder || '',
      })
      onDone(t.id)
    } catch (e) { setErr(e.message) }
  }
  return (
    <div className="grid g3">
      <label className="f">Notes<textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Who to contact, what to watch for" /></label>
      <label className="f">Reminder date<input type="date" value={reminder} onChange={(e) => setReminder(e.target.value)} /></label>
      <div style={{ alignSelf: 'flex-end' }} className="row">
        <button className="primary" onClick={save}>Save to watch list</button>
        {err && <span className="err">{err}</span>}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ tracked
function Tracked({ defs }) {
  const [items, setItems] = useState(null)
  const [err, setErr] = useState('')
  const load = () => api.get('/api/market/tracked').then(setItems).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [])

  if (err && !items) return <div className="err">{err}</div>
  if (!items) return <p className="muted">Loading…</p>
  return (
    <>
      {err && <div className="err">{err}</div>}
      {!items.length && <div className="panel muted">Nothing tracked yet. Use Track on the Recompetes tab.</div>}
      {items.map((t) => <TrackedCard key={t.id} t={t} defs={defs} onChange={load} onError={setErr} />)}
    </>
  )
}

function TrackedCard({ t, defs, onChange, onError }) {
  const [form, setForm] = useState({ status: t.status, notes: t.notes, reminder_date: t.reminder_date })
  const [msg, setMsg] = useState('')
  const [crm, setCrm] = useState(null)
  const [oppQ, setOppQ] = useState('')
  const [opps, setOpps] = useState(null)
  const days = t.days_left
  const dirty = form.status !== t.status || form.notes !== t.notes || form.reminder_date !== t.reminder_date

  const run = async (fn, ok) => {
    setMsg(''); onError('')
    try { await fn(); if (ok) setMsg(ok); onChange() } catch (e) { onError(e.message) }
  }
  const save = () => run(() => api.put(`/api/market/tracked/${t.id}`, form), 'Saved.')
  const detail = () => run(() => api.post(`/api/market/tracked/${t.id}/refresh-detail`), 'Award detail loaded.')
  const remove = () => { if (confirm('Stop tracking this contract?')) run(() => api.del(`/api/market/tracked/${t.id}`)) }
  const link = (id) => run(() => api.put(`/api/market/tracked/${t.id}`, { opportunity_id: id }), id ? 'Opportunity linked.' : 'Unlinked.')
  const findOpps = async () => { try { setOpps(await api.get('/api/market/opportunity-options?q=' + encodeURIComponent(oppQ))) } catch (e) { onError(e.message) } }
  const logCrm = () => run(async () => {
    const r = await api.post(`/api/market/tracked/${t.id}/crm`, crm)
    setCrm(null)
    setMsg(`${r.created ? 'Created' : 'Updated'} ${r.organization} in Contacts and logged the interaction.`)
  })

  return (
    <div className="panel">
      <div className="row spread">
        <div>
          <h2 style={{ marginBottom: 2 }}><a href={t.url} target="_blank" rel="noreferrer" className="mono">{t.award_id || t.generated_internal_id}</a> {t.recipient}</h2>
          <div className="small muted">{[t.agency, t.sub_agency, t.office].filter(Boolean).join(' / ')}</div>
        </div>
        <div className={`mono ${days != null && days <= 180 ? 'due-soon' : ''}`}>
          Ends {t.end_date || 'n/a'}{days != null ? ` (${days} days)` : ''}
        </div>
      </div>
      <p className="small">{t.description}</p>
      <div className="small muted">
        {money(t.amount)} obligated · NAICS {t.naics || 'n/a'} · PSC {t.psc || 'n/a'}
        {t.set_aside && ` · ${t.set_aside}`}{t.extent_competed && ` · ${t.extent_competed}`}{t.offers && ` · ${t.offers} offers`}
      </div>
      <div className="grid g3" style={{ marginTop: 10 }}>
        <label className="f">Status
          <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
            {defs.statuses.map((s) => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
          </select>
        </label>
        <label className="f">Reminder date<input type="date" value={form.reminder_date} onChange={(e) => setForm({ ...form, reminder_date: e.target.value })} /></label>
        <label className="f">Notes<textarea rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></label>
      </div>
      <div className="row" style={{ marginTop: 8, flexWrap: 'wrap' }}>
        <button className="primary" onClick={save} disabled={!dirty}>Save</button>
        <button onClick={detail}>Load award detail</button>
        <button onClick={() => setCrm(crm ? null : { name: t.office || t.sub_agency || t.agency, kind: 'note', summary: '', next_step: '', follow_up_date: '' })}>Add buyer to Contacts</button>
        {t.organization_id && <Link className="small" to="/contacts">Open in Contacts</Link>}
        <button className="link" onClick={remove}>Stop tracking</button>
        {msg && <span className="okmsg">{msg}</span>}
      </div>

      {crm && (
        <div className="grid g3" style={{ marginTop: 10 }}>
          <label className="f">Organization (awarding office)<input value={crm.name} onChange={(e) => setCrm({ ...crm, name: e.target.value })} /></label>
          <label className="f">Interaction type
            <select value={crm.kind} onChange={(e) => setCrm({ ...crm, kind: e.target.value })}>
              {['note', 'email', 'call', 'meeting', 'event', 'portal'].map((k) => <option key={k}>{k}</option>)}
            </select>
          </label>
          <label className="f">Follow-up date<input type="date" value={crm.follow_up_date} onChange={(e) => setCrm({ ...crm, follow_up_date: e.target.value })} /></label>
          <label className="f">Summary (blank logs that you started tracking this contract)<textarea rows={2} value={crm.summary} onChange={(e) => setCrm({ ...crm, summary: e.target.value })} /></label>
          <label className="f">Next step<input value={crm.next_step} onChange={(e) => setCrm({ ...crm, next_step: e.target.value })} placeholder="Email the small business specialist" /></label>
          <div style={{ alignSelf: 'flex-end' }}><button className="primary" onClick={logCrm}>Save to Contacts</button></div>
        </div>
      )}

      <div style={{ marginTop: 10 }}>
        {t.opportunity_id
          ? <span className="small">Linked to <Link to={`/opportunities/${t.opportunity_id}`}>opportunity #{t.opportunity_id}</Link> <button className="link" onClick={() => link(null)}>unlink</button></span>
          : (
            <div className="row" style={{ flexWrap: 'wrap' }}>
              <span className="small muted">When the follow-on shows up on SAM.gov, link it here:</span>
              <input value={oppQ} onChange={(e) => setOppQ(e.target.value)} placeholder="title or solicitation number" style={{ maxWidth: 240 }} />
              <button onClick={findOpps}>Find</button>
            </div>
          )}
        {opps && !t.opportunity_id && (
          <ul className="clean small" style={{ marginTop: 6 }}>
            {opps.map((o) => (
              <li key={o.id}><button className="link" onClick={() => { link(o.id); setOpps(null) }}>Link</button> {o.solicitation_number} {o.title} <span className="muted">{o.agency}</span></li>
            ))}
            {!opps.length && <li className="muted">No matching opportunities saved in the app.</li>}
          </ul>
        )}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ buyers
function Buyers({ defs }) {
  const [f, setF] = useState({ naics: defs.naics.join(', '), psc: defs.psc.join(', '), basis: defs.naics.length ? 'naics' : 'psc', years: 3 })
  const [data, setData] = useState(null)
  const [offices, setOffices] = useState(null)
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const body = (refresh) => ({ naics: list(f.naics), psc: list(f.psc), basis: f.basis, years: Number(f.years), refresh })

  const run = async (refresh = false) => {
    setBusy('main'); setErr(''); setOffices(null)
    try { setData(await api.post('/api/market/buyers', body(refresh))) } catch (e) { setErr(e.message) }
    setBusy('')
  }
  const loadOffices = async (refresh = false) => {
    setBusy('offices'); setErr('')
    try { setOffices(await api.post('/api/market/buyers/offices', { ...body(refresh), sample: 20 })) } catch (e) { setErr(e.message) }
    setBusy('')
  }

  const maxYear = data ? Math.max(...data.years.map((y) => y.obligations), 0) : 0
  const maxSub = data ? Math.max(...data.sub_agencies.map((s) => s.amount), 0) : 0
  const maxRec = data ? Math.max(...data.recipients.map((s) => s.amount), 0) : 0
  const maxOff = offices ? Math.max(...offices.offices.map((s) => s.amount), 0) : 0

  return (
    <>
      <div className="panel">
        <div className="grid g4">
          <label className="f">NAICS codes<input value={f.naics} onChange={set('naics')} /></label>
          <label className="f">PSC / FSC codes<input value={f.psc} onChange={set('psc')} /></label>
          <label className="f">Match on
            <select value={f.basis} onChange={set('basis')}>
              <option value="naics">NAICS codes</option>
              <option value="psc">PSC / FSC codes</option>
              <option value="both">Both (a listed NAICS and a listed PSC)</option>
            </select>
          </label>
          <label className="f">Fiscal years
            <select value={f.years} onChange={set('years')}>{[1, 2, 3, 5].map((y) => <option key={y} value={y}>Last {y} complete</option>)}</select>
          </label>
        </div>
        <div className="row" style={{ marginTop: 10 }}>
          <button className="primary" onClick={() => run(false)} disabled={!!busy}>{busy === 'main' ? 'Loading…' : 'Show buyers'}</button>
          {data && <button onClick={() => run(true)} disabled={!!busy}>Refresh</button>}
          {data && <span className="small muted">As of {asOf(data.as_of)}. FY{data.fiscal_years[0]} to FY{data.fiscal_years[data.fiscal_years.length - 1]} ({data.range.start} to {data.range.end}).</span>}
        </div>
      </div>
      {err && <div className="err">{err}</div>}
      {data && (
        <>
          <div className="grid g4">
            <div className="panel"><div className="small muted">Contract obligations</div><div className="mkt-big">{money(data.totals.obligations)}</div></div>
            <div className="panel"><div className="small muted">Awards with activity (summed by year)</div><div className="mkt-big">{data.totals.awards.toLocaleString()}</div></div>
            <div className="panel"><div className="small muted">Small business set-aside share</div><div className="mkt-big">{pct(data.totals.sb_share_dollars)}</div><div className="small muted">of dollars, {pct(data.totals.sb_share_awards)} of awards</div></div>
            <div className="panel"><div className="small muted">SDVOSB set-aside share</div><div className="mkt-big">{pct(data.totals.sdvosb_share_dollars)}</div><div className="small muted">of dollars, {pct(data.totals.sdvosb_share_awards)} of awards</div></div>
          </div>

          <div className="panel">
            <h2>Obligations by fiscal year</h2>
            <table>
              <thead><tr><th>FY</th><th>Obligations</th><th></th><th>Awards</th><th>Avg per award</th><th>SB set-aside $</th><th>SDVOSB set-aside $</th></tr></thead>
              <tbody>
                {data.years.map((y) => (
                  <tr key={y.fiscal_year}>
                    <td className="mono">FY{y.fiscal_year}</td>
                    <td className="mono">{money(y.obligations)}</td>
                    <td style={{ width: '28%' }}><Bar value={y.obligations} max={maxYear} /></td>
                    <td className="mono">{y.awards.toLocaleString()}</td>
                    <td className="mono">{money(y.avg_award)}</td>
                    <td className="mono">{money(y.sb_obligations)} <span className="muted">({y.sb_awards})</span></td>
                    <td className="mono">{money(y.sdvosb_obligations)} <span className="muted">({y.sdvosb_awards})</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="small muted">Obligations are contract dollars obligated in each year. Award counts are contracts with any activity that year, so the average is dollars per active award, not the size of new awards. Set-aside figures use the set-aside type recorded on the award (award counts in parentheses).</p>
          </div>

          <div className="grid g2">
            <div className="panel">
              <h2>Top awarding sub-agencies</h2>
              <table>
                <thead><tr><th>Sub-agency</th><th>Obligations</th><th></th><th>Awards</th><th>Avg</th></tr></thead>
                <tbody>
                  {data.sub_agencies.map((s) => (
                    <tr key={s.name + s.agency}>
                      <td>{s.name}<div className="small muted">{s.agency}</div></td>
                      <td className="mono">{money(s.amount)}</td>
                      <td style={{ width: '22%' }}><Bar value={s.amount} max={maxSub} /></td>
                      <td className="mono">{s.awards != null ? s.awards.toLocaleString() : ''}</td>
                      <td className="mono">{money(s.avg_award)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="panel">
              <div className="row spread"><h2>Top recipients</h2><Link className="small" to="/competitors">Open Competitor intel</Link></div>
              <table>
                <thead><tr><th>Company</th><th>Obligations</th><th></th></tr></thead>
                <tbody>
                  {data.recipients.map((r) => (
                    <tr key={r.recipient_id || r.name}>
                      <td>{r.name}<div className="small muted mono">{r.uei}</div></td>
                      <td className="mono">{money(r.amount)}</td>
                      <td style={{ width: '30%' }}><Bar value={r.amount} max={maxRec} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="panel">
            <div className="row spread">
              <h2>Awarding offices</h2>
              <div className="row">
                <button onClick={() => loadOffices(false)} disabled={!!busy}>{busy === 'offices' ? 'Loading…' : offices ? 'Reload' : 'Load office sample'}</button>
                {offices && <button onClick={() => loadOffices(true)} disabled={!!busy}>Refresh</button>}
              </div>
            </div>
            <p className="small muted">USAspending does not total spending by contracting office, so this is a sample: the offices behind the {offices ? offices.sample_size : 20} largest awards in the range (amounts are each award's total obligation).</p>
            {offices && (
              <table>
                <thead><tr><th>Office</th><th>Awards in sample</th><th>Obligated</th><th></th><th>Set-asides used</th></tr></thead>
                <tbody>
                  {offices.offices.map((o) => (
                    <tr key={o.office + o.sub_agency}>
                      <td>{o.office}<div className="small muted">{[o.agency, o.sub_agency].filter(Boolean).join(' / ')}</div></td>
                      <td className="mono">{o.awards}</td>
                      <td className="mono">{money(o.amount)}</td>
                      <td style={{ width: '20%' }}><Bar value={o.amount} max={maxOff} /></td>
                      <td className="small">{Object.entries(o.set_asides).map(([k, n]) => `${defs.set_aside_labels[k] || k} (${n})`).join(', ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </>
  )
}
