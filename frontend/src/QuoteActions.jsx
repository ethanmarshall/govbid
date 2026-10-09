import { useEffect, useState } from 'react'
import { api, qs } from './api'

const usd = (n) => (n == null ? '' : `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`)
const LS_KEY = 'govbid.customerQuote.last'
const readLast = () => { try { return JSON.parse(localStorage.getItem(LS_KEY) || '{}') } catch { return {} } }
const BT_LABELS = { SB: 'Small', SDVOSB: 'SDVOSB', VOSB: 'VOSB', WOSB: 'WOSB', EDWOSB: 'EDWOSB', HUBZone: 'HUBZone', HUBZONE: 'HUBZone', '8A': '8(a)' }

// Customer quote document and vendor RFQs for one saved part quote.
export default function QuoteActions({ quoteId, refreshKey }) {
  const [open, setOpen] = useState('')
  if (!quoteId) return null
  return (
    <div className="panel quote-actions">
      <div className="row">
        <button className={open === 'customer' ? 'primary' : ''} onClick={() => setOpen(open === 'customer' ? '' : 'customer')}>Customer quote</button>
        <button className={open === 'rfq' ? 'primary' : ''} onClick={() => setOpen(open === 'rfq' ? '' : 'rfq')}>Request vendor quotes</button>
      </div>
      {open === 'customer' && <CustomerQuote key={`${quoteId}-${refreshKey}`} quoteId={quoteId} />}
      {open === 'rfq' && <VendorRfq key={`${quoteId}-${refreshKey}`} quoteId={quoteId} />}
    </div>
  )
}

