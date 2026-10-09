import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, qs } from '../api'

const enc = (id) => encodeURIComponent(id)
const PAGE = 50

function FreeTag({ free }) {
  return <span className={`badge ${free ? 'b-eligible_now' : 'b-not_eligible'}`}>{free ? 'Free' : 'Paid'}</span>
}

function useCopy() {
  const [copied, setCopied] = useState('')
  const copy = async (text) => {
    try { await navigator.clipboard.writeText(text); setCopied(text); setTimeout(() => setCopied(''), 1500) } catch {}
  }
  return [copied, copy]
}

export default function Standards() {
  const [params] = useSearchParams()
  const [q, setQ] = useState(params.get('q') || '')
  const [debQ, setDebQ] = useState('')
  const [scope, setScope] = useState('all')
  const [category, setCategory] = useState('')
  const [free, setFree] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [cats, setCats] = useState([])
  const [catTotal, setCatTotal] = useState(0)
  const [err, setErr] = useState('')
  const [open, setOpen] = useState(params.get('open')) // base_id shown in the detail panel
  const [showImport, setShowImport] = useState(false)
  const [tick, setTick] = useState(0)
  const reload = () => setTick((t) => t + 1)

  useEffect(() => {
    const t = setTimeout(() => { setDebQ(q.trim()); setPage(1) }, 250)
    return () => clearTimeout(t)
  }, [q])

  useEffect(() => {
    let live = true
    api.get('/api/standards?' + qs({ q: debQ, scope, category, free, page, limit: PAGE }))
      .then((r) => { if (live) { setData(r); setErr('') } })
      .catch((e) => live && setErr(e.message))
    api.get('/api/standards/categories?' + qs({ q: debQ, scope, free }))
      .then((r) => { if (live) { setCats(r.categories); setCatTotal(r.total) } })
      .catch(() => {})
    return () => { live = false }
  }, [debQ, scope, category, free, page, tick])

  const setScopeTab = (s) => { setScope(s); setPage(1); setCategory('') }
  const pick = (c) => { setCategory(c === category ? '' : c); setPage(1) }

  const toggleSave = async (item) => {
    try { await api.put(`/api/standards/${enc(item.base_id)}`, { in_library: !item.in_library }); reload() } catch (e) { setErr(e.message) }
  }

  const items = data?.items || []
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE)) : 1

  return (
    <>
      <div className="row spread">
        <h1>Standards library</h1>
        <button onClick={() => setShowImport((v) => !v)}>{showImport ? 'Close import' : 'Import a list'}</button>
      </div>
      <p className="sub">
        Military standards, specifications and DIDs are free on <a href="https://quicksearch.dla.mil/qsSearch.aspx" target="_blank" rel="noreferrer">ASSIST QuickSearch</a>, the official DoD source.
        Industry standards (ASME, ASTM, AWS, IPC, SAE, UL, NFPA, ISO) are sold by their publishers.
        Always work to the exact revision the contract cites, not just the newest one.
      </p>

      {showImport && <ImportPanel onDone={() => { reload() }} />}
      {err && <div className="err">{err}</div>}

      <div className="tabs">
        <button className={scope === 'all' ? 'on' : ''} onClick={() => setScopeTab('all')}>All</button>
        <button className={scope === 'library' ? 'on' : ''} onClick={() => setScopeTab('library')}>My library</button>
        <button className={scope === 'cited' ? 'on' : ''} onClick={() => setScopeTab('cited')}>Cited in solicitations</button>
      </div>

      <div className="row" style={{ marginBottom: 12 }}>
        <input
          style={{ minWidth: 340, flex: '1 1 340px', maxWidth: 520 }}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Type any document ID (MIL-DTL-38999, DI-NDTI-80809B, ASTM B633) or a topic"
          autoFocus
        />
        <select value={free} onChange={(e) => { setFree(e.target.value); setPage(1) }}>
          <option value="">Free and paid</option>
          <option value="true">Free only</option>
          <option value="false">Paid only</option>
        </select>
        {data && <span className="small muted">{data.total.toLocaleString()} documents</span>}
      </div>

      <div className="row std-chips">
        <button className={`chip ${category === '' ? 'on' : ''}`} onClick={() => pick('')}>All ({catTotal})</button>
        {cats.map((c) => (
          <button key={c.category} className={`chip ${category === c.category ? 'on' : ''}`} onClick={() => pick(c.category)}>
            {c.category} ({c.count})
          </button>
        ))}
      </div>

      {data?.lookup && <LookupCard lookup={data.lookup} onOpen={setOpen} onChanged={reload} />}

      <div className="panel" style={{ padding: 0, overflowX: 'auto' }}>
        <table className="std-table">
          <thead>
            <tr>
              <th>Document</th>
              <th>Title</th>
              <th>Category</th>
              <th></th>
              <th>Rev on file</th>
              <th>Cited</th>
              <th style={{ textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map((i) => (
              <Row key={i.base_id} item={i} onOpen={() => setOpen(i.base_id)} onToggleSave={() => toggleSave(i)} onChanged={reload} onErr={setErr} />
            ))}
          </tbody>
        </table>
        {data && items.length === 0 && !data.lookup && (
          <p className="muted" style={{ padding: 16 }}>
            {scope === 'library' ? 'Nothing saved yet. Use Save on any document, or attach your own PDF copy.' : scope === 'cited' ? 'No solicitation has cited a standard yet. Analyze a solicitation and its cited documents appear here.' : 'Nothing matches that search.'}
          </p>
        )}
        {!data && !err && <p className="muted" style={{ padding: 16 }}>Loading…</p>}
      </div>

      {pages > 1 && (
        <div className="row" style={{ justifyContent: 'center' }}>
          <button disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
          <span className="small muted">Page {page} of {pages}</span>
          <button disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      )}

      {open && <Detail baseId={open} onClose={() => setOpen(null)} onChanged={reload} />}
    </>
  )
}

