import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'

const usd = (n) => (n == null ? '' : `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`)
const STATUSES = ['submitted', 'reviewing', 'confirmed', 'declined', 'closed', 'draft']
const STATUS_LABEL = { draft: 'Not submitted', submitted: 'New', reviewing: 'In review', confirmed: 'Confirmed', declined: 'Declined', closed: 'Closed' }
const KIND_LABEL = { instant: 'Instant', estimate: 'Estimate', manual: 'Manual', needs_input: 'Needs input' }

function shown(r) {
  const p = r.public_result || {}
  if (p.kind === 'instant') return `${usd(p.unit_price)} ea`
  if (p.kind === 'estimate') return `${usd(p.unit_low)} to ${usd(p.unit_high)} ea`
  return 'no price'
}

export default function CustomerRequests() {
  const [params, setParams] = useSearchParams()
  const [rows, setRows] = useState(null)
  const [filter, setFilter] = useState('')
  const [drafts, setDrafts] = useState(false)
  const [err, setErr] = useState('')
  const [showSettings, setShowSettings] = useState(false)
  const sel = params.get('id')
  const load = () => api.get('/api/portal/requests?' + new URLSearchParams({ status: filter, include_drafts: drafts })).then(setRows).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [filter, drafts])
  const publicUrl = `${window.location.origin}/quote`

  return (
    <>
      <h1>Customer requests</h1>
      <p className="sub">Projects customers submit from your public quote page. Instant quotes and estimates are priced from your shop rates; nothing is final until you confirm it with the customer.</p>
      <div className="panel">
        <div className="row spread">
          <div className="row">
            <span className="small">Customer page:</span>
            <a className="mono small" href={publicUrl} target="_blank" rel="noreferrer">{publicUrl}</a>
            <button className="small-btn" onClick={() => navigator.clipboard?.writeText(publicUrl)}>Copy link</button>
          </div>
          <button className="link" onClick={() => setShowSettings(!showSettings)}>{showSettings ? 'Hide' : 'Portal settings'}</button>
        </div>
        {showSettings && <PortalSettings onSaved={load} />}
      </div>
      {err && <div className="err">{err}</div>}
      <div className="row" style={{ marginBottom: 10 }}>
        {[['', 'All'], ...STATUSES.filter((s) => s !== 'draft').map((s) => [s, STATUS_LABEL[s]])].map(([k, label]) => (
          <button key={k || 'all'} className={`chip ${filter === k ? 'on' : ''}`} onClick={() => setFilter(k)}>{label}</button>
        ))}
        <label className="check small"><input type="checkbox" checked={drafts} onChange={(e) => setDrafts(e.target.checked)} /> Include quotes not submitted</label>
      </div>
      <div className={sel ? 'crm-split' : ''}>
        <div className="panel">
          {!rows ? <p className="muted">Loading…</p> : !rows.length ? <p className="muted">No requests yet. Share the customer page link once the portal is on.</p> : (
            <table className="small">
              <thead><tr><th>Request</th><th>Customer</th><th>Type</th><th>Shown</th><th>Status</th></tr></thead>
              <tbody>{rows.map((r) => (
                <tr key={r.id} className={`click ${String(r.id) === sel ? 'sel' : ''}`} onClick={() => setParams({ id: r.id })}>
                  <td><b className="mono">{r.ref}</b><div className="muted">{(r.submitted_at || r.created_at || '').slice(0, 10)} · qty {r.quantity}</div></td>
                  <td>{r.contact_name || <span className="muted">not given</span>}{r.company && <div className="muted">{r.company}</div>}</td>
                  <td>{KIND_LABEL[r.kind] || r.kind}{r.export_controlled && <div><span className="tag due-soon">export-controlled</span></div>}</td>
                  <td className="mono">{shown(r)}</td>
                  <td>{STATUS_LABEL[r.status] || r.status}</td>
                </tr>
              ))}</tbody>
            </table>
          )}
        </div>
        {sel && <RequestDetail id={sel} onChange={load} onClose={() => setParams({})} />}
      </div>
    </>
  )
}

