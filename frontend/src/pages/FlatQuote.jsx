import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import QuoteActions from '../QuoteActions'

const usd = (n) => (n == null ? '' : `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`)
const fmt = (n, d = 3) => (n == null ? '' : Number(n).toFixed(d).replace(/\.?0+$/, ''))
const PROC_LABEL = { laser_cut: 'Laser', waterjet: 'Waterjet', plasma: 'Plasma', router: 'CNC router' }
// which material classes each process can cut (the backend enforces the hard limits)
const PROC_OK = {
  laser_cut: ['ferrous', 'nonferrous', 'plastic'],
  waterjet: ['ferrous', 'nonferrous', 'plastic', 'wood', 'composite'],
  plasma: ['ferrous', 'nonferrous'],
  router: ['nonferrous', 'plastic', 'wood', 'composite'],
}
const defaultOpts = () => ({
  process: 'laser_cut', material: 'A36 / 1018 steel', thickness: 0.125, sheet: '48 x 96', sheet_width: '', sheet_length: '',
  spacing_in: '', edge_margin_in: '', full_sheets: false, deburr: 'hand', finishes: [], pem_unit_cost: '',
  first_article: false, material_certs: false, packaging: 'commercial', freight_per_lot: '', tolerance: 'standard',
})

export default function FlatQuote({ meta, quoteId, oppId, onSaved }) {
  const [o, setO] = useState(null) // /api/flat/options
  const [files, setFiles] = useState([]) // parsed file results (svg, warnings, units)
  const [parts, setParts] = useState([])
  const [opts, setOpts] = useState(defaultOpts)
  const [read, setRead] = useState({ units: 'auto', ignore_layers: '', tolerance_in: '' })
  const [qtyText, setQtyText] = useState('1, 10, 50')
  const [head, setHead] = useState({ name: '', part_number: '', nsn: '' })
  const [est, setEst] = useState(null)
  const [pick, setPick] = useState(null)
  const [save, setSave] = useState({ opportunity_id: oppId ? Number(oppId) : null, status: 'draft', notes: '' })
  const [opps, setOpps] = useState([])
  const [busy, setBusy] = useState(false)
  const [drag, setDrag] = useState(false)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [showDetail, setShowDetail] = useState(false)
  const [showRead, setShowRead] = useState(false)
  const lastFiles = useRef([])
  const input = useRef()
  const timer = useRef()

  useEffect(() => { api.get('/api/flat/options').then((r) => { setO(r); setRead((x) => ({ ...x, ignore_layers: r.ignore_layers.join(', ') })) }).catch((e) => setErr(e.message)) }, [])
  useEffect(() => { api.get('/api/opportunities?' + new URLSearchParams({ my_naics_only: 'false', limit: 200 })).then((r) => setOpps(r.results || [])).catch(() => {}) }, [])
  useEffect(() => {
    if (!quoteId) return
    api.get(`/api/flat/quotes/${quoteId}`).then((q) => {
      const s = q.spec
      setParts(s.parts || [])
      setFiles((s.source?.files) || [])
      setOpts({ ...defaultOpts(), ...(s.options || {}) })
      setQtyText((s.quantities || [1]).join(', '))
      setHead({ name: s.name || '', part_number: s.part_number || '', nsn: s.nsn || '' })
      setSave({ opportunity_id: q.opportunity_id, status: q.status, notes: q.notes || '' })
      if (q.quoted_quantity) setPick(q.quoted_quantity)
    }).catch((e) => setErr(e.message))
  }, [quoteId])
  useEffect(() => {
    if (!oppId || quoteId) return
    api.get(`/api/opportunities/${oppId}`).then((x) => setHead((h) => ({ ...h, name: h.name || x.title, nsn: h.nsn || x.nsn || '' }))).catch(() => {})
  }, [oppId])

  const quantities = useMemo(() => [...new Set(qtyText.split(/[\s,]+/).map(Number).filter((n) => Number.isInteger(n) && n > 0))].sort((a, b) => a - b), [qtyText])
  const cleanOpts = useMemo(() => {
    const c = { ...opts }
    Object.keys(c).forEach((k) => { if (c[k] === '' || c[k] == null) delete c[k] })
    return c
  }, [opts])

  // Re-price shortly after any edit
  useEffect(() => {
    clearTimeout(timer.current)
    if (!parts.length || !quantities.length || !o) { setEst(null); return }
    timer.current = setTimeout(() => {
      api.post('/api/flat/quote', { parts, quantities, options: cleanOpts })
        .then((r) => { setEst(r); setErr('') })
        .catch((e) => { setEst(null); setErr(e.message) })
    }, 300)
    return () => clearTimeout(timer.current)
  }, [JSON.stringify(parts), quantities.join(','), JSON.stringify(cleanOpts), o])

  const parse = async (list, settings = read) => {
    const dxf = [...(list || [])].filter(Boolean)
    if (!dxf.length) return
    const bad = dxf.find((f) => !/\.dxf$/i.test(f.name))
    if (bad) { setErr(`${bad.name}: upload DXF files (.dxf). Export the flat pattern from your CAD tool as DXF.`); return }
    lastFiles.current = dxf
    setBusy(true); setErr(''); setMsg('')
    const form = new FormData()
    dxf.forEach((f) => form.append('files', f))
    form.append('units', settings.units)
    form.append('ignore_layers', settings.ignore_layers)
    if (settings.tolerance_in) form.append('tolerance_in', settings.tolerance_in)
    try {
      const r = await api.upload('/api/flat/parse', form)
      setFiles(r.files)
      setParts(r.parts.map((p) => ({ ...p, include: true })))
      if (!head.name) setHead((h) => ({ ...h, name: dxf.length === 1 ? dxf[0].name.replace(/\.dxf$/i, '') : `${dxf.length} DXF parts` }))
    } catch (e) { setErr(e.message) }
    setBusy(false)
  }
  const reparse = (patch) => {
    const next = { ...read, ...patch }
    setRead(next)
    if (lastFiles.current.length) parse(lastFiles.current, next)
  }

  const set = (k, v) => setOpts((s) => ({ ...s, [k]: v }))
  const setPart = (i, patch) => setParts((ps) => ps.map((p, j) => (j === i ? { ...p, ...patch } : p)))
  const toggleFinish = (f) => setOpts((s) => ({ ...s, finishes: s.finishes.includes(f) ? s.finishes.filter((x) => x !== f) : [...s.finishes, f] }))
  const chooseProcess = (p) => setOpts((s) => {
    const ok = PROC_OK[p]
    const keep = ok.includes(o.materials[s.material])
    const fallback = Object.keys(o.materials).find((m) => ok.includes(o.materials[m]))
    return { ...s, process: p, material: keep ? s.material : fallback }
  })

  const row = est ? (est.price_breaks.find((b) => b.quantity === pick) || est.price_breaks[0]) : null
  const doSave = async () => {
    setMsg(''); setErr('')
    try {
      const q = await api.post('/api/flat/save', { parts, quantities, options: cleanOpts, ...head, source: { files },
        opportunity_id: save.opportunity_id || null, status: save.status, notes: save.notes,
        quoted_quantity: row?.quantity ?? null, quoted_unit_price: row?.unit_price ?? null, quote_id: quoteId ? Number(quoteId) : null })
      setMsg(`Saved quote #${q.id}.`)
      if (!quoteId) onSaved(q.id)
    } catch (e) { setErr(e.message) }
  }

  if (!o) return <p className="muted">{err || 'Loading…'}</p>
  const mats = Object.entries(o.materials).filter(([, c]) => PROC_OK[opts.process].includes(c)).map(([m]) => m)
  const thicknessKnown = o.thicknesses.includes(Number(opts.thickness))

  const dropzone = (
    <div className={`dropzone ${parts.length || files.length ? 'dz-sm' : ''} ${drag ? 'over' : ''}`} onClick={() => input.current.click()}
      onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
      onDrop={(e) => { e.preventDefault(); setDrag(false); parse(e.dataTransfer.files) }}>
      <input ref={input} type="file" accept=".dxf" multiple hidden onChange={(e) => { parse(e.target.files); e.target.value = '' }} />
      {busy ? <div className="big">Reading…</div>
        : parts.length || files.length ? <span className="small">Drop DXF files to replace the parts</span>
          : <><div className="big">Drop DXF flat patterns here</div><p className="muted">One or more .dxf files. A file can hold several parts as separate closed profiles. Text, dimensions and title-block layers are ignored.</p></>}
    </div>
  )

  return (
    <>
      <div className="panel">
        {dropzone}
        {err && <div className="err" style={{ marginTop: 10 }}>{err}</div>}
        <div className="row" style={{ marginTop: 10, gap: 12 }}>
          <label className="f" style={{ width: 170 }}>Units
            <select value={read.units} onChange={(e) => reparse({ units: e.target.value })}>
              {o.units.map((u) => <option key={u} value={u}>{u === 'auto' ? 'From the file (inches if none)' : u}</option>)}
            </select>
          </label>
          <button className="link" onClick={() => setShowRead(!showRead)}>{showRead ? 'Hide' : 'Layers and join tolerance'}</button>
          {lastFiles.current.length > 0 && <button className="link" onClick={() => parse(lastFiles.current)}>Read again</button>}
        </div>
        {showRead && (
          <div className="grid g2" style={{ marginTop: 8 }}>
            <label className="f">Ignore layers whose name contains (comma separated)
              <input value={read.ignore_layers} onChange={(e) => setRead({ ...read, ignore_layers: e.target.value })} onBlur={() => reparse({})} />
            </label>
            <label className="f">Join tolerance (in, blank = {o.join_tolerance_in})
              <input type="number" min="0" step="0.001" value={read.tolerance_in} onChange={(e) => setRead({ ...read, tolerance_in: e.target.value })} onBlur={() => reparse({})} />
            </label>
            <p className="small muted" style={{ gridColumn: 'span 2' }}>Lines on a layer named like "bend" are counted as bend lines, not cut. Raise the join tolerance if gaps leave open contours.</p>
          </div>
        )}
      </div>

      {files.map((f, i) => (
        <div className="panel" key={`${f.filename}-${i}`}>
          <div className="row spread">
            <b>{f.filename}</b>
            <span className="small muted">units: {f.units}{f.units_source ? ` (${f.units_source})` : ''}</span>
          </div>
          {f.svg ? <div className="dxf-preview" dangerouslySetInnerHTML={{ __html: f.svg }} /> : <p className="small muted">Preview not saved with this quote.</p>}
          <div className="small muted dxf-legend">
            <span><i style={{ background: '#dbe7f3', borderColor: '#1f4e79' }} /> part outline</span>
            <span><i style={{ background: '#fff', borderColor: '#c2410c' }} /> cutout</span>
            <span><i style={{ background: 'transparent', borderColor: '#dc2626', borderStyle: 'dashed' }} /> open contour (not cut)</span>
            <span><i style={{ background: 'transparent', borderColor: '#2563eb', borderStyle: 'dashed' }} /> bend line</span>
          </div>
          {f.warnings?.length > 0 && <ul className="clean small" style={{ marginTop: 6 }}>{f.warnings.map((w, k) => <li key={k} className="due-soon">{w}</li>)}</ul>}
        </div>
      ))}

      {parts.length > 0 && (
        <div className="panel">
          <h2>Parts ({parts.length})</h2>
          <div style={{ overflowX: 'auto' }}>
            <table className="small">
              <thead><tr><th></th><th>#</th><th>Name</th><th>Qty / set</th><th>Size (in)</th><th>Net area in²</th><th>Cut length in</th><th>Pierces</th><th>Holes</th><th>Min radius</th><th>Bends</th><th>PEM</th></tr></thead>
              <tbody>
                {parts.map((p, i) => (
                  <tr key={p.id || i} className={p.include === false ? 'muted' : ''}>
                    <td><input type="checkbox" checked={p.include !== false} onChange={(e) => setPart(i, { include: e.target.checked })} title="Include in the quote" /></td>
                    <td className="mono">{p.index}</td>
                    <td><input value={p.name || ''} onChange={(e) => setPart(i, { name: e.target.value })} style={{ width: 150 }} />{files.length > 1 && <div className="muted">{p.file}</div>}</td>
                    <td><input type="number" min="0" value={p.qty} onChange={(e) => setPart(i, { qty: e.target.value === '' ? '' : Math.max(0, Number(e.target.value)) })} style={{ width: 60 }} /></td>
                    <td className="mono">{fmt(p.width)} × {fmt(p.height)}</td>
                    <td className="mono">{fmt(p.net_area, 2)}</td>
                    <td className="mono">{fmt(p.cut_length, 2)}</td>
                    <td className="mono">{p.pierces}</td>
                    <td className="mono">{p.cutouts || 0}{p.hole_diameters?.length > 0 && <div className="muted">{p.hole_diameters.map((h) => `${h.count}× Ø${fmt(h.diameter, 4)}`).join(', ')}</div>}</td>
                    <td className="mono">{p.min_radius != null ? fmt(p.min_radius, 4) : ''}</td>
                    <td><input type="number" min="0" value={p.bends ?? 0} onChange={(e) => setPart(i, { bends: Math.max(0, Number(e.target.value) || 0) })} style={{ width: 52 }} title={p.bend_lines ? `${p.bend_lines} bend line(s) found in the DXF` : ''} /></td>
                    <td><input type="number" min="0" value={p.pem ?? 0} onChange={(e) => setPart(i, { pem: Math.max(0, Number(e.target.value) || 0) })} style={{ width: 52 }} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {parts.length > 0 && (
        <div className="builder iq">
          <div>
            <div className="panel">
              <h2>Configure</h2>
              <h3>Process</h3>
              <div className="row" style={{ gap: 6 }}>
                {Object.entries(o.processes).map(([p, label]) => <button key={p} className={`chip ${opts.process === p ? 'on' : ''}`} title={label} onClick={() => chooseProcess(p)}>{PROC_LABEL[p] || p}</button>)}
              </div>
              <div className="grid g3" style={{ marginTop: 12 }}>
                <label className="f">Material<select value={opts.material} onChange={(e) => set('material', e.target.value)}>{mats.map((m) => <option key={m}>{m}</option>)}</select></label>
                <label className="f">Thickness (in)
                  <select value={thicknessKnown ? opts.thickness : 'custom'} onChange={(e) => set('thickness', e.target.value === 'custom' ? '' : Number(e.target.value))}>
                    <optgroup label="Sheet">{o.sheet_gauges.map((t) => <option key={t} value={t}>{t.toFixed(3)}</option>)}</optgroup>
                    <optgroup label="Plate">{o.plate_thicknesses.map((t) => <option key={t} value={t}>{t.toFixed(3)}</option>)}</optgroup>
                    <option value="custom">Other…</option>
                  </select>
                  {!thicknessKnown && <input type="number" min="0" step="0.001" value={opts.thickness} onChange={(e) => set('thickness', e.target.value === '' ? '' : Number(e.target.value))} placeholder="inches" style={{ marginTop: 4 }} />}
                </label>
                <label className="f">Quantities (sets)<input value={qtyText} onChange={(e) => setQtyText(e.target.value)} placeholder="1, 10, 50" /></label>
              </div>

              <h3>Sheet and nesting</h3>
              <div className="grid g3">
                <label className="f">Sheet size (in)
                  <select value={opts.sheet} onChange={(e) => set('sheet', e.target.value)}>
                    {Object.keys(o.sheet_sizes).map((s) => <option key={s}>{s}</option>)}
                    <option value="custom">Custom…</option>
                  </select>
                </label>
                {opts.sheet === 'custom' && <>
                  <label className="f">Sheet width (in)<input type="number" min="0" value={opts.sheet_width} onChange={(e) => set('sheet_width', e.target.value === '' ? '' : Number(e.target.value))} /></label>
                  <label className="f">Sheet length (in)<input type="number" min="0" value={opts.sheet_length} onChange={(e) => set('sheet_length', e.target.value === '' ? '' : Number(e.target.value))} /></label>
                </>}
                <label className="f">Part spacing (in)<input type="number" min="0" step="0.05" value={opts.spacing_in} placeholder={String(o.config.spacing_in)} onChange={(e) => set('spacing_in', e.target.value === '' ? '' : Number(e.target.value))} /></label>
                <label className="f">Edge margin (in)<input type="number" min="0" step="0.05" value={opts.edge_margin_in} placeholder={String(o.config.edge_margin_in)} onChange={(e) => set('edge_margin_in', e.target.value === '' ? '' : Number(e.target.value))} /></label>
              </div>
              <label className="check small" style={{ display: 'block', marginTop: 6 }}><input type="checkbox" checked={!!opts.full_sheets} onChange={(e) => set('full_sheets', e.target.checked)} /> Charge whole sheets (otherwise material is charged on the sheet area each part takes)</label>

              <h3>Edges and finish</h3>
              <div className="row" style={{ gap: 6 }}>
                {Object.entries(o.deburr).map(([k, label]) => <button key={k} className={`chip ${opts.deburr === k ? 'on' : ''}`} onClick={() => set('deburr', k)}>{label}</button>)}
              </div>
              <div className="row" style={{ gap: 6, marginTop: 8 }}>
                <button className={`chip ${opts.finishes.length === 0 ? 'on' : ''}`} onClick={() => set('finishes', [])}>No finish</button>
                {o.finishes.map((f) => <button key={f} className={`chip ${opts.finishes.includes(f) ? 'on' : ''}`} onClick={() => toggleFinish(f)}>{f}</button>)}
              </div>

              <h3>Hardware, quality and delivery</h3>
              <div className="grid g3">
                <label className="f">PEM unit cost $ (blank = {usd(o.config.pem.unit_cost)} placeholder)<input type="number" min="0" step="0.01" value={opts.pem_unit_cost} onChange={(e) => set('pem_unit_cost', e.target.value === '' ? '' : Number(e.target.value))} /></label>
                <label className="f">Packaging<select value={opts.packaging} onChange={(e) => set('packaging', e.target.value)}>{o.packaging_levels.map((p) => <option key={p} value={p}>{p === 'mil_std_2073' ? 'MIL-STD-2073' : 'Commercial'}</option>)}</select></label>
                <label className="f">Freight per lot $ (blank = default)<input type="number" min="0" value={opts.freight_per_lot} onChange={(e) => set('freight_per_lot', e.target.value === '' ? '' : Number(e.target.value))} /></label>
              </div>
              <div className="row" style={{ gap: 16, marginTop: 6 }}>
                <label className="check"><input type="checkbox" checked={!!opts.first_article} onChange={(e) => set('first_article', e.target.checked)} /> First article inspection</label>
                <label className="check"><input type="checkbox" checked={!!opts.material_certs} onChange={(e) => set('material_certs', e.target.checked)} /> Material certs</label>
              </div>

              <h3>Quote info</h3>
              <div className="grid g3">
                <label className="f">Name<input value={head.name} onChange={(e) => setHead({ ...head, name: e.target.value })} /></label>
                <label className="f">Part / drawing number<input value={head.part_number} onChange={(e) => setHead({ ...head, part_number: e.target.value })} /></label>
                <label className="f">NSN<input value={head.nsn} onChange={(e) => setHead({ ...head, nsn: e.target.value })} /></label>
              </div>
              <p className="small muted" style={{ marginTop: 8 }}>{o.config.note} Laser and waterjet use your <Link to="/part-quotes?tab=rates">shop rates</Link>.</p>
            </div>
            {est && <Nesting est={est} />}
          </div>

          <div>
            <div className="panel price-panel">
              {!est || !row ? <p className="muted">{err ? '' : 'Pricing…'}</p> : (
                <>
                  <div className="small muted">{PROC_LABEL[est.process]} · {fmt(est.thickness)} in {est.material} · {est.parts_per_set} part{est.parts_per_set === 1 ? '' : 's'} per set · {fmt(est.cut_length_in, 1)} in of cut</div>
                  <div className="price-big">{usd(row.unit_price)}<span> / set</span></div>
                  <div className="row spread">
                    <div><b>{usd(row.total_price)}</b> for {row.quantity} · {row.sheets} sheet{row.sheets === 1 ? '' : 's'} · ships in about {row.lead_time_days} days</div>
                    <div className="small muted">margin {row.margin_pct}%</div>
                  </div>
                  <table style={{ marginTop: 12 }}>
                    <thead><tr><th>Sets</th><th>Price / set</th><th>Total</th><th>Sheets</th><th>Lead</th></tr></thead>
                    <tbody>{est.price_breaks.map((b) => (
                      <tr key={b.quantity} className={`clickable ${b.quantity === row.quantity ? 'sel' : ''}`} onClick={() => setPick(b.quantity)}>
                        <td className="mono">{b.quantity}</td><td className="mono"><b>{usd(b.unit_price)}</b></td><td className="mono">{usd(b.total_price)}</td><td className="mono">{b.sheets}</td><td className="mono">{b.lead_time_days}d</td>
                      </tr>))}</tbody>
                  </table>
                  <ul className="clean small" style={{ marginTop: 10 }}>
                    {est.warnings.map((w, i) => <li key={`w${i}`} className="due-soon">{w}</li>)}
                    {est.assumptions.slice(0, showDetail ? 99 : 2).map((a, i) => <li key={`a${i}`}>{a}</li>)}
                  </ul>
                  <button className="link" onClick={() => setShowDetail(!showDetail)}>{showDetail ? 'Hide cost breakdown' : 'Show cost breakdown'}</button>
                  {showDetail && (
                    <>
                      <h3>Per set ({usd(est.per_part_cost)})</h3>
                      <CostLines lines={est.per_part_lines} />
                      <h3>Per lot ({usd(est.per_lot_cost)})</h3>
                      <CostLines lines={est.per_lot_lines} />
                      <p className="small muted">G&A {Math.round(est.ga_rate * 100)}% · profit {Math.round(est.profit_rate * 100)}% · {est.part_weight_lb} lb of parts per set. {est.config_note}</p>
                    </>
                  )}
                </>
              )}
            </div>

            {est && row && (
              <div className="panel">
                <h2>Save quote</h2>
                <div className="grid g2">
                  <label className="f" style={{ gridColumn: 'span 2' }}>Opportunity
                    <select value={save.opportunity_id || ''} onChange={(e) => setSave({ ...save, opportunity_id: e.target.value ? Number(e.target.value) : null })}>
                      <option value="">Not linked</option>
                      {opps.map((x) => <option key={x.id} value={x.id}>{x.solicitation_number ? `${x.solicitation_number}: ` : ''}{(x.title || '').slice(0, 80)}</option>)}
                    </select>
                  </label>
                  <label className="f">Status<select value={save.status} onChange={(e) => setSave({ ...save, status: e.target.value })}>{meta.statuses.map((s) => <option key={s}>{s}</option>)}</select></label>
                  <label className="f">Quoting quantity<select value={row.quantity} onChange={(e) => setPick(Number(e.target.value))}>{est.price_breaks.map((b) => <option key={b.quantity} value={b.quantity}>{b.quantity} at {usd(b.unit_price)}</option>)}</select></label>
                  <label className="f" style={{ gridColumn: 'span 2' }}>Notes<textarea value={save.notes} onChange={(e) => setSave({ ...save, notes: e.target.value })} style={{ minHeight: 50 }} placeholder="Drawing rev, grain direction, edge finish callouts" /></label>
                </div>
                <div className="row" style={{ marginTop: 10 }}>
                  <button className="primary" onClick={doSave}>{quoteId ? 'Update quote' : 'Save quote'}</button>
                  {msg && <span className="small okline">{msg}</span>}
                  {save.opportunity_id && <Link className="small" to={`/opportunities/${save.opportunity_id}`}>Open opportunity</Link>}
                </div>
              </div>
            )}
            {quoteId && <QuoteActions quoteId={quoteId} refreshKey={msg} />}
          </div>
        </div>
      )}
    </>
  )
}

function CostLines({ lines }) {
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

function Nesting({ est }) {
  const n = est.nesting
  return (
    <div className="panel">
      <h2>Nesting on {n.sheet.width} × {n.sheet.length} in sheets</h2>
      <table className="small">
        <thead><tr><th>Part</th><th>Per sheet</th><th>Grid</th><th>Sheet used</th></tr></thead>
        <tbody>{n.parts.map((p) => (
          <tr key={p.id || p.name}><td>{p.name}</td><td className="mono">{p.per_sheet}</td><td className="mono">{p.grid}{p.rotated ? ' (turned 90°)' : ''}</td><td className="mono">{p.utilization_pct}%</td></tr>
        ))}</tbody>
      </table>
      <p className="small muted">
        Sheets by quantity: {Object.entries(n.by_quantity).map(([q, x]) => `${q} set(s): ${x.sheets} (${x.utilization_pct}% used)`).join(' · ')}.
        Grid nest of each part's bounding box with {n.spacing_in} in spacing and {n.edge_margin_in} in edge margin; true-shape nesting usually does better.
      </p>
    </div>
  )
}
