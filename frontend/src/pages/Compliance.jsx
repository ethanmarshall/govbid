import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, fmtDue } from '../api'

const STATUS_LABEL = {
  not_started: 'Not started',
  planned: 'Planned',
  partial: 'Partial',
  implemented: 'Implemented',
  not_applicable: 'Not applicable',
}

export default function Compliance() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') === 'l2' ? 'l2' : 'l1'
  const [rows, setRows] = useState(null)
  const [summary, setSummary] = useState(null)
  const [settings, setSettings] = useState(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [err, setErr] = useState('')

  const loadSummary = () => api.get('/api/cmmc/summary').then(setSummary).catch((e) => setErr(e.message))
  useEffect(() => {
    api.get('/api/cmmc/controls').then(setRows).catch((e) => setErr(e.message))
    api.get('/api/cmmc/settings').then(setSettings).catch(() => {})
    loadSummary()
  }, [])

  const save = async (row, patch) => {
    setErr('')
    try {
      const updated = await api.put(`/api/cmmc/controls/${row.framework}/${row.control_id}`, patch)
      setRows((rs) => rs.map((r) => (r.framework === row.framework && r.control_id === row.control_id ? updated : r)))
      loadSummary()
    } catch (e) { setErr(`${row.control_id}: ${e.message}`) }
  }

  const saveSettings = async (patch) => {
    setErr('')
    try { setSettings(await api.put('/api/cmmc/settings', patch)); loadSummary() } catch (e) { setErr(e.message) }
  }

  const fw = tab === 'l2' ? 'L2' : 'L1'
  const groups = useMemo(() => {
    if (!rows) return []
    const out = []
    rows.filter((r) => r.framework === fw && (!statusFilter || r.status === statusFilter)).forEach((r) => {
      let g = out.find((x) => x.family === r.family)
      if (!g) { g = { family: r.family, name: r.family_name, rows: [] }; out.push(g) }
      g.rows.push(r)
    })
    return out
  }, [rows, fw, statusFilter])

  if (err && !rows) return <div className="err">{err}</div>
  if (!rows || !summary) return <p className="muted">Loading…</p>

  const counts = rows.filter((r) => r.framework === fw).reduce((a, r) => ({ ...a, [r.status]: (a[r.status] || 0) + 1 }), {})
  const scoreClass = summary.sprs_score >= 110 ? 'good' : summary.sprs_score >= summary.conditional_min_score ? 'ok' : 'low'

  return (
    <>
      <h1>CMMC compliance</h1>
      <p className="sub">
        If you only handle Federal Contract Information (FCI), you need CMMC Level 1: meet the 15 FAR 52.204-21 safeguards and affirm a self-assessment in SPRS every year.
        If a contract involves Controlled Unclassified Information (CUI), you need Level 2 (the 110 NIST SP 800-171 requirements) and a current SPRS score, driven by DFARS 252.204-7012, -7019, -7020 and -7021.
      </p>
      <div className="notice">
        <b>Where to start.</b> A new small supplier usually handles only FCI, so finish Level 1 first. Write one line of evidence for each requirement (what you do, on which device or account), then record your affirmation date below.
        Level 2 only matters once a solicitation says CUI is involved; it is tracked here so you know your score before you bid on one.
      </div>
      {err && <div className="err">{err}</div>}

      <div className="grid g4 cmmc-stats">
        <div className="stat">
          <div className="n">{summary.level1_done} / {summary.level1_total}</div>
          <div className="l">Level 1 requirements met</div>
          <div className="bar"><span style={{ width: `${(100 * summary.level1_done) / summary.level1_total}%` }} /></div>
        </div>
        <div className="stat">
          <div className={`n cmmc-score ${scoreClass}`}>{summary.sprs_score}</div>
          <div className="l">SPRS score (of {summary.sprs_max}; range {summary.sprs_min} to {summary.sprs_max})</div>
        </div>
        <div className="stat">
          <div className="n">{summary.open_poam}</div>
          <div className="l">Open POA&M items{summary.next_poam_due && <>, next due <span className={summary.overdue_poam ? 'due-soon' : ''}>{fmtDue(summary.next_poam_due)}</span></>}</div>
        </div>
        <div className="stat">
          <div className="n small-n">{summary.last_sprs_submission_date ? fmtDue(summary.last_sprs_submission_date) : 'Never'}</div>
          <div className="l">Last SPRS submission{summary.affirmation_date && <>; affirmed {fmtDue(summary.affirmation_date)}</>}</div>
        </div>
      </div>

      {tab === 'l2' && summary.warnings.length > 0 && (
        <ul className="clean small cmmc-warn">{summary.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
      )}

      {settings && <Settings s={settings} onSave={saveSettings} />}

      <div className="tabs">
        <button className={tab === 'l1' ? 'on' : ''} onClick={() => setParams({})}>Level 1 (FAR 52.204-21)</button>
        <button className={tab === 'l2' ? 'on' : ''} onClick={() => setParams({ tab: 'l2' })}>Level 2 (NIST SP 800-171)</button>
      </div>

      <div className="row spread" style={{ marginBottom: 12 }}>
        <div className="row" style={{ gap: 6 }}>
          <button className={`chip ${statusFilter === '' ? 'on' : ''}`} onClick={() => setStatusFilter('')}>All</button>
          {Object.entries(STATUS_LABEL).map(([k, v]) => (
            <button key={k} className={`chip ${statusFilter === k ? 'on' : ''}`} onClick={() => setStatusFilter(statusFilter === k ? '' : k)}>{v} ({counts[k] || 0})</button>
          ))}
        </div>
        <a className="btn" href="/api/cmmc/export.xlsx">Export status and POA&M (.xlsx)</a>
      </div>

      {tab === 'l2' && (
        <p className="small muted">
          Points are from the DoD Assessment Methodology v1.2.1. Partial counts only for 3.5.3 (MFA for remote and privileged users but not everyone: 3 points off instead of 5) and 3.13.11 (encryption that is not FIPS-validated: 3 instead of 5).
          Mark remote, wireless or mobile requirements Not applicable if you do not allow that access. Only 1-point items (plus 3.13.11 when partial) can sit on a POA&M for a conditional Level 2 status, and never 3.1.20, 3.1.22, 3.10.3 to 3.10.5 or 3.12.4.
        </p>
      )}
      {tab === 'l1' && <p className="small muted">Level 1 does not allow a POA&M: every requirement must be met (or not applicable) before you affirm. The POA&M date here is just your own target.</p>}

      {groups.map((g) => (
        <div className="panel" key={g.family}>
          <h2 style={{ marginTop: 0 }}>{g.name} <span className="tag">{g.family}</span></h2>
          <table className="cmmc-table">
            <thead><tr><th style={{ width: 110 }}>ID</th><th>Requirement</th><th style={{ width: 150 }}>Status</th><th style={{ width: '30%' }}>Evidence</th><th style={{ width: 140 }}>POA&M due</th></tr></thead>
            <tbody>{g.rows.map((r) => <ControlRow key={`${r.framework}-${r.control_id}`} r={r} onSave={save} />)}</tbody>
          </table>
        </div>
      ))}
      {groups.length === 0 && <p className="muted">No requirements match this filter.</p>}
    </>
  )
}

function ControlRow({ r, onSave }) {
  const [evidence, setEvidence] = useState(r.evidence)
  const [due, setDue] = useState(r.poam_due)
  useEffect(() => { setEvidence(r.evidence); setDue(r.poam_due) }, [r.evidence, r.poam_due])
  const isL2 = r.framework === 'L2'
  const blockedPoam = isL2 && !r.poam_allowed && !(r.control_id === '3.13.11' && r.status === 'partial')
  const canPartial = !isL2 || r.partial_credit
  return (
    <tr className={`cmmc-row s-${r.status}`}>
      <td className="mono">
        {r.control_id}
        {isL2 && <div className="small muted">{r.weight ? `${r.weight} pt${r.weight > 1 ? 's' : ''}` : 'no points'}{r.deduction ? `, -${r.deduction}` : ''}</div>}
        {!isL2 && <div className="small muted">{r.far_paragraph.replace('52.204-21', '')}</div>}
      </td>
      <td>
        {!isL2 && <div className="t">{r.title}</div>}
        <div className={isL2 ? '' : 'small'}>{r.text}</div>
        {!isL2 && <div className="small muted">NIST SP 800-171: {r.nist_ids.join(', ')}</div>}
        {r.scoring_note && <div className="small muted">{r.scoring_note}</div>}
        {r.partial_credit && <div className="small muted">Partial = {r.partial_credit.partial_meaning.toLowerCase()} ({r.partial_credit.partial} pts off).</div>}
      </td>
      <td>
        <select value={r.status} onChange={(e) => onSave(r, { status: e.target.value })}>
          {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}{k === 'partial' && !canPartial ? ' (no credit)' : ''}</option>)}
        </select>
      </td>
      <td>
        <textarea rows={2} value={evidence} placeholder="What you do and where (policy, setting, screenshot)"
          onChange={(e) => setEvidence(e.target.value)} onBlur={() => evidence !== r.evidence && onSave(r, { evidence })} />
      </td>
      <td>
        <input type="date" value={due} onChange={(e) => setDue(e.target.value)} onBlur={() => due !== r.poam_due && onSave(r, { poam_due: due })} />
        {blockedPoam && r.status !== 'implemented' && r.status !== 'not_applicable' && due && <div className="small due-soon">Not allowed on a POA&M</div>}
      </td>
    </tr>
  )
}

function Settings({ s, onSave }) {
  const [d, setD] = useState(s)
  useEffect(() => setD(s), [s])
  const blur = (k) => () => d[k] !== s[k] && onSave({ [k]: d[k] })
  return (
    <div className="panel">
      <div className="grid g3">
        <label className="f">Last SPRS submission<input type="date" value={d.last_sprs_submission_date} onChange={(e) => setD({ ...d, last_sprs_submission_date: e.target.value })} onBlur={blur('last_sprs_submission_date')} /></label>
        <label className="f">Affirmation date (annual)<input type="date" value={d.affirmation_date} onChange={(e) => setD({ ...d, affirmation_date: e.target.value })} onBlur={blur('affirmation_date')} /></label>
        <label className="f">Scope: which systems hold FCI or CUI
          <textarea rows={2} value={d.scope_notes} placeholder="Example: one MacBook, Google Workspace mail, no CUI" onChange={(e) => setD({ ...d, scope_notes: e.target.value })} onBlur={blur('scope_notes')} />
        </label>
      </div>
    </div>
  )
}