function RequestDetail({ id, onChange, onClose }) {
  const [r, setR] = useState(null)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [notes, setNotes] = useState('')
  useEffect(() => { setR(null); api.get(`/api/portal/requests/${id}`).then((x) => { setR(x); setNotes(x.internal_notes || '') }).catch((e) => setErr(e.message)) }, [id])
  if (err) return <div className="panel err">{err}</div>
  if (!r) return <div className="panel"><p className="muted">Loading…</p></div>
  const p = r.public_result || {}
  const items = r.internal?.items || []
  const put = async (body) => { try { const x = await api.put(`/api/portal/requests/${id}`, body); setR(x); setMsg('Saved.'); onChange() } catch (e) { setErr(e.message) } }
  const toQuotes = async () => {
    try { const x = await api.post(`/api/portal/requests/${id}/to-quotes`); setR(x); setMsg(x.quote_ids.length ? `Saved ${x.quote_ids.length} internal quote(s).` : 'Nothing priced to save.'); onChange() } catch (e) { setErr(e.message) }
  }
  const reprice = async () => { try { setR(await api.post(`/api/portal/requests/${id}/reprice`)); setMsg('Priced again with your current rates.') } catch (e) { setErr(e.message) } }
  const del = async () => { if (!confirm(`Delete ${r.ref} and its files?`)) return; await api.del(`/api/portal/requests/${id}`); onChange(); onClose() }
  const mail = `mailto:${r.email}?subject=${encodeURIComponent(`Your quote request ${r.ref}`)}`
  const statusLink = `${window.location.origin}/quote/status/${r.ref}?t=${encodeURIComponent(r.token)}`
  return (
    <div className="panel">
      <div className="row spread"><h2 style={{ margin: 0 }}>{r.ref}</h2><button className="link" onClick={onClose}>Close</button></div>
      {r.export_controlled && <div className="notice small" style={{ marginTop: 10 }}>The customer flagged export-controlled data, or a drawing marked export-controlled or limited distribution was deleted on upload. Arrange a secure transfer; do not ask them to upload it here.</div>}
      <div className="grid g2" style={{ marginTop: 10 }}>
        <div>
          <h3>Customer</h3>
          {r.contact_name ? (
            <p className="small" style={{ margin: 0 }}><b>{r.contact_name}</b>{r.company && `, ${r.company}`}<br />
              <a href={mail}>{r.email}</a>{r.phone && <> · <a href={`tel:${r.phone}`}>{r.phone}</a></>}<br />
              Needed by: {r.needed_by || 'not given'}</p>
          ) : <p className="small muted">Not submitted yet (no contact details).</p>}
        </div>
        <div>
          <h3>What they chose</h3>
          <p className="small" style={{ margin: 0 }}>Quantity {r.quantity}<br />Material: {r.material || 'from the drawing'}<br />Finish: {r.finish || 'from the drawing'}{r.thickness ? <><br />Thickness: {r.thickness} in</> : ''}</p>
        </div>
      </div>
      {r.customer_notes && <><h3>Their notes</h3><p className="small" style={{ whiteSpace: 'pre-wrap' }}>{r.customer_notes}</p></>}
      <h3>Files</h3>
      {!r.files.length ? <p className="small muted">No files.</p> : (
        <ul className="clean small">{r.files.map((f, i) => (
          <li key={i}>{f.removed ? <span className="muted">{f.name} (deleted: export-controlled)</span> : <a href={`/api/portal/requests/${id}/files/${i}`}>{f.name}</a>} <span className="muted">{f.kind}, {f.size < 102400 ? `${Math.max(1, Math.round(f.size / 1024))} KB` : `${(f.size / 1048576).toFixed(1)} MB`}</span></li>
        ))}</ul>
      )}
      <h3>Shown to the customer</h3>
      <p className="small" style={{ margin: 0 }}><b>{KIND_LABEL[p.kind] || p.kind}</b>: {shown(r)}{p.kind === 'instant' ? `, ${usd(p.total)} total` : p.kind === 'estimate' ? `, ${usd(p.total_low)} to ${usd(p.total_high)} total` : ''}{p.lead_days ? `, about ${p.lead_days} days` : ''}</p>
      {r.internal?.shown_to_customer && <p className="small muted">Repriced since; the customer saw the earlier price.</p>}
      <h3>Your numbers</h3>
      <table className="small">
        <thead><tr><th>Item</th><th>Route</th><th>Unit cost</th><th>Unit price</th><th>Margin</th></tr></thead>
        <tbody>{items.map((it, i) => (
          <tr key={i}>
            <td><b>{it.name}</b><div className="muted">{it.desc}</div>
              {it.internal_reasons?.length > 0 && <ul className="clean muted" style={{ marginTop: 4 }}>{it.internal_reasons.slice(0, 6).map((x, j) => <li key={j}>{x}</li>)}</ul>}</td>
            <td>{it.route}{it.incomplete && <div className="due-soon">needs manual prices</div>}</td>
            <td className="mono">{usd(it.unit_cost)}</td><td className="mono">{usd(it.unit_price)}</td><td className="mono">{it.margin_pct != null ? `${it.margin_pct}%` : ''}</td>
          </tr>
        ))}</tbody>
      </table>
      <h3>Review</h3>
      <div className="grid g2">
        <label className="f">Status<select value={r.status} onChange={(e) => put({ status: e.target.value })}>{STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}</select></label>
        <label className="f">Customer's status link<input readOnly value={statusLink} onFocus={(e) => e.target.select()} /></label>
      </div>
      <label className="f" style={{ marginTop: 10 }}>Your notes<textarea value={notes} onChange={(e) => setNotes(e.target.value)} onBlur={() => notes !== (r.internal_notes || '') && put({ internal_notes: notes })} placeholder="Call notes, scope changes, the price you confirmed" /></label>
      <div className="row" style={{ marginTop: 10 }}>
        <button className="primary" onClick={toQuotes}>Save as internal quotes</button>
        <button onClick={reprice}>Price again with current rates</button>
        {r.email && <a className="btn" href={mail}>Email the customer</a>}
        <button className="link" onClick={del}>Delete</button>
      </div>
      {r.quote_ids?.length > 0 && <p className="small">Internal quotes: {r.quote_ids.map((q) => <Link key={q} to={`/part-quotes?tab=saved`} style={{ marginRight: 8 }}>#{q}</Link>)} (open them from Saved quotes to adjust and send a customer quote)</p>}
      {msg && <p className="small okline">{msg}</p>}
    </div>
  )
}

function PortalSettings({ onSaved }) {
  const [s, setS] = useState(null)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  useEffect(() => { api.get('/api/portal/settings').then(setS).catch((e) => setErr(e.message)) }, [])
  if (!s) return <p className="muted">{err || 'Loading…'}</p>
  const save = async () => { setErr(''); try { setS(await api.put('/api/portal/settings', s)); setMsg('Saved.'); onSaved?.() } catch (e) { setErr(e.message) } }
  const f = (k, label, type = 'text', props = {}) => (
    <label className="f">{label}<input type={type} value={s[k] ?? ''} onChange={(e) => setS({ ...s, [k]: type === 'number' ? Number(e.target.value) : e.target.value })} {...props} /></label>
  )
  return (
    <div style={{ marginTop: 12 }}>
      <label className="check"><input type="checkbox" checked={s.enabled} onChange={(e) => setS({ ...s, enabled: e.target.checked })} /> <b>Customer page is open</b></label>
      <p className="small due-soon">Before you open it: replace the placeholder shop rates (Part quotes, Shop rates and the rates on each tab). Customers see prices built from them.</p>
      <div className="grid g3">
        {f('display_name', 'Company name shown (blank: your profile name)')}
        {f('contact_email', 'Contact email shown', 'email')}
        {f('contact_phone', 'Contact phone shown')}
        {f('notify_email', 'Email new requests to (blank: DIGEST_TO)', 'email')}
        {f('review_days', 'Review within (business days)', 'number', { min: 0 })}
        {f('max_quantity', 'Largest quantity allowed', 'number', { min: 1 })}
        {f('estimate_low_pct', 'Estimate range: below by %', 'number', { min: 0 })}
        {f('estimate_high_pct', 'Estimate range: above by %', 'number', { min: 0 })}
        {f('incomplete_high_pct', 'Above by % when parts need manual prices', 'number', { min: 0 })}
      </div>
      <label className="f" style={{ marginTop: 10 }}>Tagline<input value={s.tagline} onChange={(e) => setS({ ...s, tagline: e.target.value })} /></label>
      <label className="f" style={{ marginTop: 10 }}>Intro<textarea value={s.intro} onChange={(e) => setS({ ...s, intro: e.target.value })} style={{ minHeight: 60 }} /></label>
      <label className="f" style={{ marginTop: 10 }}>Terms the customer accepts<textarea value={s.terms} onChange={(e) => setS({ ...s, terms: e.target.value })} style={{ minHeight: 70 }} /></label>
      <p className="small muted">Email notices need SMTP_HOST and the other SMTP settings on the server. Requests are saved either way.</p>
      {err && <div className="err">{err}</div>}
      <div className="row"><button className="primary" onClick={save}>Save portal settings</button>{msg && <span className="small okline">{msg}</span>}</div>
    </div>
  )
}
