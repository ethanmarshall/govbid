import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import './public.css'
import { accountHref, call, loadSaved, money, pdfLink, range, statusLink, statusPath, useAccount, writeSaved } from './shared'
import Account from './Account'
import Checkout, { OrderPanel } from './Checkout'

export { loadSaved }

// Customer-facing quote page (/quote) and request status page (/quote/status/:ref?t=token).
// Talks only to /api/public/*: no login, no internal data.

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

function priceText(res) {
  if (!res) return ''
  const many = (res.items || []).length > 1
  if (res.kind === 'instant') return many ? `${money(res.total)} total` : `${money(res.unit_price)} each`
  if (res.kind === 'estimate') return many ? `${range(res.total_low, res.total_high)} total (estimate)` : `${range(res.unit_low, res.unit_high)} each (estimate)`
  if (res.kind === 'needs_input') return 'Needs one more detail'
  if (res.kind === 'processing') return 'Reading your model'
  if (res.kind === 'concept') return 'Project idea'
  return 'Priced by an engineer'
}
let lastQuote = null // the quote on screen, so signing in comes back to it
function remember(req, token) {
  if (!req?.ref || !token) return
  lastQuote = { ref: req.ref, token }
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

function Sheet({ info, children, home = false, onPath }) {
  const saved = useSaved()
  const acct = useAccount()
  const me = acct?.customer
  const here = typeof window !== 'undefined' ? window.location.pathname + window.location.search : ''
  const onAccount = here.startsWith('/quote/account')
  const go = (id) => (e) => {
    if (!home) return
    e.preventDefault()
    if (onPath && (id === 'idea' || id === 'quote')) onPath(id === 'idea' ? 'idea' : 'files')
    setTimeout(() => document.getElementById(id === 'idea' ? 'quote' : id)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 30)
    history.replaceState(null, '', `#${id}`)
  }
  const site = info?.site
  const links = [['quote', 'Get a quote'], ['idea', 'Start with an idea'], site?.capabilities?.length && ['capabilities', 'Capabilities'], (site?.about || site?.experience?.length) && ['about', 'About us'],
    site?.quality?.length && ['quality', 'Quality'], site?.faq?.length && ['questions', 'Questions'], saved.length && ['saved', `Saved quotes (${saved.length})`]].filter(Boolean)
  return (
    <div className="pq">
      <div className="pq-sheet">
        <div className="pq-zones pq-zones-top" aria-hidden="true">{[1, 2, 3, 4, 5, 6].map((n) => <span key={n}>{n}</span>)}</div>
        <div className="pq-zones pq-zones-side" aria-hidden="true">{['A', 'B', 'C', 'D'].map((n) => <span key={n}>{n}</span>)}</div>
        <header className="pq-head">
          <div>
            <a className="pq-name" href="/quote">{info?.name || 'Valley Power Systems LLC'}</a>
            {info?.tagline && <p className="pq-tagline">{info.tagline}</p>}
          </div>
          <div className="pq-contact">
            {info?.contact_email && <a href={`mailto:${info.contact_email}`}>{info.contact_email}</a>}
            {info?.contact_phone && <a href={`tel:${info.contact_phone.replace(/[^0-9+]/g, '')}`}>{info.contact_phone}</a>}
            {info && acct !== undefined && !onAccount && (
              <a className="pq-acct" href={me ? '/quote/account' : accountHref(here)}
                onClick={(e) => { if (me) return; e.preventDefault(); const p = window.location.pathname; window.location.assign(accountHref(p.startsWith('/quote/status/') ? p + window.location.search : lastQuote ? statusPath(lastQuote.ref, lastQuote.token) : p)) }}>{me ? `${me.name.split(' ')[0] || 'Your'}'s account` : 'Sign in or create an account'}</a>
            )}
          </div>
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
  const [path, setPath] = useState(() => (loc.hash === '#idea' ? 'idea' : 'files'))
  const [info, setInfo] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { document.title = 'Get a quote'; call('GET', '/api/public/info').then(setInfo).catch((e) => setErr(e.message)) }, [])
  useEffect(() => { if (info?.name) document.title = `${info.name}: get a quote` }, [info?.name])
  useEffect(() => { // arriving with #capabilities etc.
    if (info && loc.hash) setTimeout(() => document.getElementById(loc.hash.slice(1))?.scrollIntoView({ block: 'start' }), 60)
  }, [info])
  const m = loc.pathname.match(/^\/quote\/status\/([A-Za-z0-9-]+)/)
  if (!info) return <Sheet info={null}><p className="pq-muted pq-pad">{err || 'Loading…'}</p></Sheet>
  if (loc.pathname.startsWith('/quote/account')) return <Sheet info={info}><Account info={info} /></Sheet>
  if (m) return <Sheet info={info}><Status refId={m[1]} token={new URLSearchParams(loc.search).get('t') || ''} info={info} /></Sheet>
  const open = info.enabled || info.owner
  return (
    <Sheet info={info} home onPath={setPath}>
      <div id="quote" className="pq-anchor">
        <PathChooser path={path} setPath={setPath} />
        <div id="idea" className="pq-anchor" />
        {path === 'idea' ? <ConceptForm info={info} /> : open ? <QuoteForm info={info} /> : (
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

function PathChooser({ path, setPath }) {
  const opt = (key, title, text) => (
    <button type="button" role="tab" aria-selected={path === key} className={`pq-path ${path === key ? 'on' : ''}`}
      onClick={() => { setPath(key); history.replaceState(null, '', key === 'idea' ? '#idea' : '#quote') }}>
      <b>{title}</b><span>{text}</span>
    </button>
  )
  return (
    <div className="pq-paths" role="tablist" aria-label="How do you want to start?">
      {opt('files', 'I have drawings or models', 'Upload STEP, PDF, DXF or board files and get a price now.')}
      {opt('idea', 'I have an idea', 'No drawings yet? Tell us what you need and an engineer will help you get there.')}
    </div>
  )
}

// A project without drawings: the idea, goals, must-haves, conditions, quantities, budget, timing and contact.
function ConceptForm({ info }) {
  const o = info.concept_options || {}
  const [c, setC] = useState({ title: '', stage: '', description: '', goals: '', users: '', must_haves: [''], nice_to_haves: '',
    environment: [], environment_notes: '', power: [], standards: [], standards_other: '', size_limits: '', interfaces: '',
    quantity_first: '', quantity_annual: '', budget: '', budget_notes: '', needed_by: '', deadline_firm: false, help: [],
    government: false, contract_ref: '', end_customer: '', nda: false, contact_method: 'Email', best_time: '', heard: '', notes: '' })
  const [who, setWho] = useState({ name: '', company: '', email: '', phone: '', accept_terms: false, export_controlled: false })
  const [files, setFiles] = useState([])
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState(null)
  const [err, setErr] = useState('')
  const [done, setDone] = useState(null)
  const fileIn = useRef()
  const set = (k) => (e) => setC({ ...c, [k]: e?.target ? (e.target.type === 'checkbox' ? e.target.checked : e.target.value) : e })
  const toggle = (k, v) => setC({ ...c, [k]: c[k].includes(v) ? c[k].filter((x) => x !== v) : [...c[k], v] })
  const must = c.must_haves
  const setMust = (i, v) => setC({ ...c, must_haves: must.map((x, j) => (j === i ? v : x)) })
  const addMust = (v = '') => setC({ ...c, must_haves: [...must.filter((x, j) => x.trim() || j < must.length - 1), v, ''].filter((x, j, a) => x !== '' || j === a.length - 1) })
  const addFiles = (list) => {
    const next = [...files]
    for (const f of list) {
      if (f.size > info.max_file_mb * 1048576) { setErr(`${f.name} is larger than ${info.max_file_mb} MB.`); continue }
      if (!next.some((x) => x.name === f.name && x.size === f.size)) next.push(f)
    }
    setFiles(next.slice(0, info.max_files))
  }
  const send = async (e) => {
    e.preventDefault(); setErr(''); setBusy(true); setProgress(0)
    const form = new FormData()
    form.append('payload', JSON.stringify({ concept: { ...c, must_haves: must.filter((x) => x.trim()) }, contact: who }))
    form.append('website', '')
    if (!who.export_controlled) files.forEach((f) => form.append('files', f))
    try {
      const r = await upload('/api/public/concept', form, setProgress)
      remember({ ...r, files: r.files }, r.token)
      setDone(r)
      setTimeout(() => document.getElementById('quote')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 30)
    } catch (x) { setErr(x.message) }
    setBusy(false); setProgress(null)
  }
  const chips = (k, list) => (
    <div className="pq-chips">
      {(list || []).map((v) => (
        <label key={v} className={`pq-chip ${c[k].includes(v) ? 'on' : ''}`}>
          <input type="checkbox" checked={c[k].includes(v)} onChange={() => toggle(k, v)} />{v}
        </label>
      ))}
    </div>
  )
  if (done) {
    const link = statusLink(done.ref, done.token)
    return (
      <div className="pq-concept-done">
        <h1>We have your project</h1>
        <p>Your reference is <b>{done.ref}</b>. {done.result?.message}</p>
        <p className="pq-muted">Keep this link to see what you sent and where it stands:</p>
        <div className="pq-linkrow"><input readOnly value={link} onFocus={(e) => e.target.select()} aria-label="Status link" />
          <button type="button" className="pq-btn ghost" onClick={() => navigator.clipboard?.writeText(link)}>Copy link</button></div>
      </div>
    )
  }
  return (
    <form className="pq-concept" onSubmit={send}>
      <h1>Tell us about your project</h1>
      <p className="pq-intro">No drawings needed. The more you tell us, the better our first answer, but only the parts marked required are needed. An engineer reads every project and replies within {info.review_days} business day{info.review_days === 1 ? '' : 's'}.</p>

      <fieldset className="pq-step">
        <legend><span className="pq-stepno">1</span>The idea</legend>
        <div className="pq-fields two">
          <label>Project name<input value={c.title} onChange={set('title')} maxLength={120} placeholder="Pump control trainer" /></label>
          <label>Where it stands
            <select value={c.stage} onChange={set('stage')}><option value="">Choose one</option>{(o.stages || []).map((v) => <option key={v}>{v}</option>)}</select>
          </label>
        </div>
        <label className="pq-notes">What do you want built? (required)
          <textarea required minLength={20} value={c.description} onChange={set('description')} maxLength={4000} rows={4}
            placeholder="What it is, what it does, and roughly how big it is. Rough is fine." /></label>
        <label className="pq-notes">What problem does it solve, and what does success look like?
          <textarea value={c.goals} onChange={set('goals')} maxLength={3000} rows={3} placeholder="Students can practice a full startup without risk to real equipment." /></label>
        <label className="pq-notes">Who will use it, and how?<input value={c.users} onChange={set('users')} maxLength={1000} placeholder="Instructors and students, about 4 hours a day" /></label>
      </fieldset>

      <fieldset className="pq-step">
        <legend><span className="pq-stepno">2</span>Must haves</legend>
        <p className="pq-hint">Things that are not negotiable: if the design misses one, it does not work for you.</p>
        <ul className="pq-must">
          {must.map((v, i) => (
            <li key={i}>
              <input value={v} onChange={(e) => setMust(i, e.target.value)} maxLength={300} aria-label={`Must have ${i + 1}`}
                placeholder={i === 0 ? 'Runs on 120 VAC from a standard outlet' : 'Another must have'}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addMust() } }} />
              {must.length > 1 && <button type="button" className="pq-link" onClick={() => setC({ ...c, must_haves: must.filter((_, j) => j !== i) })} aria-label="Remove">Remove</button>}
            </li>
          ))}
        </ul>
        <div className="pq-chips pq-hints"><span className="pq-muted">Common ones:</span>
          {(info.must_have_hints || []).map((h) => <button type="button" key={h} className="pq-chip" onClick={() => addMust(h + ': ')}>{h}</button>)}
        </div>
        <label className="pq-notes">Nice to have, if it fits the budget<textarea value={c.nice_to_haves} onChange={set('nice_to_haves')} maxLength={3000} rows={2} /></label>
      </fieldset>

      <fieldset className="pq-step">
        <legend><span className="pq-stepno">3</span>Where and how it works</legend>
        <p className="pq-label">Where it will be used</p>{chips('environment', o.environments)}
        <label className="pq-notes">Temperatures, moisture, vibration or anything harsh<input value={c.environment_notes} onChange={set('environment_notes')} maxLength={1500} placeholder="0 to 40 C, occasional washdown" /></label>
        <p className="pq-label">Power available</p>{chips('power', o.power)}
        <p className="pq-label">Standards it must meet</p>{chips('standards', o.standards)}
        <div className="pq-fields two">
          <label>Other standards or specs<input value={c.standards_other} onChange={set('standards_other')} maxLength={500} placeholder="NAVSEA spec, customer drawing, ..." /></label>
          <label>Size and weight limits<input value={c.size_limits} onChange={set('size_limits')} maxLength={800} placeholder="Fits on a 30 x 60 in bench, under 150 lb" /></label>
        </div>
        <label className="pq-notes">What it connects to or works with<input value={c.interfaces} onChange={set('interfaces')} maxLength={1500} placeholder="Existing PLC, 4-20 mA sensors, a laptop over USB" /></label>
      </fieldset>

      <fieldset className="pq-step">
        <legend><span className="pq-stepno">4</span>Quantity, budget and timing</legend>
        <div className="pq-fields">
          <label>First order<select value={c.quantity_first} onChange={set('quantity_first')}><option value="">Choose one</option>{(o.volumes || []).map((v) => <option key={v}>{v}</option>)}</select></label>
          <label>Later, per year<input value={c.quantity_annual} onChange={set('quantity_annual')} maxLength={120} placeholder="About 20" /></label>
          <label>Budget<select value={c.budget} onChange={set('budget')}><option value="">Choose one</option>{(o.budgets || []).map((v) => <option key={v}>{v}</option>)}</select></label>
          <label>Needed by<input type="date" value={c.needed_by} onChange={set('needed_by')} /></label>
        </div>
        <label className="pq-check"><input type="checkbox" checked={c.deadline_firm} onChange={set('deadline_firm')} /><span>The date is firm (for example, a contract delivery or class start date)</span></label>
      </fieldset>

      <fieldset className="pq-step">
        <legend><span className="pq-stepno">5</span>What you need from us</legend>
        {chips('help', o.help)}
        <label className="pq-check"><input type="checkbox" checked={c.government} onChange={set('government')} /><span>This is for a government contract or a government end user</span></label>
        {c.government && (
          <div className="pq-fields two">
            <label>Contract or solicitation number<input value={c.contract_ref} onChange={set('contract_ref')} maxLength={200} /></label>
            <label>End customer or agency<input value={c.end_customer} onChange={set('end_customer')} maxLength={200} /></label>
          </div>
        )}
        <label className="pq-check"><input type="checkbox" checked={c.nda} onChange={set('nda')} /><span>Send me an NDA before I share details</span></label>
      </fieldset>

      <fieldset className="pq-step">
        <legend><span className="pq-stepno">6</span>Sketches, photos or documents (optional)</legend>
        {!who.export_controlled && (
          <div className="pq-drop pq-drop-small" onClick={() => fileIn.current.click()} role="button" tabIndex={0}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileIn.current.click() } }}
            onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); addFiles(e.dataTransfer.files) }}>
            <input ref={fileIn} type="file" multiple hidden onChange={(e) => { addFiles(e.target.files); e.target.value = '' }} />
            <div className="pq-drop-main">Add a sketch, photo, or similar product</div>
            <div className="pq-drop-sub">Photos, PDFs, documents or any CAD you have. Up to {info.max_files} files.</div>
          </div>
        )}
        {files.length > 0 && !who.export_controlled && (
          <ul className="pq-files">{files.map((f, i) => (
            <li key={i}><span>{f.name}</span><span className="pq-muted">{size(f.size)}</span>
              <button type="button" className="pq-link" onClick={() => setFiles(files.filter((_, j) => j !== i))}>Remove</button></li>
          ))}</ul>
        )}
        <label className="pq-check"><input type="checkbox" checked={who.export_controlled} onChange={(e) => setWho({ ...who, export_controlled: e.target.checked })} />
          <span>The project involves export-controlled (ITAR/EAR) technical data. <span className="pq-muted">Don't upload it here; we will arrange a secure transfer.</span></span></label>
      </fieldset>

      <fieldset className="pq-step">
        <legend><span className="pq-stepno">7</span>How to reach you</legend>
        <div className="pq-fields two">
          <label>Name (required)<input required autoComplete="name" value={who.name} onChange={(e) => setWho({ ...who, name: e.target.value })} /></label>
          <label>Company or organization<input autoComplete="organization" value={who.company} onChange={(e) => setWho({ ...who, company: e.target.value })} /></label>
          <label>Email (required)<input required type="email" autoComplete="email" value={who.email} onChange={(e) => setWho({ ...who, email: e.target.value })} /></label>
          <label>Phone<input type="tel" autoComplete="tel" value={who.phone} onChange={(e) => setWho({ ...who, phone: e.target.value })} /></label>
          <label>Best way to reach you<select value={c.contact_method} onChange={set('contact_method')}>{(o.contact_methods || []).map((v) => <option key={v}>{v}</option>)}</select></label>
          <label>Best time<input value={c.best_time} onChange={set('best_time')} maxLength={120} placeholder="Weekdays after 2 pm Eastern" /></label>
        </div>
        <label className="pq-notes">Anything else we should know<textarea value={c.notes} onChange={set('notes')} maxLength={3000} rows={2} /></label>
        <label className="pq-notes">How did you hear about us?<input value={c.heard} onChange={set('heard')} maxLength={200} /></label>
        <label className="pq-check"><input type="checkbox" required checked={who.accept_terms} onChange={(e) => setWho({ ...who, accept_terms: e.target.checked })} />
          <span>I have not included export-controlled (ITAR/EAR) or classified information in this form or its files.</span></label>
      </fieldset>

      {err && <p className="pq-err" role="alert">{err}</p>}
      <div className="pq-actions">
        <button className="pq-btn" disabled={busy}>{busy ? (progress != null && progress < 1 && files.length ? `Uploading ${Math.round(progress * 100)}%` : 'Sending…') : 'Send my project'}</button>
        <span className="pq-muted">We reply within {info.review_days} business day{info.review_days === 1 ? '' : 's'}.</span>
      </div>
    </form>
  )
}

