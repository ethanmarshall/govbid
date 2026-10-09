import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'

// Subcontract questions: [key, label, help]
const QUESTIONS = [
  ['commercial', 'Commercial product or service', 'Sold to the general public in the same form.'],
  ['cots', 'COTS item', 'Commercially available off-the-shelf, bought without modification.'],
  ['prime_commercial', 'My prime contract is a commercial contract', 'Prime awarded under FAR part 12.'],
  ['supplies', 'Supplies', ''],
  ['services', 'Services', ''],
  ['sca_covered', 'Service Contract Labor Standards apply', 'Service employees doing the work.'],
  ['maintenance_repair', 'Maintenance and repair services', ''],
  ['construction', 'Construction', ''],
  ['involves_fci', 'Vendor will have Federal contract information', 'FCI on their computers or email.'],
  ['involves_cui', 'Vendor will get CUI / covered defense information', 'Drawings or data marked CUI, export controlled tech data.'],
  ['operationally_critical', 'Operationally critical support', ''],
  ['us_work', 'Some work performed in the United States', ''],
  ['international', 'Some work or supplies outside the United States', ''],
  ['small_business', 'Vendor is a small business', ''],
  ['further_subcontracting', 'Vendor will subcontract part of the work', ''],
  ['pii', 'Vendor handles PII or a Privacy Act system of records', ''],
  ['electronic_parts', 'Electronic parts or assemblies with them', ''],
  ['original_manufacturer', 'Vendor is the original manufacturer of those parts', ''],
  ['specialty_metals', 'Items contain specialty metals', 'Titanium, zirconium, many alloy steels, and nickel or cobalt alloys (see the clause definition).'],
  ['iuid', 'Items need IUID marking', ''],
  ['ocean_shipping', 'Vendor ships supplies by sea', ''],
  ['resale_no_value_added', 'I resell the item without adding value', ''],
  ['contingency_support', 'Shipped in direct support of contingency operations or exercises', ''],
]

const blankSub = () => ({ value: '', performance_days: '', supplies: true, us_work: true })
const usd = (n) => (n == null ? '' : `$${Number(n).toLocaleString()}`)
const VERDICT = { yes: 'Flow down', no: 'Not required', check: 'Check the clause' }

