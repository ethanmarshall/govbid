import { Fragment, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { PartsTable } from '../public/PublicQuote'
import { DesignChecks, Order8020 } from './Order8020'

const usd = (n) => (n == null ? '' : `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`)
const STATUSES = ['submitted', 'reviewing', 'confirmed', 'ordered', 'in_production', 'shipped', 'declined', 'closed', 'draft']
const STATUS_LABEL = { draft: 'Not submitted', submitted: 'New', reviewing: 'In review', confirmed: 'Confirmed', ordered: 'Ordered', in_production: 'In production', shipped: 'Shipped', declined: 'Declined', closed: 'Closed' }
const ORDER_LABEL = { awaiting_payment: 'Waiting for card payment', paid: 'Paid', po_received: 'PO received', invoiced: 'Invoiced, on terms', invoice_due: 'Invoice due before we start', cancelled: 'Cancelled', payment_review: 'Payment to check', awaiting_signature: 'Waiting for signature' }
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
  // how many unsubmitted quotes the list is hiding, so an empty list says so
  const [hidden, setHidden] = useState(0)
  useEffect(() => {
    if (drafts || filter) { setHidden(0); return }
    api.get('/api/portal/requests?include_drafts=true').then((all) => setHidden(all.filter((x) => x.status === 'draft').length)).catch(() => {})
  }, [drafts, filter, rows])
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
          {!rows ? <p className="muted">Loading…</p> : !rows.length ? (hidden > 0
            ? <div><p className="muted">No submitted requests yet. {hidden} quote{hidden === 1 ? '' : 's'} people priced but did not send {hidden === 1 ? 'is' : 'are'} hidden.</p>
              <button className="small-btn" onClick={() => setDrafts(true)}>Show {hidden === 1 ? 'it' : `all ${hidden}`}</button></div>
            : <p className="muted">No requests yet. Share the customer page link once the portal is on.</p>) : (
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
      {(r.order?.status || r.order?.unmatched_payments?.length > 0) && <OrderBox r={r} id={id} setR={setR} setMsg={setMsg} setErr={setErr} onChange={onChange} />}
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
      <MoneySummary m={r.summary} />
      <h3>Your numbers, line by line</h3>
      <p className="small muted" style={{ marginTop: 0 }}>Tool price is before calibration. A final price replaces the tool's for the customer and is saved as a calibration sample, so the tool learns from each job.</p>
      <LineTable r={r} id={id} setR={setR} setMsg={setMsg} setErr={setErr} />
      <ColumnKey />
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

function Agreement({ o, id, setR, setMsg, setErr, onChange }) {
  const ag = o.agreement
  const sig = ag.signed || {}
  const waive = async () => {
    const note = prompt('Release this order without the online signature. Why? (for example: signed on paper, or government contract)')
    if (!note) return
    try { setR(await api.post(`/api/portal/requests/${id}/agreement/waive`, { note })); setMsg('Released. The invoice is made.'); onChange() } catch (e) { setErr(e.message) }
  }
  return (
    <p className="small" style={{ margin: '6px 0' }}>
      {ag.status === 'pending' && <><b>Do not start: waiting for the customer to sign the order agreement</b> (sent {(ag.sent_at || '').slice(0, 10)}). The invoice is made when they sign. </>}
      {ag.status === 'signed' && <>Agreement signed by <b>{sig.name}</b>, {sig.title}{sig.company ? `, ${sig.company}` : ''} on {(sig.at || '').replace('T', ' ').slice(0, 16)} UTC from {sig.ip}{sig.email_verified ? ', email code confirmed' : ''}. </>}
      {ag.status === 'waived' && <>Agreement not signed online: {ag.waived?.note}. </>}
      <a href={`/api/portal/requests/${id}/agreement.pdf`} target="_blank" rel="noreferrer">Agreement PDF</a>
      {ag.status === 'pending' && <> · <button className="link" onClick={waive}>Release without online signature</button></>}
    </p>
  )
}

function OrderBox({ r, id, setR, setMsg, setErr, onChange }) {
  const o = r.order
  const a = o.ship_to || {}
  const set = async (status) => {
    if (status === 'cancelled' && !confirm(`Cancel order ${o.number}? A card payment is not refunded here; refund it in Stripe.`)) return
    try { setR(await api.put(`/api/portal/requests/${id}/order`, { status })); setMsg(`Order marked ${ORDER_LABEL[status].toLowerCase()}.`); onChange() } catch (e) { setErr(e.message) }
  }
  const unmatched = o.unmatched_payments?.length > 0 && <p className="small err" style={{ margin: '6px 0' }}>Card payment{o.unmatched_payments.length > 1 ? 's' : ''} on an old checkout page: {o.unmatched_payments.map((u) => `${usd(u.amount)} (${u.payment_intent || u.id}, ${u.at.slice(0, 10)})`).join('; ')}. Refund or apply it in Stripe.</p>
  if (!o.number) return <div className="notice" style={{ marginTop: 12 }}><h3 style={{ margin: 0 }}>Payment with no current order</h3>{unmatched}</div>
  return (
    <div className="notice" style={{ marginTop: 12 }}>
      <div className="row spread"><h3 style={{ margin: 0 }}>{o.number ? `Order ${o.number}: ${usd(o.amount)}` : 'Payment with no current order'}</h3><b>{ORDER_LABEL[o.status] || o.status || ''}</b></div>
      <p className="small" style={{ margin: '6px 0' }}>
        {o.method === 'card' ? <>Card through Stripe</> : <>Invoice{o.invoice_number ? <> <b>{o.invoice_number}</b></> : ''}, {o.terms_days ? `net ${o.terms_days}, due ${o.due_date}` : 'due on receipt (start when paid)'}{o.po_number ? <>, PO <b>{o.po_number}</b></> : ''}{o.billing_email ? `, send to ${o.billing_email}` : ''}</>}
        {o.paid_at ? `, paid ${o.paid_at.slice(0, 10)}${o.paid_amount ? ` (${usd(o.paid_amount)})` : ''}` : ''}{o.payment_intent ? `, ${o.payment_intent}` : ''}
        {o.invoice_number && <> · <a href={`/api/portal/requests/${id}/invoice.pdf`} target="_blank" rel="noreferrer">{o.status === 'paid' && o.method === 'card' ? 'Receipt' : 'Invoice'} PDF</a></>}
        <br />Placed {(o.placed_at || '').replace('T', ' ')}{o.lead_days ? `, ships in about ${o.lead_days} days` : ''}
        <br />Ship to: {[a.name, a.company, a.line1, a.line2, `${a.city}, ${a.state} ${a.zip}`, a.phone].filter(Boolean).join(', ')}
        {o.notes && <><br />Order notes: {o.notes}</>}
      </p>
      {o.review_reason && <p className="small err" style={{ margin: '6px 0' }}>{o.review_reason} Check the payment in Stripe before starting work, then mark it paid or cancel and refund.</p>}
      {unmatched}
      <table className="small"><thead><tr><th>Line</th><th>Qty</th><th>Each</th><th>Total</th></tr></thead>
        <tbody>{(o.lines || []).map((l, i) => <tr key={i}><td>{l.name}{l.group ? <span className="muted"> ({l.group})</span> : ''}<div className="muted">{[l.process, l.material, l.finish && l.finish !== 'none' && l.finish].filter(Boolean).join(', ')}</div></td><td className="mono">{l.qty}</td><td className="mono">{usd(l.unit_price)}</td><td className="mono">{usd(l.total)}</td></tr>)}</tbody>
      </table>
      <div className="row" style={{ marginTop: 8 }}>
        {['invoiced', 'invoice_due', 'po_received', 'payment_review'].includes(o.status) && <button className="primary" onClick={() => set('paid')}>Mark paid</button>}
        {o.status && o.status !== 'cancelled' && <button className="link" onClick={() => set('cancelled')}>Cancel order</button>}
      </div>
      {o.agreement && <Agreement o={o} id={id} setR={setR} setMsg={setMsg} setErr={setErr} onChange={onChange} />}
      {o.status === 'invoice_due' && <p className="small" style={{ margin: '6px 0' }}><b>Do not start yet:</b> this customer has no terms, so the work starts when the invoice is paid. Mark it paid when the money arrives.</p>}
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

// A T-slot frame line in review: the parts list read from the model (or your edited copy), the prices it uses, and
// what each cost came to. Prices entered here apply to this quote only, unless you also save them as your rates.
const BOM_KIND = { profile: 'Extrusion cut', hardware: 'Hardware', panel: 'Panel', custom: 'Other item' }
const OPS = { counterbore: 'cbore', miter_cut: 'miter', end_tap: 'end tap', access_hole: 'access hole', drill_thru: 'drill', drill_thru_cbore: 'drill + cbore', miter_cbore: 'miter cbore', central_connector_cbore: 'central conn.' }
let catalogCache = null
const loadCatalog = () => (catalogCache ||= api.get('/api/extrusion/catalog').catch((e) => { catalogCache = null; throw e }))

function FrameBom({ it, id, setR, setMsg, setErr }) {
  const bom = it.spec.bom || {}
  const [cat, setCat] = useState(null)
  const [lines, setLines] = useState(() => structuredClone(bom.lines ?? it.spec.model_lines ?? it.spec.lines ?? []))
  const [prices, setPrices] = useState(() => structuredClone(bom.prices || {}))
  const [cut, setCut] = useState(bom.cut_charge ?? '')
  const [note, setNote] = useState(bom.note || '')
  const [saveRates, setSaveRates] = useState(false)
  const [busy, setBusy] = useState(false)
  useEffect(() => { loadCatalog().then(setCat).catch((e) => setErr(e.message)) }, [])
  useEffect(() => { // the server's copy after each save
    const b = it.spec.bom || {}
    setLines(structuredClone(b.lines ?? it.spec.model_lines ?? it.spec.lines ?? [])); setPrices(structuredClone(b.prices || {})); setCut(b.cut_charge ?? ''); setNote(b.note || '')
  }, [it.spec])
  if (!cat) return <p className="small muted">Loading the catalog…</p>

  const byId = {
    profile: Object.fromEntries(cat.profiles.map((p) => [p.id, p])),
    hardware: Object.fromEntries(cat.hardware.map((h) => [h.id, h])),
    panel: Object.fromEntries(cat.panels.map((p) => [p.id, p])),
  }
  const group = { profile: 'profiles', hardware: 'hardware', panel: 'panels' }
  const rateOf = (kind, cid) => { const x = byId[kind]?.[cid]; return kind === 'profile' ? x?.price_per_in : kind === 'panel' ? x?.price_per_sqft : x?.unit_price }
  const unit = { profile: '$/in', hardware: '$/each', panel: '$/sq ft' }
  const setLine = (i, ch) => setLines(lines.map((l, j) => (j === i ? { ...l, ...ch } : l)))
  const setOp = (i, op, n) => {
    const old = (lines[i].machining || []).find((o) => o.op === op)
    const ops = (lines[i].machining || []).filter((o) => o.op !== op)
    setLine(i, { machining: n > 0 ? [...ops, { ...(old || {}), op, count: n }] : ops })
  }
  const setPrice = (g, k, v) => setPrices((old) => {
    const out = structuredClone(old)
    out[g] = { ...(out[g] || {}) }
    if (v === '') delete out[g][k]; else out[g][k] = Number(v)
    if (!Object.keys(out[g]).length) delete out[g]
    return out
  })
  const fam = (() => { const p = lines.find((l) => l.kind === 'profile'); return byId.profile[p?.catalog_id]?.family || '15' })()
  const add = (kind) => setLines([...lines, kind === 'profile' ? { kind, catalog_id: lines.find((l) => l.kind === 'profile')?.catalog_id || '1515', qty: 1, length_in: 12, machining: [] }
    : kind === 'hardware' ? { kind, catalog_id: cat.hardware.find((h) => h.family === fam)?.id || cat.hardware[0].id, qty: 1 }
      : kind === 'panel' ? { kind, catalog_id: cat.panels[0].id, qty: 1, width_in: 12, height_in: 12 } : { kind, description: '', qty: 1, unit_price: '' }])

  // every catalog item and machining op this parts list uses, for its price for this quote
  const used = []
  const seen = new Set()
  lines.forEach((l) => {
    if (l.kind !== 'custom' && l.catalog_id && !seen.has(l.kind + l.catalog_id)) { seen.add(l.kind + l.catalog_id); used.push({ kind: l.kind, id: l.catalog_id }) }
  })
  const ops = [...new Set(lines.flatMap((l) => (l.kind === 'profile' ? (l.machining || []).map((o) => o.op) : [])))]
  const opRate = Object.fromEntries(cat.machining.map((m) => [m.id, m.price]))

  const save = async (b) => {
    setBusy(true); setErr('')
    try {
      const x = await api.put(`/api/portal/requests/${id}/lines`, { lines: { [it.key]: { bom: b } } })
      if (saveRates && b) {
        const cfg = structuredClone(cat.config)
        cfg.prices = cfg.prices || {}
        for (const g of ['profiles', 'hardware', 'panels']) cfg.prices[g] = { ...(cfg.prices[g] || {}), ...(b.prices?.[g] || {}) }
        cfg.machining = { ...(cfg.machining || {}), ...(b.prices?.machining || {}) }
        if (b.cut_charge !== undefined && b.cut_charge !== '') cfg.cut_charge = Number(b.cut_charge)
        await api.put('/api/pricing/config', { changes: { extrusion: cfg } })
        catalogCache = null
        setCat(await loadCatalog())
      }
      setR(x)
      setMsg(!b ? 'Back to the parts list and prices read from the model.' : saveRates ? 'Saved for this quote and as your extrusion rates. Reprice other requests to use them.' : 'Saved for this quote and repriced.')
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const edited = bom.lines != null || bom.prices || bom.cut_charge != null
  const downloadSheet = async (kind) => {
    try {
      const res = await fetch(`/api/extrusion/${kind === 'cut' ? 'cutlist' : 'purchase'}.xlsx`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lines: it.spec.lines || [], quantities: [it.qty || 1], builds: it.qty || 1, title: it.name, options: {} }),
      })
      if (!res.ok) throw new Error(`Could not make the ${kind === 'cut' ? 'cut' : 'purchase'} list (${res.status})`)
      const url = URL.createObjectURL(await res.blob())
      const a = document.createElement('a')
      a.href = url
      a.download = `${String(it.name || 'frame').replace(/[^a-z0-9]+/gi, '-').toLowerCase()}-${kind === 'cut' ? 'cut-list' : 'purchase-list'}.xlsx`
      a.click()
      setTimeout(() => URL.revokeObjectURL(url), 2000)
    } catch (e) { setErr(e.message) }
  }
  const priceInput = (g, k, rate, step = '0.01') => (
    <input type="number" min="0" step={step} style={{ width: 80 }} placeholder={rate != null ? String(rate) : ''}
      value={prices[g]?.[k] ?? ''} onChange={(e) => setPrice(g, k, e.target.value)} />
  )
  const costs = it.spec.costs || []
  const total = costs.reduce((a, c) => a + (c.cost || 0), 0)
  return (
    <div className="panel frame-bom" style={{ margin: '10px 0', minWidth: 0 }}>
      <div className="row spread"><b>{it.name}: parts list{edited ? ' (edited for this quote)' : ' (read from the model)'}</b>
        {it.spec.joints_measured && <span className="small muted">Joints measured from the model</span>}</div>

      <h3>Prices for this quote</h3>
      <p className="small muted" style={{ marginTop: 0 }}>Enter what your distributor charges today. Blank uses your rate, shown in gray.</p>
      <table className="small">
        <thead><tr><th>Item</th><th>Unit</th><th>This quote</th></tr></thead>
        <tbody>
          {used.map(({ kind, id: cid }) => (
            <tr key={kind + cid}><td>{byId[kind]?.[cid]?.name || cid}</td><td className="muted">{unit[kind]}</td>
              <td>{priceInput(group[kind], cid, rateOf(kind, cid), kind === 'profile' ? '0.001' : '0.01')}</td></tr>
          ))}
          {ops.map((op) => <tr key={op}><td>{cat.machining.find((m) => m.id === op)?.name || op}</td><td className="muted">$/operation</td><td>{priceInput('machining', op, opRate[op])}</td></tr>)}
          {lines.some((l) => l.kind === 'profile') && (
            <tr><td>Supplier cut charge</td><td className="muted">$/cut</td>
              <td><input type="number" min="0" step="0.01" style={{ width: 80 }} placeholder={String(cat.config.cut_charge ?? '')} value={cut} onChange={(e) => setCut(e.target.value)} /></td></tr>
          )}
        </tbody>
      </table>
      <label className="f" style={{ maxWidth: 420, marginTop: 6 }}>Where the prices came from (optional)
        <input value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} placeholder="80/20 web cart, Oct 12" /></label>

      <h3>Parts</h3>
      <div style={{ overflowX: 'auto' }}>
        <table className="small">
          <thead><tr><th>Type</th><th>Item</th><th>Qty</th><th>Size (in)</th><th>Machining each</th><th>Price each</th><th /></tr></thead>
          <tbody>{lines.map((l, i) => (
            <tr key={i}>
              <td>{BOM_KIND[l.kind]}</td>
              <td style={{ minWidth: 170 }}>
                {l.kind === 'custom'
                  ? <input value={l.description || ''} placeholder="Latch, bracket, labor..." onChange={(e) => setLine(i, { description: e.target.value })} />
                  : <select value={l.catalog_id} onChange={(e) => setLine(i, { catalog_id: e.target.value })} style={{ maxWidth: 210 }}>
                    {(l.kind === 'profile' ? cat.profiles : l.kind === 'panel' ? cat.panels : cat.hardware.filter((h) => !h.family || h.family === byId.hardware[l.catalog_id]?.family || h.id === l.catalog_id))
                      .map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
                  </select>}
                {l.kind !== 'custom' && l.description && <div className="muted">{String(l.description).toLowerCase().slice(0, 80)}</div>}
              </td>
              <td><input type="number" min="0" step="1" style={{ width: 60 }} value={l.qty ?? ''} onChange={(e) => setLine(i, { qty: e.target.value === '' ? '' : Number(e.target.value) })} /></td>
              <td style={{ whiteSpace: 'nowrap' }}>
                {l.kind === 'profile' && <input type="number" min="0" step="0.0625" style={{ width: 75 }} value={l.length_in ?? ''} onChange={(e) => setLine(i, { length_in: e.target.value === '' ? '' : Number(e.target.value) })} />}
                {l.kind === 'panel' && <>
                  <input type="number" min="0" step="0.0625" style={{ width: 65 }} value={l.width_in ?? ''} onChange={(e) => setLine(i, { width_in: e.target.value === '' ? '' : Number(e.target.value) })} /> x{' '}
                  <input type="number" min="0" step="0.0625" style={{ width: 65 }} value={l.height_in ?? ''} onChange={(e) => setLine(i, { height_in: e.target.value === '' ? '' : Number(e.target.value) })} />
                </>}
              </td>
              <td style={{ whiteSpace: 'nowrap' }}>{l.kind === 'profile' && ['counterbore', 'miter_cut', 'end_tap'].map((op) => (
                <label key={op} className="muted" style={{ marginRight: 6 }}>{OPS[op]} <input type="number" min="0" max="100" step="1" style={{ width: 44 }}
                  value={(l.machining || []).find((o) => o.op === op)?.count ?? 0} onChange={(e) => setOp(i, op, Number(e.target.value) || 0)} /></label>
              ))}</td>
              <td>
                {l.kind === 'panel' ? <span className="muted">by sq ft</span>
                  : <input type="number" min="0" step="0.01" style={{ width: 80 }}
                    placeholder={l.kind === 'custom' ? 'required' : l.kind === 'profile' ? 'by inch' : String(prices.hardware?.[l.catalog_id] ?? rateOf('hardware', l.catalog_id) ?? '')}
                    title={l.kind === 'profile' ? 'Optional: the supplier price for one cut piece (material and cut). Blank prices it by the inch.' : ''}
                    value={l.unit_price ?? ''} onChange={(e) => setLine(i, { unit_price: e.target.value === '' ? null : Number(e.target.value) })} />}
              </td>
              <td><button className="link small" onClick={() => setLines(lines.filter((_, j) => j !== i))}>Remove</button></td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <div className="row" style={{ gap: 6, marginTop: 6 }}>
        <button className="small-btn" onClick={() => add('hardware')}>Add hardware</button>
        <button className="small-btn" onClick={() => add('custom')}>Add other item</button>
        <button className="small-btn" onClick={() => add('profile')}>Add extrusion cut</button>
        <button className="small-btn" onClick={() => add('panel')}>Add panel</button>
      </div>
      <label className="check" style={{ marginTop: 10 }}><input type="checkbox" checked={saveRates} onChange={(e) => setSaveRates(e.target.checked)} /> Also save these prices as my extrusion rates for future quotes</label>
      <div className="row" style={{ gap: 6, marginTop: 6 }}>
        <button className="primary" disabled={busy} onClick={() => save({ lines, prices, cut_charge: cut === '' ? null : cut, note })}>{busy ? 'Saving…' : 'Save and reprice'}</button>
        {edited && <button disabled={busy} onClick={() => save(null)}>Go back to the model's parts list and my rates</button>}
      </div>

      <h3>80/20 design checks</h3>
      <DesignChecks checks={it.spec.checks} />
      <h3>80/20 order list</h3>
      <Order8020 order={it.spec.order_8020} builds={it.qty || 1} />
      <div className="row" style={{ gap: 6, marginTop: 6 }}>
        <button className="small-btn" onClick={() => downloadSheet('purchase')}>Download purchase list</button>
        <button className="small-btn" onClick={() => downloadSheet('cut')}>Download cut list</button>
      </div>

      <h3>What it costs</h3>
      <div style={{ overflowX: 'auto' }}><table className="small">
        <tbody>{costs.map((c, j) => (
          <tr key={j}><td>{c.category}</td><td>{c.item}{c.note && <div className="muted">{c.note}</div>}</td>
            <td className="mono">{c.rate != null && c.hours == null ? `@ ${usd(c.rate)}` : c.hours != null ? `${c.hours} h` : ''}</td><td className="mono">{usd(c.cost)}</td></tr>
        ))}
          <tr><td /><td><b>Cost for one build</b> (before G&A, profit and per-lot costs)</td><td /><td className="mono"><b>{usd(total)}</b></td></tr></tbody>
      </table></div>
    </div>
  )
}

// Is the job worth it: the whole request at a glance (portal.money_summary).
function MoneySummary({ m }) {
  if (!m || !m.price) return null
  const saw = m.customer_saw || {}
  const sawText = saw.total != null ? usd(saw.total) : saw.total_low != null ? `${usd(saw.total_low)} to ${usd(saw.total_high)}` : ''
  const pct = (v) => (m.price ? `${Math.round((v / m.price) * 100)}%` : '')
  const split = m.split || {}
  const rows = [
    ['Bought material and hardware', split.bought, 'Extrusion, plate, casters, fasteners and parts you buy, plus 80/20 cuts and machining'],
    ['Material handling', split.handling, 'Your markup on bought material for ordering, receiving and paying for it up front'],
    ['Shop time', split.shop, 'Your labor and machine time at your shop rates: setup, machining, cutting, assembly, inspection'],
    ['Packaging and freight', split.ship, ''],
    ['Other', split.other, ''],
  ].filter((x) => x[1] > 0.5)
  const good = m.profit_pct != null && m.profit_pct >= 10
  return (
    <div className="panel" style={{ margin: '10px 0' }}>
      <div className="row spread" style={{ alignItems: 'baseline' }}>
        <h3 style={{ margin: 0 }}>Is it worth it?</h3>
        {sawText && <span className="small muted">Customer was shown {sawText}</span>}
      </div>
      <div className="grid g3" style={{ marginTop: 8 }}>
        <div><div className="small muted">Price (our number)</div><div style={{ fontSize: 22 }}><b>{usd(m.price)}</b></div></div>
        <div><div className="small muted">Your cost</div><div style={{ fontSize: 22 }}><b>{usd(m.cost)}</b></div></div>
        <div><div className="small muted">Profit after overhead and card fee</div>
          <div style={{ fontSize: 22 }} className={good ? 'okline' : 'due-soon'}><b>{usd(m.profit)}</b>{m.profit_pct != null && <span className="small"> ({m.profit_pct}%)</span>}</div></div>
      </div>
      {(m.shop_hours > 0 || m.profit_per_hour != null) && (
        <p className="small" style={{ margin: '8px 0 0' }}>About <b>{m.shop_hours} hours</b> of shop time{m.profit_per_hour != null ? <>, so about <b>{usd(m.profit_per_hour)}</b> profit per hour on top of the wages in your shop rates</> : ''}.
          {m.no_hours?.length > 0 && <span className="muted"> Hours not known for: {m.no_hours.join(', ')}.</span>}</p>
      )}
      <table className="small" style={{ marginTop: 8 }}>
        <tbody>
          {rows.map(([label, v, note]) => (
            <tr key={label}><td>{label}{note && <div className="muted">{note}</div>}</td><td className="mono">{usd(v)}</td><td className="mono muted">{pct(v)}</td></tr>
          ))}
          <tr><td><b>Your cost</b></td><td className="mono"><b>{usd(m.cost)}</b></td><td className="mono muted">{pct(m.cost)}</td></tr>
          <tr><td>Overhead (G&A, {Math.round(m.ga_rate * 100)}% of cost)<div className="muted">Rent, insurance, software, quoting time: the G&A rate in your shop rates</div></td><td className="mono">{usd(m.overhead)}</td><td className="mono muted">{pct(m.overhead)}</td></tr>
          {m.card_fee > 0 && <tr><td>Card fee allowance ({m.card_fee_pct}%)<div className="muted">Goes to Stripe if they pay by card, or comes off as the discount if they pay by check or transfer</div></td><td className="mono">{usd(m.card_fee)}</td><td className="mono muted">{pct(m.card_fee)}</td></tr>}
          <tr><td><b>Profit</b></td><td className="mono"><b>{usd(m.profit)}</b></td><td className="mono muted">{pct(m.profit)}</td></tr>
        </tbody>
      </table>
      {(m.unpriced?.length > 0 || m.uncosted?.length > 0) && (
        <p className="small due-soon" style={{ margin: '6px 0 0' }}>Not counted yet: {[...m.unpriced, ...m.uncosted].join(', ')} (no price or cost; set a final price or price it by hand).</p>
      )}
      <p className="small muted" style={{ margin: '6px 0 0' }}>These use your shop rates and extrusion prices. While those are still the placeholders, treat this as a rough guide.</p>
    </div>
  )
}

function ColumnKey() {
  return (
    <details style={{ marginTop: 8 }}>
      <summary className="small"><b>What the columns mean</b></summary>
      <dl className="small" style={{ margin: '6px 0 0' }}>
        <dt><b>Route</b></dt><dd>Instant: priced and orderable now. Estimate: shown as a range until you review it. Manual: no price; you price it.</dd>
        <dt><b>Setup (lot)</b></dt><dd>One-time cost for the whole order however many parts: programming, machine setup, first article, supplier order charge. It is why one part costs far more each than ten.</dd>
        <dt><b>Run (each)</b></dt><dd>Cost to make one more part: material, machine or cutting time, labor, inspection, packaging. Hover to see the split.</dd>
        <dt><b>Cost each</b></dt><dd>Your total cost per part at this quantity: run cost plus the setup spread over the quantity. Labor is at your shop rates, which include wages and shop overhead per hour.</dd>
        <dt><b>Tool price</b></dt><dd>What the pricing tool works out: cost, plus material handling, then G&A (overhead) and profit, plus the card fee allowance on the website. Before calibration.</dd>
        <dt><b>Calibration</b></dt><dd>A factor learned from the final prices you set on past jobs of the same kind (x1.10 means the tool ran 10% low before). None until you have set some.</dd>
        <dt><b>Price each</b></dt><dd>What the customer pays per part: the tool price after calibration, or your final price.</dd>
        <dt><b>Margin</b></dt><dd>(Price minus cost) divided by price. It includes the G&A share and the card fee allowance, so your profit is lower than the margin: see the summary above.</dd>
        <dt><b>Final price each</b></dt><dd>Type a price to replace the tool's. The customer sees it, and it is saved as a calibration sample.</dd>
      </dl>
    </details>
  )
}

// Material, finish and process for one line in review: the same choices the customer has, open to you even after they
// submit. Saving prices the request again.
let infoCache = null
const loadInfo = () => (infoCache ||= api.get('/api/public/info').catch((e) => { infoCache = null; throw e }))

function MadeAs({ it, info, change }) {
  const ed = it.editable || {}
  if (!info || !(ed.material || ed.finish || ed.process)) return null
  const mats = it.kind === 'flat' ? info.sheet_materials || [] : [...(info.materials || []), ...(info.print_materials || [])]
  const procs = it.options?.processes || []
  const assumed = (it.facts || []).some((f) => f.label === 'Material' && f.flag === 'assumed')
  return (
    <div className="row small" style={{ gap: 6, marginTop: 4, flexWrap: 'wrap', alignItems: 'center' }}>
      {ed.material && (
        <select value={it.material || ''} title="Material" style={assumed ? { borderColor: '#b26a00' } : undefined}
          onChange={(e) => change(it.key, { material: e.target.value, process: null, process_material: null })}>
          {!mats.includes(it.material) && it.material && <option>{it.material}</option>}
          {mats.map((m) => <option key={m}>{m}</option>)}
        </select>
      )}
      {ed.process && procs.length > 1 && (
        <select value={`${it.process}|${it.material}`} title="How it is made. Choosing Bought or Make it here is remembered for parts with this name on later quotes."
          onChange={(e) => { const [process, material] = e.target.value.split('|'); change(it.key, { process, process_material: material }) }}>
          {procs.map((o) => <option key={`${o.process}|${o.material}`} value={`${o.process}|${o.material}`}>{o.label}{o.process === '3d_print' ? ` (${o.material})` : ''}{o.unit_price != null ? `, ${usd(o.unit_price)}` : ''}</option>)}
        </select>
      )}
      {ed.finish && (
        <select value={it.finish && it.finish !== 'none' ? it.finish : 'none'} title="Finish" onChange={(e) => change(it.key, { finish: e.target.value })}>
          <option value="none">No finish</option>
          {(info.finishes || []).map((f) => <option key={f}>{f}</option>)}
        </select>
      )}
      {ed.infill && (
        <select value={it.infill || 40} title="Infill" onChange={(e) => change(it.key, { infill: Number(e.target.value) })}>
          {[20, 40, 60, 80, 100].map((v) => <option key={v} value={v}>{v}% infill</option>)}
        </select>
      )}
      {assumed && <span className="due-soon">material assumed</span>}
    </div>
  )
}

function LineTable({ r, id, setR, setMsg, setErr }) {
  const items = r.internal?.items || []
  const [finals, setFinals] = useState({})
  const [open, setOpen] = useState({})
  const [info, setInfo] = useState(null)
  const [busyKey, setBusyKey] = useState('')
  useEffect(() => { loadInfo().then(setInfo).catch(() => {}) }, [])
  const change = async (key, ch) => {
    setBusyKey(key); setErr('')
    try {
      const x = await api.put(`/api/portal/requests/${id}/lines`, { lines: { [key]: ch } })
      setR(x); setMsg('Changed and priced again. The customer sees the new price.')
    } catch (e) { setErr(e.message) } finally { setBusyKey('') }
  }
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
          <Fragment key={it.key}>
          <tr>
            <td style={{ minWidth: 200 }}><b>{it.name}</b>{it.group && <div className="muted">{it.group}</div>}<div className="muted">{it.desc}</div>
              <MadeAs it={it} info={info} change={change} />{busyKey === it.key && <div className="small muted">Pricing…</div>}
              {it.internal_reasons?.length > 0 && (
                <>
                  <button className="link small" onClick={() => setOpen({ ...open, [it.key]: !open[it.key] })}>{open[it.key] ? 'Hide notes' : `${it.internal_reasons.length} note(s)`}</button>
                  {open[it.key] && <ul className="clean muted" style={{ marginTop: 4 }}>{it.internal_reasons.slice(0, 8).map((x, j) => <li key={j}>{x}</li>)}</ul>}
                </>
              )}
              {it.spec?.costs && (
                <div><button className="link small" onClick={() => setOpen({ ...open, [`${it.key}#bom`]: !open[`${it.key}#bom`] })}>
                  {open[`${it.key}#bom`] ? 'Hide parts list' : 'Edit parts list and prices'}</button>
                  {(it.spec.bom?.lines || it.spec.bom?.prices || it.spec.bom?.cut_charge != null) && <span className="due-soon"> edited</span>}</div>
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
          </Fragment>
        ))}</tbody>
      </table>
      {items.filter((it) => open[`${it.key}#bom`] && it.spec?.costs).map((it) => <FrameBom key={it.key} it={it} id={id} setR={setR} setMsg={setMsg} setErr={setErr} />)}
    </div>
  )
}

// Past work on the customer site. Every entry is labeled by what it really was, and stays a hidden draft until you
// publish it: anything shown here is something a customer or contracting officer may ask you about.
function PastWork({ projects, setProjects, kinds, setErr }) {
  const [busy, setBusy] = useState(-1)
  const set = (i, ch) => setProjects(projects.map((p, j) => (j === i ? { ...p, ...ch } : p)))
  const move = (i, d) => { const out = [...projects]; const [x] = out.splice(i, 1); out.splice(i + d, 0, x); setProjects(out) }
  const upload = async (i, file) => {
    if (!file) return
    setBusy(i); setErr('')
    try {
      const f = new FormData(); f.append('file', file)
      const r = await api.upload('/api/portal/site-media', f)
      set(i, { image: r.name })
    } catch (e) { setErr(e.message) } finally { setBusy(-1) }
  }
  return (
    <div style={{ marginTop: 14 }}>
      <h4 style={{ margin: '0 0 4px' }}>Our work (past work)</h4>
      <p className="small muted" style={{ marginTop: 0 }}>Only list work you can back up. Pick what each entry really was; customers see that label. Entries stay hidden until you tick Published and save.</p>
      {projects.map((p, i) => (
        <div key={i} className="panel" style={{ marginBottom: 10 }}>
          <div className="grid g3">
            <label className="f">Title<input value={p.title || ''} maxLength={120} onChange={(e) => set(i, { title: e.target.value })} /></label>
            <label className="f">What it was
              <select value={p.kind || 'in_house'} onChange={(e) => set(i, { kind: e.target.value })}>
                {Object.entries(kinds).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select></label>
            <label className="f">Year<input value={p.year || ''} maxLength={12} onChange={(e) => set(i, { year: e.target.value })} /></label>
          </div>
          <label className="f" style={{ marginTop: 8 }}>Summary<textarea value={p.summary || ''} maxLength={1200} style={{ minHeight: 60 }} onChange={(e) => set(i, { summary: e.target.value })} /></label>
          <label className="f" style={{ marginTop: 8 }}>Details, one per line<textarea value={(p.details || []).join('\n')} style={{ minHeight: 60 }}
            onChange={(e) => set(i, { details: e.target.value.split('\n') })} /></label>
          <div className="row" style={{ gap: 10, marginTop: 8, alignItems: 'center' }}>
            {p.image && <img src={`/api/public/site-media/${p.image}`} alt="" style={{ height: 64, border: '1px solid var(--line, #ccc)' }} />}
            <label className="small">{p.image ? 'Replace photo' : 'Add a photo'} <input type="file" accept="image/png,image/jpeg,image/webp" disabled={busy === i} onChange={(e) => upload(i, e.target.files?.[0])} /></label>
            {p.image && <button className="link small" onClick={() => set(i, { image: '' })}>Remove photo</button>}
            {p.image && <input className="small" style={{ flex: 1, minWidth: 160 }} placeholder="Photo description, for screen readers" value={p.image_alt || ''} onChange={(e) => set(i, { image_alt: e.target.value })} />}
          </div>
          <div className="row" style={{ gap: 12, marginTop: 8 }}>
            {p.sample
              ? <span className="small due-soon">Sample for previewing the page: only you see it, signed in. Replace it with a real job; it can't be published.</span>
              : <label className="check"><input type="checkbox" checked={!!p.published} onChange={(e) => set(i, { published: e.target.checked })} /> <b>Published</b> (customers see it)</label>}
            {!p.published && !p.sample && <span className="small due-soon">Draft: only you see it, signed in</span>}
            {p.sample && <button className="link small" onClick={() => set(i, { sample: false, published: false })}>This is now a real job</button>}
            <span style={{ marginLeft: 'auto' }} />
            {i > 0 && <button className="link small" onClick={() => move(i, -1)}>Move up</button>}
            {i < projects.length - 1 && <button className="link small" onClick={() => move(i, 1)}>Move down</button>}
            <button className="link small" onClick={() => setProjects(projects.filter((_, j) => j !== i))}>Delete</button>
          </div>
        </div>
      ))}
      <button className="small-btn" onClick={() => setProjects([...projects, { title: '', kind: 'customer', year: String(new Date().getFullYear()), summary: '', details: [], published: false }])}>Add past work</button>
    </div>
  )
}

function PortalSettings({ onSaved }) {
  const [s, setS] = useState(null)
  const [site, setSite] = useState(null)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [projects, setProjects] = useState([])
  useEffect(() => { api.get('/api/portal/settings').then((v) => { setS(v); setSite(siteText(v.site)); setProjects(v.site.projects || []) }).catch((e) => setErr(e.message)) }, [])
  if (!s) return <p className="muted">{err || 'Loading…'}</p>
  const save = async () => {
    setErr(''); setMsg('')
    try { const { site: _ignored, site_defaults: _d, ...rest } = s; const v = await api.put('/api/portal/settings', { ...rest, site: { ...siteFrom(site), projects } }); setS(v); setSite(siteText(v.site)); setProjects(v.site.projects || []); setMsg('Saved.'); onSaved?.() } catch (e) { setErr(e.message) }
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
      <h3>T-slot frames in uploaded models</h3>
      <div className="grid g3">
        {f('frame_band_pct', 'Range above the price by % when the parts list is complete', 'number', { min: 0 })}
        <label className="f">Infill panels with no material in their name
          <select value={s.frame_panel_material || 'PC'} onChange={(e) => setS({ ...s, frame_panel_material: e.target.value })}>
            <option value="PC">Polycarbonate</option><option value="ACR">Acrylic</option><option value="ACM">Aluminum composite (ACM)</option>
          </select></label>
        <label className="check" style={{ alignSelf: 'end' }}><input type="checkbox" checked={s.frame_review ?? true} onChange={(e) => setS({ ...s, frame_review: e.target.checked })} /> An engineer confirms frames before they can be ordered</label>
      </div>
      <p className="small muted" style={{ margin: '4px 0 0' }}>The cut list, joints and hardware are read from the model. When every joint is measured the frame gets this narrow range instead of the estimate range above. Name panels with their material (polycarbonate, acrylic, ACM) to skip the default.</p>
      <label className="f" style={{ marginTop: 10 }}>Tagline<input value={s.tagline} onChange={(e) => setS({ ...s, tagline: e.target.value })} /></label>
      <label className="f" style={{ marginTop: 10 }}>Intro above the upload box<textarea value={s.intro} onChange={(e) => setS({ ...s, intro: e.target.value })} style={{ minHeight: 60 }} /></label>
      <label className="f" style={{ marginTop: 10 }}>Terms the customer accepts<textarea value={s.terms} onChange={(e) => setS({ ...s, terms: e.target.value })} style={{ minHeight: 70 }} /></label>
      <h3>Invoices</h3>
      <div className="grid g2">
        <label className="f">Remit-to address, printed on invoices<textarea value={s.remit_to || ''} onChange={(e) => setS({ ...s, remit_to: e.target.value })} style={{ minHeight: 80 }} placeholder={'Valley Power Systems LLC\nStreet\nCity, State ZIP'} /></label>
        <label className="f">How to pay, printed on invoices<textarea value={s.pay_instructions || ''} onChange={(e) => setS({ ...s, pay_instructions: e.target.value })} style={{ minHeight: 80 }} placeholder={'Bank transfer (ACH): bank name, routing and account number.\nChecks payable to Valley Power Systems LLC, mailed to the address above.'} /></label>
      </div>
      <p className="small muted" style={{ margin: '4px 0 0' }}>Only customers with an order see these, on their invoice. Approve net terms per customer in Customer accounts.</p>
      <div className="grid g3" style={{ marginTop: 8 }}>
        {f('card_fee_pct', 'Card fee allowance, % (0 to 4)', 'number', { min: 0, max: 4, step: 0.1 })}
      </div>
      <p className="small muted" style={{ margin: '4px 0 0' }}>Website prices include this so card payments cover the processing fee (Stripe is about 2.9% plus 30 cents).
        Invoices paid by check or bank transfer get the same percent off. This is a cash discount, which is allowed everywhere, unlike a card surcharge. Set 0 to turn it off.</p>
      <h3>Design assistant</h3>
      <label className="check"><input type="checkbox" checked={s.design_ai !== false} onChange={(e) => setS({ ...s, design_ai: e.target.checked })} /> Let customers describe a part to the AI on Design a part (needs ANTHROPIC_API_KEY in Render; without it they still get the sizes form, 3D model and price)</label>
      <div className="grid g2" style={{ marginTop: 6 }}>
        <label className="f">Most AI messages a day, all customers<input type="number" min="0" value={s.design_ai_daily ?? 300} onChange={(e) => setS({ ...s, design_ai_daily: Number(e.target.value) })} /></label>
      </div>
      <p className="small muted" style={{ margin: '4px 0 0' }}>Each message costs a few cents of API use. Each visitor is also limited to 40 messages an hour.</p>
      <h3>Order agreement</h3>
      <p className="small muted" style={{ marginTop: 0 }}>Customers who choose an invoice sign this online before you start. Schedule A (every line, price, PO and ship-to) is added automatically. Placeholders: {Object.entries(s.agreement_placeholders || {}).map(([k, v]) => `{${k}} ${v}`).join(', ')}. This is a starting point, not legal advice: have a business attorney in your state review it.</p>
      <textarea value={s.agreement_template || s.agreement_default || ''} onChange={(e) => setS({ ...s, agreement_template: e.target.value })} style={{ width: '100%', minHeight: 260, fontSize: 13 }} />
      {s.agreement_template && <button className="link" onClick={() => setS({ ...s, agreement_template: '' })}>Use the default text</button>}

      <h3 style={{ marginTop: 22 }}>What the site says about you</h3>
      <p className="small due-soon">This is suggested text. Read every line and change it so it matches what you actually do, in house or through partners. Customers will hold you to it.</p>
      {t('about', 'About us', 'A paragraph or two. Leave a blank line between paragraphs.', 4)}
      {t('capabilities', 'Capabilities', 'One per line, as Title: details', 9)}
      <div className="grid g2">
        {t('experience', 'Experience', 'One per line', 5)}
        {t('industries', 'Who you work with', 'One per line', 5)}
      </div>
      {t('quality', 'Quality and compliance', 'One per line', 5)}
      <PastWork projects={projects} setProjects={setProjects} kinds={s.project_kinds || {}} setErr={setErr} />
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