function Row({ item, onOpen, onToggleSave, onChanged, onErr }) {
  const fileRef = useRef()
  const upload = async (file) => {
    if (!file) return
    const fd = new FormData()
    fd.append('file', file)
    try { await api.upload(`/api/standards/${enc(item.base_id)}/file`, fd); onChanged() } catch (e) { onErr(e.message) }
  }
  const openHref = item.has_file ? `/api/standards/${enc(item.base_id)}/file` : (item.publisher_url && !item.free ? item.publisher_url : item.assist_url)
  return (
    <tr>
      <td style={{ whiteSpace: 'nowrap' }}>
        <button className="link mono" onClick={onOpen}>{item.base_id}</button>
      </td>
      <td>
        <span className="std-title">{item.title || <span className="muted">Untitled</span>}</span>
        {item.status && <span className="small muted"> ({item.status})</span>}
      </td>
      <td className="small muted">{item.category}</td>
      <td><FreeTag free={item.free} /></td>
      <td className="mono">{item.revision_on_file || <span className="muted">none</span>}</td>
      <td>
        {item.cited_count > 0 ? (
          <span className={item.mismatch ? 'due-soon' : ''} title={item.mismatch ? 'A solicitation cites a different revision than the one on file' : ''}>
            {item.cited_count}{item.mismatch ? ' (rev differs)' : ''}
          </span>
        ) : <span className="muted">0</span>}
      </td>
      <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
        <button className="small-btn" onClick={onToggleSave}>{item.in_library ? 'Saved' : 'Save'}</button>{' '}
        <button className="small-btn" onClick={() => fileRef.current?.click()}>{item.has_file ? 'Replace PDF' : 'Attach PDF'}</button>{' '}
        <a className="btn small-btn" href={openHref} target="_blank" rel="noreferrer">{item.has_file ? 'Open PDF' : 'Open'}</a>
        <input ref={fileRef} type="file" accept="application/pdf,.pdf" style={{ display: 'none' }} onChange={(e) => { upload(e.target.files[0]); e.target.value = '' }} />
      </td>
    </tr>
  )
}

function LinkButtons({ entry }) {
  const [copied, copy] = useCopy()
  return (
    <div className="row" style={{ gap: 8 }}>
      <a className="btn small-btn" href={entry.assist_url} target="_blank" rel="noreferrer">Open in ASSIST</a>
      <button className="small-btn" onClick={() => copy(entry.base_id)}>{copied === entry.base_id ? 'Copied' : 'Copy ID'}</button>
      <a className="btn small-btn" href={entry.everyspec_url} target="_blank" rel="noreferrer">Search EverySpec</a>
      {entry.publisher_url && !entry.free && <a className="btn small-btn" href={entry.publisher_url} target="_blank" rel="noreferrer">Publisher: {entry.publisher}</a>}
    </div>
  )
}

