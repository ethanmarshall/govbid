import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'

const usd = (n) => (n == null || n === '' ? '' : `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`)
const pct = (n) => (n == null ? '' : `${Number(n).toFixed(2)}%`)
const num = (v) => (v === '' || v == null ? '' : Number(v))
const blankClin = (n) => ({ clin: String(n).padStart(4, '0'), description: '', kind: 'services', quantity: 1, unit: 'LO', nsn: '', labor: [], materials: [], subcontracts: [], odcs: [], parts: [] })

export default function PricingWorkbook() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || 'builds'
  const id = params.get('id')
  const go = (t, extra = {}) => setParams({ ...(t === 'builds' ? {} : { tab: t }), ...extra })
  return (
    <>
      <h1>Pricing workbook</h1>
      <p className="sub">Price service, engineering and design-and-build bids from labor hours, materials, subcontracts and your indirect rates. For a single machined or printed part, use Part quotes and pull it in as a part line.</p>
      <div className="tabs">
        <button className={tab === 'builds' ? 'on' : ''} onClick={() => go('builds')}>Price builds</button>
        <button className={tab === 'rates' ? 'on' : ''} onClick={() => go('rates')}>Indirect rates and labor</button>
      </div>
      {tab === 'builds' && (id ? <BuildEditor key={id} id={Number(id)} onBack={() => go('builds')} /> : <BuildList onOpen={(bid) => go('builds', { id: bid })} oppId={params.get('opportunity')} />)}
      {tab === 'rates' && <RatesAndLabor />}
    </>
  )
}

// ------------------------------------------------------------------ list
function BuildList({ onOpen, oppId }) {
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { api.get('/api/workbook/builds').then((d) => setRows(d.builds)).catch((e) => setErr(e.message)) }, [])
  const create = async () => {
    try { const b = await api.post('/api/workbook/builds', oppId ? { opportunity_id: Number(oppId) } : {}); onOpen(b.id) } catch (e) { setErr(e.message) }
  }
  const started = useRef(false)
  useEffect(() => { // coming from an opportunity: open its build, or start one
    if (!oppId || !rows || started.current) return
    started.current = true
    const existing = rows.find((r) => r.opportunity?.id === Number(oppId))
    if (existing) onOpen(existing.id); else create()
  }, [oppId, rows])
  if (!rows) return err ? <div className="err">{err}</div> : <p className="muted">Loading…</p>
  return (
    <div className="panel" style={{ overflowX: 'auto' }}>
      <div className="row spread"><h2 style={{ margin: 0 }}>Price builds</h2><button className="primary" onClick={create}>New price build</button></div>
      {err && <div className="err">{err}</div>}
      <table style={{ marginTop: 10 }}>
        <thead><tr><th>Build</th><th>Opportunity</th><th>CLINs</th><th>Total price</th><th>Profit</th><th>Status</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="click" onClick={() => onOpen(r.id)}>
              <td className="t">{r.name}{r.los_warnings?.length > 0 && <div className="small due-soon">Subcontracting limit exceeded</div>}</td>
              <td className="small">{r.opportunity ? `${r.opportunity.solicitation_number || ''} ${r.opportunity.title.slice(0, 60)}` : <span className="muted">none</span>}</td>
              <td className="mono">{r.clins}</td><td className="mono">{usd(r.total_price)}</td><td className="mono">{pct(r.profit_pct)}</td><td><span className="tag">{r.status}</span></td>
            </tr>
          ))}
          {!rows.length && <tr><td colSpan={6} className="muted" style={{ padding: 20 }}>No price builds yet. Set your indirect rates and labor categories first, then start one here or from an opportunity.</td></tr>}
        </tbody>
      </table>
    </div>
  )
}

