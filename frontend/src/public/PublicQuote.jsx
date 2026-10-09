import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import './public.css'

// Customer-facing quote page (/quote) and request status page (/quote/status/:ref?t=token).
// Talks only to /api/public/*: no login, no internal data.

const money = (n, cents = true) => (n == null ? '' : `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: cents ? 2 : 0, maximumFractionDigits: cents ? 2 : 0 })}`)
const range = (lo, hi) => `${money(lo, lo < 100)} to ${money(hi, hi < 100)}`

// File uploads go through XMLHttpRequest so the page can show upload progress (large STEP files on a phone take a while).
function upload(url, form, onProgress) {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest()
    x.open('POST', url)
    x.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded / e.total) }
    x.upload.onload = () => onProgress(1)
    x.onload = () => {
      let data = null
      try { data = JSON.parse(x.responseText) } catch { /* not json */ }
      if (x.status >= 200 && x.status < 300) resolve(data)
      else reject(new Error((data && typeof data.detail === 'string' && data.detail) || `Something went wrong (${x.status}). Try again.`))
    }
    x.onerror = () => reject(new Error('The upload did not go through. Check your connection and try again.'))
    x.send(form)
  })
}
const FILE_KIND = [[/\.(step|stp)$/i, '3D model'], [/\.pdf$/i, 'Drawing'], [/\.dxf$/i, 'Flat pattern'], [/\.(zip|gbr|gtl|gbl|gko|drl|xln)$/i, 'Circuit board files']]
const fileKind = (name) => (FILE_KIND.find(([rx]) => rx.test(name)) || [null, 'Reference'])[1]
const size = (n) => (n < 102400 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1048576).toFixed(1)} MB`)

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

// Quotes this browser has priced, so a customer can come back to them. Only refs and private links, kept on their device.
const SAVED_KEY = 'pq-saved-quotes'
export function loadSaved() {
  try { const v = JSON.parse(localStorage.getItem(SAVED_KEY) || '[]'); return Array.isArray(v) ? v : [] } catch { return [] }
}
function writeSaved(list) { try { localStorage.setItem(SAVED_KEY, JSON.stringify(list.slice(0, 30))) } catch { /* private mode */ } }
function priceText(res) {
  if (!res) return ''
  if (res.kind === 'instant') return `${money(res.unit_price)} each`
  if (res.kind === 'estimate') return `${range(res.unit_low, res.unit_high)} each (estimate)`
  if (res.kind === 'needs_input') return 'Needs one more detail'
  return 'Priced by an engineer'
}
function remember(req, token) {
  if (!req?.ref || !token) return
  const entry = { ref: req.ref, token, created: req.created || new Date().toISOString().slice(0, 10), quantity: req.result?.quantity || req.quantity,
    price: priceText(req.result), status: req.status_label || '', files: (req.files || []).map((f) => f.name).slice(0, 3).join(', ') }
  writeSaved([entry, ...loadSaved().filter((x) => x.ref !== req.ref)])
  window.dispatchEvent(new Event('pq-saved'))
}
function useSaved() {
  const [list, setList] = useState(loadSaved)
  useEffect(() => { const f = () => setList(loadSaved()); window.addEventListener('pq-saved', f); window.addEventListener('storage', f); return () => { window.removeEventListener('pq-saved', f); window.removeEventListener('storage', f) } }, [])
  return list
}
const statusLink = (ref, token) => `${window.location.origin}/quote/status/${ref}?t=${encodeURIComponent(token)}`
const pdfLink = (ref, token) => `/api/public/quote/${ref}/pdf?token=${encodeURIComponent(token)}`

function Sheet({ info, children, home = false }) {
  const saved = useSaved()
  const go = (id) => (e) => { if (home) { e.preventDefault(); document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' }); history.replaceState(null, '', `#${id}`) } }
  const site = info?.site
  const links = [['quote', 'Get a quote'], site?.capabilities?.length && ['capabilities', 'Capabilities'], (site?.about || site?.experience?.length) && ['about', 'About us'],
    site?.quality?.length && ['quality', 'Quality'], site?.faq?.length && ['questions', 'Questions'], saved.length && ['saved', `Saved quotes (${saved.length})`]].filter(Boolean)
  return (
    <div className="pq">
      <div className="pq-sheet">
        <div className="pq-zones pq-zones-top" aria-hidden="true">{[1, 2, 3, 4, 5, 6].map((n) => <span key={n}>{n}</span>)}</div>
        <div className="pq-zones pq-zones-side" aria-hidden="true">{['A', 'B', 'C', 'D'].map((n) => <span key={n}>{n}</span>)}</div>
        <header className="pq-head">
          <div>
            <a className="pq-name" href="/quote">{info?.name || 'Quote request'}</a>
            {info?.tagline && <p className="pq-tagline">{info.tagline}</p>}
          </div>
          {(info?.contact_email || info?.contact_phone) && (
            <div className="pq-contact">
              {info.contact_email && <a href={`mailto:${info.contact_email}`}>{info.contact_email}</a>}
              {info.contact_phone && <a href={`tel:${info.contact_phone.replace(/[^0-9+]/g, '')}`}>{info.contact_phone}</a>}
            </div>
          )}
        </header>
        {info && links.length > 1 && (
          <nav className="pq-nav" aria-label="Sections">
            {links.map(([id, label]) => <a key={id} href={`/quote#${id}`} onClick={go(id)}>{label}</a>)}
          </nav>
        )}
        {info?.owner && !info.enabled && (
          <p className="pq-preview" role="status"><b>Preview.</b> Only you can get prices here because you are signed in. Customers see this page with a note to email you until you open it in Customer requests, Portal settings.</p>
        )}
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
  useEffect(() => { if (info?.name) document.title = `${info.name}: get a quote` }, [info?.name])
  useEffect(() => { // arriving with #capabilities etc.
    if (info && loc.hash) setTimeout(() => document.getElementById(loc.hash.slice(1))?.scrollIntoView({ block: 'start' }), 60)
  }, [info])
  const m = loc.pathname.match(/^\/quote\/status\/([A-Za-z0-9-]+)/)
  if (!info) return <Sheet info={null}><p className="pq-muted pq-pad">{err || 'Loading…'}</p></Sheet>
  if (m) return <Sheet info={info}><Status refId={m[1]} token={new URLSearchParams(loc.search).get('t') || ''} info={info} /></Sheet>
  const open = info.enabled || info.owner
  return (
    <Sheet info={info} home>
      <div id="quote" className="pq-anchor">
        {open ? <QuoteForm info={info} /> : (
          <div className="pq-closed">
            <h1>Send us your files for a price</h1>
            <p>Online pricing is not open yet. Email your drawings or models{info.contact_email ? <> to <a href={`mailto:${info.contact_email}`}>{info.contact_email}</a></> : ''} with the quantity you need, and we will reply with a price.</p>
          </div>
        )}
      </div>
      <SavedQuotes />
      <SiteSections info={info} />
    </Sheet>
  )
}