// ------------------------------------------------------------ customer quote
function CustomerQuote({ quoteId }) {
  const [data, setData] = useState(null)
  const [form, setForm] = useState(null)
  const [err, setErr] = useState('')
  const [showDefaults, setShowDefaults] = useState(false)

  const load = () => api.get(`/api/quote-tools/${quoteId}/customer-quote`).then((d) => {
    setData(d)
    const last = readLast()
    const o = d.options || {}
    const s = d.settings || {}
    const pick = (k, fallback) => o[k] ?? last[k] ?? fallback ?? ''
    setForm({
      customer_name: o.customer_name ?? d.customer.name ?? '',
      attn: o.attn ?? '',
      validity_days: pick('validity_days', s.validity_days),
      fob: pick('fob', s.fob),
      payment_terms: pick('payment_terms', s.payment_terms),
      shipping: pick('shipping', s.shipping),
      inspection_acceptance: pick('inspection_acceptance', s.inspection_acceptance),
      packaging: o.packaging ?? '',
      notes: o.notes ?? '',
      quantities: (o.quantities && o.quantities.length ? o.quantities : d.available_quantities),
    })
  }).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [quoteId])

  if (err) return <p className="err" style={{ marginTop: 12 }}>{err}</p>
  if (!data || !form) return <p className="muted small">Loading…</p>
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const toggleQty = (q) => setForm({ ...form, quantities: form.quantities.includes(q) ? form.quantities.filter((x) => x !== q) : [...form.quantities, q].sort((a, b) => a - b) })
  const lines = data.lines.length ? data.lines : []
  const shown = (data.available_quantities || []).filter((q) => form.quantities.includes(q))

  const download = (ext) => {
    if (!form.quantities.length) { setErr('Pick at least one quantity.'); return }
    const { quantities, ...rest } = form
    try { localStorage.setItem(LS_KEY, JSON.stringify({ validity_days: rest.validity_days, fob: rest.fob, payment_terms: rest.payment_terms, shipping: rest.shipping, inspection_acceptance: rest.inspection_acceptance })) } catch {}
    const url = `/api/quote-tools/${quoteId}/customer-quote.${ext}?${qs({ ...rest, quantities: quantities.join(',') })}`
    const a = document.createElement('a')
    a.href = url
    a.download = ''
    a.click()
  }

  return (
    <div style={{ marginTop: 14 }}>
      <div className="row spread">
        <h2 style={{ margin: 0 }}>Customer quote {data.number}</h2>
        <span className="small muted">Shows prices and lead times only. Internal cost and margin never appear.</span>
      </div>
      <div className="grid g3" style={{ marginTop: 10 }}>
        <label className="f">Customer<input value={form.customer_name} onChange={set('customer_name')} placeholder="Agency or prime" /></label>
        <label className="f">Attention<input value={form.attn} onChange={set('attn')} placeholder="Buyer or contracting officer" /></label>
        <label className="f">Valid for (days)<input type="number" min="1" max="365" value={form.validity_days} onChange={set('validity_days')} /></label>
        <label className="f">FOB<input value={form.fob} onChange={set('fob')} /></label>
        <label className="f">Payment terms<input value={form.payment_terms} onChange={set('payment_terms')} /></label>
        <label className="f">Packaging<input value={form.packaging} onChange={set('packaging')} placeholder={data.terms.packaging} /></label>
        <label className="f">Shipping<input value={form.shipping} onChange={set('shipping')} /></label>
        <label className="f">Inspection and acceptance<input value={form.inspection_acceptance} onChange={set('inspection_acceptance')} /></label>
        <div className="f">
          <span className="small muted">Quantities to show</span>
          <div className="row" style={{ marginTop: 4 }}>
            {(data.available_quantities || []).map((q) => (
              <button key={q} className={`chip ${form.quantities.includes(q) ? 'on' : ''}`} onClick={() => toggleQty(q)}>{q}</button>
            ))}
          </div>
        </div>
        <label className="f" style={{ gridColumn: '1 / -1' }}>Notes<textarea value={form.notes} onChange={set('notes')} style={{ minHeight: 50 }} placeholder="Exceptions, assumptions, first article, source approval status" /></label>
      </div>
      {lines.length > 0 && (
        <table className="small" style={{ marginTop: 10 }}>
          <thead><tr><th>Quantity</th><th>Unit price</th><th>Extended</th><th>Lead time</th></tr></thead>
          <tbody>
            {lines.filter((l) => shown.includes(l.quantity) || !shown.length).map((l) => (
              <tr key={l.quantity}><td>{l.quantity}</td><td>{usd(l.unit_price)}</td><td>{usd(l.extended_price)}</td><td>{l.lead_time}</td></tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="row" style={{ marginTop: 10 }}>
        <button className="primary" onClick={() => download('pdf')}>Download PDF</button>
        <button onClick={() => download('docx')}>Download Word</button>
        <button className="link small" onClick={() => setShowDefaults(!showDefaults)}>{showDefaults ? 'Hide defaults' : 'Edit defaults and letterhead'}</button>
      </div>
      <p className="small muted" style={{ marginTop: 6 }}>Letterhead comes from Profile (name, UEI, CAGE) and Capability statement (contact, phone, email, website). The mailing address and the defaults below are set here.</p>
      {showDefaults && <QuoteDefaults onSaved={load} />}
    </div>
  )
}

function QuoteDefaults({ onSaved }) {
  const [s, setS] = useState(null)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  useEffect(() => { api.get('/api/quote-tools/settings').then(setS).catch((e) => setErr(e.message)) }, [])
  if (!s) return err ? <p className="err">{err}</p> : null
  const set = (k) => (e) => setS({ ...s, [k]: e.target.value })
  const save = async () => {
    setErr(''); setMsg('')
    try { setS(await api.put('/api/quote-tools/settings', { ...s, validity_days: Number(s.validity_days) })); setMsg('Defaults saved.'); onSaved?.() } catch (e) { setErr(e.message) }
  }
  return (
    <div className="panel" style={{ marginTop: 10, background: '#fbfaf7' }}>
      <h3 style={{ marginTop: 0 }}>Defaults for every customer quote</h3>
      <div className="grid g3">
        <label className="f">Valid for (days)<input type="number" value={s.validity_days} onChange={set('validity_days')} /></label>
        <label className="f">Payment terms<input value={s.payment_terms} onChange={set('payment_terms')} /></label>
        <label className="f">FOB<input value={s.fob} onChange={set('fob')} /></label>
        <label className="f">Shipping<input value={s.shipping} onChange={set('shipping')} /></label>
        <label className="f">Inspection and acceptance<input value={s.inspection_acceptance} onChange={set('inspection_acceptance')} /></label>
        <label className="f">Mailing address (one line per row)<textarea value={s.address} onChange={set('address')} style={{ minHeight: 50 }} /></label>
        <label className="f" style={{ gridColumn: '1 / -1' }}>Footer text<textarea value={s.footer_text} onChange={set('footer_text')} style={{ minHeight: 40 }} /></label>
      </div>
      <div className="row" style={{ marginTop: 8 }}>
        <button onClick={save}>Save defaults</button>
        {msg && <span className="small okline">{msg}</span>}
        {err && <span className="small due-soon">{err}</span>}
      </div>
    </div>
  )
}

// ------------------------------------------------------------ vendor RFQs
function VendorRfq({ quoteId }) {
  const [vendors, setVendors] = useState(null)
  const [rfqs, setRfqs] = useState([])
  const [check, setCheck] = useState(null)
  const [picked, setPicked] = useState([])
  const [form, setForm] = useState({ due_date: '', message: '', include_files: true, quantities: '' })
  const [warn, setWarn] = useState([])
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const loadRfqs = () => api.get(`/api/quote-tools/${quoteId}/rfqs`).then(setRfqs).catch((e) => setErr(e.message))
  useEffect(() => {
    api.get('/api/quote-tools/vendors').then(setVendors).catch((e) => setErr(e.message))
    api.get(`/api/quote-tools/${quoteId}/export-check`).then(setCheck).catch(() => {})
    api.get(`/api/pricing/quotes/${quoteId}`).then((q) => setForm((f) => ({ ...f, quantities: (q.price_breaks || []).map((b) => b.quantity).join(', ') }))).catch(() => {})
    loadRfqs()
  }, [quoteId])

  const toggle = (id) => setPicked(picked.includes(id) ? picked.filter((x) => x !== id) : [...picked, id])
  const create = async () => {
    setErr(''); setWarn([]); setBusy(true)
    try {
      const quantities = form.quantities.split(/[\s,]+/).filter(Boolean).map(Number).filter((n) => n > 0)
      const r = await api.post(`/api/quote-tools/${quoteId}/rfq`, { vendor_ids: picked, due_date: form.due_date, message: form.message, include_files: form.include_files, quantities })
      setWarn(r.warnings || [])
      setPicked([])
      await loadRfqs()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <div style={{ marginTop: 14 }}>
      <h2>Request vendor quotes</h2>
      {err && <p className="err">{err}</p>}
      {check?.flagged && (
        <div className="notice">
          <b>Controlled technical data.</b> {check.reasons.join(' ')} Files will not go in the package. Send drawings only to vendors that hold an active JCP certification (DD Form 2345) and are authorized recipients, with the markings intact.
        </div>
      )}
      {vendors && vendors.length === 0 && <p className="muted small">No vendors yet. Add shops in Contacts with the kind "vendor".</p>}
      {vendors && vendors.length > 0 && (
        <table className="small">
          <thead><tr><th></th><th>Vendor</th><th>Size and status</th><th>Email</th><th>Location</th></tr></thead>
          <tbody>
            {vendors.map((v) => (
              <tr key={v.id} className="click" onClick={() => toggle(v.id)}>
                <td><input type="checkbox" checked={picked.includes(v.id)} onChange={() => toggle(v.id)} onClick={(e) => e.stopPropagation()} /></td>
                <td><div className="t">{v.name}</div>{v.capabilities && <div className="muted">{v.capabilities.slice(0, 90)}</div>}</td>
                <td className="row" style={{ gap: 4 }}>
                  {Object.keys(v.business_types).map((k) => <span key={k} className="tag">{BT_LABELS[k] || k}</span>)}
                  {v.is_manufacturer && <span className="tag">Manufacturer</span>}
                  {!Object.keys(v.business_types).length && !v.is_manufacturer && <span className="muted">not recorded</span>}
                </td>
                <td>{v.email || <span className="muted">none on file</span>}</td>
                <td>{[v.city, v.state].filter(Boolean).join(', ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="grid g3" style={{ marginTop: 10 }}>
        <label className="f">Reply by<input type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} /></label>
        <label className="f">Quantities<input value={form.quantities} onChange={(e) => setForm({ ...form, quantities: e.target.value })} placeholder="10, 50, 100" /></label>
        <label className="check" style={{ alignSelf: 'end' }}><input type="checkbox" checked={form.include_files} onChange={(e) => setForm({ ...form, include_files: e.target.checked })} /> Include STEP, drawing and BOM in the package</label>
        <label className="f" style={{ gridColumn: '1 / -1' }}>Message<textarea value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })} style={{ minHeight: 50 }} placeholder="Context for the vendor, for example: government buy, repeat order, delivery needs" /></label>
      </div>
      <div className="row" style={{ marginTop: 8 }}>
        <button className="primary" disabled={!picked.length || busy} onClick={create}>Create {picked.length || ''} request{picked.length === 1 ? '' : 's'}</button>
        <span className="small muted">Creates an email draft and a file package for each vendor. Nothing is sent automatically.</span>
      </div>
      {warn.length > 0 && <div className="notice" style={{ marginTop: 10 }}><ul className="clean">{warn.map((w, i) => <li key={i}>{w}</li>)}</ul></div>}

      {rfqs.length > 0 && (
        <>
          <h3>Requests ({rfqs.length})</h3>
          <p className="small muted">"Open in email" starts a draft in your mail app. Email links cannot carry attachments, so download the package and attach it yourself.</p>
          {rfqs.map((r) => <RfqCard key={r.id} r={r} onChanged={loadRfqs} />)}
        </>
      )}
    </div>
  )
}

function RfqCard({ r, onChanged }) {
  const [show, setShow] = useState(false)
  const [resp, setResp] = useState(null)
  const [copied, setCopied] = useState(false)
  const [err, setErr] = useState('')

  const copy = async () => {
    try { await navigator.clipboard.writeText(`Subject: ${r.subject}\n\n${r.body}`); setCopied(true); setTimeout(() => setCopied(false), 1500) } catch { setErr('Copy failed. Select the text and copy it by hand.') }
  }
  const act = async (fn) => { setErr(''); try { await fn(); onChanged() } catch (e) { setErr(e.message) } }
  const startResp = () => setResp({
    prices: (r.response?.prices?.length ? r.response.prices : r.quantities.map((q) => ({ quantity: q, unit_price: '' }))).map((p) => ({ ...p })),
    lead_days: r.response?.lead_days ?? '', tooling_charge: r.response?.tooling_charge || '', freight: r.response?.freight || '',
    quote_ref: r.response?.quote_ref || '', valid_until: r.response?.valid_until || '', notes: r.response_notes || '',
  })
  const saveResp = () => act(async () => {
    const num = (v) => (v === '' || v == null ? null : Number(v))
    await api.post(`/api/quote-tools/rfqs/${r.id}/response`, {
      prices: resp.prices.filter((p) => p.unit_price !== '' && p.quantity).map((p) => ({ quantity: Number(p.quantity), unit_price: Number(p.unit_price) })),
      lead_days: num(resp.lead_days), tooling_charge: num(resp.tooling_charge), freight: num(resp.freight),
      quote_ref: resp.quote_ref, valid_until: resp.valid_until, notes: resp.notes,
    })
    setResp(null)
  })

  return (
    <div className="card rfq-card">
      <div className="row spread">
        <div className="row">
          <b>{r.vendor_name}</b>
          <span className={`tag rfq-${r.status}`}>{r.status}</span>
          {r.due_date && <span className={`small ${r.overdue ? 'due-soon' : 'muted'}`}>reply by {r.due_date}{r.overdue ? ' (overdue)' : ''}</span>}
          {r.files_blocked && <span className="small due-soon">files held back</span>}
        </div>
        <select value={r.status} onChange={(e) => act(() => api.put(`/api/quote-tools/rfqs/${r.id}`, { status: e.target.value }))}>
          {['sent', 'awaiting', 'responded', 'declined'].map((s) => <option key={s}>{s}</option>)}
        </select>
      </div>
      <div className="small muted" style={{ marginTop: 4 }}>{r.subject}</div>
      {r.response && (
        <div className="small" style={{ marginTop: 4 }}>
          Response: {r.response.prices.map((p) => `${p.quantity} at ${usd(p.unit_price)}`).join(', ')}{r.response.lead_days != null ? `, ${r.response.lead_days} days` : ''}. Shown in Make or buy.
        </div>
      )}
      <div className="row" style={{ marginTop: 8 }}>
        <button className="link small" onClick={() => setShow(!show)}>{show ? 'Hide email' : 'Show email'}</button>
        <button onClick={copy}>{copied ? 'Copied' : 'Copy'}</button>
        <a className="btn" href={r.mailto} title={r.vendor_email ? '' : 'No email on file: add the address in your mail app'}>Open in email</a>
        <a className="btn" href={`/api/quote-tools/rfqs/${r.id}/package.zip`}>Download package</a>
        <span className="small muted">{r.package_files.join(', ')}</span>
        <button onClick={resp ? () => setResp(null) : startResp}>{resp ? 'Cancel' : 'Record response'}</button>
        {r.status !== 'declined' && <button className="link small" onClick={() => act(() => api.post(`/api/quote-tools/rfqs/${r.id}/decline`, {}))}>Mark declined</button>}
        <button className="link small" onClick={() => window.confirm('Delete this request?') && act(() => api.del(`/api/quote-tools/rfqs/${r.id}`))}>Delete</button>
      </div>
      {err && <p className="err" style={{ marginTop: 8 }}>{err}</p>}
      {show && <pre className="desc mono small rfq-body">{r.body}</pre>}
      {resp && (
        <div style={{ marginTop: 10 }}>
          <table className="small" style={{ maxWidth: 420 }}>
            <thead><tr><th>Quantity</th><th>Unit price ($)</th><th></th></tr></thead>
            <tbody>
              {resp.prices.map((p, i) => (
                <tr key={i}>
                  <td><input type="number" value={p.quantity} onChange={(e) => { const prices = [...resp.prices]; prices[i] = { ...p, quantity: e.target.value }; setResp({ ...resp, prices }) }} style={{ width: 90 }} /></td>
                  <td><input type="number" step="0.01" value={p.unit_price} onChange={(e) => { const prices = [...resp.prices]; prices[i] = { ...p, unit_price: e.target.value }; setResp({ ...resp, prices }) }} style={{ width: 110 }} /></td>
                  <td><button className="link small" onClick={() => setResp({ ...resp, prices: resp.prices.filter((_, j) => j !== i) })}>Remove</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          <button className="link small" onClick={() => setResp({ ...resp, prices: [...resp.prices, { quantity: '', unit_price: '' }] })}>Add quantity</button>
          <div className="grid g4" style={{ marginTop: 8 }}>
            <label className="f">Lead time (days ARO)<input type="number" value={resp.lead_days} onChange={(e) => setResp({ ...resp, lead_days: e.target.value })} /></label>
            <label className="f">Tooling or setup ($)<input type="number" value={resp.tooling_charge} onChange={(e) => setResp({ ...resp, tooling_charge: e.target.value })} /></label>
            <label className="f">Freight ($)<input type="number" value={resp.freight} onChange={(e) => setResp({ ...resp, freight: e.target.value })} /></label>
            <label className="f">Their quote no.<input value={resp.quote_ref} onChange={(e) => setResp({ ...resp, quote_ref: e.target.value })} /></label>
            <label className="f">Valid until<input type="date" value={resp.valid_until} onChange={(e) => setResp({ ...resp, valid_until: e.target.value })} /></label>
            <label className="f" style={{ gridColumn: 'span 3' }}>Notes<input value={resp.notes} onChange={(e) => setResp({ ...resp, notes: e.target.value })} /></label>
          </div>
          <div className="row" style={{ marginTop: 8 }}>
            <button className="primary" onClick={saveResp}>Save response</button>
            <span className="small muted">Saved as a vendor quote, so Make or buy compares it with your in-house price.</span>
          </div>
        </div>
      )}
    </div>
  )
}
