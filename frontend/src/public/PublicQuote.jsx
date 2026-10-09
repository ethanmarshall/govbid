import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import './public.css'

// Customer-facing quote page (/quote) and request status page (/quote/status/:ref?t=token).
// Talks only to /api/public/*: no login, no internal data.

const money = (n, cents = true) => (n == null ? '' : `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: cents ? 2 : 0, maximumFractionDigits: cents ? 2 : 0 })}`)
const range = (lo, hi) => `${money(lo, lo < 100)} to ${money(hi, hi < 100)}`

async function call(method, url, body, form) {
  const opts = { method, headers: {} }
  if (form) opts.body = form
  else if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body) }
  const res = await fetch(url, opts)
  let data = null
  try { data = await res.json() } catch { /* not json */ }
  if (!res.ok) throw new Error((data && (typeof data.detail === 'string' ? data.detail : null)) || `Something went wrong (${res.status}). Try again.`)
  return data
}

function Sheet({ info, children }) {
  return (
    <div className="pq">
      <div className="pq-sheet">
        <div className="pq-zones pq-zones-top" aria-hidden="true">{[1, 2, 3, 4, 5, 6].map((n) => <span key={n}>{n}</span>)}</div>
        <div className="pq-zones pq-zones-side" aria-hidden="true">{['A', 'B', 'C', 'D'].map((n) => <span key={n}>{n}</span>)}</div>
        <header className="pq-head">
          <div>
            <div className="pq-name">{info?.name || 'Quote request'}</div>
            {info?.tagline && <p className="pq-tagline">{info.tagline}</p>}
          </div>
          {(info?.contact_email || info?.contact_phone) && (
            <div className="pq-contact">
              {info.contact_email && <a href={`mailto:${info.contact_email}`}>{info.contact_email}</a>}
              {info.contact_phone && <a href={`tel:${info.contact_phone.replace(/[^0-9+]/g, '')}`}>{info.contact_phone}</a>}
            </div>
          )}
        </header>
        {children}
      </div>
    </div>
  )
}

export default function PublicQuote() {
  const loc = useLocation()
  const [info, setInfo] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { document.title = 'Get a quote'; call('GET', '/api/public/info').then(setInfo).catch((e) => setErr(e.message)) }, [])
  useEffect(() => { if (info?.name) document.title = `Get a quote from ${info.name}` }, [info?.name])
  const m = loc.pathname.match(/^\/quote\/status\/([A-Za-z0-9-]+)/)
  if (!info) return <Sheet info={null}><p className="pq-muted pq-pad">{err || 'Loading…'}</p></Sheet>
  if (m) return <Sheet info={info}><Status refId={m[1]} token={new URLSearchParams(loc.search).get('t') || ''} info={info} /></Sheet>
  if (!info.enabled) {
    return (
      <Sheet info={info}>
        <div className="pq-closed">
          <h1>Online quotes are not open yet</h1>
          <p>Send your drawings or models{info.contact_email ? <> to <a href={`mailto:${info.contact_email}`}>{info.contact_email}</a></> : ' to us by email'} and we will reply with a price.</p>
        </div>
      </Sheet>
    )
  }
  return <Sheet info={info}><QuoteForm info={info} /></Sheet>
}