function SavedQuotes() {
  const saved = useSaved()
  if (!saved.length) return null
  const drop = (ref) => { writeSaved(loadSaved().filter((x) => x.ref !== ref)); window.dispatchEvent(new Event('pq-saved')) }
  return (
    <section id="saved" className="pq-sec pq-anchor" aria-labelledby="saved-h">
      <h2 id="saved-h">Your saved quotes</h2>
      <p className="pq-muted pq-secnote">Kept in this browser. Open one to change the quantity, download it, or send it to us.</p>
      <ul className="pq-saved">
        {saved.map((q) => (
          <li key={q.ref}>
            <a className="pq-saved-ref" href={`/quote/status/${q.ref}?t=${encodeURIComponent(q.token)}`}>{q.ref}</a>
            <span className="pq-saved-what">{q.files || 'No files'}<span className="pq-muted"> {q.created}, quantity {Number(q.quantity || 1).toLocaleString()}</span></span>
            <span className="pq-saved-price">{q.price}</span>
            <span className="pq-saved-act">
              <a href={pdfLink(q.ref, q.token)} target="_blank" rel="noopener">PDF</a>
              <button type="button" className="pq-link" onClick={() => drop(q.ref)} aria-label={`Remove ${q.ref} from this list`}>Remove</button>
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}

function SiteSections({ info }) {
  const site = info.site || {}
  const fill = (t) => String(t || '').replaceAll('{review_days}', String(info.review_days))
  const co = info.company
  return (
    <>
      {site.capabilities?.length > 0 && (
        <section id="capabilities" className="pq-sec pq-anchor" aria-labelledby="cap-h">
          <h2 id="cap-h">What we make</h2>
          <table className="pq-bom">
            <thead><tr><th scope="col">Item</th><th scope="col">Capability</th><th scope="col">Details</th></tr></thead>
            <tbody>
              {site.capabilities.map((c, i) => (
                <tr key={i}><td><span className="pq-balloon">{i + 1}</span></td><th scope="row">{c.title}</th><td>{c.text}</td></tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {(site.about || site.experience?.length > 0) && (
        <section id="about" className="pq-sec pq-anchor pq-two" aria-labelledby="about-h">
          <div>
            <h2 id="about-h">About us</h2>
            {site.about && site.about.split(/\n\s*\n/).map((para, i) => <p key={i} className="pq-prose">{para}</p>)}
            {site.industries?.length > 0 && <p className="pq-prose"><b>Who we work with:</b> {site.industries.join(', ')}.</p>}
          </div>
          {site.experience?.length > 0 && (
            <div>
              <h3>Experience</h3>
              <ol className="pq-notes-list">{site.experience.map((x, i) => <li key={i}>{x}</li>)}</ol>
            </div>
          )}
        </section>
      )}

      <section className="pq-sec" aria-labelledby="how-h">
        <h2 id="how-h">How quoting works</h2>
        <ol className="pq-steps">
          <li><b>Upload your files</b><span>A STEP model, PDF drawing, DXF, or circuit board files, with the quantity you need.</span></li>
          <li><b>See your price</b><span>Single parts get an instant price. Assemblies and complex builds get an estimate range.</span></li>
          <li><b>Send it to us</b><span>Add your contact details. Save the quote as a PDF or a link if you are not ready yet.</span></li>
          <li><b>We confirm, then build</b><span>We confirm the details and final price with you{info.review_days ? ` within ${info.review_days} business day${info.review_days === 1 ? '' : 's'}` : ''} before any work starts.</span></li>
        </ol>
      </section>

      {(site.quality?.length > 0 || co) && (
        <section id="quality" className="pq-sec pq-anchor pq-two" aria-labelledby="q-h">
          <div>
            <h2 id="q-h">Quality and compliance</h2>
            {site.quality?.length > 0 && <ul className="pq-ticks">{site.quality.map((x, i) => <li key={i}>{x}</li>)}</ul>}
          </div>
          {co && (
            <div className="pq-tb pq-codes" aria-label="Company registration">
              {(co.uei || co.cage) && (
                <div className="pq-tb-row">
                  {co.uei && <div className="pq-cell"><span>UEI</span><b>{co.uei}</b></div>}
                  {co.cage && <div className="pq-cell"><span>CAGE code</span><b>{co.cage}</b></div>}
                </div>
              )}
              {co.naics?.length > 0 && <div className="pq-tb-row"><div className="pq-cell"><span>NAICS</span><b>{co.naics.join(', ')}</b></div></div>}
              {co.certifications?.length > 0 && <div className="pq-tb-row"><div className="pq-cell"><span>Certifications</span><b>{co.certifications.join(', ')}</b></div></div>}
            </div>
          )}
        </section>
      )}

      {site.faq?.length > 0 && (
        <section id="questions" className="pq-sec pq-anchor" aria-labelledby="faq-h">
          <h2 id="faq-h">Questions</h2>
          <div className="pq-faq">
            {site.faq.map((f, i) => <details key={i}><summary>{f.q}</summary><p>{fill(f.a)}</p></details>)}
          </div>
        </section>
      )}

      <footer className="pq-foot">
        <div><b>{info.name}</b>
          {co && (co.uei || co.cage) && <div className="pq-muted pq-foot-codes">{[co.uei && `UEI ${co.uei}`, co.cage && `CAGE ${co.cage}`].filter(Boolean).join(', ')}</div>}
        </div>
        <div className="pq-foot-links">
          {info.contact_email && <a href={`mailto:${info.contact_email}`}>{info.contact_email}</a>}
          {info.contact_phone && <a href={`tel:${info.contact_phone.replace(/[^0-9+]/g, '')}`}>{info.contact_phone}</a>}
          <a href="/quote#quote" onClick={(e) => { e.preventDefault(); document.getElementById('quote')?.scrollIntoView({ behavior: 'smooth' }) }}>Start a quote</a>
        </div>
      </footer>
    </>
  )
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
  const current = useRef(null) // { ref, token } of the quote on screen
  const [progress, setProgress] = useState(null) // upload share 0..1 while sending files
  const hasDxf = files.some((f) => /\.dxf$/i.test(f.name))
  const extraSheet = useMemo(() => (info.sheet_materials || []).filter((x) => !info.materials.includes(x)), [info])

  // The file picker shows every file: iPhone, iPad and Mac grey out .step, .stp, .dxf and Gerber files
  // when a type filter is set, because they have no registered type there. So names are checked here.
  const okExt = useMemo(() => (info.accept || '').toLowerCase().split(',').filter(Boolean), [info.accept])
  const addFiles = (list) => {
    const next = [...files]
    const bad = []
    for (const f of list) {
      const ext = (f.name.match(/\.[^.]+$/) || [''])[0].toLowerCase()
      if (okExt.length && !okExt.includes(ext)) { bad.push(f.name); continue }
      if (!next.some((x) => x.name === f.name && x.size === f.size)) next.push(f)
    }
    setFiles(next.slice(0, info.max_files))
    setStale(!!req)
    setErr(bad.length ? `We can't use ${bad.join(', ')}. Send STEP (.step or .stp), PDF, DXF, or circuit board files (a .zip of Gerbers is best).`
      : next.length > info.max_files ? `Up to ${info.max_files} files. Zip PCB files together.` : '')
  }
  const removeFile = (i) => { setFiles(files.filter((_, j) => j !== i)); setStale(!!req) }

  const getPrice = async () => {
    clearTimeout(timer.current)
    current.current = null // drop any reprice still on its way for the old quote
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
    if (info.owner && !info.enabled) form.append('preview', 'true')
    try {
      setProgress(0)
      const r = await upload('/api/public/quote', form, setProgress)
      current.current = { ref: r.ref, token: r.token }
      setReq(r); setStale(false); remember(r, r.token)
      setTimeout(() => { if (window.matchMedia('(max-width: 899px)').matches) block.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }, 50)
    } catch (e) { setErr(e.message) }
    setBusy(false); setProgress(null)
  }

  // after a price: quantity, material, finish and thickness reprice without uploading again.
  // Each answer is applied only to the quote it was asked for, so a slow reply about an older quote
  // can never overwrite a newer one (or pair its number with the wrong private link).
  useEffect(() => {
    const mine = current.current
    if (!mine || busy || req?.submitted || stale) return
    const want = Math.max(1, parseInt(qty, 10) || 1)
    const t = thickness === '' ? null : Number(thickness)
    if (req && want === (req.result?.quantity || req.quantity) && material === (req.material || '') && finish === (req.finish || '') && t === (req.thickness ?? null)) return
    clearTimeout(timer.current)
    timer.current = setTimeout(async () => {
      try {
        const r = await call('POST', `/api/public/quote/${mine.ref}/options`, { token: mine.token, quantity: Math.max(1, parseInt(qty, 10) || 1), material, finish, thickness: thickness === '' ? null : Number(thickness) })
        if (current.current?.ref !== mine.ref) return
        remember(r, mine.token)
        setReq({ ...r, token: mine.token }); setErr('')
      } catch (e) { if (current.current?.ref === mine.ref) setErr(e.message) }
    }, 450)
    return () => clearTimeout(timer.current)
  }, [qty, material, finish, thickness, busy])

  const res = req?.result
  return (
    <>
    <div className="pq-body">
      <section className="pq-form" aria-label="Your project">
        <h1>Upload your files, get a price</h1>
        <p className="pq-intro">{info.intro}</p>

        {!controlled && (
          <div className={`pq-drop ${drag ? 'over' : ''}`} onClick={() => input.current.click()} role="button" tabIndex={0}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.current.click() } }}
            onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files) }}>
            <input ref={input} type="file" multiple hidden onChange={(e) => { addFiles(e.target.files); e.target.value = '' }} />
            <div className="pq-drop-main">Drop your files here, or choose files</div>
            <div className="pq-drop-sub">3D model (STEP), drawing (PDF), flat pattern (DXF), or circuit board files (zip of Gerbers, BOM and pick-and-place). Up to {info.max_files} files, {info.max_file_mb} MB each.</div>
          </div>
        )}
        {files.length > 0 && !controlled && (
          <ul className="pq-files">
            {files.map((f, i) => (
              <li key={i}><span>{f.name}<span className="pq-filekind">{fileKind(f.name)}</span></span><span className="pq-muted">{size(f.size)}</span>
                <button type="button" className="pq-link" onClick={() => removeFile(i)} aria-label={`Remove ${f.name}`}>Remove</button></li>
            ))}
          </ul>
        )}

        <div className="pq-fields">
          <label>Quantity<input type="number" min="1" max={info.max_quantity} step="1" inputMode="numeric" value={qty} onChange={(e) => setQty(e.target.value)} /></label>
          <label>Material
            <select value={material} onChange={(e) => setMaterial(e.target.value)}>
              <option value="">Not sure</option>
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
            {busy ? (progress != null && progress < 1 && files.length ? `Uploading ${Math.round(progress * 100)}%` : 'Reading your files…') : req && !stale ? 'Price again' : 'Get price'}
          </button>
          {stale && <span className="pq-muted">Your files changed. Get the price again.</span>}
        </div>
      </section>

      <aside className="pq-side" ref={block} aria-live="polite">
        <TitleBlock req={req} info={info} qty={qty} material={material} busy={busy} progress={progress} />
        {req && !stale && !req.submitted && <SaveBar req={req} token={req.token} info={info} />}
        {req && !stale && res?.kind !== 'needs_input' && <SubmitForm req={req} setReq={setReq} info={info} />}
      </aside>
    </div>
    {req && !stale && <ItemReads req={req} token={req.token} />}
    </>
  )
}

function TitleBlock({ req, info, qty, material, busy, progress }) {
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
        <div className="pq-cell wide"><span>Material</span><b>{req?.material || material || 'From your files'}</b></div>
      </div>
      <div className="pq-tb-price">
        {busy && !res && (
          <div className="pq-progress" role="status">
            <p className="pq-muted">{progress != null && progress < 1 ? 'Uploading your files…' : 'Reading your files. Drawings and assemblies can take up to a minute.'}</p>
            <div className="pq-bar"><span style={{ width: `${Math.round((progress == null ? 0.05 : progress < 1 ? progress * 0.6 : 0.85) * 100)}%` }} className={progress >= 1 ? 'pq-bar-wait' : ''} /></div>
          </div>
        )}
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
      {res?.items?.length > 0 && (
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
  const link = statusLink(req.ref, req.token)
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
        <p><a href={pdfLink(req.ref, req.token)} target="_blank" rel="noopener">Save a PDF copy</a></p>
      </div>
    )
  }
  const send = async () => {
    setBusy(true); setErr('')
    try {
      const r = await call('POST', `/api/public/quote/${req.ref}/submit`, { token: req.token, ...f })
      setReq({ ...r, token: req.token }); remember(r, req.token)
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

// What we read from each file, plus a three-view drawing, so the customer can catch a misread before ordering.
const FLAG = { assumed: 'Assumed. Check this', check: 'Please check' }
export function ItemReads({ req, token, viewUrl }) {
  const items = (req?.result?.items || []).filter((it) => it.facts?.length || it.view)
  if (!items.length) return null
  const src = (key) => (viewUrl ? viewUrl(key) : `/api/public/quote/${req.ref}/views/${key}.svg?token=${encodeURIComponent(token)}`)
  const flagged = items.some((it) => (it.facts || []).some((f) => f.flag))
  return (
    <section className="pq-reads" aria-labelledby="reads-h">
      <h2 id="reads-h">What we read from your files</h2>
      <p className="pq-secnote pq-muted">{flagged
        ? 'Lines marked for checking are guesses or things we could not find. If anything here is wrong, change the options above or tell us in the notes, and we will price it from the right information.'
        : 'Check these against your files. If anything is wrong, change the options above or tell us in the notes.'}</p>
      {items.map((it, i) => (
        <article key={i} className={`pq-read ${it.view ? '' : 'no-view'}`}>
          {it.view && (
            <figure className="pq-views">
              <a href={src(it.view.key)} target="_blank" rel="noopener" title="Open full size">
                <img src={src(it.view.key)} alt={`Front, top, right and isometric views of ${it.name}`} loading="lazy" />
              </a>
              <figcaption className="pq-muted">{it.view.note} Tap the drawing to open it full size.</figcaption>
            </figure>
          )}
          <div className="pq-facts">
            <h3>{it.name}</h3>
            <dl>
              {(it.facts || []).map((f, j) => (
                <div key={j} className={f.flag ? `flag-${f.flag}` : ''}>
                  <dt>{f.label}</dt>
                  <dd>{f.value}{f.flag && <span className="pq-flag">{FLAG[f.flag]}</span>}</dd>
                </div>
              ))}
            </dl>
          </div>
        </article>
      ))}
    </section>
  )
}

function SaveBar({ req, token, info }) {
  const [copied, setCopied] = useState(false)
  const link = statusLink(req.ref, token)
  const copy = () => {
    const done = () => { setCopied(true); setTimeout(() => setCopied(false), 2500) }
    if (navigator.clipboard?.writeText) navigator.clipboard.writeText(link).then(done).catch(() => window.prompt('Copy this link', link))
    else window.prompt('Copy this link', link)
  }
  return (
    <div className="pq-save">
      <div className="pq-save-row">
        <a className="pq-btn ghost" href={pdfLink(req.ref, token)} target="_blank" rel="noopener">Save as PDF</a>
        <button type="button" className="pq-btn ghost" onClick={copy}>{copied ? 'Link copied' : 'Copy link'}</button>
      </div>
      <p className="pq-muted pq-save-note">Saved in this browser under Your saved quotes. We keep quotes you have not sent us for {info.keep_days || 30} days.</p>
    </div>
  )
}

function Forget({ refId, token }) { // a saved entry whose link no longer works is dropped from the list
  useEffect(() => { const list = loadSaved(); const next = list.filter((x) => !(x.ref === refId && x.token === token)); if (next.length !== list.length) { writeSaved(next); window.dispatchEvent(new Event('pq-saved')) } }, [refId, token])
  return null
}

function Status({ refId, token, info }) {
  const [r, setR] = useState(null)
  const [err, setErr] = useState('')
  const [qty, setQty] = useState('')
  const [sent, setSent] = useState(false)
  const timer = useRef()
  const navigate = useNavigate()
  useEffect(() => {
    call('GET', `/api/public/quote/${refId}?token=${encodeURIComponent(token)}`)
      .then((v) => { setR(v); setQty(String(v.result?.quantity || v.quantity || 1)); remember(v, token) }).catch((e) => setErr(e.message))
  }, [refId, token])
  useEffect(() => { // a saved, unsent quote: change the quantity and see the new price
    if (!r || r.submitted || !qty || Number(qty) === (r.result?.quantity || r.quantity)) return
    clearTimeout(timer.current)
    timer.current = setTimeout(async () => {
      try { const v = await call('POST', `/api/public/quote/${r.ref}/options`, { token, quantity: Math.max(1, parseInt(qty, 10) || 1) }); setR(v); remember(v, token); setErr('') } catch (e) { setErr(e.message) }
    }, 450)
    return () => clearTimeout(timer.current)
  }, [qty])
  if (err && !r) return <div className="pq-closed"><h1>Quote not found</h1><Forget refId={refId} token={token} /><p>{err} <button className="pq-link" onClick={() => navigate('/quote')}>Start a new quote</button></p></div>
  if (!r) return <p className="pq-muted pq-pad">Loading…</p>
  const draft = !r.submitted
  const res = r.result || {}
  return (
    <>
    <div className="pq-body">
      <section className="pq-form">
        <h1>{draft ? `Saved quote ${r.ref}` : `Request ${r.ref}`}</h1>
        <p className="pq-intro"><b>{r.status_label}.</b> {draft
          ? 'Change the quantity to see a new price, then send it to us when you are ready.'
          : r.status === 'submitted' || r.status === 'reviewing' ? `We will contact you within ${info.review_days} business day${info.review_days === 1 ? '' : 's'}.` : ''}</p>
        {draft && res.kind !== 'manual' && (
          <div className="pq-fields">
            <label>Quantity<input type="number" min="1" max={info.max_quantity} step="1" inputMode="numeric" value={qty} onChange={(e) => setQty(e.target.value)} /></label>
          </div>
        )}
        {err && <p className="pq-err" role="alert">{err}</p>}
        {r.files?.length > 0 && <ul className="pq-files">{r.files.map((f, i) => <li key={i}><span>{f.name}</span><span className="pq-muted">{f.removed ? 'not kept (export-controlled)' : ''}</span><span /></li>)}</ul>}
        {r.notes && <p className="pq-muted" style={{ whiteSpace: 'pre-wrap' }}>{r.notes}</p>}
        <p><button className="pq-link" onClick={() => navigate('/quote')}>Start another quote</button></p>
      </section>
      <aside className="pq-side">
        <TitleBlock req={r} info={info} qty={qty || r.quantity} material={r.material} busy={false} />
        {draft && <SaveBar req={r} token={token} info={info} />}
        {draft || sent
          ? res.kind !== 'needs_input' && <SubmitForm req={{ ...r, token }} setReq={(v) => { setR(v); setSent(true) }} info={info} />
          : <p><a href={pdfLink(r.ref, token)} target="_blank" rel="noopener">Save a PDF copy</a></p>}
      </aside>
    </div>
    <ItemReads req={r} token={token} />
    </>
  )
}