export default function Flowdown() {
  const [opps, setOpps] = useState([])
  const [oppId, setOppId] = useState(new URLSearchParams(window.location.search).get('opportunity') || '')
  const [text, setText] = useState('')
  const [sub, setSub] = useState(blankSub)
  const [res, setRes] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [po, setPo] = useState({ vendor: '', po_number: '', prime_contract: '', buyer: '' })
  const [include, setInclude] = useState({})
  const [showAll, setShowAll] = useState(false)
  const [table, setTable] = useState(null)

  useEffect(() => {
    api.get('/api/workbook/opportunities').then((d) => setOpps(d.opportunities || [])).catch(() => {})
  }, [])

  const body = () => ({
    opportunity_id: oppId ? Number(oppId) : null,
    clause_text: text,
    subcontract: { ...sub, value: Number(sub.value) || 0, performance_days: Number(sub.performance_days) || 0 },
  })

  const run = async () => {
    setErr(''); setBusy(true)
    try {
      const r = await api.post('/api/flowdown/check', body())
      setRes(r); setInclude({})
      if (!r.results.length) setErr('No clause numbers found. Paste clause numbers or pick an opportunity that has an analysis.')
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const download = async () => {
    setErr('')
    try {
      const extra = Object.keys(include).filter((k) => include[k])
      const r = await api.post('/api/flowdown/po-attachment', { ...body(), ...po, include: extra })
      const blob = await r.blob()
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `PO_${po.po_number || 'terms'}_flowdown.docx`
      a.click()
      URL.revokeObjectURL(a.href)
    } catch (e) { setErr(e.message) }
  }

  const loadAll = async () => {
    if (!table) setTable(await api.get('/api/flowdown/clauses'))
    setShowAll((v) => !v)
  }

  const shown = useMemo(() => {
    if (!res) return []
    const order = { yes: 0, check: 1, no: 2 }
    return [...res.results].sort((a, b) => order[a.flow_down] - order[b.flow_down])
  }, [res])

  const setQ = (k) => (e) => setSub({ ...sub, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })

  return (
    <>
      <h1>Clause flowdown</h1>
      <p className="sub">Find which prime contract clauses go into a vendor purchase order or subcontract, and print the PO terms attachment.</p>
      {err && <div className="err">{err}</div>}

      <div className="grid g2">
        <div className="panel">
          <h3>1. Prime contract clauses</h3>
          <label className="f">Opportunity (uses its analysis and compliance matrix)
            <select value={oppId} onChange={(e) => setOppId(e.target.value)}>
              <option value="">None</option>
              {opps.map((o) => <option key={o.id} value={o.id}>{o.solicitation_number || `#${o.id}`} {o.title?.slice(0, 70)}</option>)}
            </select>
          </label>
          <label className="f">Or paste clause numbers or Section I text
            <textarea rows={6} value={text} onChange={(e) => setText(e.target.value)} placeholder="52.204-21, 52.222-36, 252.204-7012 ..." />
          </label>
          <p className="small muted">Clause numbers are picked out automatically (52.xxx-xx and 252.xxx-xxxx).</p>
        </div>

        <div className="panel">
          <h3>2. About the subcontract</h3>
          <div className="grid g2">
            <label className="f">Value ($)<input type="number" value={sub.value} onChange={setQ('value')} /></label>
            <label className="f">Performance period (days)<input type="number" value={sub.performance_days} onChange={setQ('performance_days')} /></label>
          </div>
          <div className="fd-questions">
            {QUESTIONS.map(([k, label, help]) => (
              <label key={k} className="check" title={help}>
                <input type="checkbox" checked={!!sub[k]} onChange={setQ(k)} /> {label}
              </label>
            ))}
          </div>
          <div className="row" style={{ marginTop: 10 }}>
            <button className="primary" onClick={run} disabled={busy}>{busy ? 'Checking…' : 'Check flowdown'}</button>
            <button onClick={() => { setSub(blankSub()); setRes(null) }}>Reset</button>
          </div>
        </div>
      </div>

      {res && res.results.length > 0 && (
        <div className="panel">
          <div className="row spread">
            <h3>Result{res.opportunity ? `: ${res.opportunity}` : ''}</h3>
            <span className="small muted">{res.flow_down.length} to flow down, {res.check.length} to check, {res.not_required.length} not required</span>
          </div>
          {sub.commercial && <p className="notice small">{res.commercial_note}</p>}
          <table>
            <thead><tr><th>Clause</th><th>Decision</th><th>Why</th><th>Rule in the clause</th><th>Add to PO</th></tr></thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.number}>
                  <td className="mono">
                    {r.source_url ? <a href={r.source_url} target="_blank" rel="noreferrer">{r.number}</a> : r.number}
                    <div className="small">{r.title}</div>
                    {r.date && <div className="small muted">({r.date})</div>}
                  </td>
                  <td><span className={`tag fd-${r.flow_down}`}>{VERDICT[r.flow_down]}</span></td>
                  <td className="small">
                    {r.reason}
                    {r.portion && <div><b>Extent:</b> {r.portion}</div>}
                    {r.note && <div className="muted">{r.note}</div>}
                  </td>
                  <td className="small muted" style={{ maxWidth: 380 }}>
                    <div>{r.condition}</div>
                    {r.paragraph && <details><summary>Clause text</summary>{r.paragraph}</details>}
                  </td>
                  <td>
                    {r.flow_down === 'yes' ? <span className="small">Included</span> : (
                      <label className="check small"><input type="checkbox" checked={!!include[r.number]} onChange={(e) => setInclude({ ...include, [r.number]: e.target.checked })} /> Add</label>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3 style={{ marginTop: 16 }}>3. PO terms attachment</h3>
          <div className="grid g4">
            <label className="f">Vendor<input value={po.vendor} onChange={(e) => setPo({ ...po, vendor: e.target.value })} /></label>
            <label className="f">PO number<input value={po.po_number} onChange={(e) => setPo({ ...po, po_number: e.target.value })} /></label>
            <label className="f">Prime contract<input value={po.prime_contract} onChange={(e) => setPo({ ...po, prime_contract: e.target.value })} /></label>
            <label className="f">Buyer (your company)<input value={po.buyer} onChange={(e) => setPo({ ...po, buyer: e.target.value })} /></label>
          </div>
          <button className="primary" onClick={download} style={{ marginTop: 8 }}>Download PO attachment (.docx)</button>
          <p className="small muted">Lists the clauses marked "Flow down" plus any you added, incorporated by reference. Confirm the clause dates against your prime contract.</p>
        </div>
      )}

      <div className="panel">
        <div className="row spread">
          <h3>Clause table</h3>
          <button className="link" onClick={loadAll}>{showAll ? 'Hide' : 'Show all clauses'}</button>
        </div>
        <p className="small muted">
          Each rule was read from the clause text on acquisition.gov (checked {table?.verified_on || '2026-10-08'}). Thresholds change with inflation
          adjustments, so confirm them against the clause dates in your contract. Commercial subcontracts follow FAR 52.244-6(c)(1) or 52.212-5(e)(1) and DFARS 252.244-7000.
        </p>
        {showAll && table && (
          <table>
            <thead><tr><th>Clause</th><th>Flowdown</th><th>Condition</th><th>Threshold</th></tr></thead>
            <tbody>
              {table.clauses.map((c) => (
                <tr key={c.number}>
                  <td className="mono"><a href={c.source_url} target="_blank" rel="noreferrer">{c.number}</a><div className="small">{c.title}</div></td>
                  <td className="small">{c.status.replace('_', ' ')}{c.commercial ? ', incl. commercial' : ''}</td>
                  <td className="small">{c.condition}</td>
                  <td className="small">{usd(c.threshold)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  )
}