function LookupCard({ lookup, onOpen, onChanged }) {
  const { parsed, entry, known } = lookup
  const [busy, setBusy] = useState(false)
  const save = async () => {
    setBusy(true)
    try { await api.put(`/api/standards/${enc(entry.base_id)}`, { in_library: true, revision_on_file: parsed.revision || undefined }); onChanged(); onOpen(entry.base_id) } finally { setBusy(false) }
  }
  return (
    <div className="panel std-lookup">
      <div className="row spread">
        <div>
          <span className="mono" style={{ fontWeight: 600 }}>{entry.base_id}</span>
          {parsed.revision && <span className="small muted"> revision {parsed.revision}</span>}
          {parsed.change && <span className="small muted">, {parsed.change}</span>}
          <span style={{ marginLeft: 8 }}><FreeTag free={entry.free} /></span>
        </div>
        <button className="primary small-btn" disabled={busy} onClick={save}>Add to my library</button>
      </div>
      <p className="small" style={{ margin: '8px 0' }}>
        {entry.title ? entry.title : known ? '' : 'Not in the built-in catalog.'}
        {entry.parent_id && <> Part of <button className="link mono" onClick={() => onOpen(entry.parent_id)}>{entry.parent_id}</button>.</>}
        {entry.publisher && <span className="muted"> Publisher: {entry.publisher}.</span>}
        {!entry.title && ' ASSIST cannot be linked to a single document, so paste the ID into its Document ID search.'}
      </p>
      <LinkButtons entry={entry} />
    </div>
  )
}