export function ConceptBrief({ r }) {
  if (!r.concept?.length) return null
  return (
    <section className="pq-parts" aria-labelledby="brief-h">
      <h2 id="brief-h">Your project</h2>
      <div className="pq-facts pq-brief"><dl>
        {r.concept.map((x, i) => <div key={i}><dt>{x.label}</dt><dd>{x.text}</dd></div>)}
      </dl></div>
    </section>
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
          <a href="/login" className="pq-muted">Staff sign in</a>
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
    const big = []
    for (const f of list) {
      const ext = (f.name.match(/\.[^.]+$/) || [''])[0].toLowerCase()
      if (okExt.length && !okExt.includes(ext)) { bad.push(f.name); continue }
      if (f.size > info.max_file_mb * 1048576) { big.push(f.name); continue }
      if (!next.some((x) => x.name === f.name && x.size === f.size)) next.push(f)
    }
    setFiles(next.slice(0, info.max_files))
    setStale(!!req)
    setErr(big.length ? `${big.join(', ')} is larger than ${info.max_file_mb} MB. Email it to us${info.contact_email ? ` at ${info.contact_email}` : ''} or send a share link in the notes.`
      : bad.length ? `We can't use ${bad.join(', ')}. Send STEP (.step or .stp), PDF, DXF, or circuit board files (a .zip of Gerbers is best).`
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

  // one part's own choices: quantity, material, finish, process. Sent together after a short pause.
  const [linePending, setLinePending] = useState(false)
  const lineQueue = useRef({})
  const lineTimer = useRef()
  const changeLine = (key, patch) => {
    const mine = current.current
    if (!mine) return
    lineQueue.current[key] = { ...(lineQueue.current[key] || {}), ...patch }
    setLinePending(true)
    clearTimeout(lineTimer.current)
    lineTimer.current = setTimeout(async () => {
      const lines = lineQueue.current
      lineQueue.current = {}
      try {
        const r = await call('POST', `/api/public/quote/${mine.ref}/options`, { token: mine.token, lines })
        if (current.current?.ref === mine.ref) { remember(r, mine.token); setReq({ ...r, token: mine.token }); setErr('') }
      } catch (e) { setErr(e.message) }
      setLinePending(false)
    }, 600)
  }

  // a big model is read in the background: check back until the price is ready
  useEffect(() => {
    if (req?.result?.kind !== 'processing' || stale) return
    const mine = current.current
    const t = setInterval(async () => {
      if (!mine || current.current?.ref !== mine.ref) return
      try {
        const r = await call('GET', `/api/public/quote/${mine.ref}?token=${encodeURIComponent(mine.token)}`)
        if (current.current?.ref !== mine.ref) return
        if (r.result?.kind !== 'processing') { remember(r, mine.token); setReq({ ...r, token: mine.token }) }
      } catch { /* try again next time */ }
    }, 5000)
    return () => clearInterval(t)
  }, [req?.ref, req?.result?.kind, stale])

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
        {req && !stale && <NextStep req={req} token={req.token} setReq={setReq} info={info} />}
      </aside>
    </div>
    {req && !stale && <PartsTable req={req} token={req.token} info={info} onLine={changeLine} pending={linePending} />}
    </>
  )
}

function TitleBlock({ req, info, qty, material, busy, progress }) {
  const res = req?.result
  const kind = res?.kind
  const q = res?.quantity || Math.max(1, parseInt(qty, 10) || 1)
  const items = res?.items || []
  const nLines = items.length
  const single = nLines === 1 ? items[0] : null
  return (
    <div className={`pq-tb ${kind ? `k-${kind}` : ''}`}>
      <div className="pq-tb-row">
        <div className="pq-cell"><span>{kind === 'concept' ? 'Project' : 'Quote'}</span><b>{req?.ref || 'Not priced yet'}</b></div>
        {kind !== 'concept' && <div className="pq-cell"><span>{nLines > 1 ? 'Parts' : 'Quantity'}</span><b>{nLines > 1 ? nLines : q.toLocaleString()}</b></div>}
      </div>
      {kind !== 'concept' && <div className="pq-tb-row">
        <div className="pq-cell wide"><span>Material</span><b>{nLines > 1 ? 'Set for each part below' : (single?.material || req?.material || material || 'From your files')}</b></div>
      </div>}
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
            {single ? (
              <>
                <div className="pq-big">{money(single.unit_price)}<small> each</small></div>
                <div className="pq-total">{money(res.total)} for {single.qty.toLocaleString()}</div>
              </>
            ) : (
              <>
                <div className="pq-big">{money(res.total)}<small> total</small></div>
                <div className="pq-total">{nLines} parts{q > 1 ? `, ${money(res.unit_price)} per set of ${q.toLocaleString()}` : ''}</div>
              </>
            )}
          </>
        )}
        {kind === 'estimate' && (
          <>
            <span className="pq-kind">Estimate, confirmed after review</span>
            {single && single.unit_low != null ? (
              <>
                <div className="pq-big pq-range">{range(single.unit_low, single.unit_high)}<small> each</small></div>
                <div className="pq-total">{range(res.total_low, res.total_high)} for {single.qty.toLocaleString()}</div>
              </>
            ) : (
              <>
                <div className="pq-big pq-range">{range(res.total_low, res.total_high)}<small> total</small></div>
                <div className="pq-total">{nLines} parts{q > 1 ? `, ${range(res.unit_low, res.unit_high)} per set` : ''}{res.unpriced_lines ? `, ${res.unpriced_lines} priced by an engineer` : ''}</div>
              </>
            )}
          </>
        )}
        {kind === 'concept' && <span className="pq-kind">Project idea, an engineer will reply</span>}
        {(kind === 'manual' || kind === 'needs_input') && <span className="pq-kind">{kind === 'manual' ? 'Priced by an engineer' : 'One more detail'}</span>}
        {kind === 'processing' && (
          <div className="pq-progress" role="status">
            <span className="pq-kind">Reading your model</span>
            <div className="pq-bar" style={{ marginTop: 12 }}><span className="pq-bar-wait" style={{ width: '70%' }} /></div>
          </div>
        )}
        {res?.message && <p className="pq-msg">{res.message}</p>}
      </div>
      {res?.lead_days ? <div className="pq-tb-row"><div className="pq-cell wide"><span>Ships in about</span><b>{res.lead_days} days after {kind === 'instant' ? 'you order' : 'the order is confirmed'}</b></div></div> : null}
    </div>
  )
}

