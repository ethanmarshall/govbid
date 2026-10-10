import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { PartsTable } from '../public/PublicQuote'

const usd = (n) => (n == null ? '' : `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`)
const STATUSES = ['submitted', 'reviewing', 'confirmed', 'ordered', 'in_production', 'shipped', 'declined', 'closed', 'draft']
const STATUS_LABEL = { draft: 'Not submitted', submitted: 'New', reviewing: 'In review', confirmed: 'Confirmed', ordered: 'Ordered', in_production: 'In production', shipped: 'Shipped', declined: 'Declined', closed: 'Closed' }
const ORDER_LABEL = { awaiting_payment: 'Waiting for card payment', paid: 'Paid by card', po_received: 'PO received', invoiced: 'Invoiced', cancelled: 'Cancelled' }
const KIND_LABEL = { instant: 'Instant', estimate: 'Estimate', manual: 'Manual', needs_input: 'Needs input', processing: 'Reading model', concept: 'Project idea' }

function shown(r) {
  const p = r.public_result || {}
  const many = (p.items || []).length > 1
  if (p.kind === 'instant') return many ? `${usd(p.total)} total` : `${usd(p.unit_price)} ea`
  if (p.kind === 'estimate') return many ? `${usd(p.total_low)} to ${usd(p.total_high)} total` : `${usd(p.unit_low)} to ${usd(p.unit_high)} ea`
  if (p.kind === 'processing') return 'reading model'
  if (p.kind === 'concept') return (r.concept_title || 'idea')
  return 'no price'
}