function QuoteForm({ info }) {
  const [files, setFiles] = useState([])
  const [qty, setQty] = useState('1')
  const [material, setMaterial] = useState('')
  const [finish, setFinish] = useState('')
  const [thickness, setThickness] = useState('')
  const [notes, setNotes] = useState('')
  const [controlled, setControlled] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [req, setReq] = useState(null) // public view + token
  const [stale, setStale] = useState(false) // files changed since the price
  const [drag, setDrag] = useState(false)
  const input = useRef()
  const block = useRef()
  const timer = useRef()
  const hasDxf = files.some((f) => /\.dxf$/i.test(f.name))
  const extraSheet = useMemo(() => (info.sheet_materials || []).filter((x) => !info.materials.includes(x)), [info])

  const addFiles = (list) => {
    const next = [...files]
    for (const f of list) if (!next.some((x) => x.name === f.name && x.size === f.size)) next.push(f)
    setFiles(next.slice(0, info.max_files))
    setStale(!!req)
    setErr(next.length > info.max_files ? `Up to ${info.max_files} files. Zip PCB files together.` : '')
  }
  const removeFile = (i) => { setFiles(files.filter((_, j) => j !== i)); setStale(!!req) }

  const getPrice = async () => {
    setBusy(true); setErr('')
    const form = new FormData()
    if (!controlled) files.forEach((f) => form.append('files', f))
    form.append('quantity', String(Math.max(1, parseInt(qty, 10) || 1)))
    form.append('material', material)
    form.append('finish', finish)
    form.append('thickness', thickness)
    form.append('notes', notes)
    form.append('export_controlled', controlled ? 'true' : 'false')
    form.append('website', '')
    try {
      const r = await call('POST', '/api/public/quote', undefined, form)
      setReq(r); setStale(false)
      setTimeout(() => { if (window.matchMedia('(max-width: 899px)').matches) block.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }, 50)
    } catch (e) { setErr(e.message) }
    setBusy(false)
  }

  // after a price: quantity, material, finish and thickness reprice without uploading again
  useEffect(() => {
    if (!req || req.submitted || stale) return
    clearTimeout(timer.current)
    timer.current = setTimeout(async () => {
      try {
        const r = await call('POST', `/api/public/quote/${req.ref}/options`, { token: req.token, quantity: Math.max(1, parseInt(qty, 10) || 1), material, finish, thickness: thickness === '' ? null : Number(thickness) })
        setReq((old) => ({ ...r, token: old.token })); setErr('')
      } catch (e) { setErr(e.message) }
    }, 450)
    return () => clearTimeout(timer.current)
  }, [qty, material, finish, thickness])

  const res = req?.result
  return (
    <div className="pq-body">
      <section className="pq-form" aria-label="Your project">
        <h1>Upload your files, get a price</h1>
        <p className="pq-intro">{info.intro}</p>

        {!controlled && (
          <div className={`pq-drop ${drag ? 'over' : ''}`} onClick={() => input.current.click()} role="button" tabIndex={0}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.current.click() } }}
            onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files) }}>
            <input ref={input} type="file" multiple hidden accept={info.accept} onChange={(e) => { addFiles(e.target.files); e.target.value = '' }} />
            <div className="pq-drop-main">Drop your files here, or choose files</div>
            <div className="pq-drop-sub">3D model (STEP), drawing (PDF), flat pattern (DXF), or circuit board files (zip of Gerbers, BOM and pick-and-place). Up to {info.max_files} files, {info.max_file_mb} MB each.</div>
          </div>
        )}
        {files.length > 0 && !controlled && (
          <ul className="pq-files">
            {files.map((f, i) => (
              <li key={i}><span>{f.name}</span><span className="pq-muted">{f.size < 102400 ? `${Math.max(1, Math.round(f.size / 1024))} KB` : `${(f.size / 1048576).toFixed(1)} MB`}</span>
                <button type="button" className="pq-link" onClick={() => removeFile(i)} aria-label={`Remove ${f.name}`}>Remove</button></li>
            ))}
          </ul>
        )}

        <div className="pq-fields">
          <label>Quantity<input type="number" min="1" max={info.max_quantity} step="1" inputMode="numeric" value={qty} onChange={(e) => setQty(e.target.value)} /></label>
          <label>Material
            <select value={material} onChange={(e) => setMaterial(e.target.value)}>
              <option value="">Not sure, use the drawing</option>
              <optgroup label="Metals and plastics">{info.materials.map((x) => <option key={x}>{x}</option>)}</optgroup>
              <optgroup label="3D printing">{info.print_materials.map((x) => <option key={x}>{x}</option>)}</optgroup>
              {extraSheet.length > 0 && <optgroup label="Sheet goods (flat parts)">{extraSheet.map((x) => <option key={x}>{x}</option>)}</optgroup>}
            </select>
          </label>
          <label>Finish
            <select value={finish} onChange={(e) => setFinish(e.target.value)}>
              <option value="">From the drawing</option>
              <option value="none">None</option>
              {info.finishes.map((x) => <option key={x}>{x}</option>)}
            </select>
          </label>
          {(hasDxf || res?.kind === 'needs_input') && (
            <label className={res?.kind === 'needs_input' && !thickness ? 'pq-ask' : ''}>Sheet thickness (inches)
              <input type="number" min="0.005" max="6" step="any" inputMode="decimal" placeholder="0.125" value={thickness} onChange={(e) => setThickness(e.target.value)} />
            </label>
          )}
        </div>
        <label className="pq-notes">Anything we should know
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={3000} placeholder="Tolerances, finishes, certifications, delivery date, how the parts go together" />
        </label>
        <label className="pq-check">
          <input type="checkbox" checked={controlled} onChange={(e) => { setControlled(e.target.checked); setStale(!!req) }} />
          <span>My project includes export-controlled (ITAR/EAR) technical data. <span className="pq-muted">Don't upload it here. Check this and send your contact details, and we will arrange a secure transfer.</span></span>
        </label>

        {err && <p className="pq-err" role="alert">{err}</p>}
        <div className="pq-actions">
          <button type="button" className="pq-btn" disabled={busy || (!files.length && !controlled && !notes.trim())} onClick={getPrice}>
            {busy ? 'Pricing your files…' : req && !stale ? 'Price again' : 'Get price'}
          </button>
          {stale && <span className="pq-muted">Your files changed. Get the price again.</span>}
        </div>
      </section>

      <aside className="pq-side" ref={block} aria-live="polite">
        <TitleBlock req={req} info={info} qty={qty} material={material} busy={busy} />
        {req && !stale && res?.kind !== 'needs_input' && <SubmitForm req={req} setReq={setReq} info={info} />}
      </aside>
    </div>
  )
}