// After pricing: order it now when every line has a firm price, otherwise send it for review.
function NextStep({ req, token, setReq, info }) {
  const [review, setReview] = useState(false)
  const kind = req.result?.kind
  if (kind === 'needs_input' || kind === 'processing') return null
  if (req.order && req.order.status !== 'awaiting_payment') return <OrderPanel order={req.order} info={info} fresh />
  if (req.checkout?.eligible) {
    return (
      <>
        <Checkout req={req} token={token} setReq={setReq} info={info} />
        {req.submitted ? null : review ? <SubmitForm req={req} setReq={setReq} info={info} secondary />
          : <p className="pq-or"><button type="button" className="pq-link" onClick={() => setReview(true)}>Rather have an engineer look at it before you order?</button></p>}
      </>
    )
  }
  return <SubmitForm req={req} setReq={setReq} info={info} secondary={review} />
}

function SubmitForm({ req, setReq, info, secondary = false }) {
  const me = useAccount()?.customer
  const [f, setF] = useState({ name: '', company: '', email: '', phone: '', needed_by: '', notes: '', accept_terms: false })
  useEffect(() => { if (me) setF((x) => ({ ...x, name: x.name || me.name, company: x.company || me.company, email: x.email || me.email, phone: x.phone || me.phone })) }, [me?.id])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [copied, setCopied] = useState(false)
  const kind = req.result?.kind
  const action = secondary ? 'Send for review' : kind === 'instant' ? 'Place order request' : 'Request review'
  const link = statusLink(req.ref, req.token)
  if (req.submitted) {
    return (
      <div className="pq-done">
        <h2>{kind === 'instant' && !secondary ? 'Order request sent' : 'Review requested'}</h2>
        <p>Your request is <b>{req.ref}</b>. {kind === 'instant' && !secondary
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
      <h2>{secondary ? 'Or ask us to look at it first' : kind === 'instant' ? 'Order this' : 'Send it for review'}</h2>
      {secondary && <p className="pq-muted pq-small">An engineer checks the files and confirms the price and delivery date before you order. Nothing is charged.</p>}
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

// One row per part: its quantity, material, finish and how it is made can each be changed, and its price.
// "Details" shows what we read from the files and the three-view drawing.
export function PartsTable({ req, token, info, onLine, pending, viewUrl }) {
  const items = req?.result?.items || []
  const [open, setOpen] = useState(() => (items.length === 1 ? { [items[0]?.key]: true } : {}))
  if (!items.length) return null
  const editable = !!onLine && !req.submitted
  const src = (key) => (viewUrl ? viewUrl(key) : `/api/public/quote/${req.ref}/views/${key}.svg?token=${encodeURIComponent(token)}`)
  const flagged = items.some((it) => (it.facts || []).some((f) => f.flag))
  const groups = [...new Set(items.map((it) => it.group || ''))]
  return (
    <section className="pq-parts" aria-labelledby="parts-h">
      <div className="pq-parts-head">
        <h2 id="parts-h">{items.length === 1 ? 'Your part' : `Your parts (${items.length})`}</h2>
        {pending && <span className="pq-muted" role="status">Updating prices…</span>}
      </div>
      <p className="pq-secnote pq-muted">{editable ? 'Change the quantity, material, finish or how a part is made, and its price updates. ' : ''}
        Open Details to check what we read from your files{flagged ? ': lines marked for checking are guesses or things we could not find' : ''}.</p>
      {groups.map((g) => (
        <div key={g || 'none'} className="pq-group">
          {g && <h3 className="pq-group-name">{g}</h3>}
          <ul className="pq-lines">
            {items.filter((it) => (it.group || '') === g).map((it) => (
              <PartRow key={it.key} it={it} info={info} editable={editable} onLine={onLine} open={!!open[it.key]}
                toggle={() => setOpen({ ...open, [it.key]: !open[it.key] })} src={src} />
            ))}
          </ul>
        </div>
      ))}
    </section>
  )
}

const FLAG = { assumed: 'Assumed. Check this', check: 'Please check' }
function PartRow({ it, info, editable, onLine, open, toggle, src }) {
  const ed = it.editable || {}
  const [qty, setQty] = useState(String(it.qty))
  useEffect(() => { setQty(String(it.qty)) }, [it.qty])
  const mats = it.kind === 'flat' ? info.sheet_materials || [] : [...(info.materials || []), ...(info.print_materials || [])]
  const procs = it.options?.processes || []
  const procVal = `${it.process}|${it.material}`
  const price = it.unit_price != null ? money(it.unit_price) : it.unit_low != null ? range(it.unit_low, it.unit_high) : null
  const total = it.total != null ? money(it.total) : it.total_low != null ? range(it.total_low, it.total_high) : null
  const flagged = (it.facts || []).some((f) => f.flag)
  return (
    <li className={`pq-line r-${it.route}`}>
      <div className="pq-line-main">
        <div className="pq-line-name">
          <b>{it.name}</b>
          <span className="pq-muted">{it.desc}{it.qty_per > 1 && it.group ? `, ${it.qty_per} per assembly` : ''}</span>
          {it.note && <span className="pq-note">{it.note}</span>}
        </div>
        <label className="pq-mini">Qty
          {editable && ed.qty ? (
            <input type="number" min="1" step="1" inputMode="numeric" value={qty}
              onChange={(e) => setQty(e.target.value)}
              onBlur={() => { const v = parseInt(qty, 10); if (v > 0 && v !== it.qty) onLine(it.key, { qty: v }); else setQty(String(it.qty)) }}
              onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur() }} />
          ) : <b>{it.qty.toLocaleString()}</b>}
        </label>
        <label className="pq-mini">Material
          {editable && ed.material ? (
            <select value={it.material || ''} onChange={(e) => onLine(it.key, { material: e.target.value, process: null, process_material: null })}>
              {!mats.includes(it.material) && it.material && <option>{it.material}</option>}
              {mats.map((m) => <option key={m}>{m}</option>)}
            </select>
          ) : <b>{it.material || '—'}</b>}
        </label>
        <label className="pq-mini">Finish
          {editable && ed.finish ? (
            <select value={it.finish && it.finish !== 'none' ? it.finish : 'none'} onChange={(e) => onLine(it.key, { finish: e.target.value })}>
              <option value="none">None</option>
              {(info.finishes || []).map((f) => <option key={f}>{f}</option>)}
            </select>
          ) : <b>{it.finish && it.finish !== 'none' ? it.finish : 'None'}</b>}
        </label>
        <label className="pq-mini pq-mini-wide">Made by
          {editable && ed.process && procs.length > 1 ? (
            <select value={procVal} onChange={(e) => { const [process, material] = e.target.value.split('|'); onLine(it.key, { process, process_material: material }) }}>
              {procs.map((o) => <option key={`${o.process}|${o.material}`} value={`${o.process}|${o.material}`}>{o.label}{o.material !== it.material && o.process === '3d_print' ? ` (${o.material.replace(/ \(DMLS\)/, '')})` : ''}, {money(o.unit_price)}</option>)}
            </select>
          ) : <b>{it.process_label || '—'}</b>}
        </label>
        <div className="pq-line-price">
          {price ? <><b>{price}</b><span className="pq-muted"> each</span>{total && <div className="pq-muted">{total}</div>}</> : <span className="pq-muted">{it.route === 'processing' ? 'Reading…' : 'By review'}</span>}
          {it.confirmed && <div className="pq-ok">Confirmed</div>}
        </div>
      </div>
      {(it.facts?.length > 0 || it.view) && (
        <button type="button" className="pq-link pq-details" aria-expanded={open} onClick={toggle}>
          {open ? 'Hide details' : 'Details'}{flagged && !open ? <span className="pq-flagdot"> (check)</span> : null}
        </button>
      )}
      {open && (
        <div className={`pq-read ${it.view ? '' : 'no-view'}`}>
          {it.view && (
            <figure className="pq-views">
              <a href={src(it.view.key)} target="_blank" rel="noopener" title="Open full size">
                <img src={src(it.view.key)} alt={`Front, top, right and isometric views of ${it.name}`} loading="lazy" />
              </a>
              <figcaption className="pq-muted">{it.view.note} Tap the drawing to open it full size.</figcaption>
            </figure>
          )}
          <div className="pq-facts">
            <dl>
              {(it.facts || []).map((f, j) => (
                <div key={j} className={f.flag ? `flag-${f.flag}` : ''}>
                  <dt>{f.label}</dt>
                  <dd>{f.value}{f.flag && <span className="pq-flag">{FLAG[f.flag]}</span>}</dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      )}
    </li>
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
  const [linePending, setLinePending] = useState(false)
  const lineQueue = useRef({})
  const lineTimer = useRef()
  const changeLine = (key, patch) => {
    lineQueue.current[key] = { ...(lineQueue.current[key] || {}), ...patch }
    setLinePending(true)
    clearTimeout(lineTimer.current)
    lineTimer.current = setTimeout(async () => {
      const lines = lineQueue.current
      lineQueue.current = {}
      try { const v = await call('POST', `/api/public/quote/${refId}/options`, { token, lines }); setR(v); remember(v, token); setErr('') } catch (e) { setErr(e.message) }
      setLinePending(false)
    }, 600)
  }
  useEffect(() => {
    if (r?.result?.kind !== 'processing') return
    const t = setInterval(() => {
      call('GET', `/api/public/quote/${refId}?token=${encodeURIComponent(token)}`)
        .then((v) => { if (v.result?.kind !== 'processing') { setR(v); remember(v, token) } }).catch(() => {})
    }, 5000)
    return () => clearInterval(t)
  }, [r?.result?.kind, refId, token])
  if (err && !r) return <div className="pq-closed"><h1>Quote not found</h1><Forget refId={refId} token={token} /><p>{err} <button className="pq-link" onClick={() => navigate('/quote')}>Start a new quote</button></p></div>
  if (!r) return <p className="pq-muted pq-pad">Loading…</p>
  const draft = !r.submitted
  const qs = new URLSearchParams(window.location.search)
  const payNote = qs.get('paid') ? (r.order?.status === 'paid' ? { ok: true, text: 'Payment received. Thank you, your order is in.' } : r.order?.status === 'awaiting_payment' ? { ok: false, text: 'We have not received the payment confirmation yet. Refresh this page in a minute.' } : null)
    : qs.get('cancelled') && r.order?.status === 'awaiting_payment' ? { ok: false, text: 'Payment was not completed. Your quote is still here when you are ready.' } : null
  const res = r.result || {}
  return (
    <>
    <div className="pq-body">
      <section className="pq-form">
        <h1>{r.order && r.status !== 'draft' ? `Order ${r.ref}` : draft ? `Saved quote ${r.ref}` : `Request ${r.ref}`}</h1>
        <p className="pq-intro"><b>{r.status_label}.</b> {draft
          ? (r.checkout?.eligible ? 'Change the quantity to see a new price, then place your order when you are ready.' : 'Change the quantity to see a new price, then send it to us when you are ready.')
          : r.status === 'ordered' ? 'We have your order and will confirm the ship date by email.'
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
        {payNote && <p className={payNote.ok ? 'pq-okline' : 'pq-err'} role="status">{payNote.text}</p>}
        {r.order && !(draft || sent) && <OrderPanel order={r.order} info={info} />}
        {draft || sent || r.checkout?.eligible
          ? <NextStep req={{ ...r, token }} token={token} setReq={(v) => { setR(v); setSent(true) }} info={info} />
          : <p><a href={pdfLink(r.ref, token)} target="_blank" rel="noopener">Save a PDF copy</a></p>}
      </aside>
    </div>
    {r.result?.kind === 'concept' ? <ConceptBrief r={r} /> : <PartsTable req={r} token={token} info={info} onLine={draft ? changeLine : null} pending={linePending} />}
    </>
  )
}