export default function CustomerRequests() {
  const [params, setParams] = useSearchParams()
  const [rows, setRows] = useState(null)
  const [filter, setFilter] = useState('')
  const [drafts, setDrafts] = useState(false)
  const [err, setErr] = useState('')
  const [showSettings, setShowSettings] = useState(false)
  const [open, setOpen] = useState(null)
  const sel = params.get('id')
  useEffect(() => { api.get('/api/portal/settings').then((v) => setOpen(v.enabled)).catch(() => {}) }, [showSettings])
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
        {open === false && !showSettings && (
          <p className="small due-soon" style={{ marginBottom: 0 }}>Your customer site is closed. Customers see your capabilities and a note to email you. Because you are signed in, you can open it and try quotes yourself. Turn it on in Portal settings.</p>
        )}
        {open && !showSettings && <p className="small okline" style={{ marginBottom: 0 }}>Your customer site is open. Anyone with the link can get prices.</p>}
        {showSettings && <PortalSettings onSaved={() => { load(); api.get('/api/portal/settings').then((v) => setOpen(v.enabled)).catch(() => {}) }} />}
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
        {r.kind !== 'concept' && <div>
          <h3>What they chose</h3>
          <p className="small" style={{ margin: 0 }}>Quantity {r.quantity}<br />Material: {r.material || 'from the drawing'}<br />Finish: {r.finish || 'from the drawing'}{r.thickness ? <><br />Thickness: {r.thickness} in</> : ''}</p>
        </div>}
      </div>
      {r.order?.status && <OrderBox r={r} id={id} setR={setR} setMsg={setMsg} setErr={setErr} onChange={onChange} />}
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
      {r.kind === 'concept' && (
        <>
          <h3>Their project</h3>
          <table className="small"><tbody>{(r.concept || []).map((x, i) => (
            <tr key={i}><td className="muted" style={{ width: 170, verticalAlign: 'top' }}>{x.label}</td><td style={{ whiteSpace: 'pre-wrap' }}>{x.text}</td></tr>
          ))}</tbody></table>
        </>
      )}
      {r.kind !== 'concept' && <>
      <h3>Your numbers, line by line</h3>
      <p className="small muted" style={{ marginTop: 0 }}>Tool price is before calibration. A final price replaces the tool's for the customer and is saved as a calibration sample, so the tool learns from each job.</p>
      <LineTable r={r} id={id} setR={setR} setMsg={setMsg} setErr={setErr} />
      <div className="pq pq-embed"><PartsTable req={{ ...r, result: p, submitted: true }} info={{}} viewUrl={(key) => `/api/portal/requests/${id}/views/${key}.svg`} /></div>
      </>}
      <h3>Review</h3>
      <div className="grid g2">
        <label className="f">Status<select value={r.status} onChange={(e) => put({ status: e.target.value })}>{STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}</select></label>
        <label className="f">Customer's status link<input readOnly value={statusLink} onFocus={(e) => e.target.select()} /></label>
      </div>
      <label className="f" style={{ marginTop: 10 }}>Your notes<textarea value={notes} onChange={(e) => setNotes(e.target.value)} onBlur={() => notes !== (r.internal_notes || '') && put({ internal_notes: notes })} placeholder="Call notes, scope changes, the price you confirmed" /></label>
      <div className="row" style={{ marginTop: 10 }}>
        <button className="primary" onClick={toQuotes}>Save as internal quotes</button>
        {r.kind !== 'concept' && <button onClick={reprice}>Price again with current rates</button>}
        {r.email && <a className="btn" href={mail}>Email the customer</a>}
        <button className="link" onClick={del}>Delete</button>
      </div>
      {r.quote_ids?.length > 0 && <p className="small">Internal quotes: {r.quote_ids.map((q) => <Link key={q} to={`/part-quotes?tab=saved`} style={{ marginRight: 8 }}>#{q}</Link>)} (open them from Saved quotes to adjust and send a customer quote)</p>}
      {msg && <p className="small okline">{msg}</p>}
    </div>
  )
}

function OrderBox({ r, id, setR, setMsg, setErr, onChange }) {
  const o = r.order
  const a = o.ship_to || {}
  const set = async (status) => {
    if (status === 'cancelled' && !confirm(`Cancel order ${o.number}? A card payment is not refunded here; refund it in Stripe.`)) return
    try { setR(await api.put(`/api/portal/requests/${id}/order`, { status })); setMsg(`Order marked ${ORDER_LABEL[status].toLowerCase()}.`); onChange() } catch (e) { setErr(e.message) }
  }
  return (
    <div className="notice" style={{ marginTop: 12 }}>
      <div className="row spread"><h3 style={{ margin: 0 }}>Order {o.number}: {usd(o.amount)}</h3><b>{ORDER_LABEL[o.status] || o.status}</b></div>
      <p className="small" style={{ margin: '6px 0' }}>
        {o.method === 'card' ? <>Card through Stripe{o.paid_at ? `, paid ${o.paid_at.slice(0, 10)} (${usd(o.paid_amount)})` : ''}{o.payment_intent ? `, ${o.payment_intent}` : ''}</> : <>Purchase order <b>{o.po_number}</b>{o.billing_email ? `, invoice to ${o.billing_email}` : ''}</>}
        <br />Placed {(o.placed_at || '').replace('T', ' ')}{o.lead_days ? `, ships in about ${o.lead_days} days` : ''}
        <br />Ship to: {[a.name, a.company, a.line1, a.line2, `${a.city}, ${a.state} ${a.zip}`, a.phone].filter(Boolean).join(', ')}
        {o.notes && <><br />Order notes: {o.notes}</>}
      </p>
      <table className="small"><thead><tr><th>Line</th><th>Qty</th><th>Each</th><th>Total</th></tr></thead>
        <tbody>{(o.lines || []).map((l, i) => <tr key={i}><td>{l.name}{l.group ? <span className="muted"> ({l.group})</span> : ''}<div className="muted">{[l.process, l.material, l.finish && l.finish !== 'none' && l.finish].filter(Boolean).join(', ')}</div></td><td className="mono">{l.qty}</td><td className="mono">{usd(l.unit_price)}</td><td className="mono">{usd(l.total)}</td></tr>)}</tbody>
      </table>
      <div className="row" style={{ marginTop: 8 }}>
        {o.method === 'po' && o.status === 'po_received' && <button className="primary" onClick={() => set('invoiced')}>Mark invoiced</button>}
        {o.method === 'po' && o.status === 'invoiced' && <button className="primary" onClick={() => set('paid')}>Mark paid</button>}
        {o.status !== 'cancelled' && <button className="link" onClick={() => set('cancelled')}>Cancel order</button>}
      </div>
      <p className="small muted" style={{ marginBottom: 0 }}>Move the request status to In production and Shipped below as the job moves; the customer sees it on their status page and in their account.</p>
    </div>
  )
}

// The site text is edited as plain text: one entry per line, or "Title: details" for capabilities,
// and question/answer blocks separated by a blank line for questions.
const lines = (t) => String(t || '').split('\n').map((x) => x.trim()).filter(Boolean)
const toCaps = (list) => (list || []).map((c) => (c.text ? `${c.title}: ${c.text}` : c.title)).join('\n')
const fromCaps = (t) => lines(t).map((l) => { const i = l.indexOf(':'); return i > 0 ? { title: l.slice(0, i).trim(), text: l.slice(i + 1).trim() } : { title: l, text: '' } })
const toFaq = (list) => (list || []).map((f) => `${f.q}\n${f.a}`).join('\n\n')
const fromFaq = (t) => String(t || '').split(/\n\s*\n/).map((b) => b.trim()).filter(Boolean).map((b) => { const [q, ...a] = b.split('\n'); return { q: q.trim(), a: a.join(' ').trim() } })
const siteText = (site) => ({ about: site.about || '', capabilities: toCaps(site.capabilities), experience: (site.experience || []).join('\n'),
  industries: (site.industries || []).join('\n'), quality: (site.quality || []).join('\n'), faq: toFaq(site.faq) })
const siteFrom = (t) => ({ about: t.about, capabilities: fromCaps(t.capabilities), experience: lines(t.experience), industries: lines(t.industries), quality: lines(t.quality), faq: fromFaq(t.faq) })

function LineTable({ r, id, setR, setMsg, setErr }) {
  const items = r.internal?.items || []
  const [finals, setFinals] = useState({})
  const [open, setOpen] = useState({})
  const save = async (key, value) => {
    try {
      const x = await api.put(`/api/portal/requests/${id}/lines`, { lines: { [key]: { final_unit_price: value === '' ? null : Number(value) } } })
      setR(x); setMsg(value === '' ? 'Final price cleared.' : 'Final price saved. The customer sees it, and it was added to calibration.')
    } catch (e) { setErr(e.message) }
  }
  const sum = (b) => Object.values(b?.per_part || {}).reduce((a, v) => a + v, 0)
  if (!items.length) return <p className="small muted">No lines.</p>
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="small">
        <thead><tr><th>Line</th><th>Qty</th><th>Route</th><th>Setup (lot)</th><th>Run (each)</th><th>Cost each</th><th>Tool price</th><th>Calibration</th><th>Price each</th><th>Margin</th><th>Final price each</th></tr></thead>
        <tbody>{items.map((it) => (
          <tr key={it.key}>
            <td style={{ minWidth: 200 }}><b>{it.name}</b>{it.group && <div className="muted">{it.group}</div>}<div className="muted">{it.desc}</div>
              {it.internal_reasons?.length > 0 && (
                <>
                  <button className="link small" onClick={() => setOpen({ ...open, [it.key]: !open[it.key] })}>{open[it.key] ? 'Hide notes' : `${it.internal_reasons.length} note(s)`}</button>
                  {open[it.key] && <ul className="clean muted" style={{ marginTop: 4 }}>{it.internal_reasons.slice(0, 8).map((x, j) => <li key={j}>{x}</li>)}</ul>}
                </>
              )}</td>
            <td className="mono">{it.qty}{it.qty_per > 1 ? <div className="muted">{it.qty_per}/set</div> : null}</td>
            <td>{it.route}{it.incomplete && <div className="due-soon">incomplete</div>}</td>
            <td className="mono">{it.breakdown ? usd(it.breakdown.lot_cost) : ''}</td>
            <td className="mono" title={it.breakdown ? Object.entries(it.breakdown.per_part).map(([k, v]) => `${k}: ${usd(v)}`).join('\n') : ''}>{it.breakdown ? usd(sum(it.breakdown)) : ''}</td>
            <td className="mono">{usd(it.unit_cost)}</td>
            <td className="mono">{usd(it.raw_unit_price)}</td>
            <td className="small">{it.calibration ? <span title={it.calibration.why}>x{it.calibration.factor}</span> : <span className="muted">none</span>}</td>
            <td className="mono"><b>{usd(it.unit_price)}</b></td>
            <td className="mono">{it.margin_pct != null ? `${it.margin_pct}%` : ''}</td>
            <td style={{ minWidth: 130 }}>
              <div className="row" style={{ gap: 4, flexWrap: 'nowrap' }}>
                <input type="number" min="0" step="0.01" style={{ width: 90 }} placeholder={it.final_unit_price ?? ''}
                  value={finals[it.key] ?? (it.final_unit_price ?? '')} onChange={(e) => setFinals({ ...finals, [it.key]: e.target.value })} />
                <button className="small-btn" onClick={() => save(it.key, finals[it.key] ?? '')}>Set</button>
              </div>
            </td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  )
}

function PortalSettings({ onSaved }) {
  const [s, setS] = useState(null)
  const [site, setSite] = useState(null)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  useEffect(() => { api.get('/api/portal/settings').then((v) => { setS(v); setSite(siteText(v.site)) }).catch((e) => setErr(e.message)) }, [])
  if (!s) return <p className="muted">{err || 'Loading…'}</p>
  const save = async () => {
    setErr(''); setMsg('')
    try { const { site: _ignored, site_defaults: _d, ...rest } = s; const v = await api.put('/api/portal/settings', { ...rest, site: siteFrom(site) }); setS(v); setSite(siteText(v.site)); setMsg('Saved.'); onSaved?.() } catch (e) { setErr(e.message) }
  }
  const f = (k, label, type = 'text', props = {}) => (
    <label className="f">{label}<input type={type} value={s[k] ?? ''} onChange={(e) => setS({ ...s, [k]: type === 'number' ? Number(e.target.value) : e.target.value })} {...props} /></label>
  )
  const t = (k, label, hint, rows = 5) => (
    <label className="f" style={{ marginTop: 10 }}>{label}{hint && <span className="small muted" style={{ fontWeight: 400 }}>{hint}</span>}
      <textarea value={site[k]} onChange={(e) => setSite({ ...site, [k]: e.target.value })} rows={rows} style={{ minHeight: rows * 20 }} /></label>
  )
  return (
    <div style={{ marginTop: 12 }}>
      <label className="check"><input type="checkbox" checked={s.enabled} onChange={(e) => setS({ ...s, enabled: e.target.checked })} /> <b>Customer site is open for quotes</b></label>
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
      <label className="f" style={{ marginTop: 10 }}>Intro above the upload box<textarea value={s.intro} onChange={(e) => setS({ ...s, intro: e.target.value })} style={{ minHeight: 60 }} /></label>
      <label className="f" style={{ marginTop: 10 }}>Terms the customer accepts<textarea value={s.terms} onChange={(e) => setS({ ...s, terms: e.target.value })} style={{ minHeight: 70 }} /></label>

      <h3 style={{ marginTop: 22 }}>What the site says about you</h3>
      <p className="small due-soon">This is suggested text. Read every line and change it so it matches what you actually do, in house or through partners. Customers will hold you to it.</p>
      {t('about', 'About us', 'A paragraph or two. Leave a blank line between paragraphs.', 4)}
      {t('capabilities', 'Capabilities', 'One per line, as Title: details', 9)}
      <div className="grid g2">
        {t('experience', 'Experience', 'One per line', 5)}
        {t('industries', 'Who you work with', 'One per line', 5)}
      </div>
      {t('quality', 'Quality and compliance', 'One per line', 5)}
      {t('faq', 'Questions', 'Question on the first line, answer below it, blank line between questions. {review_days} becomes your review time.', 12)}
      <label className="check" style={{ marginTop: 8 }}><input type="checkbox" checked={!!s.show_codes} onChange={(e) => setS({ ...s, show_codes: e.target.checked })} /> Show your UEI, CAGE code, NAICS codes and the certifications you hold (from Company profile). Pending certifications are never shown.</label>
      <p className="small"><button className="link" onClick={() => setSite(siteText(s.site_defaults))}>Put back the suggested text</button> (not saved until you save)</p>

      <p className="small muted">Email notices need SMTP_HOST and the other SMTP settings on the server. Requests are saved either way.</p>
      {err && <div className="err">{err}</div>}
      <div className="row"><button className="primary" onClick={save}>Save portal settings</button>{msg && <span className="small okline">{msg}</span>}
        <a className="small" href="/quote" target="_blank" rel="noreferrer">View the customer site</a></div>
    </div>
  )
}