function TitleBlock({ req, info, qty, material, busy }) {
  const res = req?.result
  const kind = res?.kind
  const q = res?.quantity || Math.max(1, parseInt(qty, 10) || 1)
  return (
    <div className={`pq-tb ${kind ? `k-${kind}` : ''}`}>
      <div className="pq-tb-row">
        <div className="pq-cell"><span>Quote</span><b>{req?.ref || 'Not priced yet'}</b></div>
        <div className="pq-cell"><span>Quantity</span><b>{q.toLocaleString()}</b></div>
      </div>
      <div className="pq-tb-row">
        <div className="pq-cell wide"><span>Material</span><b>{req?.material || material || 'From the drawing'}</b></div>
      </div>
      <div className="pq-tb-price">
        {busy && !res && <p className="pq-muted">Reading your files…</p>}
        {!res && !busy && <p className="pq-muted">Your price appears here. Add your files and choose Get price.</p>}
        {kind === 'instant' && (
          <>
            <span className="pq-kind">Instant quote</span>
            <div className="pq-big">{money(res.unit_price)}<small> each</small></div>
            <div className="pq-total">{money(res.total)} for {q.toLocaleString()}</div>
          </>
        )}
        {kind === 'estimate' && (
          <>
            <span className="pq-kind">Estimate, confirmed after review</span>
            <div className="pq-big pq-range">{range(res.unit_low, res.unit_high)}<small> each</small></div>
            <div className="pq-total">{range(res.total_low, res.total_high)} for {q.toLocaleString()}</div>
          </>
        )}
        {(kind === 'manual' || kind === 'needs_input') && <span className="pq-kind">{kind === 'manual' ? 'Priced by an engineer' : 'One more detail'}</span>}
        {res?.message && <p className="pq-msg">{res.message}</p>}
      </div>
      {res?.lead_days ? <div className="pq-tb-row"><div className="pq-cell wide"><span>Ships in about</span><b>{res.lead_days} days after the order is confirmed</b></div></div> : null}
      {res?.items?.length > 0 && (res.items.length > 1 || res.items.some((i) => i.note)) && (
        <ul className="pq-items">
          {res.items.map((it, i) => (
            <li key={i}>
              <div className="pq-item-top"><b>{it.name}</b>
                <span>{it.unit_price != null ? money(it.unit_price) : it.unit_low != null ? range(it.unit_low, it.unit_high) : 'by review'}</span></div>
              <div className="pq-muted">{it.desc}</div>
              {it.note && <div className="pq-note">{it.note}</div>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function SubmitForm({ req, setReq, info }) {
  const [f, setF] = useState({ name: '', company: '', email: '', phone: '', needed_by: '', notes: '', accept_terms: false })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [copied, setCopied] = useState(false)
  const kind = req.result?.kind
  const action = kind === 'instant' ? 'Place order request' : 'Request review'
  const link = `${window.location.origin}/quote/status/${req.ref}?t=${encodeURIComponent(req.token)}`
  if (req.submitted) {
    return (
      <div className="pq-done">
        <h2>{kind === 'instant' ? 'Order request sent' : 'Review requested'}</h2>
        <p>Your request is <b>{req.ref}</b>. {kind === 'instant'
          ? 'We will confirm the order and delivery date with you before we start.'
          : `An engineer will review your files and contact you within ${info.review_days} business day${info.review_days === 1 ? '' : 's'} to confirm what you need and the final cost.`}</p>
        <p className="pq-muted">Keep this link to check on your request:</p>
        <div className="pq-linkrow"><input readOnly value={link} onFocus={(e) => e.target.select()} aria-label="Status link" />
          <button type="button" className="pq-btn ghost" onClick={() => { navigator.clipboard?.writeText(link).then(() => setCopied(true)).catch(() => {}) }}>{copied ? 'Copied' : 'Copy link'}</button></div>
      </div>
    )
  }
  const send = async () => {
    setBusy(true); setErr('')
    try {
      const r = await call('POST', `/api/public/quote/${req.ref}/submit`, { token: req.token, ...f })
      setReq({ ...r, token: req.token })
    } catch (e) { setErr(e.message) }
    setBusy(false)
  }
  return (
    <form className="pq-submit" onSubmit={(e) => { e.preventDefault(); send() }}>
      <h2>{kind === 'instant' ? 'Order this' : 'Send it for review'}</h2>
      <div className="pq-fields two">
        <label>Name<input required autoComplete="name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
        <label>Company<input autoComplete="organization" value={f.company} onChange={(e) => setF({ ...f, company: e.target.value })} /></label>
        <label>Email<input required type="email" autoComplete="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></label>
        <label>Phone<input type="tel" autoComplete="tel" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></label>
        <label>Needed by<input type="date" value={f.needed_by} onChange={(e) => setF({ ...f, needed_by: e.target.value })} /></label>
      </div>
      <label className="pq-check">
        <input type="checkbox" required checked={f.accept_terms} onChange={(e) => setF({ ...f, accept_terms: e.target.checked })} />
        <span>{info.terms}</span>
      </label>
      {err && <p className="pq-err" role="alert">{err}</p>}
      <button className="pq-btn" disabled={busy}>{busy ? 'Sending…' : action}</button>
    </form>
  )
}

function Status({ refId, token, info }) {
  const [r, setR] = useState(null)
  const [err, setErr] = useState('')
  const navigate = useNavigate()
  useEffect(() => { call('GET', `/api/public/quote/${refId}?token=${encodeURIComponent(token)}`).then(setR).catch((e) => setErr(e.message)) }, [refId, token])
  if (err) return <div className="pq-closed"><h1>Request not found</h1><p>{err} <button className="pq-link" onClick={() => navigate('/quote')}>Start a new quote</button></p></div>
  if (!r) return <p className="pq-muted pq-pad">Loading…</p>
  return (
    <div className="pq-body">
      <section className="pq-form">
        <h1>Request {r.ref}</h1>
        <p className="pq-intro"><b>{r.status_label}.</b> {r.status === 'submitted' || r.status === 'reviewing'
          ? `We will contact you within ${info.review_days} business day${info.review_days === 1 ? '' : 's'}.` : ''}</p>
        {r.files?.length > 0 && <ul className="pq-files">{r.files.map((f, i) => <li key={i}><span>{f.name}</span><span className="pq-muted">{f.removed ? 'not kept (export-controlled)' : ''}</span></li>)}</ul>}
        {r.notes && <p className="pq-muted" style={{ whiteSpace: 'pre-wrap' }}>{r.notes}</p>}
        <p><button className="pq-link" onClick={() => navigate('/quote')}>Start another quote</button></p>
      </section>
      <aside className="pq-side"><TitleBlock req={r} info={info} qty={r.quantity} material={r.material} busy={false} /></aside>
    </div>
  )
}
