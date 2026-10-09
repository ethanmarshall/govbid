import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import MakeOrBuy from '../MakeOrBuy'
import QuoteActions from '../QuoteActions'
import DfmPanel from '../DfmPanel'
import AssemblyPanel from '../AssemblyPanel'
import DrawingQuote from '../DrawingQuote'
import { BuildQtyInput, buildFromSaved, buildList, toBuild } from '../qty'
import HeatSetInserts from '../HeatSetInserts'
import StepViewer from '../StepViewer'

const usd = (n) => (n == null ? '' : `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`)
const PROCESS_LABEL = { auto: 'Auto-detect', cnc_mill: 'CNC milling', cnc_lathe: 'CNC turning', sheet_metal: 'Sheet metal', '3d_print': '3D printing' }

const defaultOpts = () => ({
  process: 'auto', material: '6061-T6 aluminum', thickness: '', finishes: [], tolerance: 'standard',
  infill: 0.4, support: true, threaded_holes: 0, inserts: 0, weld_length_in: 0, first_article: false, material_certs: false,
  packaging: 'commercial', reference_unit_price: '', name: '', part_number: '', nsn: '', drawing_id: '', drawing_name: '',
})

export default function InstantQuote({ meta, quoteId, oppId, onSaved, onOpenManual }) {
  const [cadOpts, setCadOpts] = useState(null)
  const [file, setFile] = useState(null) // { file_id, filename, geometry, mesh }
  const [busy, setBusy] = useState(false)
  const [drag, setDrag] = useState(false)
  const [opts, setOpts] = useState(defaultOpts)
  const [qtyText, setQtyText] = useState('1') // units to build; priced at 1 unit and at this quantity
  const [qty, setQtyList] = useState([1])
  const [pick, setPick] = useState(1)
  const [res, setRes] = useState(null)
  const [err, setErr] = useState('')
  const [showDetail, setShowDetail] = useState(false)
  const [save, setSave] = useState({ opportunity_id: oppId ? Number(oppId) : null, status: 'draft', notes: '' })
  const [opps, setOpps] = useState([])
  const [msg, setMsg] = useState('')
  const [drawing, setDrawing] = useState(null) // read result from /api/drawings/read
  const [drawingBusy, setDrawingBusy] = useState(false)
  const [drawingErr, setDrawingErr] = useState('')
  const [drawingMsg, setDrawingMsg] = useState('')
  const drawingFile = useRef(null)
  const input = useRef()
  const timer = useRef()

  useEffect(() => { api.get('/api/cad/options').then(setCadOpts) }, [])
  useEffect(() => {
    api.get('/api/opportunities?' + new URLSearchParams({ my_naics_only: 'false', limit: 200 })).then((r) => setOpps(r.results)).catch(() => {})
  }, [])
  // Prefill from a linked opportunity
  useEffect(() => {
    if (!oppId || quoteId) return
    api.get(`/api/opportunities/${oppId}`).then((o) => {
      setOpts((s) => ({ ...s, name: s.name || o.title || '', nsn: s.nsn || o.nsn || '' }))
      if (o.quantity && Number(o.quantity) > 0) { const q = Number(o.quantity); setQty(String(q)); setPick(q) }
    }).catch(() => {})
  }, [oppId, quoteId])
  // Reopen a saved instant quote
  useEffect(() => {
    if (!quoteId) return
    api.get(`/api/pricing/quotes/${quoteId}`).then(async (q) => {
      const cad = q.spec?.cad
      if (!cad) { onOpenManual(quoteId); return }
      setOpts({ ...defaultOpts(), ...(cad.options || {}), name: q.spec.name || '', part_number: q.spec.part_number || '', nsn: q.spec.nsn || '' })
      const qs = q.spec.quantities || [1]
      const n = buildFromSaved(qs, q.quoted_quantity)
      setQtyText(String(n)); setQtyList(buildList(n)); setPick(n)
      setSave({ opportunity_id: q.opportunity_id, status: q.status, notes: q.notes || '' })
      try { setFile(await api.get(`/api/cad/${cad.file_id}`)) } catch (e) { setErr(`${e.message} (${cad.filename})`) }
      if (cad.options?.drawing_id) api.get(`/api/drawings/${cad.options.drawing_id}`).then(setDrawing).catch(() => {})
    })
  }, [quoteId])

  // ------------------------------------------------------------ drawing (PDF)
  const readDrawing = async (f, useAi = false) => {
    if (!f) return
    if (!/\.pdf$/i.test(f.name)) { setDrawingErr('Upload the drawing as a PDF.'); return }
    drawingFile.current = f
    setDrawingBusy(true); setDrawingErr(''); setDrawingMsg('')
    const form = new FormData()
    form.append('file', f)
    if (useAi) form.append('use_ai', 'true')
    try {
      const d = await api.upload('/api/drawings/read', form)
      setDrawing(d)
      setOpts((s) => ({ ...s, drawing_id: d.drawing_id, drawing_name: d.filename }))
    } catch (e) { setDrawingErr(e.message) }
    setDrawingBusy(false)
  }

  const applyDrawing = () => {
    const q = drawing?.quote_options || {}
    const applied = []
    const n = { ...opts, drawing_id: drawing.drawing_id, drawing_name: drawing.filename }
    if (q.material && cadOpts.materials.includes(q.material)) {
      n.material = q.material
      if (opts.process === '3d_print') n.process = 'auto'
      applied.push('material')
    }
    const printing = n.process === '3d_print'
    const fins = (q.finishes || []).filter((f) => cadOpts.finishes.includes(f))
    if (fins.length && !printing) { n.finishes = fins; applied.push('finish') }
    if (q.tolerance && cadOpts.tolerances.includes(q.tolerance)) { n.tolerance = q.tolerance; applied.push('tolerance') }
    if (q.threaded_holes) { n.threaded_holes = q.threaded_holes; applied.push('threaded holes') }
    if (q.inserts && !printing) { n.inserts = q.inserts; applied.push('inserts') }
    if (q.part_number) { n.part_number = q.part_number; applied.push('part number') }
    if (q.name) { n.name = q.name; applied.push('name') }
    if (q.material_certs) { n.material_certs = true; applied.push('material certs') }
    if (q.first_article) { n.first_article = true; applied.push('first article') }
    setOpts(n)
    setDrawingMsg(applied.length ? `Applied: ${applied.join(', ')}.` : 'Nothing on the drawing mapped to a quote option.')
  }

  const clearDrawing = () => {
    setDrawing(null); setDrawingErr(''); setDrawingMsg(''); drawingFile.current = null
    setOpts((s) => ({ ...s, drawing_id: '', drawing_name: '' }))
  }

  const drawingPanel = (
    <DrawingPanel drawing={drawing} name={opts.drawing_name} busy={drawingBusy} err={drawingErr} msg={drawingMsg}
      onFile={(f) => readDrawing(f)} onAi={() => readDrawing(drawingFile.current, true)} canAi={!!drawingFile.current}
      onApply={applyDrawing} onClear={clearDrawing} />
  )

  const setQty = (t) => {
    setQtyText(t)
    setQtyList(buildList(t)); setPick(toBuild(t))
  }

  const upload = async (f) => {
    if (!f) return
    if (!/\.(step|stp)$/i.test(f.name)) { setErr('Upload a STEP file (.step or .stp). Export it from SolidWorks, Fusion, Inventor, Onshape or any CAD tool.'); return }
    setBusy(true); setErr(''); setRes(null); setMsg('')
    const form = new FormData()
    form.append('file', f)
    try {
      const d = await api.upload('/api/cad/upload', form)
      setFile(d)
      const stem = (n) => (n || '').replace(/\.(step|stp)$/i, '')
      // a fresh part gets its own name unless the user typed one
      setOpts((s) => ({ ...s, process: 'auto', thickness: '', name: !s.name || (file && s.name === stem(file.filename)) ? stem(d.filename) : s.name }))
    } catch (e) { setErr(e.message) }
    setBusy(false)
  }

  // Live price, debounced
  useEffect(() => {
    if (!file) return
    clearTimeout(timer.current)
    timer.current = setTimeout(async () => {
      const o = { ...opts, quantities: qty, filename: file.filename }
      for (const k of ['thickness', 'reference_unit_price', 'drawing_id', 'drawing_name']) if (o[k] === '' || o[k] == null) delete o[k]
      if (o.process !== '3d_print') { delete o.infill; delete o.support }
      try { setRes(await api.post('/api/cad/quote', { file_id: file.file_id, options: o })); setErr('') } catch (e) { setRes(null); setErr(e.message) }
    }, 300)
    return () => clearTimeout(timer.current)
  }, [file, JSON.stringify(opts), qty.join(',')])

  const set = (k, v) => setOpts((s) => ({ ...s, [k]: v }))
  // Switching between metal and printing swaps the material list and the finishes
  const chooseProcess = (p) => setOpts((s) => {
    const toPrint = p === '3d_print'
    const wasPrint = s.process === '3d_print'
    if (toPrint === wasPrint) return { ...s, process: p }
    return { ...s, process: p, finishes: [], material: toPrint ? 'PETG' : '6061-T6 aluminum', weld_length_in: 0 }
  })
  const toggleFinish = (f) => setOpts((s) => ({ ...s, finishes: s.finishes.includes(f) ? s.finishes.filter((x) => x !== f) : [...s.finishes, f] }))

  const doSave = async () => {
    setMsg(''); setErr('')
    const row = res.estimate.price_breaks.find((b) => b.quantity === pick)
    const body = { spec: res.spec, opportunity_id: save.opportunity_id || null, status: save.status, notes: save.notes, quoted_quantity: pick, quoted_unit_price: row?.unit_price ?? null }
    try {
      const q = quoteId ? await api.put(`/api/pricing/quotes/${quoteId}`, body) : await api.post('/api/pricing/quotes', body)
      setMsg(`Saved quote #${q.id}.`)
      if (!quoteId) onSaved(q.id)
    } catch (e) { setErr(e.message) }
  }

  if (!cadOpts) return <p className="muted">Loading…</p>

  // ------------------------------------------------------------ empty state
  if (!file) {
    return (
      <>
      <div className="panel">
        <div
          className={`dropzone ${drag ? 'over' : ''}`}
          onClick={() => input.current.click()}
          onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files[0]) }}
        >
          <input ref={input} type="file" hidden onChange={(e) => upload(e.target.files[0])} />
          {busy ? <><div className="big">Reading your model…</div><p className="muted">Measuring volume, holes, bends and stock size.</p></>
            : <><div className="big">Drop a STEP file here</div><p className="muted">or click to choose one (.step or .stp, up to 60 MB). One part per file works best.</p></>}
        </div>
        {err && <div className="err" style={{ marginTop: 10 }}>{err}</div>}
        <div style={{ marginTop: 14 }}>{drawingPanel}</div>
        <p className="small muted" style={{ marginTop: 12 }}>
          Supports CNC milled, CNC turned, formed sheet metal and 3D printed parts. Prices come from your <Link to="/part-quotes?tab=rates">shop rates</Link>, so set those first.
          No model? Drop the PDF drawing and quote from it, or use the <button className="link" onClick={() => onOpenManual()}>manual estimator</button>.
        </p>
      </div>
      {drawing && <DrawingQuote key={drawing.drawing_id} drawing={drawing} cadOpts={cadOpts} statuses={meta.statuses} oppId={oppId} />}
      </>
    )
  }

  const g = file.geometry
  const bb = g.bounding_box
  const est = res?.estimate
  const row = est?.price_breaks.find((b) => b.quantity === pick) || est?.price_breaks[0]
  const process = res?.process || (opts.process === 'auto' ? g.suggested_process : opts.process)
  const isSheet = process === 'sheet_metal'
  const isPrint = process === '3d_print'
  const printTech = isPrint ? cadOpts.print_materials[opts.material] : null
  const available = Object.keys(cadOpts.processes).filter((p) => p === 'auto' || p === 'cnc_mill' || (p === 'cnc_lathe' && g.turned) || (p === 'sheet_metal' && g.sheet_metal) || p === '3d_print')

  return (
    <div className="builder iq">
      <div>
        <div className="panel">
          <div className="row spread">
            <div><b>{file.filename}</b> <span className="small muted">{PROCESS_LABEL[g.suggested_process]} detected</span></div>
            <div className="row">
              <a className="small" href={`/api/cad/${file.file_id}/download`}>Download STEP</a>
              <button className="link" onClick={() => { setRes(null); setErr(''); setFile(null); setOpts((o) => ({ ...o, name: o.name === file.filename.replace(/\.(step|stp)$/i, '') ? '' : o.name })) }}>Upload a different part</button>
            </div>
          </div>
          <StepViewer mesh={file.mesh} />
          <div className="geo small">
            <span><b>{bb.length} × {bb.width} × {bb.height}</b> in</span>
            <span>Volume <b>{g.volume}</b> in³</span>
            <span>Holes <b>{g.holes.length}</b>{g.holes.length > 0 && ` (${[...new Set(g.holes.map((h) => h.diameter))].slice(0, 4).map((d) => `Ø${d}`).join(', ')})`}</span>
            {g.sheet_metal && <span>Sheet <b>{g.sheet_metal.thickness}</b> in, <b>{g.sheet_metal.bends}</b> bend{g.sheet_metal.bends === 1 ? '' : 's'}</span>}
            {g.turned && <span>Turned Ø<b>{g.turned.max_diameter}</b> × {g.turned.length} in</span>}
            {g.faces.freeform > 0 && <span className="due-soon">{g.faces.freeform} contoured surfaces</span>}
          </div>
        </div>

        <div className="panel">{drawingPanel}</div>

        <DfmPanel fileId={file.file_id} process={process} material={opts.material} />

        {(g.solids || 1) > 1 && <AssemblyPanel key={file.file_id} file={file} cadOpts={cadOpts} quantities={qty} statuses={meta.statuses} oppId={save.opportunity_id || oppId} onSaved={() => {}} />}

        <div className="panel">
          <h2>Configure</h2>
          <h3>Process</h3>
          <div className="row" style={{ gap: 6 }}>
            {available.map((p) => (
              <button key={p} className={`chip ${opts.process === p ? 'on' : ''}`} onClick={() => chooseProcess(p)} title={cadOpts.processes[p]}>
                {PROCESS_LABEL[p]}{p === 'auto' ? ` (${PROCESS_LABEL[g.suggested_process]})` : ''}
              </button>
            ))}
          </div>

          <div className="grid g3" style={{ marginTop: 12 }}>
            <label className="f">Material
              {isPrint ? (
                <select value={opts.material} onChange={(e) => set('material', e.target.value)}>
                  {Object.entries(cadOpts.print_technologies).map(([t, label]) => (
                    <optgroup key={t} label={label}>
                      {Object.entries(cadOpts.print_materials).filter(([, mt]) => mt === t).map(([m]) => <option key={m}>{m}</option>)}
                    </optgroup>
                  ))}
                </select>
              ) : (
                <select value={opts.material} onChange={(e) => set('material', e.target.value)}>{cadOpts.materials.map((m) => <option key={m}>{m}</option>)}</select>
              )}
            </label>
            {isPrint && printTech === 'fdm' && (
              <label className="f">Infill
                <select value={opts.infill} onChange={(e) => set('infill', Number(e.target.value))}>
                  {[0.15, 0.2, 0.3, 0.4, 0.6, 0.8, 1].map((v) => <option key={v} value={v}>{Math.round(v * 100)}%{v === 1 ? ' (solid)' : ''}</option>)}
                </select>
              </label>
            )}
            {isPrint && (printTech === 'fdm' || printTech === 'sla') && (
              <label className="check" style={{ alignSelf: 'end', paddingBottom: 8 }}><input type="checkbox" checked={opts.support !== false} onChange={(e) => set('support', e.target.checked)} /> Needs supports</label>
            )}
            {isSheet && (
              <label className="f">Thickness (in)
                <select value={opts.thickness} onChange={(e) => set('thickness', e.target.value ? Number(e.target.value) : '')}>
                  <option value="">From model ({g.sheet_metal.thickness})</option>
                  {cadOpts.sheet_gauges.map((t) => <option key={t} value={t}>{t.toFixed(3)}</option>)}
                </select>
              </label>
            )}
            <label className="f">Tolerance
              <select value={opts.tolerance} onChange={(e) => set('tolerance', e.target.value)}>
                {cadOpts.tolerances.map((t) => <option key={t} value={t}>{t === 'standard' ? 'Standard (±.005)' : t === 'tight' ? 'Tight (±.002)' : 'Precision (±.0005)'}</option>)}
              </select>
            </label>
            <BuildQtyInput value={qtyText} onChange={setQty} label="Parts to build" />
          </div>

          <h3>Finish</h3>
          <div className="row" style={{ gap: 6 }}>
            <button className={`chip ${opts.finishes.length === 0 ? 'on' : ''}`} onClick={() => set('finishes', [])}>{isPrint ? 'As printed' : 'As machined / no finish'}</button>
            {(isPrint ? cadOpts.print_finishes : cadOpts.finishes).map((f) => <button key={f} className={`chip ${opts.finishes.includes(f) ? 'on' : ''}`} onClick={() => toggleFinish(f)}>{f}</button>)}
          </div>

          <h3>Additional features</h3>
          <div className="grid g3">
            <label className="f">{isPrint ? 'Threaded holes (heat-set inserts)' : 'Threaded holes'}<input type="number" min="0" value={opts.threaded_holes} onChange={(e) => set('threaded_holes', Math.max(0, Number(e.target.value) || 0))} /></label>
            {!isPrint && <label className="f">Hardware inserts (PEM)<input type="number" min="0" value={opts.inserts} onChange={(e) => set('inserts', Math.max(0, Number(e.target.value) || 0))} /></label>}
            {!isPrint && <label className="f">Weld length (in)<input type="number" min="0" value={opts.weld_length_in} onChange={(e) => set('weld_length_in', Math.max(0, Number(e.target.value) || 0))} /></label>}
          </div>
          {isPrint && <HeatSetInserts file={file} onFile={(d) => { setFile(d); setOpts((o) => ({ ...o, threaded_holes: 0 })) }} />}
          {g.holes.length > 0 && !isPrint && <p className="small muted" style={{ marginTop: 4 }}>The model has {g.holes.length} hole{g.holes.length === 1 ? '' : 's'}. Count how many are tapped on the drawing; threads usually are not modeled.</p>}

          <h3>Quality and delivery</h3>
          <div className="row" style={{ gap: 16 }}>
            <label className="check"><input type="checkbox" checked={opts.first_article} onChange={(e) => set('first_article', e.target.checked)} /> First article inspection</label>
            <label className="check"><input type="checkbox" checked={opts.material_certs} onChange={(e) => set('material_certs', e.target.checked)} /> Material certs</label>
            <label className="f" style={{ width: 170 }}>Packaging
              <select value={opts.packaging} onChange={(e) => set('packaging', e.target.value)}>
                {cadOpts.packaging_levels.map((p) => <option key={p} value={p}>{p === 'mil_std_2073' ? 'MIL-STD-2073' : 'Commercial'}</option>)}
              </select>
            </label>
          </div>

          <h3>Part info</h3>
          <div className="grid g3">
            <label className="f">Name<input value={opts.name} onChange={(e) => set('name', e.target.value)} /></label>
            <label className="f">Part number<input value={opts.part_number} onChange={(e) => set('part_number', e.target.value)} /></label>
            <label className="f">NSN<input value={opts.nsn} onChange={(e) => set('nsn', e.target.value)} placeholder="5340-01-…" /></label>
            <label className="f">Last award unit price $<input type="number" value={opts.reference_unit_price} onChange={(e) => set('reference_unit_price', e.target.value === '' ? '' : Number(e.target.value))} /></label>
          </div>
          <NsnHistory nsn={opts.nsn} onUsePrice={(p) => set('reference_unit_price', p)} />
        </div>
      </div>

      <div>
        <div className="panel price-panel">
          {err && <div className="err">{err}</div>}
          {!est ? <p className="muted">{err ? '' : 'Pricing…'}</p> : (
            <>
              <div className="small muted">{PROCESS_LABEL[process]} · {opts.material}{opts.finishes.length ? ` · ${opts.finishes.join(', ')}` : ''}</div>
              <div className="price-big">{usd(row.unit_price)}<span> / part</span></div>
              <div className="row spread">
                <div><b>{usd(row.total_price)}</b> for {row.quantity} · ships in about {row.lead_time_days} days</div>
                <div className="small muted">margin {row.margin_pct}%</div>
              </div>
              <table style={{ marginTop: 12 }}>
                <thead><tr><th>Qty</th><th>Unit price</th><th>Total</th><th>Lead</th>{row.vs_reference_pct !== undefined && <th>vs last award</th>}</tr></thead>
                <tbody>
                  {est.price_breaks.map((b) => (
                    <tr key={b.quantity} className={`clickable ${b.quantity === row.quantity ? 'sel' : ''}`} onClick={() => setPick(b.quantity)}>
                      <td className="mono">{b.quantity}</td><td className="mono"><b>{usd(b.unit_price)}</b></td><td className="mono">{usd(b.total_price)}</td><td className="mono">{b.lead_time_days}d</td>
                      {b.vs_reference_pct !== undefined && <td className="mono" title={b.reference_note}>{b.vs_reference_pct > 0 ? '+' : ''}{b.vs_reference_pct}%</td>}
                    </tr>
                  ))}
                </tbody>
              </table>
              {(est.warnings.length > 0 || est.assumptions.length > 0) && (
                <ul className="clean small" style={{ marginTop: 10 }}>
                  {est.warnings.map((w, i) => <li key={`w${i}`} className="due-soon">{w}</li>)}
                  {est.assumptions.slice(0, showDetail ? 99 : 3).map((a, i) => <li key={`a${i}`}>{a}</li>)}
                </ul>
              )}
              <button className="link" onClick={() => setShowDetail(!showDetail)}>{showDetail ? 'Hide cost breakdown' : 'Show cost breakdown'}</button>
              {showDetail && (
                <>
                  <h3>Per part ({usd(est.per_part_cost)})</h3>
                  <CostLines lines={est.per_part_lines} />
                  <h3>Per lot ({usd(est.per_lot_cost)} + finishing)</h3>
                  <CostLines lines={est.per_lot_lines} />
                  <p className="small muted">Stock: {res.spec.stock.shape.replace('_', ' ')} {Object.entries(res.spec.stock.dims).map(([k, v]) => `${k} ${v}`).join(', ')} in · weight {est.part_weight_lb} lb. {est.config_note}</p>
                </>
              )}
            </>
          )}
        </div>

        {est && (
          <div className="panel">
            <h2>Save quote</h2>
            <div className="grid g2">
              <label className="f" style={{ gridColumn: 'span 2' }}>Opportunity
                <select value={save.opportunity_id || ''} onChange={(e) => setSave({ ...save, opportunity_id: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">Not linked</option>
                  {opps.map((o) => <option key={o.id} value={o.id}>{o.solicitation_number ? `${o.solicitation_number}: ` : ''}{o.title.slice(0, 80)}</option>)}
                </select>
              </label>
              <label className="f">Status<select value={save.status} onChange={(e) => setSave({ ...save, status: e.target.value })}>{meta.statuses.map((s) => <option key={s}>{s}</option>)}</select></label>
              <label className="f">Quoting quantity<select value={row.quantity} onChange={(e) => setPick(Number(e.target.value))}>{est.price_breaks.map((b) => <option key={b.quantity} value={b.quantity}>{b.quantity} at {usd(b.unit_price)}</option>)}</select></label>
              <label className="f" style={{ gridColumn: 'span 2' }}>Notes<textarea value={save.notes} onChange={(e) => setSave({ ...save, notes: e.target.value })} style={{ minHeight: 50 }} placeholder="Drawing rev, callouts the model does not show, supplier quotes" /></label>
            </div>
            <div className="row" style={{ marginTop: 10 }}>
              <button className="primary" onClick={doSave}>{quoteId ? 'Update quote' : 'Save quote'}</button>
              {msg && <span className="small">{msg}</span>}
              {save.opportunity_id && <Link className="small" to={`/opportunities/${save.opportunity_id}`}>Open opportunity</Link>}
            </div>
          </div>
        )}
        {quoteId && <QuoteActions quoteId={quoteId} refreshKey={msg} />}
        {quoteId && <MakeOrBuy quoteId={quoteId} refreshKey={msg} />}
      </div>
    </div>
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

// ------------------------------------------------------------ drawing upload and summary
function DrawingPanel({ drawing, name, busy, err, msg, onFile, onAi, canAi, onApply, onClear }) {
  const [drag, setDrag] = useState(false)
  const ref = useRef()
  const d = drawing
  const pick = (
    <input ref={ref} type="file" accept=".pdf,application/pdf" hidden onChange={(e) => { onFile(e.target.files[0]); e.target.value = '' }} />
  )
  if (!d) {
    return (
      <div>
        <div className={`dropzone dz-sm ${drag ? 'over' : ''}`} onClick={() => ref.current.click()}
          onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); onFile(e.dataTransfer.files[0]) }}>
          {pick}
          {busy ? <b>Reading the drawing…</b> : <><b>Drawing (PDF)</b><div className="small muted">Drop the part drawing here to fill material, finish, tolerance, threads and part number. Before or after the STEP file.</div></>}
        </div>
        {name && !busy && <p className="small muted" style={{ marginTop: 6 }}>Saved with this quote: {name}</p>}
        {err && <div className="err" style={{ marginTop: 8 }}>{err}</div>}
      </div>
    )
  }
  const q = d.quote_options || {}
  const fins = (d.finishes || []).map((f) => f.mapped || f.raw).join(', ')
  const warn = (d.warnings || []).filter((w) => /distribution|export/i.test(w))
  const other = (d.warnings || []).filter((w) => !/distribution|export/i.test(w))
  return (
    <div>
      {pick}
      <div className="row spread">
        <div><b>Drawing</b> <a className="small" href={`/api/drawings/${d.drawing_id}/file`} target="_blank" rel="noreferrer">{d.filename || name}</a>
          {d.ai_used && <span className="tag" style={{ marginLeft: 6 }}>read by Claude</span>}</div>
        <div className="row">
          <button className="link" onClick={() => ref.current.click()} disabled={busy}>{busy ? 'Reading…' : 'Replace'}</button>
          <button className="link" onClick={onClear}>Remove</button>
        </div>
      </div>
      {warn.map((w, i) => <div key={i} className="small due-soon" style={{ marginTop: 6 }}>{w}</div>)}
      {d.text_found || d.ai_used ? (
        <table className="small dwg-sum" style={{ marginTop: 8 }}>
          <tbody>
            <tr><td className="muted">Part number</td><td className="mono">{d.part_number || <span className="muted">not found</span>}{d.revision && <> rev <b>{d.revision}</b></>}{d.cage && <span className="muted"> · CAGE {d.cage}</span>}</td></tr>
            {d.title && <tr><td className="muted">Title</td><td>{d.title}</td></tr>}
            <tr><td className="muted">Material</td><td>{d.material?.mapped || <span className="muted">not mapped</span>}{d.material?.raw && <div className="muted">{d.material.raw}</div>}</td></tr>
            <tr><td className="muted">Finish</td><td>{fins || <span className="muted">none found</span>}</td></tr>
            <tr><td className="muted">Tolerance</td><td>{d.tolerance?.class || <span className="muted">not found</span>}{d.tolerance?.raw && <span className="muted"> ({d.tolerance.raw})</span>}</td></tr>
            <tr><td className="muted">Threads</td><td>{d.threads?.count ? `${d.threads.count}: ${d.threads.callouts.join(', ')}` : <span className="muted">none found</span>}</td></tr>
            {(d.inspection?.first_article || d.inspection?.material_certs) && <tr><td className="muted">Quality</td><td>{[d.inspection.first_article && 'first article', d.inspection.material_certs && 'material certs'].filter(Boolean).join(', ')}</td></tr>}
            {d.welding?.specs?.length > 0 && <tr><td className="muted">Welding</td><td>{d.welding.specs.join(', ')}</td></tr>}
            {d.distribution?.letter && <tr><td className="muted">Distribution</td><td className={d.distribution.letter !== 'A' ? 'due-soon' : ''}>Statement {d.distribution.letter}</td></tr>}
          </tbody>
        </table>
      ) : (
        canAi && (
          <p className="small" style={{ marginTop: 8 }}>
            <button className="small-btn" onClick={onAi} disabled={busy}>Read it with Claude</button>{' '}
            <span className="muted">Sends the PDF to Anthropic. Only for drawings you may share with an outside service: never ITAR/EAR or limited-distribution drawings.</span>
          </p>
        )
      )}
      {other.length > 0 && <ul className="clean small muted" style={{ marginTop: 6 }}>{other.map((w, i) => <li key={i}>{w}</li>)}</ul>}
      <div className="row" style={{ marginTop: 8 }}>
        <button className="primary small-btn" onClick={onApply} disabled={!Object.keys(q).length}>Apply to quote</button>
        {msg && <span className="small">{msg}</span>}
        {!Object.keys(q).length && <span className="small muted">Nothing to apply automatically.</span>}
      </div>
      {err && <div className="err" style={{ marginTop: 8 }}>{err}</div>}
    </div>
  )
}

// ------------------------------------------------------------ NSN award history
const nsnDigits = (s) => (s || '').replace(/^\s*NSN[:#\s]*/i, '').replace(/[\s-]/g, '')
const validNsn = (s) => /^(\d{13}|\d{9})$/.test(nsnDigits(s))

function NsnHistory({ nsn, onUsePrice }) {
  const [hist, setHist] = useState(null)
  const [links, setLinks] = useState(null)
  const [open, setOpen] = useState(false)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [reload, setReload] = useState(0)
  const fileRef = useRef()
  const key = validNsn(nsn) ? nsnDigits(nsn) : ''

  useEffect(() => {
    setHist(null); setLinks(null); setErr('')
    if (!key) return
    let live = true
    const t = setTimeout(async () => {
      try {
        const h = await api.get(`/api/nsn/${key}/history`)
        if (!live) return
        setHist(h)
        if (!h.records.length) { const l = await api.get(`/api/nsn/${key}/links`); if (live) setLinks(l) }
      } catch (e) { if (live) setErr(e.message) }
    }, 500)
    return () => { live = false; clearTimeout(t) }
  }, [key, reload])

  const importFile = async (f) => {
    if (!f) return
    setMsg(''); setErr('')
    const form = new FormData()
    form.append('file', f)
    form.append('nsn', key)
    try {
      const r = await api.upload('/api/nsn/import', form)
      setMsg(`Imported ${r.imported} award${r.imported === 1 ? '' : 's'}${r.duplicates ? `, ${r.duplicates} already on file` : ''}${r.skipped ? `, ${r.skipped} skipped` : ''}.`)
      setReload((n) => n + 1)
    } catch (e) { setErr(e.message) }
  }

  if (!key) return null
  const s = hist?.stats
  const importBtn = (
    <>
      <input ref={fileRef} type="file" accept=".csv,.xlsx,.tsv,.txt" hidden onChange={(e) => { importFile(e.target.files[0]); e.target.value = '' }} />
      <button className="link" onClick={() => fileRef.current.click()}>Import DIBBS award results (CSV/XLSX)</button>
    </>
  )
  return (
    <div className="nsn-hist small">
      {err && <div className="err">{err}</div>}
      {!hist ? (!err && <span className="muted">Checking award history…</span>) : hist.records.length === 0 ? (
        <>
          <div><b>No award history</b> for {hist.nsn}. DIBBS blocks automated access, so history comes from DIBBS results you import, awards you enter, and your own won and lost quotes.</div>
          {links && (
            <ul className="clean" style={{ marginTop: 4 }}>
              {links.links.map((l) => <li key={l.url}><a href={l.url} target="_blank" rel="noreferrer">{l.label}</a> <span className="muted">{l.note}</span></li>)}
              {links.notes.slice(0, 1).map((n, i) => <li key={i} className="muted">{n}</li>)}
            </ul>
          )}
          <div style={{ marginTop: 4 }}>{importBtn}</div>
        </>
      ) : (
        <>
          <div>
            <b>Award history:</b> {s.count} record{s.count === 1 ? '' : 's'}
            {s.last_unit_price != null
              ? <>, last {usd(s.last_unit_price)}{s.last_price_date && ` on ${s.last_price_date}`}{s.last_priced_awardee && ` to ${s.last_priced_awardee}`}</>
              : <>, last award {s.last_award_date || 'undated'}{s.last_awardee && ` to ${s.last_awardee}`}, no unit prices on file</>}
            {s.priced_count > 1 && <span className="muted"> · median {usd(s.median_unit_price)}, range {usd(s.min)} to {usd(s.max)}</span>}
            {s.our_last_losing_price != null && <span className="muted"> · our last losing price {usd(s.our_last_losing_price)}</span>}
          </div>
          <div className="row" style={{ gap: 14, marginTop: 2 }}>
            {s.last_unit_price != null && <button className="link" onClick={() => onUsePrice(s.last_unit_price)}>Use last award price</button>}
            <button className="link" onClick={() => setOpen(!open)}>{open ? 'Hide records' : 'Show records'}</button>
            {importBtn}
          </div>
          {open && (
            <table className="small" style={{ marginTop: 6 }}>
              <thead><tr><th>Date</th><th>Contract</th><th>Awardee</th><th>Qty</th><th>Unit</th><th>Total</th><th>Source</th></tr></thead>
              <tbody>
                {hist.records.map((r) => (
                  <tr key={r.id} className={r.source === 'quote_lost' ? 'muted' : ''} title={r.notes}>
                    <td className="mono">{r.award_date}</td><td className="mono">{r.contract_number}</td><td>{r.awardee || r.cage}</td>
                    <td className="mono">{r.quantity ?? ''}{r.unit_of_issue && ` ${r.unit_of_issue}`}</td><td className="mono">{usd(r.unit_price)}</td>
                    <td className="mono">{usd(r.total)}</td><td>{r.source.replace('_', ' ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
      {msg && <div className="okmsg">{msg}</div>}
    </div>
  )
}
