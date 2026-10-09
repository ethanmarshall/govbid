import { Suspense, lazy, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import MakeOrBuy from '../MakeOrBuy'
const InstantQuote = lazy(() => import('./InstantQuote')) // three.js loads only on this tab

const usd = (n) => (n == null ? '' : `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`)

const DIM_FIELDS = {
  plate: ['length', 'width', 'thickness'],
  sheet: ['length', 'width', 'thickness'],
  bar_round: ['diameter', 'length'],
  bar_rect: ['width', 'thickness', 'length'],
  tube_round: ['od', 'wall', 'length'],
  tube_rect: ['width', 'height', 'wall', 'length'],
}

// Fields shown for each operation type: [key, label, kind]
const OP_FIELDS = {
  cnc_mill: [['setups', 'Setups', 'n'], ['cycle_minutes', 'Cycle min (blank = estimate)', 'n'], ['features.holes', 'Holes', 'n'], ['features.tapped_holes', 'Tapped holes', 'n'], ['features.pockets', 'Pockets', 'n'], ['features.profile_in', 'Profile in', 'n'], ['features.volume_removed_in3', 'Removed in³', 'n']],
  cnc_lathe: [['setups', 'Setups', 'n'], ['cycle_minutes', 'Cycle min (blank = estimate)', 'n'], ['features.diameters', 'Diameters', 'n'], ['features.threads', 'Threads', 'n'], ['features.grooves', 'Grooves', 'n'], ['features.cross_holes', 'Cross holes', 'n']],
  manual_machining: [['setups', 'Setups', 'n'], ['minutes_per_part', 'Min/part', 'n']],
  laser_cut: [['cut_length_in', 'Cut length in', 'n'], ['pierces', 'Pierces', 'n']],
  waterjet: [['cut_length_in', 'Cut length in', 'n'], ['pierces', 'Pierces', 'n']],
  press_brake: [['bends', 'Bends', 'n']],
  weld: [['process', 'Process', ['mig', 'tig']], ['weld_length_in', 'Weld in', 'n'], ['joints', 'Joints', 'n'], ['fixture', 'Fixture', 'b'], ['certified_welder', 'Certified weld', 'b']],
  hardware_insert: [['count', 'Count', 'n'], ['unit_cost', 'Unit cost $', 'n'], ['minutes_each', 'Min each', 'n']],
  assembly: [['minutes_per_part', 'Min/part', 'n']],
  deburr: [['minutes_per_part', 'Min/part', 'n']],
  fabrication: [['minutes_per_part', 'Min/part', 'n']],
}

const getPath = (o, p) => p.split('.').reduce((a, k) => (a == null ? undefined : a[k]), o)
const setPath = (o, p, v) => {
  const keys = p.split('.')
  const out = { ...o }
  let cur = out
  keys.slice(0, -1).forEach((k) => { cur[k] = { ...(cur[k] || {}) }; cur = cur[k] })
  const last = keys.at(-1)
  if (v === '' || v == null) delete cur[last]
  else cur[last] = v
  return out
}

const blankSpec = () => ({
  name: '', part_number: '', nsn: '', quantities: [10, 50, 100], material: '6061-T6 aluminum',
  stock: { shape: 'plate', dims: {} }, tolerance: 'standard', operations: [], finishes: [],
  inspection: { first_article: false }, packaging: { level: 'commercial' }, approved_source_required: true,
})

export default function PartQuotes() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || 'instant'
  const [meta, setMeta] = useState(null)
  useEffect(() => { api.get('/api/pricing/meta').then(setMeta) }, [])
  if (!meta) return <p className="muted">Loading…</p>
  const go = (t, extra = {}) => setParams({ ...(t === 'instant' ? {} : { tab: t }), ...extra })
  return (
    <>
      <h1>Part quotes</h1>
      <p className="sub">Drop in a STEP file for an instant price, or build an estimate by hand. The same engine is available to AI agents through the GovBid Pro MCP server.</p>
      <div className="tabs">
        <button className={tab === 'instant' ? 'on' : ''} onClick={() => go('instant')}>Instant quote</button>
        <button className={tab === 'quote' ? 'on' : ''} onClick={() => go('quote')}>Manual estimate</button>
        <button className={tab === 'saved' ? 'on' : ''} onClick={() => go('saved')}>Saved quotes</button>
        <button className={tab === 'rates' ? 'on' : ''} onClick={() => go('rates')}>Shop rates</button>
      </div>
      {tab === 'quote' && <QuoteBuilder meta={meta} quoteId={params.get('id')} oppId={params.get('opportunity')} onSaved={(id) => go('quote', { id })} />}
      {tab === 'instant' && <Suspense fallback={<p className="muted">Loading…</p>}><InstantQuote key={params.get('id') || 'new'} meta={meta} quoteId={params.get('id')} oppId={params.get('opportunity')} onSaved={(id) => go('instant', { id })} onOpenManual={(id) => go('quote', id ? { id } : {})} /></Suspense>}
      {tab === 'saved' && <SavedQuotes onOpen={(r) => go(r.cad_file ? 'instant' : 'quote', { id: r.id })} />}
      {tab === 'rates' && <ShopRates onChanged={() => api.get('/api/pricing/meta').then(setMeta)} />}
    </>
  )
}