// ------------------------------------------------------------------ editor
function BuildEditor({ id, onBack }) {
  const [b, setB] = useState(null)
  const [calc, setCalc] = useState(null)
  const [cats, setCats] = useState([])
  const [pqs, setPqs] = useState([])
  const [opps, setOpps] = useState([])
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [dirty, setDirty] = useState(false)
  const timer = useRef()

  useEffect(() => {
    api.get(`/api/workbook/builds/${id}`).then((d) => { setB(d); setCalc(d.computed) }).catch((e) => setErr(e.message))
    api.get('/api/workbook/labor').then((d) => setCats(d.categories)).catch(() => {})
    api.get('/api/workbook/part-quotes').then((d) => setPqs(d.quotes)).catch(() => {})
    api.get('/api/workbook/opportunities').then((d) => setOpps(d.opportunities)).catch(() => {})
  }, [id])

  // Live compute of the unsaved draft
  useEffect(() => {
    if (!b || !dirty) return
    clearTimeout(timer.current)
    timer.current = setTimeout(async () => {
      try { setCalc(await api.post('/api/workbook/compute', { rates: b.rates, set_aside: b.set_aside, clins: b.clins, competitors: b.competitors, target_price: b.target_price })); setErr('') } catch (e) { setErr(e.message) }
    }, 300)
    return () => clearTimeout(timer.current)
  }, [JSON.stringify(b)])

  if (!b) return err ? <div className="err">{err}</div> : <p className="muted">Loading…</p>
  const upd = (patch) => { setB((x) => ({ ...x, ...patch })); setDirty(true); setMsg('') }
  const updClin = (i, patch) => upd({ clins: b.clins.map((c, j) => (j === i ? { ...c, ...patch } : c)) })
  const updRow = (i, list, k, patch) => updClin(i, { [list]: b.clins[i][list].map((r, j) => (j === k ? { ...r, ...patch } : r)) })
  const addRow = (i, list, row) => updClin(i, { [list]: [...(b.clins[i][list] || []), row] })
  const delRow = (i, list, k) => updClin(i, { [list]: b.clins[i][list].filter((_, j) => j !== k) })

  const save = async () => {
    try {
      const d = await api.put(`/api/workbook/builds/${id}`, { name: b.name, opportunity_id: b.opportunity_id, set_aside: b.set_aside, clins: b.clins, competitors: b.competitors, target_price: b.target_price, status: b.status, notes: b.notes })
      setB(d); setCalc(d.computed); setDirty(false); setMsg('Saved.')
    } catch (e) { setErr(e.message) }
  }
  const action = async (fn, note) => {
    try { if (dirty) await save(); const d = await fn(); setB(d); setCalc(d.computed); setDirty(false); setMsg(note || 'Done.') } catch (e) { setErr(e.message) }
  }
  const remove = async () => { if (confirm('Delete this price build?')) { await api.del(`/api/workbook/builds/${id}`); onBack() } }

  const T = calc?.totals
  const ccalc = (i) => calc?.clins?.[i]
  return (
    <>
      <div className="row spread" style={{ marginBottom: 10 }}>
        <button className="link" onClick={onBack}>← All price builds</button>
        <div className="row">
          {msg && <span className="small okline">{msg}</span>}
          <button className="primary" onClick={save} disabled={!dirty}>Save</button>
          <a className="btn" href={`/api/workbook/builds/${id}/export.xlsx`}>Export Excel</a>
          <button className="link" onClick={remove}>Delete</button>
        </div>
      </div>
      {err && <div className="err">{err}</div>}
      <div className="builder iq">
        <div>
          <div className="panel">
            <div className="grid g2">
              <label className="f" style={{ gridColumn: 'span 2' }}>Name<input value={b.name} onChange={(e) => upd({ name: e.target.value })} /></label>
              <label className="f">Opportunity
                <select value={b.opportunity_id || ''} onChange={(e) => upd({ opportunity_id: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">None</option>
                  {[...(b.opportunity && !opps.some((o) => o.id === b.opportunity.id) ? [b.opportunity] : []), ...opps].map((o) => <option key={o.id} value={o.id}>{o.solicitation_number ? `${o.solicitation_number}: ` : ''}{o.title.slice(0, 60)}</option>)}
                </select>
              </label>
              <label className="f">Status<select value={b.status} onChange={(e) => upd({ status: e.target.value })}>{['draft', 'review', 'final', 'submitted'].map((s) => <option key={s}>{s}</option>)}</select></label>
            </div>
            <div className="row" style={{ marginTop: 8, gap: 16 }}>
              <label className="check"><input type="checkbox" checked={!!b.set_aside} onChange={(e) => upd({ set_aside: e.target.checked })} /> Set-aside (check limitations on subcontracting)</label>
              {b.opportunity_id && <Link className="small" to={`/opportunities/${b.opportunity_id}`}>Open opportunity</Link>}
            </div>
            <p className="small muted" style={{ marginBottom: 0 }}>
              Rates on this build: fringe {b.rates.fringe_pct}%, overhead {b.rates.overhead_pct}%, G&A {b.rates.ga_pct}%, profit {b.rates.profit_pct}%.{' '}
              <button className="link" onClick={() => action(() => api.post(`/api/workbook/builds/${id}/reload-rates`), 'Rates reloaded from your current indirect rates.')}>Reload current rates</button>
            </p>
          </div>

          {b.clins.map((c, i) => (
            <div key={i} className="panel">
              <div className="row spread">
                <div className="row">
                  <input className="mono" style={{ width: 70 }} value={c.clin} onChange={(e) => updClin(i, { clin: e.target.value })} />
                  <input style={{ minWidth: 220 }} value={c.description} placeholder="CLIN description" onChange={(e) => updClin(i, { description: e.target.value })} />
                </div>
                <button className="link" onClick={() => upd({ clins: b.clins.filter((_, j) => j !== i) })}>Remove CLIN</button>
              </div>
              <div className="grid g4" style={{ marginTop: 8 }}>
                <label className="f">Type<select value={c.kind} onChange={(e) => updClin(i, { kind: e.target.value })}><option value="services">Services</option><option value="supplies">Supplies</option></select></label>
                <label className="f">Quantity<input type="number" value={c.quantity} onChange={(e) => updClin(i, { quantity: num(e.target.value) })} /></label>
                <label className="f">Unit<input value={c.unit || ''} onChange={(e) => updClin(i, { unit: e.target.value })} /></label>
                <label className="f">NSN (optional)<input value={c.nsn || ''} onChange={(e) => updClin(i, { nsn: e.target.value })} /></label>
              </div>

              <h3>Labor</h3>
              <table className="small"><tbody>
                {(c.labor || []).map((l, k) => (
                  <tr key={k}>
                    <td><select value={l.category_id || ''} onChange={(e) => updRow(i, 'labor', k, { category_id: e.target.value ? Number(e.target.value) : null })}>
                      <option value="">Pick a labor category</option>{cats.map((ct) => <option key={ct.id} value={ct.id}>{ct.name} (${ct.hourly_rate}/h)</option>)}</select></td>
                    <td><input type="number" style={{ width: 90 }} value={l.hours} onChange={(e) => updRow(i, 'labor', k, { hours: num(e.target.value) })} /> h</td>
                    <td className="mono">{usd(ccalc(i)?.labor?.[k]?.cost)}</td>
                    <td><button className="link" onClick={() => delRow(i, 'labor', k)}>×</button></td>
                  </tr>
                ))}
              </tbody></table>
              <button className="link" onClick={() => addRow(i, 'labor', { category_id: cats[0]?.id || null, hours: 0 })}>+ Labor</button>
              {!cats.length && <span className="small muted"> Add labor categories on the rates tab first.</span>}

              <CostRows title="Materials" rows={c.materials} onAdd={() => addRow(i, 'materials', { description: '', cost: 0 })} onUpd={(k, p) => updRow(i, 'materials', k, p)} onDel={(k) => delRow(i, 'materials', k)} />
              <CostRows title="Subcontracts" rows={c.subcontracts} nameKey="name" extra={(r, k) => (
                <label className="check small" title="Another firm in the same program (e.g. another SDVOSB on an SDVOSB set-aside)"><input type="checkbox" checked={!!r.similarly_situated} onChange={(e) => updRow(i, 'subcontracts', k, { similarly_situated: e.target.checked })} /> similarly situated</label>
              )} onAdd={() => addRow(i, 'subcontracts', { name: '', cost: 0, similarly_situated: false })} onUpd={(k, p) => updRow(i, 'subcontracts', k, p)} onDel={(k) => delRow(i, 'subcontracts', k)} />
              <CostRows title="ODCs and travel" rows={c.odcs} extra={(r, k) => (
                <select value={r.kind || 'odc'} onChange={(e) => updRow(i, 'odcs', k, { kind: e.target.value })}><option value="odc">ODC</option><option value="travel">Travel</option></select>
              )} onAdd={() => addRow(i, 'odcs', { description: '', cost: 0, kind: 'odc' })} onUpd={(k, p) => updRow(i, 'odcs', k, p)} onDel={(k) => delRow(i, 'odcs', k)} />

              <h3>Fixed-price part lines</h3>
              <table className="small"><tbody>
                {(c.parts || []).map((p, k) => (
                  <tr key={k}>
                    <td><select value={p.part_quote_id || ''} onChange={(e) => {
                      const q = pqs.find((x) => x.id === Number(e.target.value))
                      updRow(i, 'parts', k, { part_quote_id: q?.id || null, description: q ? q.name : p.description, unit_price: q?.quoted_unit_price ?? p.unit_price, quantity: q?.quoted_quantity ?? p.quantity })
                    }}><option value="">Manual</option>{pqs.map((q) => <option key={q.id} value={q.id}>#{q.id} {q.name}{q.quoted_unit_price ? ` (${usd(q.quoted_unit_price)})` : ''}</option>)}</select></td>
                    <td><input value={p.description || ''} placeholder="Description" onChange={(e) => updRow(i, 'parts', k, { description: e.target.value })} /></td>
                    <td><input type="number" style={{ width: 70 }} value={p.quantity} onChange={(e) => updRow(i, 'parts', k, { quantity: num(e.target.value) })} /> ×</td>
                    <td><input type="number" style={{ width: 90 }} value={p.unit_price} onChange={(e) => updRow(i, 'parts', k, { unit_price: num(e.target.value) })} /></td>
                    <td><button className="link" onClick={() => delRow(i, 'parts', k)}>×</button></td>
                  </tr>
                ))}
              </tbody></table>
              <button className="link" onClick={() => addRow(i, 'parts', { part_quote_id: null, description: '', quantity: 1, unit_price: 0 })}>+ Part line</button>
              <span className="small muted"> Already priced in Part quotes, so no further burden is added.</span>
            </div>
          ))}
          <button onClick={() => upd({ clins: [...b.clins, blankClin(b.clins.length + 1)] })}>+ Add CLIN</button>

          <div className="panel" style={{ marginTop: 16 }}>
            <h2>Notes</h2>
            <textarea value={b.notes || ''} onChange={(e) => upd({ notes: e.target.value })} style={{ minHeight: 70 }} placeholder="Basis of estimate: where hours and material prices came from." />
          </div>
        </div>

        <div>
          <div className="panel price-panel">
            {!T ? <p className="muted">Add a CLIN to see the price.</p> : (
              <>
                <div className="small muted">Total price, {b.clins.length} CLIN{b.clins.length === 1 ? '' : 's'}</div>
                <div className="price-big">{usd(T.price)}</div>
                <div className="small">Cost {usd(T.total_cost)} · profit {usd(T.profit)} ({pct(calc.effective_profit_pct)}) · {T.hours} labor hours</div>
                <table className="small" style={{ marginTop: 10 }}>
                  <thead><tr><th>CLIN</th><th>Labor</th><th>Fringe + OH</th><th>Mat + sub + ODC</th><th>G&A</th><th>Profit</th><th>Price</th></tr></thead>
                  <tbody>{calc.clins.map((c) => (
                    <tr key={c.clin}><td className="mono">{c.clin}</td><td className="mono">{usd(c.direct_labor)}</td><td className="mono">{usd(c.fringe + c.overhead)}</td>
                      <td className="mono">{usd(c.materials + c.material_handling + c.subcontracts + c.odc)}</td><td className="mono">{usd(c.ga)}</td><td className="mono">{usd(c.profit)}</td><td className="mono"><b>{usd(c.price)}</b></td></tr>
                  ))}</tbody>
                </table>
                {calc.los?.applies && (
                  <>
                    <h3>Limitations on subcontracting</h3>
                    {calc.los.portions.map((p) => <div key={p.kind} className={`small ${p.over ? 'due-soon' : 'okline'}`}>{p.kind}: {pct(p.pct)} to subcontractors that are not similarly situated (limit {calc.los.limit_pct}%, FAR 52.219-14 {p.paragraph})</div>)}
                    {calc.los.warnings.map((w, i) => <div key={i} className="small due-soon">{w}</div>)}
                  </>
                )}
                {calc.burdened_rates?.length > 0 && (
                  <>
                    <h3>Fully burdened labor rates</h3>
                    <table className="small"><tbody>{calc.burdened_rates.map((r, i) => <tr key={i}><td>{r.category}</td><td className="mono">{usd(r.direct)} direct</td><td className="mono">{usd(r.billing_rate)}/h billed</td><td className="mono muted">wrap {r.wrap_rate}</td></tr>)}</tbody></table>
                  </>
                )}
              </>
            )}
          </div>

          <div className="panel">
            <div className="row spread">
              <h2 style={{ margin: 0 }}>Price to win</h2>
              <button className="link" onClick={() => action(() => api.post(`/api/workbook/builds/${id}/reference-prices`), 'Pulled last award prices for CLINs with an NSN.')}>Pull last award prices (NSN)</button>
            </div>
            <table className="small" style={{ marginTop: 8 }}><tbody>
              {(b.competitors || []).map((c, k) => {
                const g = calc?.competitors?.[k]?.total_gap
                return (
                  <tr key={k}>
                    <td><input value={c.name} placeholder="Competitor or past award" onChange={(e) => upd({ competitors: b.competitors.map((x, j) => (j === k ? { ...x, name: e.target.value } : x)) })} /></td>
                    <td><input type="number" style={{ width: 110 }} value={c.total ?? ''} placeholder="total $" onChange={(e) => upd({ competitors: b.competitors.map((x, j) => (j === k ? { ...x, total: num(e.target.value) || null } : x)) })} /></td>
                    <td className={`mono ${g && g.gap > 0 ? 'due-soon' : ''}`}>{g ? `${g.gap > 0 ? '+' : ''}${usd(g.gap)} (${g.gap_pct}%)` : ''}</td>
                    <td><button className="link" onClick={() => upd({ competitors: b.competitors.filter((_, j) => j !== k) })}>×</button></td>
                  </tr>
                )
              })}
            </tbody></table>
            <button className="link" onClick={() => upd({ competitors: [...(b.competitors || []), { name: '', source: 'manual', prices: {}, total: null }] })}>+ Comparison price</button>
            <p className="small muted">Use past award amounts from Competitor intel or USAspending. A positive gap means you are higher.</p>
            <label className="f" style={{ marginTop: 8 }}>Target price $
              <input type="number" value={b.target_price ?? ''} onChange={(e) => upd({ target_price: num(e.target.value) || null })} />
            </label>
            {T && b.target_price && (
              <input type="range" min={Math.round(T.total_cost * 0.9)} max={Math.round(T.total_cost * 1.4)} step="1" value={b.target_price} onChange={(e) => upd({ target_price: Number(e.target.value) })} style={{ width: '100%' }} />
            )}
            {calc?.backsolve && (
              <p className={`small ${calc.backsolve.negative ? 'due-soon' : ''}`}>At {usd(calc.backsolve.target_price)} your profit is {usd(calc.backsolve.profit)} ({pct(calc.backsolve.profit_pct)}).{calc.backsolve.warning ? ` ${calc.backsolve.warning}` : ''}</p>
            )}
          </div>
        </div>
      </div>
    </>
  )
}

function CostRows({ title, rows = [], nameKey = 'description', extra, onAdd, onUpd, onDel }) {
  return (
    <>
      <h3>{title}</h3>
      <table className="small"><tbody>
        {rows.map((r, k) => (
          <tr key={k}>
            <td><input value={r[nameKey] || ''} placeholder={nameKey === 'name' ? 'Subcontractor' : 'Description'} onChange={(e) => onUpd(k, { [nameKey]: e.target.value })} /></td>
            <td>$<input type="number" style={{ width: 100 }} value={r.cost} onChange={(e) => onUpd(k, { cost: num(e.target.value) })} /></td>
            <td>{extra?.(r, k)}</td>
            <td><button className="link" onClick={() => onDel(k)}>×</button></td>
          </tr>
        ))}
      </tbody></table>
      <button className="link" onClick={onAdd}>+ {title.split(' ')[0].replace(/s$/, '')}</button>
    </>
  )
}

// ------------------------------------------------------------------ rates and labor
function RatesAndLabor() {
  const [meta, setMeta] = useState(null)
  const [r, setR] = useState(null)
  const [labor, setLabor] = useState([])
  const [calcIn, setCalcIn] = useState({ direct_labor: '', fringe_costs: '', overhead_costs: '', ga_costs: '', materials: '', subcontracts: '', other_direct: '' })
  const [calcOut, setCalcOut] = useState(null)
  const [cat, setCat] = useState({ name: '', description: '', hourly_rate: '', annual_salary: '', calc_category: '' })
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const loadLabor = () => api.get('/api/workbook/labor').then((d) => setLabor(d.categories))
  useEffect(() => {
    api.get('/api/workbook/meta').then(setMeta)
    api.get('/api/workbook/rates').then((d) => { setR(d); if (d.calc_inputs && Object.keys(d.calc_inputs).length) setCalcIn((c) => ({ ...c, ...d.calc_inputs })) })
    loadLabor()
  }, [])
  if (!r || !meta) return <p className="muted">Loading…</p>

  const saveRates = async (extra = {}) => {
    setErr(''); setMsg('')
    try {
      const body = { fringe_pct: Number(r.fringe_pct), overhead_pct: Number(r.overhead_pct), ga_pct: Number(r.ga_pct), profit_pct: Number(r.profit_pct),
        material_handling_pct: Number(r.material_handling_pct), overhead_base: r.overhead_base, ga_base: r.ga_base, fee_base: r.fee_base, ...extra }
      setR(await api.put('/api/workbook/rates', body)); setMsg('Rates saved. New price builds use them; existing builds keep theirs until you reload.')
      loadLabor()
    } catch (e) { setErr(e.message) }
  }
  const runCalc = async () => {
    const body = Object.fromEntries(Object.entries(calcIn).map(([k, v]) => [k, Number(v) || 0]))
    try { setCalcOut(await api.post('/api/workbook/rates/calculate', { ...body, overhead_base: r.overhead_base, ga_base: r.ga_base })) } catch (e) { setErr(e.message) }
  }
  const useCalc = () => {
    const next = { ...r, fringe_pct: calcOut.fringe_pct, overhead_pct: calcOut.overhead_pct, ga_pct: calcOut.ga_pct }
    setR(next)
    saveRates({ fringe_pct: calcOut.fringe_pct, overhead_pct: calcOut.overhead_pct, ga_pct: calcOut.ga_pct, calc_inputs: Object.fromEntries(Object.entries(calcIn).map(([k, v]) => [k, Number(v) || 0])) })
  }
  const addCat = async () => {
    if (!cat.name.trim()) return
    try {
      await api.post('/api/workbook/labor', { ...cat, hourly_rate: Number(cat.hourly_rate) || 0, annual_salary: cat.annual_salary ? Number(cat.annual_salary) : null })
      setCat({ name: '', description: '', hourly_rate: '', annual_salary: '', calc_category: '' }); loadLabor()
    } catch (e) { setErr(e.message) }
  }
  const rateIn = (k, label) => (
    <label className="f">{label}<input type="number" step="0.1" value={r[k]} onChange={(e) => setR({ ...r, [k]: e.target.value })} />
      {meta.explanations[k] && <span className="small muted" style={{ fontWeight: 400 }}>{meta.explanations[k]}</span>}</label>
  )

  return (
    <>
      {err && <div className="err">{err}</div>}
      {msg && <div className="okmsg">{msg}</div>}
      <div className="grid g2">
        <div className="panel">
          <h2>Indirect rates</h2>
          <div className="grid g2">
            {rateIn('fringe_pct', 'Fringe %')}
            {rateIn('overhead_pct', 'Overhead %')}
            {rateIn('ga_pct', 'G&A %')}
            {rateIn('profit_pct', 'Profit %')}
            {rateIn('material_handling_pct', 'Material handling %')}
          </div>
          <h3>How each rate is applied</h3>
          {Object.entries(meta.bases).map(([k, opts]) => (
            <label key={k} className="f">{k === 'overhead_base' ? 'Overhead applies to' : k === 'ga_base' ? 'G&A applies to' : 'Profit applies to'}
              <select value={r[k]} onChange={(e) => setR({ ...r, [k]: e.target.value })}>{Object.entries(opts).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
            </label>
          ))}
          <button className="primary" style={{ marginTop: 10 }} onClick={() => saveRates()}>Save rates</button>
          {meta.explanations.fully_burdened && <p className="small muted">{meta.explanations.fully_burdened}</p>}
        </div>
        <div className="panel">
          <h2>Rate calculator</h2>
          <p className="small muted">{meta.explanations.calculator || 'Enter what you expect to spend in a year and get starting rates.'}</p>
          <div className="grid g2">
            {[['direct_labor', 'Direct labor $ (billable hours x pay)'], ['fringe_costs', 'Fringe $ (payroll taxes, health, retirement, leave)'], ['overhead_costs', 'Overhead $ (shop rent, tools, software, insurance)'], ['ga_costs', 'G&A $ (accounting, legal, BD, office)'], ['materials', 'Materials $'], ['subcontracts', 'Subcontracts $'], ['other_direct', 'Other direct $']].map(([k, l]) => (
              <label key={k} className="f">{l}<input type="number" value={calcIn[k]} onChange={(e) => setCalcIn({ ...calcIn, [k]: e.target.value })} /></label>
            ))}
          </div>
          <div className="row" style={{ marginTop: 8 }}><button onClick={runCalc}>Calculate</button>
            {calcOut && <button className="primary" onClick={useCalc}>Use these rates</button>}</div>
          {calcOut && <ul className="clean small" style={{ marginTop: 8 }}>{calcOut.steps.map((x, i) => <li key={i}>{x}</li>)}</ul>}
        </div>
      </div>

      <div className="panel" style={{ overflowX: 'auto' }}>
        <h2>Labor categories</h2>
        <p className="small muted">Direct (unburdened) hourly pay for each role. Compare your fully burdened rates against awarded rates on <a href={meta.calc_url} target="_blank" rel="noreferrer">GSA CALC+</a>.</p>
        <table>
          <thead><tr><th>Category</th><th>Direct $/h</th><th>Billed $/h</th><th>CALC+ category</th><th></th></tr></thead>
          <tbody>
            {labor.map((c) => (
              <tr key={c.id}>
                <td><div className="t">{c.name}</div><div className="small muted">{c.description}</div></td>
                <td className="mono">{usd(c.hourly_rate)}</td>
                <td className="mono">{usd(c.burdened?.billing_rate)}</td>
                <td className="small">{c.calc_category}</td>
                <td><button className="link" onClick={async () => { if (confirm(`Delete ${c.name}?`)) { await api.del(`/api/workbook/labor/${c.id}`); loadLabor() } }}>Delete</button></td>
              </tr>
            ))}
            <tr>
              <td><input value={cat.name} placeholder="Electrical engineer" onChange={(e) => setCat({ ...cat, name: e.target.value })} /></td>
              <td><input type="number" style={{ width: 90 }} value={cat.hourly_rate} placeholder="$/h" onChange={(e) => setCat({ ...cat, hourly_rate: e.target.value })} /> or <input type="number" style={{ width: 110 }} value={cat.annual_salary} placeholder="salary/yr" onChange={(e) => setCat({ ...cat, annual_salary: e.target.value })} /></td>
              <td></td>
              <td><input value={cat.calc_category} placeholder="Engineer III" onChange={(e) => setCat({ ...cat, calc_category: e.target.value })} /></td>
              <td><button className="primary small-btn" onClick={addCat}>Add</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </>
  )
}
