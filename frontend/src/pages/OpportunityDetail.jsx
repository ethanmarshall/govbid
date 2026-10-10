import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, fmtDue, money } from '../api'
import { DaysLeft, EligBadge, useMeta } from '../App.jsx'
import { ASSIST, resourcesForClauses } from '../resources'
import SourcesSoughtDraft from '../SourcesSoughtDraft'

const STATUS_OPTIONS = ['open', 'in progress', 'done', 'n/a']

export default function OpportunityDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const meta = useMeta()
  const [o, setO] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState('')
  const [tab, setTab] = useState('overview')
  const fileRef = useRef()

  const load = () => api.get(`/api/opportunities/${id}`).then(setO).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [id])

  const run = async (label, fn) => {
    setBusy(label); setErr(''); setMsg('')
    try { await fn() } catch (e) { setErr(e.message) }
    setBusy('')
  }

  const upload = () => run('upload', async () => {
    const files = fileRef.current.files
    if (!files.length) return
    const fd = new FormData()
    Array.from(files).forEach((f) => fd.append('files', f))
    const r = await api.upload(`/api/opportunities/${id}/documents`, fd)
    fileRef.current.value = ''
    setMsg(`Uploaded ${r.saved.length} file(s).`)
    await load()
  })

  const fetchAttachments = () => run('fetch', async () => {
    const r = await api.post(`/api/opportunities/${id}/fetch-attachments`)
    setMsg(`Downloaded ${r.saved.length} attachment(s).` + (r.errors.length ? ` ${r.errors.length} failed; download those from SAM.gov and upload them here.` : ''))
    await load()
  })

  const analyze = () => run('analyze', async () => {
    const r = await api.post(`/api/opportunities/${id}/analyze`)
    setO(r)
    setTab('breakdown')
  })

  const savePipeline = (patch) => run('pipeline', async () => {
    const current = o.pipeline || { stage: 'tracking', priority: 'medium', bid_amount: null, notes: '', debrief: '' }
    await api.put(`/api/opportunities/${id}/pipeline`, { ...current, ...patch })
    await load()
  })

  const updateRow = (idx, key, value) => {
    const m = o.analysis.compliance_matrix.map((r, i) => (i === idx ? { ...r, [key]: value } : r))
    setO({ ...o, analysis: { ...o.analysis, compliance_matrix: m } })
  }
  const saveMatrix = () => run('matrix', async () => {
    await api.put(`/api/opportunities/${id}/matrix`, { compliance_matrix: o.analysis.compliance_matrix })
    setMsg('Compliance matrix saved.')
  })

  if (err && !o) return <div className="err">{err}</div>
  if (!o) return <p className="muted">Loading…</p>
  const e = o.eligibility
  const b = o.analysis?.breakdown || {}

  return (
    <>
      <p className="small"><Link to="/opportunities">← Opportunities</Link></p>
      <div className="row spread" style={{ alignItems: 'flex-start' }}>
        <div style={{ maxWidth: 900 }}>
          <h1>{o.title}</h1>
          <p className="sub">{o.agency}</p>
        </div>
        <div className="row">
          {o.url && <a className="btn" href={o.url} target="_blank" rel="noreferrer">Open on {o.source === 'dibbs' ? 'DIBBS' : o.source === 'sam' ? 'SAM.gov' : 'source'}</a>}
          <button onClick={() => { if (confirm('Remove this opportunity?')) api.del(`/api/opportunities/${id}`).then(() => nav('/opportunities')) }}>Remove</button>
        </div>
      </div>

      {err && <div className="err">{err}</div>}
      {msg && <div className="okmsg">{msg}</div>}

      <div className="grid g4" style={{ marginBottom: 16 }}>
        <Field l="Solicitation #" v={<span className="mono">{o.solicitation_number || 'n/a'}</span>} />
        <Field l="Notice type" v={o.notice_type || 'n/a'} />
        <Field l="Response due" v={<>{fmtDue(o.response_deadline)} <span className="small">(<DaysLeft days={o.days_left} />)</span></>} />
        <Field l="NAICS / PSC" v={<span className="mono">{o.naics || '—'} / {o.psc || '—'}</span>} />
        <Field l="Set-aside" v={e.set_aside_label} />
        <Field l="Place of performance" v={o.place_of_performance || 'n/a'} />
        {o.nsn && <Field l="NSN / Qty" v={<span className="mono">{o.nsn} {o.quantity && `× ${o.quantity}`}</span>} />}
        {o.estimated_value != null && <Field l="Value" v={money(o.estimated_value)} />}
      </div>

      <div className="panel">
        <div className="row spread">
          <div className="row"><h2 style={{ margin: 0 }}>Can you bid?</h2><EligBadge status={e.status} /></div>
          <Link className="small" to="/profile">Edit certifications</Link>
        </div>
        <p style={{ marginBottom: e.warnings.length ? 8 : 0 }}>{e.reason}</p>
        {e.warnings.length > 0 && <ul className="clean small">{e.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>}
      </div>

      {o.jcp_note && <div className="err">{o.jcp_note} <Link to="/profile">Update JCP status</Link></div>}

      <BidScore oppId={o.id} key={`${o.id}-${o.analysis?.created_at || ''}`} />

      {o.changes?.some((c) => !c.seen) && (
        <div className="panel">
          <div className="row spread">
            <h2 style={{ margin: 0 }}>Changed since you started tracking</h2>
            <button className="link" onClick={() => run('seen', async () => { await api.post(`/api/watch/seen?opportunity_id=${o.id}`); await load() })}>Mark as seen</button>
          </div>
          <table className="small" style={{ marginTop: 8 }}><tbody>
            {o.changes.filter((c) => !c.seen).map((c) => (
              <tr key={c.id}><td style={{ whiteSpace: 'nowrap' }}><b>{c.field}</b></td><td className="muted">{c.old || '(blank)'}</td><td>→ {c.new}</td><td className="muted" style={{ whiteSpace: 'nowrap' }}>{c.detected_at?.slice(0, 10)}</td></tr>
            ))}
          </tbody></table>
          <p className="small muted" style={{ marginBottom: 0 }}>Pull the new attachments on the Documents tab and re-run the analysis so the compliance matrix covers the amendment.</p>
        </div>
      )}

      <PipelineBar o={o} stages={meta?.pipeline_stages || []} onSave={savePipeline} busy={busy === 'pipeline'} />

      <PackagesBar oppId={o.id} hasAnalysis={!!o.analysis} />

      <SourcesSoughtDraft opp={o} />

      <div className="tabs">
        {['overview', 'documents', 'breakdown', 'matrix'].map((t) => (
          <button key={t} className={tab === t ? 'on' : ''} onClick={() => setTab(t)}>
            {{ overview: 'Notice', documents: `Documents (${o.documents.length})`, breakdown: 'Requirements breakdown', matrix: `Compliance matrix${o.analysis ? ` (${o.analysis.compliance_matrix.length})` : ''}` }[t]}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <div className="grid g2">
          <div className="panel">
            <h2>Description</h2>
            {o.description ? <div className="desc">{stripHtml(o.description)}</div> : <p className="muted">No description loaded. SAM.gov descriptions load when the API key is set; otherwise open the notice on SAM.gov.</p>}
          </div>
          <div className="panel">
            <h2>Contacts</h2>
            {o.contacts?.length ? o.contacts.map((c, i) => (
              <div key={i} style={{ marginBottom: 10 }}>
                <div className="t">{c.name} <span className="small muted">{c.title}</span></div>
                <div className="small">{c.email && <a href={`mailto:${c.email}`}>{c.email}</a>} {c.phone}</div>
              </div>
            )) : <p className="muted">No contacts listed.</p>}
          </div>
        </div>
      )}

      {tab === 'documents' && (
        <div className="panel">
          <h2>Solicitation documents</h2>
          <p className="small muted">Add the RFP/RFQ, SOW/PWS, Section L and M, and amendments. The analysis reads every file here plus the notice description.</p>
          <div className="row" style={{ marginBottom: 12 }}>
            <input type="file" multiple ref={fileRef} accept=".pdf,.docx,.xlsx,.txt,.html,.htm" />
            <button onClick={upload} disabled={busy === 'upload'}>{busy === 'upload' ? 'Uploading…' : 'Upload'}</button>
            {o.source === 'sam' && o.attachments?.length > 0 && (
              <button onClick={fetchAttachments} disabled={busy === 'fetch'}>{busy === 'fetch' ? 'Downloading…' : `Pull ${o.attachments.length} attachment(s) from SAM.gov`}</button>
            )}
          </div>
          {o.documents.length === 0 ? <p className="muted">No documents yet.</p> : (
            <table><tbody>
              {o.documents.map((d) => (
                <tr key={d}><td className="mono">{d}</td><td style={{ textAlign: 'right' }}>
                  <button className="link" onClick={() => run('del', async () => { await api.del(`/api/opportunities/${id}/documents/${encodeURIComponent(d)}`); await load() })}>Delete</button>
                </td></tr>
              ))}
            </tbody></table>
          )}
          <div style={{ marginTop: 16 }}>
            <button className="primary" onClick={analyze} disabled={busy === 'analyze'}>
              {busy === 'analyze' ? 'Analyzing…' : o.analysis ? 'Re-run analysis' : 'Analyze requirements'}
            </button>
            <span className="small muted" style={{ marginLeft: 10 }}>{meta?.ai_configured ? 'Uses Claude.' : 'Rule-based (add ANTHROPIC_API_KEY for a fuller breakdown).'}</span>
          </div>
        </div>
      )}

      {tab === 'breakdown' && (
        !o.analysis ? <div className="panel"><p className="muted">No analysis yet. Add documents and click Analyze requirements on the Documents tab.</p><button className="primary" onClick={analyze} disabled={busy === 'analyze'}>{busy === 'analyze' ? 'Analyzing…' : 'Analyze now'}</button></div> : (
          <div className="panel">
            <div className="row spread"><h2 style={{ margin: 0 }}>Summary</h2><span className="small muted">{o.analysis.method === 'claude' ? 'Claude' : 'Rule-based'} · {new Date(o.analysis.created_at + 'Z').toLocaleString()}</span></div>
            <p>{o.analysis.summary}</p>
            {b.red_flags?.length > 0 && <><h3>Red flags</h3><List items={b.red_flags} /></>}
            <div className="grid g2">
              <div>
                {b.scope && <><h3>Scope</h3><p>{b.scope}</p></>}
                {b.contract_type && <><h3>Contract type</h3><p>{b.contract_type}</p></>}
                {b.period_of_performance && <><h3>Period of performance</h3><p>{b.period_of_performance}</p></>}
                <h3>Evaluation</h3><p>{b.evaluation_method}</p>
                {b.evaluation_factors?.length > 0 && <List items={b.evaluation_factors} />}
                {b.eligibility_notes?.length > 0 && <><h3>Eligibility</h3><List items={b.eligibility_notes} /></>}
              </div>
              <div>
                {b.deadlines?.length > 0 && <><h3>Deadlines</h3><List items={b.deadlines} /></>}
                {b.page_limits?.length > 0 && <><h3>Page limits</h3><List items={b.page_limits} /></>}
                {b.submission_instructions && <><h3>Submission</h3><p>{b.submission_instructions}</p></>}
                {b.questions_to_ask?.length > 0 && <><h3>Questions for the contracting officer</h3><List items={b.questions_to_ask} /></>}
              </div>
            </div>
            {b.key_clauses?.length > 0 && (
              <>
                <h3>Key clauses</h3>
                <table><tbody>
                  {b.key_clauses.map((c, i) => <tr key={i}><td className="mono" style={{ whiteSpace: 'nowrap' }}>{c.clause}</td><td>{c.note}</td></tr>)}
                </tbody></table>
              </>
            )}
            {b.cited_standards?.length > 0 && (
              <>
                <h3>Standards and data items cited</h3>
                <p className="small muted" style={{ marginTop: 0 }}>Get the exact revision cited. MIL-STDs and DIDs are free on <a href={ASSIST} target="_blank" rel="noreferrer">ASSIST</a>; industry standards are sold by their publishers. Every one is saved to your <Link to="/standards">Standards library</Link>.</p>
                <table><tbody>
                  {b.cited_standards.map((s) => {
                    const chk = (o.standards_check || []).find((x) => x.cited_as === s.standard) || {}
                    return (
                      <tr key={s.standard}>
                        <td className="mono" style={{ whiteSpace: 'nowrap' }}>{chk.base_id ? <Link to={`/standards?open=${encodeURIComponent(chk.base_id)}`}>{s.standard}</Link> : s.standard}</td>
                        <td className="small">{chk.title || s.type}</td>
                        <td className="small muted">cited {s.count}×</td>
                        <td className="small">{chk.mismatch
                          ? <span className="due-soon">You have rev {chk.revision_on_file}; this cites rev {chk.cited_revision}</span>
                          : chk.revision_on_file ? <span className="muted">On file: rev {chk.revision_on_file}{chk.has_file ? ' (PDF)' : ''}</span> : <span className="muted">Not on file</span>}</td>
                        <td><span className={`badge ${s.free ? 'b-eligible_now' : 'b-not_eligible'}`}>{s.free ? 'Free' : 'Paid'}</span></td>
                      </tr>
                    )
                  })}
                </tbody></table>
              </>
            )}
            <RelatedResources clauses={(b.key_clauses || []).map((c) => c.clause)} />
            <p className="small muted" style={{ marginTop: 16 }}>Sources: {o.analysis.source_files.join(', ') || 'notice metadata only'}. Always confirm against the solicitation itself.</p>
          </div>
        )
      )}

      {tab === 'matrix' && (
        !o.analysis ? <div className="panel"><p className="muted">Run the analysis first.</p></div> : (
          <div className="panel" style={{ overflowX: 'auto' }}>
            <div className="row spread" style={{ marginBottom: 10 }}>
              <h2 style={{ margin: 0 }}>Compliance matrix</h2>
              <div className="row">
                <button onClick={saveMatrix} disabled={busy === 'matrix'}>Save changes</button>
                <a className="btn primary" href={`/api/opportunities/${id}/matrix.xlsx`}>Export to Excel</a>
              </div>
            </div>
            <table>
              <thead><tr><th>#</th><th>Requirement</th><th>Ref</th><th>Category</th><th>Proposal location</th><th>Status</th></tr></thead>
              <tbody>
                {o.analysis.compliance_matrix.map((r, i) => (
                  <tr key={i}>
                    <td className="mono">{r.id}</td>
                    <td style={{ minWidth: 380 }}>{r.requirement}<div className="small muted">{r.source}</div></td>
                    <td className="mono small">{r.reference}</td>
                    <td className="small">{r.category}</td>
                    <td><input value={r.response_location || ''} onChange={(ev) => updateRow(i, 'response_location', ev.target.value)} placeholder="Vol I, 2.3" style={{ width: 120 }} /></td>
                    <td><select value={r.status || 'open'} onChange={(ev) => updateRow(i, 'status', ev.target.value)}>{STATUS_OPTIONS.map((s) => <option key={s}>{s}</option>)}</select></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </>
  )
}

function PackagesBar({ oppId, hasAnalysis }) {
  const nav = useNavigate()
  const [rows, setRows] = useState([])
  const [busy, setBusy] = useState(false)
  useEffect(() => { api.get(`/api/packages?opportunity_id=${oppId}`).then(setRows).catch(() => {}) }, [oppId])
  const start = async () => {
    setBusy(true)
    try { const p = await api.post('/api/packages', { kind: 'proposal', opportunity_id: oppId }); nav(`/packages/${p.id}`) } catch { setBusy(false) }
  }
  return (
    <div className="panel row spread">
      <div className="row">
        <b>Proposal packages</b>
        {rows.length === 0 && <span className="muted small">None yet.{!hasAnalysis && ' Analyze the requirements first so the outline arrives with requirements assigned.'}</span>}
        {rows.map((p) => <Link key={p.id} to={`/packages/${p.id}`} className="tag">{p.name.slice(0, 40)} · {p.sections_done}/{p.sections_total}</Link>)}
      </div>
      <div className="row">
        <Link className="btn" to={`/part-quotes?opportunity=${oppId}`}>Quote a part</Link>
        <Link className="btn" to={`/pricing-workbook?opportunity=${oppId}`}>Price build</Link>
        <Link className="btn" to={`/flowdown?opportunity=${oppId}`}>Clause flowdown</Link>
        <Link className="btn" to={`/jobs?from_opp=${oppId}`} title="Record the award and start the job">Won it</Link>
        <button className={rows.length ? '' : 'primary'} onClick={start} disabled={busy}>{busy ? 'Creating…' : 'Start proposal package'}</button>
      </div>
    </div>
  )
}

function PipelineBar({ o, stages, onSave, busy }) {
  const p = o.pipeline
  const [notes, setNotes] = useState(p?.notes || '')
  const [bid, setBid] = useState(p?.bid_amount ?? '')
  useEffect(() => { setNotes(p?.notes || ''); setBid(p?.bid_amount ?? '') }, [o.id, p?.notes, p?.bid_amount])
  if (!p) {
    return (
      <div className="panel row spread">
        <span className="muted">Not in your pipeline.</span>
        <button className="primary" disabled={busy} onClick={() => onSave({ stage: 'tracking' })}>Track this opportunity</button>
      </div>
    )
  }
  return (
    <div className="panel">
      <div className="row">
        <label className="f">Stage
          <select value={p.stage} onChange={(e) => onSave({ stage: e.target.value })}>{stages.map((s) => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}</select>
        </label>
        <label className="f">Priority
          <select value={p.priority} onChange={(e) => onSave({ priority: e.target.value })}>{['low', 'medium', 'high'].map((s) => <option key={s}>{s}</option>)}</select>
        </label>
        <label className="f">Bid amount ($)
          <input type="number" value={bid} onChange={(e) => setBid(e.target.value)} onBlur={() => onSave({ bid_amount: bid === '' ? null : Number(bid) })} style={{ width: 140 }} />
        </label>
        <label className="f" style={{ flex: 1, minWidth: 240 }}>Notes
          <input value={notes} onChange={(e) => setNotes(e.target.value)} onBlur={() => onSave({ notes })} placeholder="Teaming partners, questions, go/no-go reasoning" />
        </label>
      </div>
    </div>
  )
}

function RelatedResources({ clauses }) {
  const items = resourcesForClauses(clauses)
  if (!items.length) return null
  return (
    <>
      <h3>Related resources</h3>
      <ul className="clean">
        {items.map((i) => (
          <li key={i.name}><a href={i.url} target="_blank" rel="noreferrer">{i.name}</a> <span className="small muted">{i.desc}</span></li>
        ))}
      </ul>
      <p className="small"><Link to="/resources">All resources and checklists</Link></p>
    </>
  )
}

const Field = ({ l, v }) => (
  <div className="stat"><div className="l">{l}</div><div style={{ marginTop: 4 }}>{v}</div></div>
)
const List = ({ items }) => <ul className="clean">{items.map((x, i) => <li key={i}>{typeof x === 'string' ? x : JSON.stringify(x)}</li>)}</ul>
const stripHtml = (s) => (s || '').replace(/<br\s*\/?>/gi, '\n').replace(/<\/p>/gi, '\n\n').replace(/<[^>]+>/g, '').replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').trim()

function BidScore({ oppId }) {
  const [s, setS] = useState(null)
  const [open, setOpen] = useState(false)
  useEffect(() => { api.get(`/api/opportunities/${oppId}/score`).then(setS).catch(() => {}) }, [oppId])
  if (!s) return null
  const tone = s.recommendation === 'Bid' ? 'b-eligible_now' : s.recommendation === 'Consider' || s.recommendation.startsWith('Bid once') ? 'b-eligible_once_certified' : 'b-not_eligible'
  return (
    <div className="panel">
      <div className="row spread">
        <div className="row">
          <h2 style={{ margin: 0 }}>Bid score</h2>
          <span className="score-num">{s.score}</span><span className="muted small">/ 100</span>
          <span className={`badge ${tone}`}>{s.recommendation}</span>
        </div>
        <button className="link" onClick={() => setOpen(!open)}>{open ? 'Hide why' : 'Why?'}</button>
      </div>
      <div className="scorebar">{s.factors.map((f) => <span key={f.factor} title={`${f.factor}: ${f.points}/${f.out_of}`} style={{ flex: f.out_of }}><i style={{ width: `${(f.points / f.out_of) * 100}%` }} /></span>)}</div>
      {open && (
        <table className="small" style={{ marginTop: 8 }}><tbody>
          {s.factors.map((f) => <tr key={f.factor}><td style={{ width: 110 }}><b>{f.factor}</b></td><td className="mono" style={{ width: 70 }}>{f.points}/{f.out_of}</td><td>{f.note}</td></tr>)}
        </tbody></table>
      )}
      {open && <p className="small muted" style={{ marginBottom: 0 }}>A guide for where to spend proposal time. Past performance, keywords and NAICS come from your profile and Past performance page.</p>}
    </div>
  )
}