function Detail({ baseId, onClose, onChanged }) {
  const [e, setE] = useState(null)
  const [form, setForm] = useState({ revision_on_file: '', notes: '' })
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [rev, setRev] = useState('')
  const fileRef = useRef()

  const load = () => api.get(`/api/standards/${enc(baseId)}`).then((r) => {
    setE(r); setForm({ revision_on_file: r.revision_on_file || '', notes: r.notes || '' })
  }).catch((x) => setErr(x.message))
  useEffect(() => { setE(null); setMsg(''); setErr(''); load() }, [baseId])
  useEffect(() => {
    const onKey = (ev) => ev.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const put = async (body, note) => {
    try { const r = await api.put(`/api/standards/${enc(baseId)}`, body); setE(r); setMsg(note); setErr(''); onChanged() } catch (x) { setErr(x.message) }
  }
  const upload = async (file) => {
    if (!file) return
    const fd = new FormData()
    fd.append('file', file)
    if (rev.trim()) fd.append('revision', rev.trim())
    try {
      const r = await api.upload(`/api/standards/${enc(baseId)}/file`, fd)
      setE(r); setForm((f) => ({ ...f, revision_on_file: r.revision_on_file || '' })); setRev(''); setMsg('PDF attached.'); setErr(''); onChanged()
    } catch (x) { setErr(x.message) }
  }
  const removeFile = async () => {
    if (!confirm('Remove the attached PDF?')) return
    try { const r = await api.del(`/api/standards/${enc(baseId)}/file`); setE(r); setMsg('PDF removed.'); onChanged() } catch (x) { setErr(x.message) }
  }

  return (
    <div className="std-drawer-wrap" onClick={onClose}>
      <aside className="std-drawer" onClick={(ev) => ev.stopPropagation()}>
        <div className="row spread">
          <span className="mono" style={{ fontSize: 15, fontWeight: 600 }}>{baseId}</span>
          <button className="small-btn" onClick={onClose}>Close</button>
        </div>
        {!e && !err && <p className="muted">Loading…</p>}
        {err && <div className="err">{err}</div>}
        {e && (
          <>
            <h2 style={{ margin: '10px 0 4px' }}>{e.title || 'Untitled document'}</h2>
            <div className="row small" style={{ gap: 6, marginBottom: 10 }}>
              <FreeTag free={e.free} />
              {e.category && <span className="tag">{e.category}</span>}
              {e.publisher && <span className="muted">{e.publisher}</span>}
              {e.status && <span className="muted">Listed status: {e.status}{e.listed_revision ? `, rev ${e.listed_revision}` : ''}{e.doc_date ? `, ${e.doc_date}` : ''}</span>}
            </div>
            {e.summary && <p style={{ marginTop: 0 }}>{e.summary}</p>}
            {e.parent_id && <p className="small muted">Slash sheet or part of {e.parent_id}.</p>}
            <LinkButtons entry={e} />
            <p className="small muted">ASSIST opens on its search page; paste the document ID there. Pick the revision your contract cites from the document history.</p>

            {e.mismatch && (
              <div className="err" style={{ marginTop: 12 }}>
                A solicitation cites a different revision than the one on file ({e.revision_on_file}). Check the citations below before you build or inspect to it.
              </div>
            )}

            <h3>Your copy</h3>
            {msg && <div className="okmsg">{msg}</div>}
            <label className="check" style={{ marginBottom: 10 }}>
              <input type="checkbox" checked={e.in_library} onChange={(ev) => put({ in_library: ev.target.checked }, ev.target.checked ? 'Saved to your library.' : 'Removed from your library.')} />
              In my library
            </label>
            <div className="grid g2" style={{ gap: 10 }}>
              <label className="f">Revision on file
                <input value={form.revision_on_file} onChange={(ev) => setForm({ ...form, revision_on_file: ev.target.value })} placeholder="for example N, 2018, Rev 3" />
              </label>
              <div />
            </div>
            <label className="f" style={{ marginTop: 10 }}>Notes
              <textarea rows={3} value={form.notes} onChange={(ev) => setForm({ ...form, notes: ev.target.value })} placeholder="Where you bought it, which contract needs it, tailoring notes" />
            </label>
            <div className="row" style={{ marginTop: 8 }}>
              <button className="primary" onClick={() => put({ revision_on_file: form.revision_on_file, notes: form.notes }, 'Saved.')}>Save</button>
            </div>

            <h3>Attached PDF</h3>
            {e.has_file ? (
              <div className="row">
                <a className="btn small-btn" href={`/api/standards/${enc(baseId)}/file`} target="_blank" rel="noreferrer">Open {e.file_name.split('__').slice(1).join('__') || 'PDF'}</a>
                <button className="small-btn" onClick={() => fileRef.current?.click()}>Replace</button>
                <button className="small-btn" onClick={removeFile}>Remove</button>
              </div>
            ) : (
              <div className="row">
                <input style={{ width: 120 }} value={rev} onChange={(ev) => setRev(ev.target.value)} placeholder="Revision" />
                <button className="small-btn" onClick={() => fileRef.current?.click()}>Attach PDF (60 MB max)</button>
              </div>
            )}
            <input ref={fileRef} type="file" accept="application/pdf,.pdf" style={{ display: 'none' }} onChange={(ev) => { upload(ev.target.files[0]); ev.target.value = '' }} />

            <h3>Cited in solicitations ({e.cited_count})</h3>
            {e.citations.length === 0 && <p className="small muted">Not cited by any analyzed solicitation yet.</p>}
            <ul className="clean">
              {e.citations.map((c, idx) => {
                const differs = c.revision && e.revision_on_file && c.revision.toUpperCase().replace(/^REV\s*/, '') !== e.revision_on_file.toUpperCase().replace(/^REV\s*/, '')
                return (
                  <li key={idx} className="req">
                    <div className="row spread">
                      <Link to={`/opportunities/${c.opportunity_id}`}>{c.solicitation_number || `Opportunity ${c.opportunity_id}`}</Link>
                      <span className="mono small">{c.cited_as}</span>
                    </div>
                    <div className="small muted">{c.title}</div>
                    <div className="small">
                      Cited revision: <span className="mono">{c.revision || 'not stated'}</span>{c.change ? `, ${c.change}` : ''}
                      {differs && <span className="due-soon"> Different from your copy ({e.revision_on_file}). Get revision {c.revision} for this job.</span>}
                      {!c.revision && <span className="muted"> When no revision is stated, ask the contracting officer or use the one in effect on the solicitation date.</span>}
                    </div>
                  </li>
                )
              })}
            </ul>
          </>
        )}
      </aside>
    </div>
  )
}

function ImportPanel({ onDone }) {
  const [file, setFile] = useState(null)
  const [toLib, setToLib] = useState(false)
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState(null)
  const [err, setErr] = useState('')
  const go = async () => {
    if (!file) return
    setBusy(true); setErr(''); setRes(null)
    const fd = new FormData()
    fd.append('file', file)
    fd.append('save_to_library', toLib ? 'true' : 'false')
    try { setRes(await api.upload('/api/standards/import', fd)); onDone() } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }
  return (
    <div className="panel">
      <h2>Import a document list</h2>
      <p className="small muted" style={{ marginTop: -6 }}>
        Load a CSV or Excel list exported from ASSIST, EverySpec or your own spreadsheet. Columns named like Document ID, Title, Status, Date and Revision are recognized; a sheet with no headers is read as ID then title.
        Imported documents become searchable here alongside the built-in catalog.
      </p>
      {err && <div className="err">{err}</div>}
      {res && <div className="okmsg">Imported {res.total.toLocaleString()} documents ({res.created.toLocaleString()} new, {res.updated.toLocaleString()} updated, {res.skipped.toLocaleString()} rows skipped).</div>}
      <div className="row">
        <input type="file" accept=".csv,.tsv,.txt,.xlsx,.xlsm" onChange={(e) => setFile(e.target.files[0] || null)} />
        <label className="check"><input type="checkbox" checked={toLib} onChange={(e) => setToLib(e.target.checked)} /> Mark all as in my library</label>
        <button className="primary" disabled={!file || busy} onClick={go}>{busy ? 'Importing…' : 'Import'}</button>
      </div>
    </div>
  )
}
