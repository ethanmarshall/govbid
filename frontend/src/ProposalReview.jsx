import { useEffect, useState } from 'react'
import { api } from './api'

const RATING_CLASS = { Outstanding: 'r-out', Good: 'r-good', Acceptable: 'r-acc', Marginal: 'r-marg', Unacceptable: 'r-unacc' }
const STATUS_CLASS = { met: 'b-eligible_now', partial: 'b-eligible_once_certified', missing: 'b-not_eligible' }
const PRIORITY = { 1: 'Must fix', 2: 'Should fix', 3: 'Polish' }

export function RatingBadge({ rating }) {
  return <span className={`badge rating ${RATING_CLASS[rating] || ''}`}>{rating || 'n/a'}</span>
}

export default function ProposalReview({ pkg, onOpenSection }) {
  const [hist, setHist] = useState(null)
  const [run, setRun] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [compFilter, setCompFilter] = useState('open')

  const load = async (selectId) => {
    try {
      const h = await api.get(`/api/writing/review/${pkg.id}`)
      setHist(h)
      if (selectId) setRun(await api.get(`/api/writing/review-run/${selectId}`))
      else setRun(h.latest)
    } catch (e) { setErr(e.message) }
  }
  useEffect(() => { load() }, [pkg.id])

  const start = async () => {
    setBusy(true); setErr('')
    try {
      const r = await api.post(`/api/writing/review/${pkg.id}`)
      setRun(r)
      await load(r.id)
    } catch (e) { setErr(e.message) }
    setBusy(false)
  }

  const pick = async (id) => {
    if (!id) return
    try { setRun(await api.get(`/api/writing/review-run/${id}`)) } catch (e) { setErr(e.message) }
  }

  const remove = async () => {
    if (!run || !confirm('Delete this review run?')) return
    await api.del(`/api/writing/review-run/${run.id}`)
    setRun(null)
    await load()
  }

  if (!hist) return <p className="muted">Loading…</p>
  const res = run?.result
  const secName = (id) => {
    const s = pkg.sections.find((x) => x.id === id)
    return s ? [s.number, s.title].filter(Boolean).join(' ') : null
  }
  const matrixById = Object.fromEntries((pkg.matrix || []).map((r) => [r.id, r]))
  const comp = (res?.compliance || []).filter((c) => compFilter === 'all' || c.status !== 'met')

  return (
    <div>
      <div className="panel">
        <div className="row spread">
          <div>
            <h2 style={{ margin: 0 }}>Evaluator review</h2>
            <p className="small muted" style={{ margin: '4px 0 0' }}>
              Reads the draft the way a source selection evaluator would: against Section L instructions, Section M factors, page limits and the compliance matrix.
              {' '}Method: <b>{hist.ai_configured ? 'Claude, with rule checks' : 'rule-based checks'}</b>
              {!hist.ai_configured && ' (set ANTHROPIC_API_KEY for a full evaluator read)'}.
            </p>
          </div>
          <div className="row">
            {hist.runs.length > 0 && (
              <select value={run?.id || ''} onChange={(e) => pick(Number(e.target.value))}>
                {hist.runs.map((r) => (
                  <option key={r.id} value={r.id}>{new Date(r.created_at + 'Z').toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })} · {r.method} · {r.rating}</option>
                ))}
              </select>
            )}
            <button className="primary" onClick={start} disabled={busy}>{busy ? 'Reviewing…' : hist.runs.length ? 'Run again' : 'Run review'}</button>
          </div>
        </div>
        {!pkg.opportunity && <div className="notice" style={{ marginTop: 12, marginBottom: 0 }}>This package has no linked opportunity, so there are no Section L/M factors or compliance matrix to review against. The review will check completeness only.</div>}
        {pkg.opportunity && !pkg.opportunity.has_analysis && <div className="notice" style={{ marginTop: 12, marginBottom: 0 }}>Analyze the linked opportunity first so the review has the evaluation factors and compliance matrix.</div>}
      </div>

      {err && <div className="err">{err}</div>}
      {!res && !busy && <p className="muted">No reviews yet. Run one when the sections have a first draft.</p>}

      {res && (
        <>
          <div className="panel review-overall">
            <div className="row spread">
              <div className="row">
                <span className="small muted">Overall (estimate)</span>
                <RatingBadge rating={res.overall.rating} />
                <span className="tag">{run.method === 'claude' ? 'Claude' : 'Rules'}</span>
                {res.stats && <span className="small muted">{res.stats.est_pages} pages · {res.stats.requirements ? `${res.stats.requirements - res.stats.missing - res.stats.partial}/${res.stats.requirements} requirements covered` : 'no matrix'}</span>}
              </div>
              <button className="link small" onClick={remove}>Delete this run</button>
            </div>
            <p style={{ marginBottom: 0 }}>{res.overall.summary}</p>
          </div>

          {res.fixes?.length > 0 && (
            <div className="panel">
              <h3 style={{ marginTop: 0 }}>Fixes ({res.fixes.length})</h3>
              <ul className="fixes">
                {res.fixes.map((f, i) => (
                  <li key={i} className={`fix p${f.priority}`}>
                    <span className="badge pri">{PRIORITY[f.priority] || `P${f.priority}`}</span>
                    <span className="fix-text">{f.action}</span>
                    {f.section_id && secName(f.section_id) && (
                      <button className="link small" onClick={() => onOpenSection(f.section_id)}>Open {secName(f.section_id)} →</button>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {res.page_limit_issues?.length > 0 && (
            <div className="err"><b>Page limits:</b><ul className="clean">{res.page_limit_issues.map((x, i) => <li key={i}>{x}</li>)}</ul></div>
          )}

          <div className="grid g2">
            {res.factors.map((f, i) => (
              <div key={i} className="panel factor-card" style={{ marginBottom: 0 }}>
                <div className="row spread">
                  <h3 style={{ margin: 0 }}>{f.factor}</h3>
                  <RatingBadge rating={f.rating} />
                </div>
                <FindingList label="Strengths" items={f.strengths} cls="f-str" />
                <FindingList label="Weaknesses" items={f.weaknesses} cls="f-weak" />
                <FindingList label="Deficiencies" items={f.deficiencies} cls="f-def" />
                <FindingList label="Risks" items={f.risks} cls="f-risk" />
                {f.section_ids?.length > 0 && (
                  <div className="row small" style={{ marginTop: 8 }}>
                    <span className="muted">Sections:</span>
                    {f.section_ids.filter(secName).map((sid) => <button key={sid} className="link small" onClick={() => onOpenSection(sid)}>{secName(sid)}</button>)}
                  </div>
                )}
              </div>
            ))}
          </div>

          {res.compliance?.length > 0 && (
            <div className="panel" style={{ marginTop: 16 }}>
              <div className="row spread">
                <h3 style={{ margin: 0 }}>Compliance ({res.compliance.filter((c) => c.status === 'met').length}/{res.compliance.length} met)</h3>
                <div className="row">
                  <button className={`chip ${compFilter === 'open' ? 'on' : ''}`} onClick={() => setCompFilter('open')}>Open items</button>
                  <button className={`chip ${compFilter === 'all' ? 'on' : ''}`} onClick={() => setCompFilter('all')}>All</button>
                </div>
              </div>
              <table className="small" style={{ marginTop: 8 }}>
                <thead><tr><th>#</th><th>Requirement</th><th>Status</th><th>Where</th><th>Note</th></tr></thead>
                <tbody>
                  {comp.map((c, i) => {
                    const r = matrixById[c.requirement_id]
                    return (
                      <tr key={i}>
                        <td className="mono">{c.requirement_id}</td>
                        <td>{r ? <>{r.reference && <span className="tag">{r.reference}</span>} {r.requirement}</> : <span className="muted">not in current matrix</span>}</td>
                        <td><span className={`badge ${STATUS_CLASS[c.status] || ''}`}>{c.status}</span></td>
                        <td>{c.where}</td>
                        <td className="muted">{c.note}</td>
                      </tr>
                    )
                  })}
                  {comp.length === 0 && <tr><td colSpan={5} className="muted">Every requirement is marked met.</td></tr>}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function FindingList({ label, items, cls }) {
  if (!items?.length) return null
  return (
    <div className={`finding ${cls}`}>
      <div className="flabel">{label}</div>
      <ul className="clean small">{items.map((x, i) => <li key={i}>{x}</li>)}</ul>
    </div>
  )
}
