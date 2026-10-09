import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, fmtDue } from '../api'
import { countWords, renderMarkdown } from '../markdown'
import { KIND_LABEL, Progress } from './Packages.jsx'
import ProposalReview from '../ProposalReview'

const SECTION_STATUS = { not_started: 'Not started', drafting: 'Drafting', review: 'In review', done: 'Done' }
const ITEM_STATUS = { not_started: 'Not started', in_progress: 'In progress', ready: 'Ready', delivered: 'Delivered', accepted: 'Accepted' }

export default function PackageBuilder() {
  const { id } = useParams()
  const nav = useNavigate()
  const [pkg, setPkg] = useState(null)
  const [meta, setMeta] = useState(null)
  const [sel, setSel] = useState(null)
  const [tab, setTab] = useState('write')
  const [err, setErr] = useState('')

  const load = useCallback(() => api.get(`/api/packages/${id}`).then((p) => {
    setPkg(p)
    setSel((cur) => (cur && p.sections.some((s) => s.id === cur) ? cur : p.sections[0]?.id ?? null))
  }).catch((e) => setErr(e.message)), [id])

  useEffect(() => { load(); api.get('/api/package-meta').then(setMeta) }, [load])

  const updatePkg = async (patch) => {
    try { setPkg(await api.put(`/api/packages/${id}`, patch)) } catch (e) { setErr(e.message) }
  }

  // Merge a saved section back into local state without a full reload
  const mergeSection = (s) => setPkg((p) => ({ ...p, sections: p.sections.map((x) => (x.id === s.id ? s : x)) }))

  if (err && !pkg) return <div className="err">{err}</div>
  if (!pkg || !meta) return <p className="muted">Loading…</p>

  const section = pkg.sections.find((s) => s.id === sel)
  const isTdp = pkg.kind === 'tdp'
  const covered = new Set(pkg.sections.flatMap((s) => s.covered_ids))
  const assigned = new Set(pkg.sections.flatMap((s) => s.requirement_ids))
  const totalWords = pkg.sections.reduce((n, s) => n + (s.words || 0), 0)
  const sectionsDone = pkg.sections.filter((s) => s.status === 'done').length

  return (
    <>
      <p className="small"><Link to="/packages">← Packages</Link>{pkg.opportunity && <> · <Link to={`/opportunities/${pkg.opportunity.id}`}>{pkg.opportunity.solicitation_number || 'Opportunity'}</Link></>}</p>
      <div className="row spread" style={{ alignItems: 'flex-start', marginBottom: 12 }}>
        <div style={{ flex: 1, minWidth: 300 }}>
          <InlineText className="title-input" value={pkg.name} onSave={(name) => updatePkg({ name })} />
          <div className="small muted">
            {KIND_LABEL[pkg.kind]}
            {pkg.opportunity && <> · {pkg.opportunity.agency}</>}
            {pkg.due_date && <> · due {fmtDue(pkg.due_date)}</>}
          </div>
        </div>
        <div className="row">
          <select value={pkg.status} onChange={(e) => updatePkg({ status: e.target.value })}>
            {meta.statuses.map((s) => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
          </select>
          <a className="btn" href={`/api/packages/${id}/export.docx`}>Word document</a>
          <a className="btn primary" href={`/api/packages/${id}/export.zip`}>Full package (.zip)</a>
        </div>
      </div>

      <div className="grid g4" style={{ marginBottom: 14 }}>
        <div className="stat"><div className="l">Sections done</div><Progress n={sectionsDone} d={pkg.sections.length} /></div>
        <div className="stat"><div className="l">Requirements covered</div>{pkg.requirements_total ? <Progress n={covered.size} d={pkg.requirements_total} /> : <div className="small muted">{pkg.opportunity ? 'Analyze the opportunity to get a matrix' : 'No linked opportunity'}</div>}</div>
        <div className="stat"><div className="l">{isTdp ? 'Deliverables ready' : 'Attachments ready'}</div><Progress n={pkg.items_ready} d={pkg.items_total} /></div>
        <div className="stat"><div className="l">Length</div><div className="mono">{totalWords.toLocaleString()} words · about {(totalWords / meta.words_per_page).toFixed(1)} pages</div></div>
      </div>

      {err && <div className="err">{err}</div>}

      <div className="tabs">
        <button className={tab === 'write' ? 'on' : ''} onClick={() => setTab('write')}>Write</button>
        <button className={tab === 'items' ? 'on' : ''} onClick={() => setTab('items')}>{isTdp ? 'Deliverables (CDRLs)' : 'Attachments and forms'} ({pkg.items.length})</button>
        {!isTdp && <button className={tab === 'review' ? 'on' : ''} onClick={() => setTab('review')}>Evaluator review</button>}
        {pkg.matrix.length > 0 && <button className={tab === 'matrix' ? 'on' : ''} onClick={() => setTab('matrix')}>Compliance ({covered.size}/{pkg.matrix.length})</button>}
        <button className={tab === 'settings' ? 'on' : ''} onClick={() => setTab('settings')}>Cover and settings</button>
      </div>

      {tab === 'write' && (
        <div className="builder">
          <Outline pkg={pkg} sel={sel} setSel={setSel} setPkg={setPkg} setErr={setErr} />
          <div style={{ minWidth: 0 }}>
            {section
              ? <SectionEditor key={section.id} pkg={pkg} section={section} meta={meta} onSaved={mergeSection} reload={load} assigned={assigned} />
              : <div className="panel"><p className="muted">Add a section to start writing.</p></div>}
          </div>
        </div>
      )}
      {tab === 'items' && <Items pkg={pkg} setPkg={setPkg} meta={meta} />}
      {tab === 'review' && <ProposalReview pkg={pkg} onOpenSection={(sid) => { setSel(sid); setTab('write') }} />}
      {tab === 'matrix' && <MatrixView pkg={pkg} onJump={(sid) => { setSel(sid); setTab('write') }} />}
      {tab === 'settings' && <Settings pkg={pkg} updatePkg={updatePkg} onDelete={async () => { if (confirm('Delete this package and its uploaded files?')) { await api.del(`/api/packages/${id}`); nav('/packages') } }} />}
    </>
  )
}

// ------------------------------------------------------------------ outline
function Outline({ pkg, sel, setSel, setPkg, setErr }) {
  const move = async (idx, dir) => {
    const ids = pkg.sections.map((s) => s.id)
    const j = idx + dir
    if (j < 0 || j >= ids.length) return
    ;[ids[idx], ids[j]] = [ids[j], ids[idx]]
    setPkg(await api.post(`/api/packages/${pkg.id}/sections/reorder`, { section_ids: ids }))
  }
  const add = async () => {
    try {
      const p = await api.post(`/api/packages/${pkg.id}/sections`, { title: 'New section', after_id: sel })
      setPkg(p)
      const before = new Set(pkg.sections.map((s) => s.id))
      const added = p.sections.find((s) => !before.has(s.id))
      if (added) setSel(added.id)
    } catch (e) { setErr(e.message) }
  }
  let lastVol = null
  return (
    <div className="outline panel">
      {pkg.sections.map((s, idx) => {
        const head = s.volume && s.volume !== lastVol
        lastVol = s.volume
        const over = s.page_limit && s.est_pages > s.page_limit
        return (
          <div key={s.id}>
            {head && <div className="vol">{s.volume}</div>}
            <div className={`oitem ${sel === s.id ? 'sel' : ''}`} onClick={() => setSel(s.id)}>
              <span className={`dot d-${s.status}`} title={SECTION_STATUS[s.status]} />
              <span className="otitle">{s.number && <span className="mono">{s.number} </span>}{s.title}</span>
              <span className="ometa">
                {s.requirement_ids.length > 0 && <span className={s.covered_ids.length === s.requirement_ids.length ? 'ok' : ''}>{s.covered_ids.length}/{s.requirement_ids.length}</span>}
                {over && <span className="over">over</span>}
              </span>
              <span className="omove">
                <button className="link" onClick={(e) => { e.stopPropagation(); move(idx, -1) }} title="Move up">↑</button>
                <button className="link" onClick={(e) => { e.stopPropagation(); move(idx, 1) }} title="Move down">↓</button>
              </span>
            </div>
          </div>
        )
      })}
      <button style={{ marginTop: 10, width: '100%' }} onClick={add}>+ Add section</button>
      <p className="small muted" style={{ marginTop: 10, marginBottom: 0 }}>Numbers show requirements covered out of assigned.</p>
    </div>
  )
}

// ------------------------------------------------------------------ section editor
function SectionEditor({ pkg, section, meta, onSaved, reload, assigned }) {
  const [s, setS] = useState(section)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [view, setView] = useState('edit')
  const [library, setLibrary] = useState([])
  const [aiOpen, setAiOpen] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const timer = useRef()
  const latest = useRef(s)
  latest.current = s
  const taRef = useRef()

  useEffect(() => { api.get('/api/library').then(setLibrary).catch(() => {}) }, [])

  const save = useCallback(async (patch) => {
    setSaving(true); setErr('')
    try {
      const body = patch || {
        volume: latest.current.volume, number: latest.current.number, title: latest.current.title, content: latest.current.content,
        page_limit: latest.current.page_limit === '' || latest.current.page_limit == null ? null : Number(latest.current.page_limit),
        status: latest.current.status, page_break_before: latest.current.page_break_before,
      }
      const saved = await api.put(`/api/sections/${section.id}`, body)
      onSaved(saved)
      setS((cur) => ({ ...cur, words: saved.words, est_pages: saved.est_pages, requirement_ids: saved.requirement_ids, covered_ids: saved.covered_ids }))
      if (!patch) setDirty(false)
    } catch (e) { setErr(e.message) }
    setSaving(false)
  }, [section.id, onSaved])

  // Autosave 1.5 s after typing stops, and on leaving the section
  const change = (patch) => {
    setS((cur) => ({ ...cur, ...patch }))
    setDirty(true)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => save(), 1500)
  }
  const dirtyRef = useRef(false)
  dirtyRef.current = dirty
  // On leaving the section: cancel the pending timer and flush unsaved text
  useEffect(() => () => {
    clearTimeout(timer.current)
    if (dirtyRef.current) save()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Requirement moves made elsewhere arrive through a reload; keep the local copy in step
  const reqKey = section.requirement_ids.join(',') + '|' + section.covered_ids.join(',')
  useEffect(() => {
    setS((cur) => ({ ...cur, requirement_ids: section.requirement_ids, covered_ids: section.covered_ids }))
  }, [reqKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const insertAtCursor = (text) => {
    const ta = taRef.current
    const content = s.content || ''
    const pos = ta ? ta.selectionStart : content.length
    const before = content.slice(0, pos)
    const sep = before && !before.endsWith('\n\n') ? (before.endsWith('\n') ? '\n' : '\n\n') : ''
    change({ content: before + sep + text.trim() + '\n\n' + content.slice(pos) })
    setView('edit')
  }

  const matrix = useMemo(() => Object.fromEntries(pkg.matrix.map((r) => [r.id, r])), [pkg.matrix])
  const reqs = s.requirement_ids.map((rid) => matrix[rid]).filter(Boolean)
  const unassigned = pkg.matrix.filter((r) => !assigned.has(r.id))
  const words = countWords(s.content)
  const pages = words / meta.words_per_page
  const limit = s.page_limit ? Number(s.page_limit) : null
  const over = limit && pages > limit

  const toggleCovered = (rid) => {
    const next = s.covered_ids.includes(rid) ? s.covered_ids.filter((x) => x !== rid) : [...s.covered_ids, rid]
    setS((cur) => ({ ...cur, covered_ids: next }))
    save({ covered_ids: next })
  }
  const moveReq = async (rid, targetId) => {
    const target = pkg.sections.find((x) => x.id === Number(targetId))
    if (!target) return
    await api.put(`/api/sections/${target.id}`, { requirement_ids: [...target.requirement_ids, rid] })
    reload()
  }
  const claim = async (rid) => {
    const next = [...s.requirement_ids, rid]
    setS((cur) => ({ ...cur, requirement_ids: next }))
    await api.put(`/api/sections/${section.id}`, { requirement_ids: next })
    reload()
  }

  return (
    <div className="panel">
      <div className="grid section-fields">
        <label className="f">Volume<input value={s.volume} onChange={(e) => change({ volume: e.target.value })} /></label>
        <label className="f">Number<input value={s.number} onChange={(e) => change({ number: e.target.value })} /></label>
        <label className="f">Section title<input value={s.title} onChange={(e) => change({ title: e.target.value })} /></label>
        <label className="f">Page limit<input type="number" step="0.5" value={s.page_limit ?? ''} onChange={(e) => change({ page_limit: e.target.value })} /></label>
        <label className="f">Status
          <select value={s.status} onChange={(e) => { setS({ ...s, status: e.target.value }); save({ status: e.target.value }) }}>
            {meta.section_statuses.map((x) => <option key={x} value={x}>{SECTION_STATUS[x]}</option>)}
          </select>
        </label>
      </div>

      {s.guidance && <div className="guidance"><b>What this section should cover.</b> {s.guidance}</div>}

      <div className="row spread" style={{ margin: '12px 0 6px' }}>
        <div className="row" style={{ gap: 6 }}>
          <button className={view === 'edit' ? 'seg on' : 'seg'} onClick={() => setView('edit')}>Write</button>
          <button className={view === 'preview' ? 'seg on' : 'seg'} onClick={() => setView('preview')}>Preview</button>
          <select value="" onChange={(e) => { const it = library.find((l) => l.id === Number(e.target.value)); if (it) insertAtCursor(it.content) }} style={{ maxWidth: 220 }}>
            <option value="">Insert from library…</option>
            {library.map((l) => <option key={l.id} value={l.id}>{l.category}: {l.title}</option>)}
          </select>
          <button onClick={() => setAiOpen(!aiOpen)} disabled={!meta.ai_configured} title={meta.ai_configured ? '' : 'Add ANTHROPIC_API_KEY to backend/.env'}>AI draft</button>
        </div>
        <div className="small">
          <span className={over ? 'due-soon' : 'muted'}>{words} words · {pages.toFixed(1)}{limit ? ` of ${limit}` : ''} pages</span>
          <span className="muted"> · {saving ? 'saving…' : dirty ? 'unsaved' : 'saved'}</span>
        </div>
      </div>

      {aiOpen && <AiPanel section={s} library={library} onResult={(text, mode) => { if (mode === 'replace') change({ content: text }); else insertAtCursor(text); setAiOpen(false) }} />}

      {view === 'edit'
        ? <textarea ref={taRef} className="editor tall" value={s.content} onChange={(e) => change({ content: e.target.value })} onBlur={() => dirty && save()}
            placeholder={'Write in Markdown.\n\n### Subheading\nParagraph text with **bold** terms.\n\n- Bullet point\n1. Numbered step\n\n| Column | Column |\n|---|---|\n| Cell | Cell |'} />
        : <div className="md-preview tall" dangerouslySetInnerHTML={{ __html: renderMarkdown(s.content) || '<p class="muted">Nothing written yet.</p>' }} />}

      <div className="row spread" style={{ marginTop: 10 }}>
        <div className="row">
          <button className="primary" onClick={() => save()} disabled={saving}>Save</button>
          <label className="check small"><input type="checkbox" checked={!!s.page_break_before} onChange={(e) => { setS({ ...s, page_break_before: e.target.checked }); save({ page_break_before: e.target.checked }) }} /> Start on new page</label>
        </div>
        <div className="row">
          <button onClick={async () => { const cat = prompt('Library category', 'Boilerplate'); if (!cat) return; await save(); await api.post(`/api/sections/${section.id}/save-to-library`, { category: cat }); setMsg('Saved to the content library.') }} disabled={!s.content.trim()}>Save to library</button>
          <button onClick={async () => { if (confirm('Delete this section? Its assigned requirements move to the previous section.')) { await api.del(`/api/sections/${section.id}`); reload() } }}>Delete section</button>
        </div>
      </div>
      {msg && <div className="okmsg" style={{ marginTop: 10 }}>{msg}</div>}
      {err && <div className="err" style={{ marginTop: 10 }}>{err}</div>}

      {pkg.matrix.length > 0 && (
        <>
          <h3>Requirements this section answers ({s.covered_ids.length}/{reqs.length} covered)</h3>
          {reqs.length === 0 && <p className="small muted">None assigned. Pull one in from the unassigned list below, or move one here from another section.</p>}
          {reqs.map((r) => (
            <div key={r.id} className="req">
              <label className="check" style={{ alignItems: 'flex-start' }}>
                <input type="checkbox" checked={s.covered_ids.includes(r.id)} onChange={() => toggleCovered(r.id)} style={{ marginTop: 3 }} />
                <span><span className="mono small muted">{r.reference || `#${r.id}`}</span> {r.requirement}</span>
              </label>
              <div className="row small" style={{ gap: 6, marginLeft: 22, marginTop: 2 }}>
                <span className="tag">{r.category}</span>
                <button className="link small" onClick={() => insertAtCursor(`### ${r.reference ? r.reference + ' ' : ''}${shortTitle(r.requirement)}\n[Respond to: ${r.requirement}]`)}>Add response heading</button>
                <select className="small" value="" onChange={(e) => moveReq(r.id, e.target.value)} style={{ padding: '2px 4px' }}>
                  <option value="">Move to…</option>
                  {pkg.sections.filter((x) => x.id !== section.id).map((x) => <option key={x.id} value={x.id}>{[x.number, x.title].filter(Boolean).join(' ')}</option>)}
                </select>
              </div>
            </div>
          ))}
          {unassigned.length > 0 && (
            <>
              <h3>Unassigned requirements ({unassigned.length})</h3>
              {unassigned.map((r) => (
                <div key={r.id} className="req small">
                  <span className="mono muted">{r.reference || `#${r.id}`}</span> {r.requirement}{' '}
                  <button className="link" onClick={() => claim(r.id)}>Assign here</button>
                </div>
              ))}
            </>
          )}
        </>
      )}
    </div>
  )
}

const shortTitle = (t) => (t || '').replace(/^(the )?(offeror|contractor|vendor)\s+(shall|must|will)\s+/i, '').split(/[.;,]/)[0].slice(0, 70).replace(/^\w/, (c) => c.toUpperCase())

function AiPanel({ section, library, onResult }) {
  const [instructions, setInstructions] = useState('')
  const [libIds, setLibIds] = useState([])
  const [busy, setBusy] = useState(false)
  const [draft, setDraft] = useState('')
  const [err, setErr] = useState('')
  const run = async (mode) => {
    setBusy(true); setErr('')
    try {
      const r = await api.post(`/api/sections/${section.id}/draft`, { instructions, library_ids: libIds, mode })
      setDraft(r.draft)
    } catch (e) { setErr(e.message) }
    setBusy(false)
  }
  return (
    <div className="ai">
      <div className="grid g2">
        <label className="f">Instructions (optional)
          <textarea value={instructions} onChange={(e) => setInstructions(e.target.value)} style={{ minHeight: 70 }} placeholder="Emphasize our VA experience. Keep it under 2 pages." />
        </label>
        <label className="f">Use library material
          <select multiple value={libIds.map(String)} onChange={(e) => setLibIds(Array.from(e.target.selectedOptions).map((o) => Number(o.value)))} style={{ minHeight: 70 }}>
            {library.map((l) => <option key={l.id} value={l.id}>{l.category}: {l.title}</option>)}
          </select>
        </label>
      </div>
      <div className="row" style={{ marginTop: 8 }}>
        <button className="primary" onClick={() => run('draft')} disabled={busy}>{busy ? 'Writing…' : 'Draft section'}</button>
        <button onClick={() => run('improve')} disabled={busy || !section.content.trim()}>Improve current text</button>
        <span className="small muted">Uses the solicitation, assigned requirements, your profile and selected library entries. Placeholders appear as [brackets] where facts are missing.</span>
      </div>
      {err && <div className="err" style={{ marginTop: 8 }}>{err}</div>}
      {draft && (
        <>
          <div className="md-preview" style={{ marginTop: 10, maxHeight: 360 }} dangerouslySetInnerHTML={{ __html: renderMarkdown(draft) }} />
          <div className="row" style={{ marginTop: 8 }}>
            <button className="primary" onClick={() => onResult(draft, 'replace')}>Replace section text</button>
            <button onClick={() => onResult(draft, 'insert')}>Insert at cursor</button>
            <button onClick={() => setDraft('')}>Discard</button>
          </div>
        </>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ deliverables / attachments
function Items({ pkg, setPkg, meta }) {
  const isTdp = pkg.kind === 'tdp'
  const [err, setErr] = useState('')
  const add = async () => setPkg(await api.post(`/api/packages/${pkg.id}/items`, { title: isTdp ? 'New deliverable' : 'New attachment' }))
  const patch = async (it, p) => {
    try {
      const saved = await api.put(`/api/items/${it.id}`, p)
      setPkg((cur) => ({ ...cur, items: cur.items.map((x) => (x.id === it.id ? saved : x)), items_ready: cur.items.map((x) => (x.id === it.id ? saved : x)).filter((x) => ['ready', 'delivered', 'accepted'].includes(x.status)).length }))
    } catch (e) { setErr(e.message) }
  }
  const upload = async (it, files) => {
    if (!files.length) return
    const fd = new FormData()
    Array.from(files).forEach((f) => fd.append('files', f))
    try {
      const saved = await api.upload(`/api/items/${it.id}/files`, fd)
      setPkg((cur) => ({ ...cur, items: cur.items.map((x) => (x.id === it.id ? saved : x)) }))
    } catch (e) { setErr(e.message) }
  }
  const removeFile = async (it, name) => {
    const saved = await api.del(`/api/items/${it.id}/files/${encodeURIComponent(name)}`)
    setPkg((cur) => ({ ...cur, items: cur.items.map((x) => (x.id === it.id ? saved : x)) }))
  }
  return (
    <div className="panel" style={{ overflowX: 'auto' }}>
      <div className="row spread" style={{ marginBottom: 8 }}>
        <p className="small muted" style={{ margin: 0 }}>
          {isTdp
            ? 'One row per CDRL line on the DD 1423. Upload the files for each; the zip export puts them in a folder per CDRL with an index.'
            : 'Forms, resumes, price sheets and anything else that ships with the proposal. Each gets its own folder in the zip export.'}
        </p>
        <button className="primary" onClick={add}>+ Add {isTdp ? 'deliverable' : 'attachment'}</button>
      </div>
      {err && <div className="err">{err}</div>}
      <table>
        <thead><tr>{isTdp && <th>CDRL</th>}<th>Title</th>{isTdp && <th>DID</th>}<th>Status</th><th>Due</th><th>Files</th><th></th></tr></thead>
        <tbody>
          {pkg.items.map((it) => (
            <tr key={it.id}>
              {isTdp && <td><Cell value={it.cdrl} onSave={(v) => patch(it, { cdrl: v })} width={60} mono /></td>}
              <td><Cell value={it.title} onSave={(v) => patch(it, { title: v })} width={260} /><Cell value={it.notes} onSave={(v) => patch(it, { notes: v })} width={260} placeholder="Notes" small /></td>
              {isTdp && <td><Cell value={it.did} onSave={(v) => patch(it, { did: v })} width={130} mono /></td>}
              <td>
                <select value={it.status} onChange={(e) => patch(it, { status: e.target.value })}>
                  {meta.item_statuses.map((x) => <option key={x} value={x}>{ITEM_STATUS[x]}</option>)}
                </select>
              </td>
              <td><input type="date" value={it.due || ''} onChange={(e) => patch(it, { due: e.target.value })} /></td>
              <td style={{ minWidth: 220 }}>
                {it.files.map((f) => (
                  <div key={f.name} className="small row" style={{ gap: 6 }}>
                    <a href={`/api/items/${it.id}/files/${encodeURIComponent(f.name)}`} className="mono">{f.name}</a>
                    <button className="link muted" onClick={() => removeFile(it, f.name)} title="Remove">×</button>
                  </div>
                ))}
                <label className="btn small-btn" style={{ marginTop: 4 }}>
                  Upload<input type="file" multiple hidden onChange={(e) => { upload(it, e.target.files); e.target.value = '' }} />
                </label>
              </td>
              <td><button className="link" onClick={async () => { if (confirm('Remove this row and its files?')) setPkg(await api.del(`/api/items/${it.id}`)) }}>Delete</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Cell({ value, onSave, width, mono, placeholder, small }) {
  const [v, setV] = useState(value || '')
  useEffect(() => setV(value || ''), [value])
  return (
    <input className={`${mono ? 'mono' : ''} ${small ? 'small' : ''}`} style={{ width, marginBottom: small ? 0 : 4 }} value={v} placeholder={placeholder}
      onChange={(e) => setV(e.target.value)} onBlur={() => v !== (value || '') && onSave(v)} />
  )
}

// ------------------------------------------------------------------ compliance overview
function MatrixView({ pkg, onJump }) {
  const where = {}
  pkg.sections.forEach((s) => s.requirement_ids.forEach((rid) => { where[rid] = { s, covered: s.covered_ids.includes(rid) } }))
  return (
    <div className="panel" style={{ overflowX: 'auto' }}>
      <p className="small muted" style={{ marginTop: 0 }}>Checking a requirement as covered in a section writes that section into the opportunity's compliance matrix as "where addressed".</p>
      <table>
        <thead><tr><th>#</th><th>Requirement</th><th>Ref</th><th>Section</th><th>Covered</th></tr></thead>
        <tbody>
          {pkg.matrix.map((r) => {
            const w = where[r.id]
            return (
              <tr key={r.id}>
                <td className="mono">{r.id}</td>
                <td>{r.requirement}</td>
                <td className="mono small">{r.reference}</td>
                <td className="small">{w ? <button className="link" onClick={() => onJump(w.s.id)}>{[w.s.number, w.s.title].filter(Boolean).join(' ')}</button> : <span className="due-soon">unassigned</span>}</td>
                <td>{w?.covered ? <span className="badge b-eligible_now">Yes</span> : <span className="badge b-not_eligible">No</span>}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ------------------------------------------------------------------ settings
function Settings({ pkg, updatePkg, onDelete }) {
  const [c, setC] = useState(pkg.cover || {})
  const [f, setF] = useState({ due_date: pkg.due_date || '', contract_number: pkg.contract_number || '', notes: pkg.notes || '' })
  const isTdp = pkg.kind === 'tdp'
  const setCover = (k) => (e) => setC({ ...c, [k]: e.target.value })
  return (
    <>
      <div className="panel">
        <h2>Cover page and headers</h2>
        <div className="grid g3">
          <label className="f">Solicitation number<input value={c.solicitation_number || ''} onChange={setCover('solicitation_number')} /></label>
          <label className="f">{isTdp ? 'Contract number' : 'Contract number (if awarded)'}<input value={f.contract_number} onChange={(e) => setF({ ...f, contract_number: e.target.value })} /></label>
          <label className="f">Issuing agency<input value={c.agency || ''} onChange={setCover('agency')} /></label>
          {!isTdp && <label className="f">Volume subtitle<input value={c.volume_title || ''} onChange={setCover('volume_title')} placeholder="Technical and Price Proposal" /></label>}
          <label className="f">Business status line<input value={c.business_status || ''} onChange={setCover('business_status')} placeholder="Service-Disabled Veteran-Owned Small Business" /></label>
          <label className="f">Due date<input value={f.due_date} onChange={(e) => setF({ ...f, due_date: e.target.value })} placeholder="2026-11-15 or 11/15/2026" /></label>
          <label className="f">Point of contact<input value={c.poc_name || ''} onChange={setCover('poc_name')} /></label>
          <label className="f">POC email<input value={c.poc_email || ''} onChange={setCover('poc_email')} /></label>
          <label className="f">POC phone<input value={c.poc_phone || ''} onChange={setCover('poc_phone')} /></label>
          {!isTdp && <label className="f">Offer valid for (days)<input type="number" value={c.validity_days || ''} onChange={(e) => setC({ ...c, validity_days: e.target.value ? Number(e.target.value) : null })} /></label>}
          <label className="f">Cover date<input value={c.date || ''} onChange={setCover('date')} placeholder="Defaults to export date" /></label>
          <label className="f">Font
            <select value={c.font || 'Times New Roman'} onChange={setCover('font')}>
              {['Times New Roman', 'Arial', 'Calibri', 'Garamond', 'Cambria'].map((x) => <option key={x}>{x}</option>)}
            </select>
          </label>
          <label className="f">Font size (pt)<input type="number" step="0.5" value={c.font_size || 12} onChange={(e) => setC({ ...c, font_size: Number(e.target.value) })} /></label>
        </div>
        {isTdp
          ? <label className="f" style={{ marginTop: 10 }}>Distribution statement (printed on the cover)<textarea value={c.distribution_statement || ''} onChange={setCover('distribution_statement')} style={{ minHeight: 60 }} /></label>
          : <label className="check" style={{ marginTop: 10 }}><input type="checkbox" checked={c.restriction_notice !== false} onChange={(e) => setC({ ...c, restriction_notice: e.target.checked })} /> Print the FAR 52.215-1(e) data restriction notice on the cover</label>}
        <label className="f" style={{ marginTop: 10 }}>Internal notes (not exported)<textarea value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></label>
        <div className="row" style={{ marginTop: 12 }}>
          <button className="primary" onClick={() => updatePkg({ cover: c, ...f })}>Save settings</button>
        </div>
      </div>
      {pkg.opportunity?.page_limits?.length > 0 && (
        <div className="panel">
          <h2>Page limits found in the solicitation</h2>
          <ul className="clean small">{pkg.opportunity.page_limits.map((x, i) => <li key={i}>{x}</li>)}</ul>
          <p className="small muted">Set the matching limit on each section so the outline warns you when a section runs long.</p>
        </div>
      )}
      <div className="panel">
        <h2>Delete package</h2>
        <p className="small muted">Removes the outline, written content and uploaded deliverable files. Library entries and the opportunity are not affected.</p>
        <button onClick={onDelete}>Delete package</button>
      </div>
    </>
  )
}

function InlineText({ value, onSave, className }) {
  const [v, setV] = useState(value)
  useEffect(() => setV(value), [value])
  return <input className={className} value={v} onChange={(e) => setV(e.target.value)} onBlur={() => v.trim() && v !== value && onSave(v.trim())} onKeyDown={(e) => e.key === 'Enter' && e.target.blur()} />
}
