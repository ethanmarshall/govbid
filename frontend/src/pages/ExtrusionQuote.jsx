import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'

const usd = (n) => (n == null ? '' : `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`)
const KINDS = [['profile', 'Profile'], ['hardware', 'Hardware'], ['panel', 'Panel'], ['custom', 'Custom (priced by hand)'], ['unmatched', 'Unmatched']]
const blankLine = (kind = 'profile') => ({ item: '', qty: 1, kind, catalog_id: '', part_number: '', description: '', length_in: null, width_in: null, height_in: null, machining: [], notes: '', confidence: 1, unit_price: null })

// "610 mm", "24.5", "2 ft", '24"' -> inches (null when blank or unreadable)
function parseLen(v) {
  const s = String(v ?? '').trim().toLowerCase()
  if (!s) return null
  const m = s.match(/^(\d+(?:\.\d+)?|\.\d+)\s*(mm|cm|m|ft|'|in|"|)$/)
  if (!m) return null
  const n = Number(m[1])
  return { mm: n / 25.4, cm: n / 2.54, m: n * 1000 / 25.4, ft: n * 12, "'": n * 12 }[m[2]] ?? n
}
const fmtLen = (v) => (v == null ? '' : String(Math.round(v * 1000) / 1000))

async function download(url, body, filename) {
  const res = await api.post(url, body)
  const blob = await res.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 2000)
}

export default function ExtrusionQuote({ meta, quoteId, oppId, onSaved }) {
  const [cat, setCat] = useState(null)
  const [lines, setLines] = useState([])
  const [qtyText, setQtyText] = useState('1, 5, 10')
  const [opts, setOpts] = useState({ pricing_mode: '', packaging_level: 'commercial', first_article: false, joints: '', freight_per_lot: '' })
  const [head, setHead] = useState({ name: '', part_number: '', nsn: '' })
  const [source, setSource] = useState({})
  const [parseInfo, setParseInfo] = useState(null)
  const [est, setEst] = useState(null)
  const [pick, setPick] = useState(null)
  const [save, setSave] = useState({ opportunity_id: oppId ? Number(oppId) : null, status: 'draft', notes: '' })
  const [opps, setOpps] = useState([])
  const [busy, setBusy] = useState(false)
  const [drag, setDrag] = useState(false)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [lastFile, setLastFile] = useState(null)
  const [showDetail, setShowDetail] = useState(false)
  const [showRates, setShowRates] = useState(false)
  const input = useRef()
  const timer = useRef()

  const loadCatalog = () => api.get('/api/extrusion/catalog').then(setCat).catch((e) => setErr(e.message))
  useEffect(() => { loadCatalog() }, [])
  useEffect(() => { api.get('/api/opportunities?' + new URLSearchParams({ my_naics_only: 'false', limit: 200 })).then((r) => setOpps(r.results || [])).catch(() => {}) }, [])
  useEffect(() => {
    if (!quoteId) return
    api.get(`/api/extrusion/quotes/${quoteId}`).then((q) => {
      const s = q.spec
      setLines(s.lines || [])
      setQtyText((s.quantities || [1]).join(', '))
      setOpts((o) => ({ ...o, ...(s.options || {}) }))
      setHead({ name: s.name || '', part_number: s.part_number || '', nsn: s.nsn || '' })
      setSource(s.source || {})
      setSave({ opportunity_id: q.opportunity_id, status: q.status, notes: q.notes || '' })
      if (q.quoted_quantity) setPick(q.quoted_quantity)
    }).catch((e) => setErr(e.message))
  }, [quoteId])
  useEffect(() => {
    if (!oppId || quoteId) return
    api.get(`/api/opportunities/${oppId}`).then((o) => setHead((h) => ({ ...h, name: h.name || o.title, nsn: h.nsn || o.nsn || '' }))).catch(() => {})
  }, [oppId])

  const quantities = useMemo(() => [...new Set(qtyText.split(/[\s,]+/).map(Number).filter((n) => Number.isInteger(n) && n > 0))].sort((a, b) => a - b), [qtyText])
  const cleanOpts = useMemo(() => {
    const o = { ...opts, name: head.name, part_number: head.part_number, nsn: head.nsn }
    Object.keys(o).forEach((k) => { if (o[k] === '' || o[k] == null) delete o[k] })
    return o
  }, [opts, head])

  // Re-price shortly after any edit
  useEffect(() => {
    clearTimeout(timer.current)
    if (!lines.length || !quantities.length) { setEst(null); return }
    timer.current = setTimeout(() => {
      api.post('/api/extrusion/quote', { lines, quantities, options: cleanOpts })
        .then((r) => { setEst(r); setErr('') })
        .catch((e) => setErr(e.message))
    }, 300)
    return () => clearTimeout(timer.current)
  }, [JSON.stringify(lines), quantities.join(','), JSON.stringify(cleanOpts), cat])

  const upload = async (file, ai = false, force = false) => {
    if (!file) return
    setBusy(true); setErr(''); setMsg(''); setLastFile(file)
    const form = new FormData()
    form.append('file', file)
    if (ai) form.append('use_ai', 'true')
    if (force) form.append('force', 'true')
    try {
      const r = await api.upload('/api/extrusion/parse', form)
      setLines(r.lines)
      setParseInfo(r)
      setSource(r.source || {})
      const d = r.drawing || {}
      setHead((h) => ({ ...h, name: h.name || (d.title ? d.title.charAt(0) + d.title.slice(1).toLowerCase() : file.name.replace(/\.[^.]+$/, '')), part_number: h.part_number || d.part_number || '' }))
    } catch (e) { setErr(e.message); setParseInfo((p) => ({ ...(p || {}), refused: /export|distribution/i.test(e.message) })) }
    setBusy(false)
  }

  const setLine = (i, patch) => setLines((ls) => ls.map((l, j) => (j === i ? { ...l, ...patch } : l)))
  const removeLine = (i) => setLines((ls) => ls.filter((_, j) => j !== i))

  const row = est ? (est.price_breaks.find((b) => b.quantity === pick) || est.price_breaks[0]) : null
  const body = { lines, quantities, options: cleanOpts }
  const doSave = async () => {
    setMsg(''); setErr('')
    try {
      const q = await api.post('/api/extrusion/save', { ...body, ...head, source, opportunity_id: save.opportunity_id || null, status: save.status, notes: save.notes,
        quoted_quantity: row?.quantity ?? null, quoted_unit_price: row?.unit_price ?? null, quote_id: quoteId ? Number(quoteId) : null })
      setMsg(`Saved quote #${q.id}.`)
      if (!quoteId) onSaved(q.id)
    } catch (e) { setErr(e.message) }
  }
  const slug = (head.name || 'extrusion-build').replace(/[^A-Za-z0-9_-]+/g, '-').slice(0, 60)
  const sheet = (kind) => download(`/api/extrusion/${kind === 'cut' ? 'cutlist' : 'purchase'}.xlsx`, { ...body, builds: row?.quantity || quantities[0] || 1, title: head.name },
    `${slug}-${kind === 'cut' ? 'cut-list' : 'purchase-list'}.xlsx`).catch((e) => setErr(e.message))

  if (!cat) return <p className="muted">{err || 'Loading…'}</p>
  const unmatched = lines.filter((l) => l.kind === 'unmatched').length

  const dropzone = (
    <div className={`dropzone ${lines.length ? 'dz-sm' : ''} ${drag ? 'over' : ''}`} onClick={() => input.current.click()}
      onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
      onDrop={(e) => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files[0]) }}>
      <input ref={input} type="file" accept=".pdf,.csv,.xlsx,.xlsm,.tsv" hidden onChange={(e) => { upload(e.target.files[0]); e.target.value = '' }} />
      {busy ? <div className="big">Reading…</div>
        : lines.length ? <span className="small">Drop another drawing PDF or BOM spreadsheet to replace the lines</span>
          : <><div className="big">Drop a drawing PDF or BOM spreadsheet</div><p className="muted">A drawing with a BOM and cut list, or a CSV/XLSX with columns like Qty, Part, Description, Length, Machining.</p></>}
    </div>
  )

  return (
    <>
      <div className="panel">
        {dropzone}
        {err && <div className="err" style={{ marginTop: 10 }}>{err}</div>}
        {parseInfo?.refused && lastFile && (
          <div className="row" style={{ marginTop: 8 }}>
            <button onClick={() => { if (confirm('Send this marked drawing to Claude anyway? Only do this if you are sure you may share it with an outside service.')) upload(lastFile, true, true) }}>Send to Claude anyway</button>
          </div>
        )}
        {parseInfo && !parseInfo.refused && lastFile && /\.pdf$/i.test(lastFile.name) && !parseInfo.lines?.some((l) => l.kind !== 'unmatched') && cat.ai_configured && (
          <div className="row" style={{ marginTop: 8 }}>
            <button onClick={() => upload(lastFile, true)}>Read the BOM with Claude</button>
            <span className="small muted">Only for drawings you may share with an outside service. Export-controlled or limited-distribution drawings are refused.</span>
          </div>
        )}
        {parseInfo?.warnings?.length > 0 && <ul className="clean small" style={{ marginTop: 10 }}>{parseInfo.warnings.map((w, i) => <li key={i} className="due-soon">{w}</li>)}</ul>}
        <div className="row" style={{ marginTop: 10 }}>
          <button onClick={() => setLines((ls) => [...ls, blankLine()])}>+ Add line</button>
          {lines.length > 0 && <button className="link" onClick={() => { if (confirm('Clear every line?')) { setLines([]); setParseInfo(null) } }}>Clear lines</button>}
          <span className="small muted" style={{ marginLeft: 'auto' }}>{cat.note} <button className="link" onClick={() => setShowRates(!showRates)}>{showRates ? 'Hide' : 'Edit'} extrusion rates and prices</button></span>
        </div>
      </div>

      {showRates && <RatesPanel cat={cat} onSaved={() => { loadCatalog(); setMsg('Extrusion rates saved.') }} />}

      {lines.length > 0 && (
        <div className="panel">
          <div className="row spread"><h2 style={{ margin: 0 }}>Lines ({lines.length})</h2>{unmatched > 0 && <span className="small due-soon">{unmatched} unmatched: pick a catalog item or price them as custom</span>}</div>
          <div style={{ overflowX: 'auto' }}>
            <table className="small ex-lines">
              <thead><tr><th>Item</th><th>Qty</th><th>Type</th><th>Catalog item</th><th>Length / size (in)</th><th>Machining</th><th>Notes</th><th></th></tr></thead>
              <tbody>
                {lines.map((l, i) => <LineRow key={i} l={l} cat={cat} onChange={(p) => setLine(i, p)} onRemove={() => removeLine(i)} />)}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {lines.length > 0 && (
        <div className="builder iq">
          <div>
            <div className="panel">
              <h2>Build</h2>
              <div className="grid g2">
                <label className="f">Name<input value={head.name} onChange={(e) => setHead({ ...head, name: e.target.value })} /></label>
                <label className="f">Part / drawing number<input value={head.part_number} onChange={(e) => setHead({ ...head, part_number: e.target.value })} /></label>
                <label className="f">NSN<input value={head.nsn} onChange={(e) => setHead({ ...head, nsn: e.target.value })} /></label>
                <label className="f">Build quantities<input value={qtyText} onChange={(e) => setQtyText(e.target.value)} placeholder="1, 5, 10" /></label>
                <label className="f">Profile pricing<select value={opts.pricing_mode} onChange={(e) => setOpts({ ...opts, pricing_mode: e.target.value })}>
                  <option value="">Rates default ({cat.config.pricing_mode === 'stock' ? 'full sticks' : 'cut to length'})</option>
                  <option value="cut_to_length">Supplier cuts to length</option>
                  <option value="stock">Buy full sticks, cut in house</option>
                </select></label>
                <label className="f">Packaging<select value={opts.packaging_level} onChange={(e) => setOpts({ ...opts, packaging_level: e.target.value })}>{cat.packaging_levels.map((p) => <option key={p}>{p}</option>)}</select></label>
                <label className="f">Joints (blank = count brackets, plates, anchors)<input type="number" min="0" value={opts.joints} onChange={(e) => setOpts({ ...opts, joints: e.target.value })} /></label>
                <label className="f">Freight per lot $ (blank = default)<input type="number" min="0" value={opts.freight_per_lot} onChange={(e) => setOpts({ ...opts, freight_per_lot: e.target.value })} /></label>
              </div>
              <label className="check small" style={{ marginTop: 8, display: 'block' }}><input type="checkbox" checked={!!opts.first_article} onChange={(e) => setOpts({ ...opts, first_article: e.target.checked })} /> First article inspection</label>
            </div>
            {est && <Nesting est={est} />}
          </div>

          <div>
            <div className="panel price-panel">
              {!est || !row ? <p className="muted">{err ? '' : 'Pricing…'}</p> : (
                <>
                  <div className="small muted">T-slot build · {est.pricing_mode === 'stock' ? 'full sticks, cut in house' : 'cut to length by supplier'} · {est.counts.pieces} pieces · {est.part_weight_lb} lb of profile</div>
                  <div className="price-big">{usd(row.unit_price)}<span> / build</span></div>
                  <div className="row spread">
                    <div><b>{usd(row.total_price)}</b> for {row.quantity} · ships in about {row.lead_time_days} days</div>
                    <div className="small muted">margin {row.margin_pct}%</div>
                  </div>
                  <table style={{ marginTop: 12 }}>
                    <thead><tr><th>Builds</th><th>Price / build</th><th>Total</th><th>Lead</th></tr></thead>
                    <tbody>{est.price_breaks.map((b) => (
                      <tr key={b.quantity} className={`clickable ${b.quantity === row.quantity ? 'sel' : ''}`} onClick={() => setPick(b.quantity)}>
                        <td className="mono">{b.quantity}</td><td className="mono"><b>{usd(b.unit_price)}</b></td><td className="mono">{usd(b.total_price)}</td><td className="mono">{b.lead_time_days}d</td>
                      </tr>))}</tbody>
                  </table>
                  <ul className="clean small" style={{ marginTop: 10 }}>
                    {est.warnings.map((w, i) => <li key={`w${i}`} className="due-soon">{w}</li>)}
                    {est.assumptions.slice(0, showDetail ? 99 : 2).map((a, i) => <li key={`a${i}`}>{a}</li>)}
                  </ul>
                  <button className="link" onClick={() => setShowDetail(!showDetail)}>{showDetail ? 'Hide cost breakdown' : 'Show cost breakdown'}</button>
                  {showDetail && (
                    <>
                      <h3>Per build ({usd(est.per_part_cost)})</h3>
                      <CostLines lines={est.per_part_lines} />
                      <h3>Per lot ({usd(est.per_lot_cost)})</h3>
                      <CostLines lines={est.per_lot_lines} />
                      <p className="small muted">G&A {Math.round(est.ga_rate * 100)}% · profit {Math.round(est.profit_rate * 100)}%.</p>
                    </>
                  )}
                  <div className="row" style={{ marginTop: 10 }}>
                    <button onClick={() => sheet('cut')}>Download cut list</button>
                    <button onClick={() => sheet('purchase')}>Download purchase list</button>
                    <span className="small muted">for {row.quantity} build(s)</span>
                  </div>
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
                      {opps.map((o) => <option key={o.id} value={o.id}>{o.solicitation_number ? `${o.solicitation_number}: ` : ''}{(o.title || '').slice(0, 80)}</option>)}
                    </select>
                  </label>
                  <label className="f">Status<select value={save.status} onChange={(e) => setSave({ ...save, status: e.target.value })}>{meta.statuses.map((s) => <option key={s}>{s}</option>)}</select></label>
                  <label className="f">Quoting quantity<select value={row.quantity} onChange={(e) => setPick(Number(e.target.value))}>{est.price_breaks.map((b) => <option key={b.quantity} value={b.quantity}>{b.quantity} at {usd(b.unit_price)}</option>)}</select></label>
                  <label className="f" style={{ gridColumn: 'span 2' }}>Notes<textarea value={save.notes} onChange={(e) => setSave({ ...save, notes: e.target.value })} style={{ minHeight: 50 }} placeholder="Drawing rev, distributor quote numbers, assumptions" /></label>
                </div>
                <div className="row" style={{ marginTop: 10 }}>
                  <button className="primary" onClick={doSave}>{quoteId ? 'Update quote' : 'Save quote'}</button>
                  {msg && <span className="small okline">{msg}</span>}
                  {save.opportunity_id && <Link className="small" to={`/opportunities/${save.opportunity_id}`}>Open opportunity</Link>}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  )
}

// ------------------------------------------------------------ one editable BOM line
function LineRow({ l, cat, onChange, onRemove }) {
  const items = l.kind === 'profile' ? cat.profiles : l.kind === 'hardware' ? cat.hardware : l.kind === 'panel' ? cat.panels : []
  const listId = `ex-cat-${l.kind}`
  const current = items.find((x) => x.id === l.catalog_id)
  const [text, setText] = useState(l.catalog_id)
  const [lenText, setLenText] = useState(fmtLen(l.length_in))
  useEffect(() => setText(l.catalog_id), [l.catalog_id])
  useEffect(() => setLenText(fmtLen(l.length_in)), [l.length_in])
  const pickItem = (v) => {
    setText(v)
    const id = v.split('  ')[0].trim()
    if (items.some((x) => x.id === id)) onChange({ catalog_id: id, confidence: 1 })
  }
  const opsUsed = new Set(l.machining.map((o) => o.op))
  const cls = l.kind === 'unmatched' ? 'ex-unmatched' : l.confidence < 0.7 ? 'ex-low' : ''
  return (
    <tr className={cls}>
      <td><input value={l.item} onChange={(e) => onChange({ item: e.target.value })} style={{ width: 46 }} /></td>
      <td><input type="number" min="0" value={l.qty} onChange={(e) => onChange({ qty: e.target.value === '' ? '' : Number(e.target.value) })} style={{ width: 54 }} /></td>
      <td><select value={l.kind} onChange={(e) => onChange({ kind: e.target.value, catalog_id: '' })}>{KINDS.map(([k, n]) => <option key={k} value={k}>{n}</option>)}</select></td>
      <td style={{ minWidth: 220 }}>
        {items.length > 0 ? (
          <>
            <input list={listId} value={text} onChange={(e) => pickItem(e.target.value)} placeholder="search catalog" style={{ width: '100%' }} />
            <datalist id={listId}>{items.map((x) => <option key={x.id} value={`${x.id}  ${x.name}`} />)}</datalist>
            {current ? <div className="muted">{current.name}</div> : l.catalog_id ? <div className="due-soon">not in catalog</div> : null}
          </>
        ) : (
          <input type="number" min="0" step="0.01" value={l.unit_price ?? ''} placeholder="unit price $" onChange={(e) => onChange({ unit_price: e.target.value === '' ? null : Number(e.target.value), kind: e.target.value === '' ? l.kind : 'custom' })} style={{ width: 110 }} />
        )}
        <div className="muted" title={l.raw}>{[l.part_number, l.description].filter(Boolean).join(' · ').slice(0, 70)}</div>
      </td>
      <td>
        {l.kind === 'profile' && <>
          <input value={lenText} onChange={(e) => setLenText(e.target.value)} onBlur={() => { const v = parseLen(lenText); onChange({ length_in: v }); setLenText(fmtLen(v)) }} placeholder='24 or 610 mm' style={{ width: 90 }} />
          {l.length_in ? <div className="muted mono">{(l.length_in * 25.4).toFixed(1)} mm</div> : <div className="due-soon">no length</div>}
        </>}
        {l.kind === 'panel' && <span className="row" style={{ gap: 4, flexWrap: 'nowrap' }}>
          <input type="number" min="0" value={l.width_in ?? ''} onChange={(e) => onChange({ width_in: e.target.value === '' ? null : Number(e.target.value) })} style={{ width: 60 }} />×
          <input type="number" min="0" value={l.height_in ?? ''} onChange={(e) => onChange({ height_in: e.target.value === '' ? null : Number(e.target.value) })} style={{ width: 60 }} />
        </span>}
      </td>
      <td style={{ minWidth: 170 }}>
        {l.kind === 'profile' && <>
          {l.machining.map((o, k) => (
            <span key={o.op} className="chip on" style={{ marginRight: 4, display: 'inline-flex', gap: 4, alignItems: 'center' }}>
              {cat.machining.find((m) => m.id === o.op)?.name || o.op} ×
              <input type="number" min="1" value={o.count} style={{ width: 54 }} onChange={(e) => onChange({ machining: l.machining.map((x, j) => (j === k ? { ...x, count: Number(e.target.value) || 1 } : x)) })} />
              <button className="link" title="remove" onClick={() => onChange({ machining: l.machining.filter((_, j) => j !== k) })}>×</button>
            </span>
          ))}
          <select value="" onChange={(e) => e.target.value && onChange({ machining: [...l.machining, { op: e.target.value, count: 1 }] })}>
            <option value="">+ op</option>
            {cat.machining.filter((m) => !opsUsed.has(m.id)).map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
        </>}
      </td>
      <td><input value={l.notes || ''} onChange={(e) => onChange({ notes: e.target.value })} style={{ width: 140 }} /></td>
      <td><button className="link" onClick={onRemove} title="Remove line">remove</button></td>
    </tr>
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
  const profs = Object.entries(est.nesting.profiles)
  if (!profs.length) return null
  return (
    <div className="panel">
      <h2>Stock nesting ({est.nesting.quantity} build{est.nesting.quantity > 1 ? 's' : ''})</h2>
      <table className="small">
        <thead><tr><th>Profile</th><th>Sticks</th><th>Stick length</th><th>Used</th><th>Drop + kerf</th><th>Waste</th></tr></thead>
        <tbody>{profs.map(([pid, n]) => (
          <tr key={pid}>
            <td className="mono">{pid}</td><td className="mono">{n.sticks}{n.oversize.length ? ` + ${n.oversize.length} special` : ''}</td>
            <td className="mono">{n.stock_length_in} in</td><td className="mono">{n.used_in} in</td><td className="mono">{n.waste_in} in</td><td className="mono">{n.waste_pct}%</td>
          </tr>))}</tbody>
      </table>
      <p className="small muted">First-fit decreasing with kerf and end trim from your extrusion rates. {est.pricing_mode === 'stock' ? 'Material is priced on these sticks.' : 'Shown for reference: material is priced cut to length.'}</p>
      {Object.keys(est.nesting_by_quantity).length > 1 && (
        <p className="small muted">Sticks by lot size: {Object.entries(est.nesting_by_quantity).map(([q, m]) => `${q} build(s): ${Object.values(m).reduce((a, x) => a + x.sticks, 0)}`).join(' · ')}</p>
      )}
    </div>
  )
}

// ------------------------------------------------------------ rates and placeholder prices
function RatesPanel({ cat, onSaved }) {
  const [d, setD] = useState(() => structuredClone(cat.config))
  const [fam, setFam] = useState('15')
  const [err, setErr] = useState('')
  const set = (path, v) => setD((old) => {
    const out = structuredClone(old)
    let cur = out
    path.slice(0, -1).forEach((k) => { cur = cur[k] })
    cur[path.at(-1)] = v
    return out
  })
  const num = (path, step = '0.01') => {
    const v = path.reduce((a, k) => a?.[k], d)
    return <input type="number" step={step} min="0" value={v ?? ''} onChange={(e) => set(path, e.target.value === '' ? '' : Number(e.target.value))} style={{ width: 80 }} />
  }
  const saveRates = async () => {
    setErr('')
    try { await api.put('/api/pricing/config', { changes: { extrusion: d } }); onSaved() } catch (e) { setErr(e.message) }
  }
  const labels = { per_build: 'Base per build', per_joint: 'Per joint', per_fastener: 'Per T-nut / retainer', per_panel: 'Per panel', per_accessory: 'Per foot, caster, hinge, handle, end cap' }
  return (
    <div className="panel">
      <div className="notice">{d.note} These settings are saved with your shop rates.</div>
      {err && <div className="err">{err}</div>}
      <div className="grid g3">
        <div>
          <h3>Cutting and stock</h3>
          <table className="small"><tbody>
            <tr><td>Default pricing</td><td><select value={d.pricing_mode} onChange={(e) => set(['pricing_mode'], e.target.value)}><option value="cut_to_length">cut to length</option><option value="stock">full sticks</option></select></td></tr>
            <tr><td>Stick length, fractional (in)</td><td>{num(['stock_length_in', 'fractional'])}</td></tr>
            <tr><td>Stick length, metric (in)</td><td>{num(['stock_length_in', 'metric'])}</td></tr>
            <tr><td>Stick price factor (x $/in)</td><td>{num(['full_stick_price_factor'])}</td></tr>
            <tr><td>Kerf (in)</td><td>{num(['kerf_in'], '0.001')}</td></tr>
            <tr><td>End trim per stick (in)</td><td>{num(['end_trim_in'])}</td></tr>
            <tr><td>Supplier cut charge $/cut</td><td>{num(['cut_charge'])}</td></tr>
            <tr><td>In-house saw minutes/piece</td><td>{num(['inhouse_cut_minutes'])}</td></tr>
          </tbody></table>
          <h3>Machining $/operation</h3>
          <table className="small"><tbody>{cat.machining.map((m) => <tr key={m.id}><td>{m.name}</td><td>{num(['machining', m.id])}</td></tr>)}</tbody></table>
        </div>
        <div>
          <h3>Assembly minutes</h3>
          <table className="small"><tbody>{Object.keys(d.assembly_minutes).map((k) => <tr key={k}><td>{labels[k] || k}</td><td>{num(['assembly_minutes', k], '0.1')}</td></tr>)}</tbody></table>
          <h3>Per build and per lot</h3>
          <table className="small"><tbody>
            <tr><td>Inspection minutes per build</td><td>{num(['inspection_minutes_per_build'], '0.1')}</td></tr>
            <tr><td>Crate $ per build</td><td>{num(['crate_per_build'])}</td></tr>
            <tr><td>Panel waste factor</td><td>{num(['panel_waste_factor'])}</td></tr>
            <tr><td>Kitting hours per lot</td><td>{num(['kitting_hours_per_lot'])}</td></tr>
            <tr><td>Supplier order charge $ per lot</td><td>{num(['supplier_order_charge'])}</td></tr>
            <tr><td>Supplier lead days</td><td>{num(['supplier_lead_days'], '1')}</td></tr>
            <tr><td>Builds per day</td><td>{num(['builds_per_day'], '1')}</td></tr>
          </tbody></table>
          <p className="small muted">Labor uses the assembly, fabrication and inspection rates; G&A, profit, packaging and freight come from the Shop rates tab.</p>
        </div>
        <div>
          <h3>Profiles $/inch</h3>
          <div style={{ maxHeight: 260, overflowY: 'auto' }}>
            <table className="small"><tbody>{cat.profiles.map((p) => <tr key={p.id}><td className="mono">{p.id}</td><td className="muted">{p.size}</td><td>{num(['prices', 'profiles', p.id], '0.001')}</td></tr>)}</tbody></table>
          </div>
          <h3>Panels $/sq ft</h3>
          <table className="small"><tbody>{cat.panels.map((p) => <tr key={p.id}><td>{p.name}</td><td>{num(['prices', 'panels', p.id])}</td></tr>)}</tbody></table>
        </div>
      </div>
      <h3>Hardware $/each</h3>
      <div className="row" style={{ gap: 6, marginBottom: 6 }}>{Object.entries(cat.families).map(([k, v]) => <button key={k} className={`chip ${fam === k ? 'on' : ''}`} onClick={() => setFam(k)}>{v.split(' (')[0]}</button>)}</div>
      <div className="grid g3">{cat.hardware.filter((h) => h.family === fam).map((h) => (
        <label key={h.id} className="row small" style={{ justifyContent: 'space-between' }}>{h.name.split(', ').slice(0, -1).join(', ') || h.name}{num(['prices', 'hardware', h.id])}</label>
      ))}</div>
      <div className="row" style={{ marginTop: 12 }}>
        <button className="primary" onClick={saveRates}>Save extrusion rates</button>
        <button onClick={() => setD(structuredClone(cat.config))}>Undo changes</button>
      </div>
    </div>
  )
}