// ------------------------------------------------------------------ builder
function QuoteBuilder({ meta, quoteId, oppId, onSaved }) {
  const [spec, setSpec] = useState(blankSpec)
  const [qtyText, setQtyText] = useState('10, 50, 100')
  const [result, setResult] = useState(null)
  const [err, setErr] = useState('')
  const [quote, setQuote] = useState({ opportunity_id: oppId ? Number(oppId) : null, status: 'draft', quoted_quantity: '', quoted_unit_price: '', notes: '' })
  const [opps, setOpps] = useState([])
  const [msg, setMsg] = useState('')
  const timer = useRef()

  useEffect(() => {
    api.get('/api/opportunities?' + new URLSearchParams({ my_naics_only: 'false', limit: 200 })).then((r) => setOpps(r.results)).catch(() => {})
  }, [])
  useEffect(() => {
    if (!quoteId) return
    api.get(`/api/pricing/quotes/${quoteId}`).then((q) => {
      setSpec(q.spec); setQtyText((q.spec.quantities || []).join(', ')); setResult(q.result)
      setQuote({ opportunity_id: q.opportunity_id, status: q.status, quoted_quantity: q.quoted_quantity ?? '', quoted_unit_price: q.quoted_unit_price ?? '', notes: q.notes || '' })
    })
  }, [quoteId])
  useEffect(() => {
    if (!oppId || quoteId) return
    api.get(`/api/opportunities/${oppId}`).then((o) => setSpec((s) => ({ ...s, name: s.name || o.title, nsn: s.nsn || o.nsn || '', quantities: o.quantity && Number(o.quantity) ? [Number(o.quantity)] : s.quantities })))
      .then(() => {}).catch(() => {})
  }, [oppId, quoteId])

  // Live estimate, debounced
  useEffect(() => {
    clearTimeout(timer.current)
    timer.current = setTimeout(async () => {
      const d = spec.stock?.dims || {}
      if (!Object.values(d).some((v) => Number(v) > 0)) { setResult(null); return }
      try { setResult(await api.post('/api/pricing/estimate', spec)); setErr('') } catch (e) { setErr(e.message) }
    }, 400)
    return () => clearTimeout(timer.current)
  }, [JSON.stringify(spec)])

  const upd = (path, v) => setSpec((s) => setPath(s, path, v))
  const num = (v) => (v === '' ? '' : Number(v))
  const setQty = (t) => {
    setQtyText(t)
    const q = t.split(/[ ,]+/).map(Number).filter((n) => n > 0)
    if (q.length) upd('quantities', q)
  }
  const addOp = (type) => setSpec((s) => ({ ...s, operations: [...s.operations, { type, ...(type === 'cnc_mill' || type === 'cnc_lathe' ? { setups: 1 } : {}), ...(type === 'weld' ? { process: 'mig', fixture: true } : {}) }] }))
  const updOp = (i, path, v) => setSpec((s) => ({ ...s, operations: s.operations.map((o, j) => (j === i ? setPath(o, path, v) : o)) }))
  const delOp = (i) => setSpec((s) => ({ ...s, operations: s.operations.filter((_, j) => j !== i) }))
  const toggleFinish = (f) => setSpec((s) => ({ ...s, finishes: s.finishes.some((x) => x.type === f) ? s.finishes.filter((x) => x.type !== f) : [...s.finishes, { type: f }] }))

  const save = async () => {
    setErr(''); setMsg('')
    const body = { spec, opportunity_id: quote.opportunity_id || null, status: quote.status, notes: quote.notes,
      quoted_quantity: quote.quoted_quantity === '' ? null : Number(quote.quoted_quantity),
      quoted_unit_price: quote.quoted_unit_price === '' ? null : Number(quote.quoted_unit_price) }
    try {
      const q = quoteId ? await api.put(`/api/pricing/quotes/${quoteId}`, body) : await api.post('/api/pricing/quotes', body)
      setMsg(`Saved quote #${q.id}.`)
      if (!quoteId) onSaved(q.id)
      setQuote((x) => ({ ...x, quoted_unit_price: q.quoted_unit_price ?? '' }))
    } catch (e) { setErr(e.message) }
  }

  const shape = spec.stock?.shape || 'plate'
  return (
    <div className="builder" style={{ gridTemplateColumns: 'minmax(0, 1.05fr) minmax(0, 1fr)' }}>
      <div>
        <div className="panel">
          <div className="row spread"><h2 style={{ margin: 0 }}>Part</h2>
            <div className="row">
              <button className="link" onClick={() => { setSpec(meta.example_spec); setQtyText(meta.example_spec.quantities.join(', ')) }}>Load example</button>
              <button className="link" onClick={() => { setSpec(blankSpec()); setQtyText('10, 50, 100'); setResult(null) }}>Clear</button>
            </div>
          </div>
          <div className="grid g3" style={{ marginTop: 10 }}>
            <label className="f" style={{ gridColumn: 'span 3' }}>Name<input value={spec.name || ''} onChange={(e) => upd('name', e.target.value)} placeholder="Bracket, mounting" /></label>
            <label className="f">Part number<input value={spec.part_number || ''} onChange={(e) => upd('part_number', e.target.value)} /></label>
            <label className="f">NSN<input value={spec.nsn || ''} onChange={(e) => upd('nsn', e.target.value)} placeholder="5340-01-…" /></label>
            <label className="f">Quantities to price<input value={qtyText} onChange={(e) => setQty(e.target.value)} placeholder="10, 50, 100" /></label>
            <label className="f">Material
              <select value={spec.material} onChange={(e) => upd('material', e.target.value)}>{meta.materials.map((m) => <option key={m}>{m}</option>)}</select>
            </label>
            <label className="f">Tolerance
              <select value={spec.tolerance || 'standard'} onChange={(e) => upd('tolerance', e.target.value)}>{meta.tolerances.map((m) => <option key={m}>{m}</option>)}</select>
            </label>
            <label className="f">Reference unit price $<input type="number" value={spec.reference_unit_price ?? ''} onChange={(e) => upd('reference_unit_price', num(e.target.value))} placeholder="last award" /></label>
          </div>

          <h3>Raw stock per part (inches)</h3>
          <div className="row">
            <select value={shape} onChange={(e) => upd('stock', { shape: e.target.value, dims: {} })}>
              {Object.keys(meta.stock_shapes).map((s) => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
            </select>
            {DIM_FIELDS[shape].map((k) => (
              <label key={k} className="f" style={{ width: 90 }}>{k}<input type="number" step="0.001" value={spec.stock?.dims?.[k] ?? ''} onChange={(e) => upd(`stock.dims.${k}`, num(e.target.value))} /></label>
            ))}
          </div>

          <h3>Operations</h3>
          {spec.operations.map((op, i) => (
            <div key={i} className="opcard">
              <div className="row spread"><b>{op.type.replace('_', ' ')}</b><button className="link" onClick={() => delOp(i)}>Remove</button></div>
              <div className="row" style={{ gap: 8, marginTop: 6 }}>
                {(OP_FIELDS[op.type] || []).map(([key, label, kind]) => (
                  <label key={key} className="f" style={{ width: kind === 'b' ? 'auto' : 112 }}>{label}
                    {kind === 'n' && <input type="number" step="0.1" value={getPath(op, key) ?? ''} onChange={(e) => updOp(i, key, num(e.target.value))} />}
                    {kind === 'b' && <input type="checkbox" checked={!!getPath(op, key)} onChange={(e) => updOp(i, key, e.target.checked)} />}
                    {Array.isArray(kind) && <select value={getPath(op, key) || kind[0]} onChange={(e) => updOp(i, key, e.target.value)}>{kind.map((k) => <option key={k}>{k}</option>)}</select>}
                  </label>
                ))}
              </div>
            </div>
          ))}
          <select value="" onChange={(e) => e.target.value && addOp(e.target.value)} style={{ marginTop: 6 }}>
            <option value="">+ Add operation…</option>
            {Object.entries(meta.operation_types).map(([k, d]) => <option key={k} value={k} title={d}>{k.replace('_', ' ')}</option>)}
          </select>

          <h3>Finishing, inspection, packaging</h3>
          <div className="row" style={{ gap: 6 }}>
            {meta.finishes.map((f) => (
              <button key={f} className={`chip ${spec.finishes.some((x) => x.type === f) ? 'on' : ''}`} onClick={() => toggleFinish(f)}>{f}</button>
            ))}
          </div>
          <div className="row" style={{ marginTop: 10, gap: 16 }}>
            <label className="check"><input type="checkbox" checked={!!spec.inspection?.first_article} onChange={(e) => upd('inspection.first_article', e.target.checked)} /> First article</label>
            <label className="check"><input type="checkbox" checked={!!spec.material_certs_required} onChange={(e) => upd('material_certs_required', e.target.checked)} /> Material certs</label>
            <label className="check"><input type="checkbox" checked={spec.approved_source_required !== false} onChange={(e) => upd('approved_source_required', e.target.checked)} /> Approved source restricted</label>
            <label className="f" style={{ width: 160 }}>Packaging
              <select value={spec.packaging?.level || 'commercial'} onChange={(e) => upd('packaging.level', e.target.value)}>{meta.packaging_levels.map((p) => <option key={p}>{p}</option>)}</select>
            </label>
            <label className="f" style={{ width: 110 }}>Freight $/lot<input type="number" value={spec.freight_per_lot ?? ''} onChange={(e) => upd('freight_per_lot', num(e.target.value))} placeholder="default" /></label>
          </div>
        </div>
      </div>

      <div>
        <div className="panel">
          <h2>Estimate</h2>
          {err && <div className="err">{err}</div>}
          {!result ? <p className="muted">Enter stock dimensions to see an estimate.</p> : <Result r={result} />}
        </div>
        {result && (
          <div className="panel">
            <h2>Save quote</h2>
            <div className="grid g2">
              <label className="f" style={{ gridColumn: 'span 2' }}>Opportunity
                <select value={quote.opportunity_id || ''} onChange={(e) => setQuote({ ...quote, opportunity_id: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">Not linked</option>
                  {opps.map((o) => <option key={o.id} value={o.id}>{o.solicitation_number ? `${o.solicitation_number}: ` : ''}{o.title.slice(0, 80)}</option>)}
                </select>
              </label>
              <label className="f">Status<select value={quote.status} onChange={(e) => setQuote({ ...quote, status: e.target.value })}>{meta.statuses.map((s) => <option key={s}>{s}</option>)}</select></label>
              <label className="f">Quoted quantity<input type="number" value={quote.quoted_quantity} onChange={(e) => setQuote({ ...quote, quoted_quantity: e.target.value })} /></label>
              <label className="f">Quoted unit price $ (blank = from break)<input type="number" step="0.01" value={quote.quoted_unit_price} onChange={(e) => setQuote({ ...quote, quoted_unit_price: e.target.value })} /></label>
              <label className="f" style={{ gridColumn: 'span 2' }}>Notes<textarea value={quote.notes} onChange={(e) => setQuote({ ...quote, notes: e.target.value })} style={{ minHeight: 60 }} placeholder="Assumptions, missing drawing details, supplier quotes" /></label>
            </div>
            <div className="row" style={{ marginTop: 10 }}>
              <button className="primary" onClick={save}>{quoteId ? 'Update quote' : 'Save quote'}</button>
              {msg && <span className="small">{msg}</span>}
              {quote.opportunity_id && <Link className="small" to={`/opportunities/${quote.opportunity_id}`}>Open opportunity</Link>}
            </div>
          </div>
        )}
        {quoteId && <MakeOrBuy quoteId={quoteId} refreshKey={msg} />}
      </div>
    </div>
  )
}

function Result({ r }) {
  return (
    <>
      <table>
        <thead><tr><th>Qty</th><th>Unit cost</th><th>Unit price</th><th>Total</th><th>Margin</th><th>Lead</th>{r.price_breaks[0]?.vs_reference_pct !== undefined && <th>vs ref.</th>}</tr></thead>
        <tbody>
          {r.price_breaks.map((b) => (
            <tr key={b.quantity}>
              <td className="mono">{b.quantity}</td><td className="mono">{usd(b.unit_cost)}</td><td className="mono"><b>{usd(b.unit_price)}</b></td>
              <td className="mono">{usd(b.total_price)}</td><td className="mono">{b.margin_pct}%</td><td className="mono">{b.lead_time_days}d</td>
              {b.vs_reference_pct !== undefined && <td className={`mono ${(b.reference_note || '').includes('cannot') ? 'due-soon' : ''}`} title={b.reference_note}>{b.vs_reference_pct > 0 ? '+' : ''}{b.vs_reference_pct}%</td>}
            </tr>
          ))}
        </tbody>
      </table>
      {r.price_breaks.some((b) => b.reference_note) && <p className="small muted">{r.price_breaks.map((b) => `Qty ${b.quantity}: ${b.reference_note}`).join(' ')}</p>}
      {r.warnings.length > 0 && <><h3>Warnings</h3><ul className="clean small">{r.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></>}
      <h3>Per part ({usd(r.per_part_cost)})</h3>
      <Lines lines={r.per_part_lines} />
      <h3>Per lot ({usd(r.per_lot_cost)} + finishing)</h3>
      <Lines lines={r.per_lot_lines} />
      {r.assumptions.length > 0 && <><h3>Assumptions</h3><ul className="clean small">{r.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul></>}
      <p className="small muted">Weight {r.part_weight_lb} lb · stock {r.stock_volume_in3} in³ · G&A {Math.round(r.ga_rate * 100)}% · profit {Math.round(r.profit_rate * 100)}%. {r.config_note}</p>
    </>
  )
}

function Lines({ lines }) {
  return (
    <table className="small">
      <tbody>
        {lines.map((l, i) => (
          <tr key={i}>
            <td style={{ width: 90 }} className="muted">{l.category}</td>
            <td>{l.item}{l.note && <div className="muted">{l.note}</div>}</td>
            <td className="mono" style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>{l.hours != null ? `${l.hours} h × $${l.rate}` : ''}</td>
            <td className="mono" style={{ textAlign: 'right' }}>{usd(l.cost)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// ------------------------------------------------------------------ saved list
function SavedQuotes({ onOpen }) {
  const [rows, setRows] = useState(null)
  const [q, setQ] = useState('')
  useEffect(() => { api.get('/api/pricing/quotes?' + new URLSearchParams({ q })).then(setRows) }, [q])
  if (!rows) return <p className="muted">Loading…</p>
  return (
    <div className="panel" style={{ overflowX: 'auto' }}>
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, NSN, part number" style={{ marginBottom: 10, minWidth: 280 }} />
      <table>
        <thead><tr><th>Part</th><th>Opportunity</th><th>Status</th><th>Quoted</th><th>Breaks</th><th>By</th><th></th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="click" onClick={() => onOpen(r)}>
              <td><div className="t">{r.name}</div><div className="small mono muted">{[r.part_number, r.nsn, r.cad_file && `STEP: ${r.cad_file}`].filter(Boolean).join(' · ')}</div></td>
              <td className="small">{r.solicitation_number || r.opportunity_title || <span className="muted">none</span>}</td>
              <td><span className="tag">{r.status}</span></td>
              <td className="mono">{r.quoted_quantity ? `${r.quoted_quantity} @ ${usd(r.quoted_unit_price)}` : ''}</td>
              <td className="small mono">{r.price_breaks.map((b) => `${b.quantity}: ${usd(b.unit_price)}`).join('  ')}</td>
              <td className="small">{r.created_by}</td>
              <td><button className="link" onClick={async (e) => { e.stopPropagation(); if (confirm('Delete this quote?')) { await api.del(`/api/pricing/quotes/${r.id}`); setRows(rows.filter((x) => x.id !== r.id)) } }}>Delete</button></td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan={7} className="muted" style={{ padding: 20 }}>No saved quotes yet.</td></tr>}
        </tbody>
      </table>
    </div>
  )
}

// ------------------------------------------------------------------ shop rates
function ShopRates({ onChanged }) {
  const [data, setData] = useState(null)
  const [draft, setDraft] = useState(null)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const load = () => api.get('/api/pricing/config').then((d) => { setData(d); setDraft(structuredClone(d.config)) })
  useEffect(() => { load() }, [])
  const changed = useMemo(() => data && draft && JSON.stringify(data.config) !== JSON.stringify(draft), [data, draft])
  if (!draft) return <p className="muted">Loading…</p>

  // Keep an emptied field in place (as '') so its row never disappears while typing
  const setV = (path, v) => setDraft((d) => {
    const keys = path.split('.')
    const out = structuredClone(d)
    let cur = out
    keys.slice(0, -1).forEach((k) => { cur = cur[k] })
    cur[keys.at(-1)] = v === '' ? '' : Number(v)
    return out
  })
  const blanks = (o, pre = '') => Object.entries(o).flatMap(([k, v]) => (v && typeof v === 'object' ? blanks(v, `${pre}${k}.`) : v === '' ? [`${pre}${k}`] : []))
  const save = async () => {
    setErr(''); setMsg('')
    const empty = blanks(draft)
    if (empty.length) { setErr(`Fill in every field before saving: ${empty.join(', ')}`); return }
    try { await api.put('/api/pricing/config', { changes: draft }); await load(); onChanged(); setMsg('Saved. New estimates use these rates.') } catch (e) { setErr(e.message) }
  }
  const addMaterial = () => {
    const raw = prompt('Material name (for example "6063-T5 aluminum")')
    const name = (raw || '').replace(/\./g, ' ').trim()
    if (!name) return
    setDraft((d) => ({ ...d, materials: { ...d.materials, [name]: { density: 0.1, price_per_lb: 5, machinability: 1, cut_factor: 1 } } }))
  }
  // A plain function (not a component) so inputs keep focus while typing
  const numIn = (path, step = '0.01') => <input type="number" step={step} value={getPath(draft, path) ?? ''} onChange={(e) => setV(path, e.target.value)} style={{ width: 90 }} />

  return (
    <>
      <div className="notice">{draft.note} Agents read the same rates through the MCP server, so set them here once.</div>
      {err && <div className="err">{err}</div>}
      {msg && <div className="okmsg">{msg}</div>}
      <div className="grid g2">
        <div className="panel">
          <h2>Burdened hourly rates ($/h)</h2>
          <table><tbody>{Object.keys(draft.rates).map((k) => <tr key={k}><td>{k.replace('_', ' ')}</td><td>{numIn(`rates.${k}`)}</td></tr>)}</tbody></table>
          <h3>Setup hours</h3>
          <table><tbody>{Object.keys(draft.setup_hours).map((k) => <tr key={k}><td>{k.replace('_', ' ')}</td><td>{numIn(`setup_hours.${k}`)}</td></tr>)}</tbody></table>
          <h3>Markups and minimums</h3>
          <table><tbody>
            <tr><td>G&A rate (0.10 = 10%)</td><td>{numIn('ga_rate')}</td></tr>
            <tr><td>Profit rate</td><td>{numIn('profit_rate')}</td></tr>
            <tr><td>Minimum lot charge $</td><td>{numIn('min_lot_charge')}</td></tr>
            <tr><td>Scrap factor</td><td>{numIn('scrap_factor')}</td></tr>
            <tr><td>Default freight $/lot</td><td>{numIn('default_freight_per_lot')}</td></tr>
            {draft.outsourcing && <>
              <tr><td>Markup on bought parts (0.15 = 15%)</td><td>{numIn('outsourcing.markup')}</td></tr>
              <tr><td>Receiving inspection $/lot (bought parts)</td><td>{numIn('outsourcing.receiving_inspection_per_lot')}</td></tr>
              <tr><td>Handling $/part (bought parts)</td><td>{numIn('outsourcing.handling_per_part')}</td></tr>
            </>}
          </tbody></table>
        </div>
        <div className="panel">
          <div className="row spread"><h2 style={{ margin: 0 }}>Materials</h2><button className="link" onClick={addMaterial}>+ Add material</button></div>
          <table>
            <thead><tr><th>Material</th><th>$/lb</th><th>lb/in³</th><th>Machin.</th><th>Cut</th></tr></thead>
            <tbody>{Object.keys(draft.materials).map((m) => (
              <tr key={m}><td className="small">{m}</td>
                <td>{numIn(`materials.${m}.price_per_lb`)}</td><td>{numIn(`materials.${m}.density`, '0.0001')}</td>
                <td>{numIn(`materials.${m}.machinability`)}</td><td>{numIn(`materials.${m}.cut_factor`)}</td></tr>
            ))}</tbody>
          </table>
          <h3>Outside finishing</h3>
          <table>
            <thead><tr><th>Finish</th><th>$/part</th><th>Lot min $</th><th>Days</th></tr></thead>
            <tbody>{Object.keys(draft.finishes).map((f) => (
              <tr key={f}><td className="small">{f}</td><td>{numIn(`finishes.${f}.per_part`)}</td><td>{numIn(`finishes.${f}.lot_min`)}</td><td>{numIn(`finishes.${f}.lead_days`, '1')}</td></tr>
            ))}</tbody>
          </table>
        </div>
      </div>
      {draft.additive && (
        <div className="grid g2">
          <div className="panel">
            <h2>3D printers</h2>
            <table>
              <thead><tr><th>Technology</th><th>Machine $/h</th><th>cm³/h</th><th>Min per in height</th><th>Post min</th><th>Support</th></tr></thead>
              <tbody>{Object.entries(draft.additive.technologies).map(([t, v]) => (
                <tr key={t}><td className="small">{v.label}</td>
                  <td>{numIn(`additive.technologies.${t}.machine_rate`)}</td><td>{numIn(`additive.technologies.${t}.cm3_per_hour`, '1')}</td>
                  <td>{numIn(`additive.technologies.${t}.minutes_per_inch_height`, '1')}</td><td>{numIn(`additive.technologies.${t}.post_minutes`, '1')}</td>
                  <td>{numIn(`additive.technologies.${t}.support_factor`)}</td></tr>
              ))}</tbody>
            </table>
            <table style={{ marginTop: 10 }}><tbody>
              <tr><td>Minimum lot charge for printed parts $</td><td>{numIn('additive.min_lot_charge')}</td></tr>
              <tr><td>Minimum charge per printed part $</td><td>{numIn('additive.min_part_charge')}</td></tr>
            </tbody></table>
            <p className="small muted">Print labor rate is under hourly rates. Support is extra material as a fraction (0.20 = 20%).</p>
          </div>
          <div className="panel">
            <h2>3D print materials and post-processing</h2>
            <table>
              <thead><tr><th>Material</th><th>Tech</th><th>$/cm³</th><th>g/cm³</th></tr></thead>
              <tbody>{Object.entries(draft.additive.materials).map(([m, v]) => (
                <tr key={m}><td className="small">{m}</td><td className="small">{v.tech.toUpperCase()}</td>
                  <td>{numIn(`additive.materials.${m}.price_per_cm3`, '0.001')}</td><td>{numIn(`additive.materials.${m}.density`)}</td></tr>
              ))}</tbody>
            </table>
            <h3>Post-processing</h3>
            <table>
              <thead><tr><th>Finish</th><th>Minutes</th><th>Consumables $</th></tr></thead>
              <tbody>{Object.keys(draft.additive.finishes).map((f) => (
                <tr key={f}><td className="small">{f}</td><td>{numIn(`additive.finishes.${f}.minutes`, '1')}</td><td>{numIn(`additive.finishes.${f}.per_part`)}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </div>
      )}
      <div className="row">
        <button className="primary" onClick={save} disabled={!changed}>Save rates</button>
        <button onClick={async () => { if (confirm('Reset every rate to the defaults?')) { await api.post('/api/pricing/config/reset'); await load(); onChanged() } }}>Reset to defaults</button>
      </div>
    </>
  )
}
