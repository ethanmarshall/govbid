import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { Dropzone, HeadFields, LotOptions, PriceCard, PriceSource, RatesPanel, SavePanel, fetchLive, numOrNull, usd, useQuotePage } from './HarnessQuote'

// Custom electromechanical assemblies: enclosure, PCBs, wiring, panel parts, peripherals and linked quotes, priced as one unit.

const blankLine = () => ({ ref: '', type: '', part_number: '', manufacturer: '', description: '', qty: 1, unit_price: null, price_source: '', distributor: '', terminations: null, method: '', mount: 'panel', customer_furnished: false })
const blankPeripheral = () => ({ description: '', part_number: '', manufacturer: '', qty: 1, unit_price: null, price_source: '', distributor: '', installed: true, minutes: null, customer_furnished: false })
const blankPcb = (n) => ({ name: `PCB assembly ${n}`, qty_per: 1, mode: 'estimate', layers: 2, width_in: null, height_in: null, thickness_in: 0.062, finish: 'HASL lead-free', copper_oz: 1, ipc_class: 2,
  impedance: false, via_in_pad: false, blind_buried: false, fab_price_each: null, smt_placements: 0, smt_unique: 0, fine_pitch: 0, bga: 0, tht_parts: 0, tht_joints: 0, sides: 1, aoi: true,
  conformal: false, conformal_masks: 0, flying_probe: false, program_minutes: 0, test_minutes: 0, bom_lines: [], bom_cost_each: null, consigned: false, buy_prices: [], buy_nre: 0, buy_lead_days: null,
  cable_mates: 0, wire_connections: 0, source: {} })
const blankEnclosure = { source: 'catalog', type: 'diecast_aluminum', length_in: null, width_in: null, height_in: null, unit_price: null, part_number: '', manufacturer: '', description: '', price_source: '', distributor: '',
  finish: 'none', silkscreen_colors: 0, silkscreen_sides: 1, mods: { auto_cutouts: true }, child: null }
const SECTION_NAMES = { enclosure: 'Enclosure', pcbs: 'Circuit boards', components: 'Panel and internal parts', peripherals: 'Peripherals', wiring: 'Wiring and harnesses', linked: 'Linked parts',
  integration: 'Integration', test: 'Test and inspection', nre: 'NRE', material: 'Material burden', shipping: 'Packaging and freight' }
const KIND_NAMES = { harness: 'Harness', panel: 'Control panel', labels: 'Labels', flat_dxf: 'DXF part', extrusion_build: 'Extrusion frame', assembly: 'STEP assembly', box_build: 'Box build', part: 'Part', drawing: 'Part (drawing)' }

const parseBreaks = (t) => String(t || '').split(/[,;\n]+/).map((x) => x.trim()).filter(Boolean).map((x) => {
  const m = x.match(/^(\d+)\s*[:@=x]?\s*\$?\s*([\d.]+)$/i)
  return m ? { quantity: Number(m[1]), unit_price: Number(m[2]) } : null
}).filter(Boolean)
const breaksText = (b) => (b || []).map((x) => `${x.quantity}: ${x.unit_price}`).join(', ')

function Num({ label, value, onChange, step = 'any', placeholder, width }) {
  return <label className="f" style={width ? { width } : undefined}>{label}<input type="number" min="0" step={step} value={value ?? ''} placeholder={placeholder} onChange={(e) => onChange(numOrNull(e.target.value))} /></label>
}
function Check({ label, checked, onChange, title }) {
  return <label className="check small" title={title}><input type="checkbox" checked={!!checked} onChange={(e) => onChange(e.target.checked)} /> {label}</label>
}

export default function BoxBuildQuote({ meta, quoteId, oppId, onSaved }) {
  const [enclosure, setEnclosure] = useState(blankEnclosure)
  const [pcbs, setPcbs] = useState([])
  const [lines, setLines] = useState([])
  const [peripherals, setPeripherals] = useState([])
  const [children, setChildren] = useState([])
  const [wiring, setWiring] = useState({ mark_wires: true })
  const [labor, setLabor] = useState({ ipc_class: 2, serialize: true, nre_in_price: true, lab_tests: [] })
  const [opts, setOpts] = useState({ packaging_level: 'commercial', first_article: false, crate: false })
  const [busy, setBusy] = useState(false)
  const [parseInfo, setParseInfo] = useState(null)
  const [live, setLive] = useState('')
  const [showRates, setShowRates] = useState(false)
  const [picker, setPicker] = useState(null) // 'child' | 'enclosure'
  const started = enclosure.source !== 'catalog' || enclosure.length_in || pcbs.length || lines.length || peripherals.length || children.length || !!quoteId

  const payload = useMemo(() => ({ enclosure, pcbs, lines, peripherals, children, wiring, labor, options: Object.fromEntries(Object.entries(opts).filter(([, v]) => v !== '' && v != null)) }),
    [enclosure, pcbs, lines, peripherals, children, wiring, labor, opts])
  const ready = !!(lines.length || pcbs.length || peripherals.length || children.length || ['custom', 'catalog'].includes(enclosure.source) && (enclosure.length_in || enclosure.unit_price != null || enclosure.child))
  const p = useQuotePage({ kind: 'box_build', apiBase: '/api/box-build', catalogUrl: '/api/box-build/catalog', ready, quoteId, oppId, onSaved, payload, defaultName: 'box-build',
    restore: (s) => {
      setEnclosure({ ...blankEnclosure, ...(s.enclosure || {}), mods: { auto_cutouts: true, ...(s.enclosure?.mods || {}) } })
      setPcbs(s.pcbs || []); setLines(s.lines || []); setPeripherals(s.peripherals || []); setChildren(s.children || [])
      setWiring({ mark_wires: true, ...(s.wiring || {}) }); setLabor((l) => ({ ...l, ...(s.labor || {}) })); setOpts((o) => ({ ...o, ...(s.options || {}) }))
    } })

  useEffect(() => { // opened from an assembly drawing: start from what was read on it
    if (quoteId) return
    let pre = null
    try { pre = JSON.parse(sessionStorage.getItem('govbid:box-prefill') || 'null'); sessionStorage.removeItem('govbid:box-prefill') } catch {}
    if (!pre) return
    setEnclosure({ ...blankEnclosure, ...(pre.enclosure || {}), mods: { auto_cutouts: true, ...(pre.enclosure?.mods || {}) } })
    setPcbs(pre.pcbs || []); setLines(pre.lines || []); setPeripherals(pre.peripherals || []); setChildren(pre.children || [])
    setWiring((w) => ({ ...w, ...(pre.wiring || {}) })); setLabor((l) => ({ ...l, ...(pre.labor || {}) })); setOpts((o) => ({ ...o, ...(pre.options || {}) }))
    p.setHead((h) => ({ ...h, name: pre.name || h.name, part_number: pre.part_number || h.part_number }))
    setParseInfo({ warnings: pre.assumptions || [], evidence: pre.evidence || [], fromDrawing: true })
  }, [quoteId])

  const uploadBom = async (file) => {
    if (!file) return
    setBusy(true); p.setErr(''); p.setMsg('')
    const form = new FormData()
    form.append('file', file)
    try {
      const r = await api.upload('/api/box-build/parse', form)
      if (r.enclosure) setEnclosure((e) => ({ ...e, ...r.enclosure, mods: e.mods }))
      setPcbs((b) => [...b, ...r.pcbs])
      setLines((l) => [...l, ...r.lines])
      setPeripherals((x) => [...x, ...r.peripherals])
      setParseInfo(r)
      p.setSource(r.source || {})
      const d = r.drawing || {}
      p.setHead((h) => ({ ...h, name: h.name || (d.title ? d.title.charAt(0) + d.title.slice(1).toLowerCase() : file.name.replace(/\.[^.]+$/, '')), part_number: h.part_number || d.drawing_number || d.part_number || '' }))
    } catch (e) { p.setErr(e.message) }
    setBusy(false)
  }

  const getLive = async () => {
    const builds = p.row?.quantity || 1
    setLive('Fetching live prices…')
    const a = await fetchLive(lines.filter((l) => !l.customer_furnished), (l) => l.part_number, (l) => l.qty * builds, p.quantities)
    const b = await fetchLive(peripherals.filter((x) => !x.customer_furnished), (x) => x.part_number, (x) => x.qty * builds, p.quantities)
    let ai = 0, bi = 0
    setLines((ls) => ls.map((l) => (l.customer_furnished ? l : a.lines[ai++])))
    setPeripherals((ps) => ps.map((x) => (x.customer_furnished ? x : b.lines[bi++])))
    setLive(`Parts: ${a.message} Peripherals: ${b.message}`)
  }

  if (!p.cat) return <p className="muted">{p.err || 'Loading…'}</p>
  const cat = p.cat
  const bd = p.est && p.row ? p.est.breakdowns[String(p.row.quantity)] : null
  const est = p.est && bd ? { ...p.est, ...bd } : null
  const c = p.est?.counts

  return (
    <>
      <div className="panel">
        <Dropzone busy={busy} compact={started} accept=".pdf,.csv,.xlsx,.xlsm,.tsv" onFile={uploadBom}
          title="Drop an assembly BOM or a drawing with a parts list"
          smallText="Drop another assembly BOM to add its lines"
          hint="CSV, XLSX or PDF with Part number or Description and Qty columns. Lines are sorted into enclosure, circuit boards, panel parts and peripherals. Or start empty with the buttons below." />
        {p.err && <div className="err" style={{ marginTop: 10 }}>{p.err}</div>}
        {parseInfo?.fromDrawing && <p className="small" style={{ marginTop: 10 }}><b>Started from the assembly drawing.</b> Check each section against the drawing: the values below were read from its notes and dimensions.</p>}
        {parseInfo?.warnings?.length > 0 && <ul className="clean small" style={{ marginTop: 10 }}>{parseInfo.warnings.map((w, i) => <li key={i} className="due-soon">{w}</li>)}</ul>}
        {parseInfo?.evidence?.length > 0 && <details className="small muted" style={{ marginTop: 6 }}><summary>What was read from the drawing ({parseInfo.evidence.length})</summary><ul className="clean">{parseInfo.evidence.map((x, i) => <li key={i}>{x}</li>)}</ul></details>}
        <div className="row" style={{ marginTop: 10, flexWrap: 'wrap' }}>
          <button onClick={() => setPcbs((b) => [...b, blankPcb(b.length + 1)])}>+ Circuit board</button>
          <button onClick={() => setLines((l) => [...l, blankLine()])}>+ Part</button>
          <button onClick={() => setPeripherals((x) => [...x, blankPeripheral()])}>+ Peripheral</button>
          <button onClick={() => setPicker('child')}>Link a saved quote</button>
          {started && <button className="link" onClick={() => { if (confirm('Clear the whole build?')) { setEnclosure(blankEnclosure); setPcbs([]); setLines([]); setPeripherals([]); setChildren([]); setParseInfo(null) } }}>Clear</button>}
          <span className="small muted" style={{ marginLeft: 'auto' }}>{cat.config.note} <button className="link" onClick={() => setShowRates(!showRates)}>{showRates ? 'Hide' : 'Edit'} box build rates</button></span>
        </div>
      </div>

      {showRates && <RatesPanel cfgKey="box_build" config={cat.config} title="box build" onSaved={() => { p.loadCatalog(); setShowRates(false); p.setMsg('Box build rates saved.') }}
        labels={{ enclosures: 'Catalog enclosures (base $ + $/in³)', enclosure_mods: 'Enclosure modifications (minutes, $)', pcb_fab: 'Bare board fab', pcba: 'Board assembly', components: 'Parts by type (price, mount min, terminations, mates)',
          termination_minutes: 'Minutes per termination', lab_tests: 'Outside lab tests (per lot)', nre: 'NRE hours' }} />}

      {picker && <LinkPicker exclude={quoteId} onClose={() => setPicker(null)} onPick={(l) => {
        const item = { quote_id: l.quote_id, name: l.name, kind: l.kind, qty_per: 1, mode: 'make', buy_unit_price: null, buy_lead_days: null, spec: l.spec }
        if (picker === 'enclosure') setEnclosure((e) => ({ ...e, source: 'custom', child: item }))
        else setChildren((cs) => [...cs, item])
        setPicker(null)
      }} />}

      <div className="builder iq">
        <div>
          <div className="panel">
            <h2>Assembly</h2>
            <HeadFields p={p} unitLabel="Unit">
              <LotOptions opts={opts} setOpts={setOpts} packaging={cat.packaging_levels} />
              <Check label="Crate or shipping case per unit" checked={opts.crate} onChange={(v) => setOpts({ ...opts, crate: v })} />
            </HeadFields>
          </div>

          <EnclosurePanel cat={cat} e={enclosure} setE={setEnclosure} auto={p.est?.auto_cutouts} onLink={() => setPicker('enclosure')} />

          <div className="panel">
            <div className="row spread"><h2 style={{ margin: 0 }}>Circuit boards ({pcbs.length})</h2><button onClick={() => setPcbs((b) => [...b, blankPcb(b.length + 1)])}>+ Circuit board</button></div>
            {!pcbs.length && <p className="small muted">Add a board and drop its Gerbers (or the fab zip), pick-and-place file and BOM. Layers, size, placements and parts are read from the files.</p>}
            {pcbs.map((b, i) => (
              <BoardCard key={i} b={b} cat={cat} quantities={p.quantities} build={p.row?.quantity || 1}
                set={(patch) => setPcbs((bs) => bs.map((x, j) => (j === i ? { ...x, ...patch } : x)))}
                remove={() => setPcbs((bs) => bs.filter((_, j) => j !== i))} onError={p.setErr} />
            ))}
          </div>

          <div className="panel">
            <div className="row spread">
              <h2 style={{ margin: 0 }}>Panel and internal parts ({lines.length})</h2>
              <span className="row"><button onClick={() => setLines((l) => [...l, blankLine()])}>+ Part</button>{(lines.length > 0 || peripherals.length > 0) && <button onClick={getLive}>Fetch live prices</button>}</span>
            </div>
            {live && <p className="small muted">{live}</p>}
            {!lines.length && <p className="small muted">Switches, connectors, indicators, displays, power supplies, fans, relays, hardware. Leave Type on Auto to have it guessed from the description.</p>}
            {lines.length > 0 && <PartsTable cat={cat} lines={lines} setLines={setLines} />}
          </div>

          <div className="panel">
            <div className="row spread"><h2 style={{ margin: 0 }}>Peripherals ({peripherals.length})</h2><button onClick={() => setPeripherals((x) => [...x, blankPeripheral()])}>+ Peripheral</button></div>
            {!peripherals.length && <p className="small muted">Bought items installed in the unit or packed with it: computers, cameras, keyboards, cables, power adapters, manuals.</p>}
            {peripherals.length > 0 && <PeripheralsTable list={peripherals} setList={setPeripherals} cat={cat} />}
          </div>

          <div className="panel">
            <h2>Wiring</h2>
            <div className="grid g3">
              <Num label="Point-to-point wires (blank = estimate)" value={wiring.wires} placeholder={c ? String(c.wires) : ''} onChange={(v) => setWiring({ ...wiring, wires: v })} />
              <Num label="Average wire length (in)" value={wiring.avg_length_in} placeholder={String(cat.config.wiring.default_length_in)} onChange={(v) => setWiring({ ...wiring, avg_length_in: v })} />
              <Num label="Cable mates (blank = estimate)" value={wiring.mates} placeholder={c ? String(c.mates) : ''} onChange={(v) => setWiring({ ...wiring, mates: v })} />
            </div>
            <Check label="Mark wires (two markers per wire)" checked={wiring.mark_wires} onChange={(v) => setWiring({ ...wiring, mark_wires: v })} />
            {c && <p className="small muted" style={{ marginBottom: 0 }}><b>{c.wires}</b> wires: {c.wire_basis}. Terminations at parts: {Object.entries(c.terminations).map(([k, v]) => `${v} ${k.replace('_', ' ')}`).join(', ') || 'none'}.</p>}
            <p className="small muted">For a real harness, quote it on the Cable harness tab, save it, and link it below.</p>
          </div>

          <div className="panel">
            <div className="row spread"><h2 style={{ margin: 0 }}>Linked quotes ({children.length})</h2><button onClick={() => setPicker('child')}>Link a saved quote</button></div>
            <p className="small muted">Any saved quote (harness, control panel, labels, machined or sheet metal part, DXF part, extrusion frame, STEP assembly, another box build) at a quantity per unit. Made items roll in at your cost; bought items at the vendor price plus burden. A link is a copy: relink after you change the original.</p>
            {children.length > 0 && <ChildrenTable list={children} setList={setChildren} />}
          </div>

          <TestPanel cat={cat} labor={labor} setLabor={setLabor} counts={c} />
        </div>

        <div>
          {p.est?.incomplete?.length > 0 && (
            <div className="panel asm-notice">
              <h2>Not ready to quote: {p.est.incomplete.length} item(s) need you</h2>
              <p className="small muted">The quote tool was not sure of these. Price them by hand (or quote them and link the quote) and check them against the drawing. The price below leaves them out, and a customer quote is blocked until they are done.</p>
              <ul className="clean small">
                {p.est.incomplete.map((it, i) => (
                  <li key={i}><b>{it.item.slice(0, 70)}</b>: {it.reason}{' '}
                    {/mark it checked/i.test(it.reason) && <button className="link" onClick={() => {
                      if (it.where === 'enclosure') setEnclosure((e) => ({ ...e, check: '' }))
                      if (it.where === 'pcbs') setPcbs((bs) => bs.map((b, j) => (j === it.index ? { ...b, check: '' } : b)))
                      if (it.where === 'lines') setLines((ls) => ls.map((l, j) => (j === it.index ? { ...l, check: '' } : l)))
                    }}>Mark checked</button>}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {est && p.row ? (
            <PriceCard est={est} row={p.row} setPick={p.setPick} unitWord="unit"
              summary={`${p.est.incomplete?.length ? 'PARTIAL PRICE, not a quote yet · ' : ''}Box build · ${pcbs.length} board design(s) · ${lines.length} parts · ${children.length} linked · breakdown at qty ${p.row.quantity}`}>
              <Sections sections={bd.sections} total={p.row.unit_cost} />
              {p.est.nre_total > 0 && <p className="small muted">NRE ${p.est.nre_total.toLocaleString()} {labor.nre_in_price ? 'is spread over each lot' : 'is left out; quote it separately'}. About {p.est.labor_hours_per_unit} labor hours per unit.</p>}
              <div className="row" style={{ marginTop: 10 }}>
                <button onClick={p.sheet}>Download purchase list</button>
                <span className="small muted">for {p.row.quantity} unit(s)</span>
              </div>
            </PriceCard>
          ) : <div className="panel"><p className="muted">{ready ? (p.err ? '' : 'Pricing…') : 'Add an enclosure size, a board, a part or a linked quote to see a price.'}</p></div>}
          {est && p.row && <SavePanel meta={meta} est={est} row={p.row} setPick={p.setPick} save={p.save} setSave={p.setSave} opps={p.opps} quoteId={quoteId} onSave={p.doSave} msg={p.msg} />}
        </div>
      </div>
    </>
  )
}

function Sections({ sections, total }) {
  const rows = Object.entries(sections).filter(([, v]) => v > 0.005).sort((a, b) => b[1] - a[1])
  const max = Math.max(...rows.map(([, v]) => v), 1)
  return (
    <div style={{ marginTop: 12 }}>
      <h3 style={{ marginBottom: 6 }}>Cost per unit by section</h3>
      <table className="small"><tbody>
        {rows.map(([k, v]) => (
          <tr key={k}>
            <td style={{ width: '42%' }}>{SECTION_NAMES[k] || k}<div className="bar"><span style={{ width: `${(v / max) * 100}%` }} /></div></td>
            <td className="mono" style={{ textAlign: 'right' }}>{usd(v)}</td>
            <td className="mono muted" style={{ textAlign: 'right', width: 50 }}>{total ? Math.round((v / total) * 100) : 0}%</td>
          </tr>
        ))}
      </tbody></table>
    </div>
  )
}

function EnclosurePanel({ cat, e, setE, auto, onLink }) {
  const set = (patch) => setE({ ...e, ...patch })
  const mod = (k, v) => setE({ ...e, mods: { ...e.mods, [k]: v } })
  const SRC = [['catalog', 'Catalog box'], ['custom', 'Custom (linked quote)'], ['customer', 'Customer furnished'], ['none', 'None']]
  return (
    <div className="panel">
      <h2>Enclosure</h2>
      <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
        {SRC.map(([k, label]) => <button key={k} className={`chip ${e.source === k ? 'on' : ''}`} onClick={() => set({ source: k })}>{label}</button>)}
      </div>
      {e.source === 'catalog' && (
        <div className="grid g3" style={{ marginTop: 10 }}>
          <label className="f">Type<select value={e.type} onChange={(x) => set({ type: x.target.value })}>{Object.entries(cat.enclosures).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
          <label className="f">Part number<input value={e.part_number} onChange={(x) => set({ part_number: x.target.value })} /></label>
          <label className="f">Unit price $ (blank = placeholder)<input type="number" min="0" step="0.01" value={e.unit_price ?? ''} onChange={(x) => set({ unit_price: numOrNull(x.target.value), price_source: x.target.value === '' ? '' : 'manual' })} /></label>
          <Num label="Length (in)" value={e.length_in} onChange={(v) => set({ length_in: v })} />
          <Num label="Width (in)" value={e.width_in} onChange={(v) => set({ width_in: v })} />
          <Num label="Height (in)" value={e.height_in} onChange={(v) => set({ height_in: v })} />
        </div>
      )}
      {e.source === 'custom' && (
        <div style={{ marginTop: 10 }}>
          {e.child ? (
            <div className="opcard">
              <div className="row spread"><b>{e.child.name}</b><span className="small muted">{KIND_NAMES[e.child.kind] || e.child.kind}{e.child.quote_id ? <> · <Link to={`/part-quotes?tab=saved`}>quote #{e.child.quote_id}</Link></> : ''}</span></div>
              <div className="row" style={{ gap: 8, marginTop: 6, flexWrap: 'wrap' }}>
                <button className={`chip ${e.child.mode === 'make' ? 'on' : ''}`} onClick={() => set({ child: { ...e.child, mode: 'make' } })}>Make (your cost)</button>
                <button className={`chip ${e.child.mode === 'buy' ? 'on' : ''}`} onClick={() => set({ child: { ...e.child, mode: 'buy' } })}>Buy</button>
                {e.child.mode === 'buy' && <input type="number" min="0" step="0.01" placeholder="vendor $ each" value={e.child.buy_unit_price ?? ''} onChange={(x) => set({ child: { ...e.child, buy_unit_price: numOrNull(x.target.value) } })} style={{ width: 120 }} />}
                <button className="link" onClick={onLink}>Link a different quote</button>
              </div>
            </div>
          ) : (
            <>
              {e.description && <p className="small"><b>{e.description}</b></p>}
              <p className="small">Quote the enclosure (Instant quote from its STEP file, DXF flat parts, or Extrusion builds), save it, then <button className="link" onClick={onLink}>link it here</button>. Or enter your price for it:</p>
              <div className="grid g3"><label className="f">Your price each ${e.unit_price == null && <span className="tag due-soon" style={{ marginLeft: 4 }}>needs manual price</span>}
                <input type="number" min="0" step="0.01" value={e.unit_price ?? ''} onChange={(x) => set({ unit_price: numOrNull(x.target.value), price_source: x.target.value === '' ? '' : 'manual' })} /></label></div>
            </>
          )}
        </div>
      )}
      {e.check && <p className="small due-soon" style={{ marginTop: 8 }}>{e.check} <button className="link" onClick={() => set({ check: '' })}>Mark checked</button></p>}
      {['catalog', 'custom', 'customer'].includes(e.source) && (
        <>
          <h3>Modifications</h3>
          <div className="grid g3">
            {[['round_holes', 'Round holes'], ['connector_cutouts', 'Connector cutouts'], ['rect_cutouts', 'Rectangular cutouts'], ['display_windows', 'Display windows'], ['vent_patterns', 'Vent or fan patterns'], ['pem_inserts', 'PEM inserts']].map(([k, label]) => (
              <Num key={k} label={label} value={e.mods[k] || null} placeholder={auto?.[k] ? String(auto[k]) : '0'} onChange={(v) => mod(k, v)} />
            ))}
          </div>
          <div className="row" style={{ gap: 16, flexWrap: 'wrap' }}>
            <Check label="Environmental gasket" checked={e.mods.gasket} onChange={(v) => mod('gasket', v)} />
            <Check label="EMI gasket" checked={e.mods.emi_gasket} onChange={(v) => mod('emi_gasket', v)} />
            {e.source === 'catalog' && <Check label="Count holes from the panel parts when blank" checked={e.mods.auto_cutouts !== false} onChange={(v) => mod('auto_cutouts', v)} />}
          </div>
          <div className="grid g3">
            <label className="f">Finish<select value={e.finish} onChange={(x) => set({ finish: x.target.value })}>{Object.entries(cat.finishes).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
            <Num label="Silkscreen colors" step="1" value={e.silkscreen_colors || null} placeholder="0" onChange={(v) => set({ silkscreen_colors: v || 0 })} />
            <Num label="Silkscreen sides" step="1" value={e.silkscreen_sides} onChange={(v) => set({ silkscreen_sides: v || 1 })} />
          </div>
        </>
      )}
    </div>
  )
}

function BoardCard({ b, set, remove, cat, quantities, build, onError }) {
  const [busy, setBusy] = useState(false)
  const [info, setInfo] = useState(null)
  const [showBom, setShowBom] = useState(false)
  const [live, setLive] = useState('')
  const [breaks, setBreaks] = useState(breaksText(b.buy_prices))
  const input = useRef()
  useEffect(() => { setBreaks(breaksText(b.buy_prices)) }, [b.mode])
  const files = async (list) => {
    if (!list?.length) return
    setBusy(true); onError('')
    const form = new FormData()
    ;[...list].forEach((f) => form.append('files', f))
    try {
      const r = await api.upload('/api/box-build/pcb-parse', form)
      set({ ...r.board, bom_lines: r.bom_lines.length ? r.bom_lines : b.bom_lines, source: r.source, mode: 'estimate' })
      setInfo(r)
    } catch (e) { onError(e.message) }
    setBusy(false)
  }
  const getLive = async () => {
    setLive('Fetching…')
    const r = await fetchLive(b.bom_lines, (x) => x.mpn, (x) => x.qty * b.qty_per * build, quantities.map((q) => Math.ceil(q * b.qty_per)))
    set({ bom_lines: r.lines })
    setLive(r.message)
  }
  const n = (k, label, step = '1', ph) => <Num label={label} step={step} value={b[k]} placeholder={ph} onChange={(v) => set({ [k]: v ?? 0 })} />
  const priced = b.bom_lines.filter((x) => x.unit_price != null).length
  const bomTotal = b.bom_lines.reduce((s, x) => s + (x.unit_price || 0) * x.qty, 0)
  return (
    <div className="opcard" style={{ marginTop: 10 }}>
      <div className="row spread" style={{ flexWrap: 'wrap', gap: 8 }}>
        <input value={b.name} onChange={(e) => set({ name: e.target.value })} style={{ fontWeight: 600, minWidth: 180 }} />
        <span className="row" style={{ gap: 6 }}>
          {[['estimate', 'Estimate'], ['buy', 'Buy from a CM'], ['customer', 'Customer furnished']].map(([k, label]) => <button key={k} className={`chip ${b.mode === k ? 'on' : ''}`} onClick={() => set({ mode: k })}>{label}</button>)}
          <button className="link" onClick={remove}>remove</button>
        </span>
      </div>
      {b.check && <p className="small due-soon" style={{ marginTop: 8 }}>{b.check} <button className="link" onClick={() => set({ check: '' })}>Mark checked</button></p>}
      <div className="grid g3" style={{ marginTop: 8 }}>
        <Num label="Boards per unit" step="1" value={b.qty_per} onChange={(v) => set({ qty_per: v || 1 })} />
        {n('cable_mates', 'Cables plugged into it')}
        {n('wire_connections', 'Loose wires landing on it')}
      </div>
      {b.mode === 'buy' && (
        <div className="grid g3">
          <label className="f" style={{ gridColumn: 'span 3' }}>CM price breaks (qty: unit price)<input value={breaks} placeholder="1: 120, 10: 64, 100: 31" onChange={(e) => { setBreaks(e.target.value); set({ buy_prices: parseBreaks(e.target.value) }) }} /></label>
          <Num label="CM NRE $ (stencil, programming, fixtures)" value={b.buy_nre} onChange={(v) => set({ buy_nre: v || 0 })} />
          <Num label="CM lead time (days)" step="1" value={b.buy_lead_days} onChange={(v) => set({ buy_lead_days: v })} />
        </div>
      )}
      {b.mode === 'estimate' && (
        <>
          <div className="dropzone dz-sm" style={{ marginTop: 8 }} onClick={() => input.current.click()}
            onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); files(e.dataTransfer.files) }}>
            <input ref={input} type="file" multiple hidden accept=".zip,.gbr,.ger,.gtl,.gbl,.gko,.gm1,.drl,.xln,.txt,.csv,.pos,.xlsx,.tsv" onChange={(e) => { files(e.target.files); e.target.value = '' }} />
            <span className="small">{busy ? 'Reading…' : 'Drop Gerbers or the fab zip, drill, pick-and-place and BOM files (any or all at once)'}</span>
          </div>
          {info && <ul className="clean small muted" style={{ marginTop: 6 }}>{info.evidence.map((x, i) => <li key={i}>{x}</li>)}{info.warnings.map((x, i) => <li key={`w${i}`} className="due-soon">{x}</li>)}</ul>}
          <h3>Bare board</h3>
          <div className="grid g3">
            {n('layers', 'Layers')}
            {n('width_in', 'Width (in)', 'any')}
            {n('height_in', 'Height (in)', 'any')}
            {n('thickness_in', 'Thickness (in)', 'any')}
            <label className="f">Surface finish<select value={b.finish} onChange={(e) => set({ finish: e.target.value })}>{cat.pcb_finishes.map((f) => <option key={f}>{f}</option>)}</select></label>
            {n('copper_oz', 'Copper (oz)')}
            <label className="f">IPC class<select value={b.ipc_class} onChange={(e) => set({ ipc_class: Number(e.target.value) })}><option value={1}>Class 1</option><option value={2}>Class 2</option><option value={3}>Class 3</option></select></label>
            <Num label="Your fab price each (blank = estimate)" value={b.fab_price_each} onChange={(v) => set({ fab_price_each: v })} />
          </div>
          <div className="row" style={{ gap: 16, flexWrap: 'wrap' }}>
            <Check label="Controlled impedance" checked={b.impedance} onChange={(v) => set({ impedance: v })} />
            <Check label="Via in pad" checked={b.via_in_pad} onChange={(v) => set({ via_in_pad: v })} />
            <Check label="Blind or buried vias" checked={b.blind_buried} onChange={(v) => set({ blind_buried: v })} />
          </div>
          <h3>Assembly</h3>
          <div className="grid g3">
            {n('smt_placements', 'SMT placements')}
            {n('smt_unique', 'Unique SMT parts')}
            <label className="f">Sides with parts<select value={b.sides} onChange={(e) => set({ sides: Number(e.target.value) })}><option value={1}>1</option><option value={2}>2</option></select></label>
            {n('fine_pitch', 'Fine pitch parts')}
            {n('bga', 'BGAs')}
            {n('tht_parts', 'Through-hole parts')}
            {n('tht_joints', 'Through-hole joints')}
            {n('program_minutes', 'Program (min)')}
            {n('test_minutes', 'Board test (min)')}
          </div>
          <div className="row" style={{ gap: 16, flexWrap: 'wrap' }}>
            <Check label="AOI" checked={b.aoi} onChange={(v) => set({ aoi: v })} />
            <Check label="Flying probe" checked={b.flying_probe} onChange={(v) => set({ flying_probe: v })} />
            <Check label="Conformal coat" checked={b.conformal} onChange={(v) => set({ conformal: v })} />
            {b.conformal && <Num label="Masked areas" step="1" value={b.conformal_masks} onChange={(v) => set({ conformal_masks: v || 0 })} width={110} />}
          </div>
          <h3>Parts</h3>
          <div className="row" style={{ gap: 12, flexWrap: 'wrap', alignItems: 'end' }}>
            <Check label="Customer furnishes the parts (consigned)" checked={b.consigned} onChange={(v) => set({ consigned: v })} />
            {!b.consigned && !b.bom_lines.length && <Num label="BOM cost per board $ (if no BOM)" value={b.bom_cost_each} onChange={(v) => set({ bom_cost_each: v })} />}
          </div>
          {!b.consigned && b.bom_lines.length > 0 && (
            <div className="small" style={{ marginTop: 6 }}>
              {b.bom_lines.length} BOM lines, {priced} priced ({usd(bomTotal)} per board so far).{' '}
              <button className="link" onClick={() => setShowBom(!showBom)}>{showBom ? 'Hide' : 'Show'} BOM</button>{' '}
              <button onClick={getLive}>Fetch live prices</button> {live && <span className="muted">{live}</span>}
              {showBom && (
                <div style={{ overflowX: 'auto', maxHeight: 320, overflowY: 'auto', marginTop: 6 }}>
                  <table className="small ex-lines">
                    <thead><tr><th>Ref</th><th>MPN</th><th>Mfr</th><th>Description</th><th>Qty</th><th>Unit $</th></tr></thead>
                    <tbody>{b.bom_lines.map((x, i) => (
                      <tr key={i} className={x.unit_price == null ? 'ex-low' : ''}>
                        <td className="mono">{x.ref}</td>
                        <td><input value={x.mpn} onChange={(e) => set({ bom_lines: b.bom_lines.map((y, j) => (j === i ? { ...y, mpn: e.target.value } : y)) })} style={{ width: 150 }} /></td>
                        <td>{x.manufacturer}</td><td>{x.description}{x.tht ? <span className="tag" style={{ marginLeft: 4 }}>THT</span> : ''}</td><td className="mono">{x.qty}</td>
                        <td style={{ whiteSpace: 'nowrap' }}><input type="number" min="0" step="0.0001" value={x.unit_price ?? ''} onChange={(e) => set({ bom_lines: b.bom_lines.map((y, j) => (j === i ? { ...y, unit_price: numOrNull(e.target.value), price_source: 'manual' } : y)) })} style={{ width: 80 }} /> <PriceSource l={x} /></td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function PartsTable({ cat, lines, setLines }) {
  const setL = (i, patch) => setLines((ls) => ls.map((l, j) => (j === i ? { ...l, ...patch } : l)))
  const comp = cat.config.components
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="small ex-lines">
        <thead><tr><th>Ref</th><th>Type</th><th>Part number / MPN</th><th>Mfr</th><th>Description</th><th>Qty</th><th>Unit price</th><th title="Wire terminations on each part">Terms</th><th>Method</th><th>Mount</th><th title="Customer furnished">CF</th><th></th></tr></thead>
        <tbody>{lines.map((l, i) => {
          const t = comp[l.type] || null
          return (
            <tr key={i} className={(l.needs_quote && l.unit_price == null) || l.check ? 'ex-unmatched' : !l.type ? 'ex-low' : l.type === 'other' && l.unit_price == null ? 'ex-unmatched' : ''}>
              <td><input value={l.ref} onChange={(e) => setL(i, { ref: e.target.value.toUpperCase() })} style={{ width: 50 }} /></td>
              <td><select value={l.type} onChange={(e) => setL(i, { type: e.target.value })} style={{ maxWidth: 150 }}><option value="">Auto (from description)</option>{Object.entries(cat.component_types).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></td>
              <td><input value={l.part_number} onChange={(e) => setL(i, { part_number: e.target.value })} style={{ width: 130 }} /></td>
              <td><input value={l.manufacturer || ''} onChange={(e) => setL(i, { manufacturer: e.target.value })} style={{ width: 80 }} /></td>
              <td><input value={l.description} onChange={(e) => setL(i, { description: e.target.value })} style={{ width: 180 }} />
                {l.check && <div className="small due-soon" style={{ maxWidth: 220 }}>{l.check} <button className="link" onClick={() => setL(i, { check: '' })}>Mark checked</button></div>}</td>
              <td><input type="number" min="0" step="any" value={l.qty} onChange={(e) => setL(i, { qty: e.target.value === '' ? 0 : Number(e.target.value) })} style={{ width: 50 }} /></td>
              <td style={{ whiteSpace: 'nowrap' }}><input type="number" min="0" step="0.01" value={l.unit_price ?? ''} placeholder={l.needs_quote ? 'enter' : t ? String(t.price) : ''} onChange={(e) => setL(i, { unit_price: numOrNull(e.target.value), price_source: e.target.value === '' ? '' : 'manual' })} style={{ width: 72 }} /> {!l.customer_furnished && (l.needs_quote && l.unit_price == null ? <span className="tag due-soon" title="The quote tool cannot price this part: enter your price or quote it and link it.">needs manual price</span> : <PriceSource l={l} />)}</td>
              <td><input type="number" min="0" step="1" value={l.terminations ?? ''} placeholder={t ? String(t.terminations) : ''} onChange={(e) => setL(i, { terminations: numOrNull(e.target.value) })} style={{ width: 46 }} /></td>
              <td><select value={l.method} onChange={(e) => setL(i, { method: e.target.value })}><option value="">{l.type ? `default (${(cat.default_methods[l.type] || '').replace('_', ' ')})` : 'default'}</option>{cat.termination_methods.map((m) => <option key={m} value={m}>{m.replace('_', ' ')}</option>)}</select></td>
              <td><select value={l.mount} onChange={(e) => setL(i, { mount: e.target.value })}><option value="panel">panel</option><option value="internal">internal</option></select></td>
              <td><input type="checkbox" checked={!!l.customer_furnished} onChange={(e) => setL(i, { customer_furnished: e.target.checked })} /></td>
              <td><button className="link" onClick={() => setLines((ls) => ls.filter((_, j) => j !== i))}>remove</button></td>
            </tr>
          )
        })}</tbody>
      </table>
      <p className="small muted">Blank prices, terminations and methods use the defaults for the type (gray). Panel-mounted parts also count toward the enclosure holes when those are left blank.</p>
    </div>
  )
}

function PeripheralsTable({ list, setList, cat }) {
  const setP = (i, patch) => setList((ls) => ls.map((l, j) => (j === i ? { ...l, ...patch } : l)))
  const ig = cat.config.integration
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="small ex-lines">
        <thead><tr><th>Description</th><th>Part number</th><th>Mfr</th><th>Qty</th><th>Unit price</th><th>Installed</th><th>Minutes each</th><th title="Customer furnished">CF</th><th></th></tr></thead>
        <tbody>{list.map((x, i) => (
          <tr key={i} className={x.unit_price == null && !x.customer_furnished ? 'ex-low' : ''}>
            <td><input value={x.description} onChange={(e) => setP(i, { description: e.target.value })} style={{ width: 180 }} /></td>
            <td><input value={x.part_number} onChange={(e) => setP(i, { part_number: e.target.value })} style={{ width: 120 }} /></td>
            <td><input value={x.manufacturer || ''} onChange={(e) => setP(i, { manufacturer: e.target.value })} style={{ width: 80 }} /></td>
            <td><input type="number" min="0" value={x.qty} onChange={(e) => setP(i, { qty: e.target.value === '' ? 0 : Number(e.target.value) })} style={{ width: 50 }} /></td>
            <td style={{ whiteSpace: 'nowrap' }}><input type="number" min="0" step="0.01" value={x.unit_price ?? ''} onChange={(e) => setP(i, { unit_price: numOrNull(e.target.value), price_source: 'manual' })} style={{ width: 80 }} /> {x.price_source === 'live' && <PriceSource l={x} />}</td>
            <td><input type="checkbox" checked={!!x.installed} onChange={(e) => setP(i, { installed: e.target.checked })} title="Unchecked: packed with the unit" /></td>
            <td><input type="number" min="0" value={x.minutes ?? ''} placeholder={String(x.installed ? ig.peripheral_install_minutes : ig.peripheral_kit_minutes)} onChange={(e) => setP(i, { minutes: numOrNull(e.target.value) })} style={{ width: 56 }} /></td>
            <td><input type="checkbox" checked={!!x.customer_furnished} onChange={(e) => setP(i, { customer_furnished: e.target.checked })} /></td>
            <td><button className="link" onClick={() => setList((ls) => ls.filter((_, j) => j !== i))}>remove</button></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  )
}

function ChildrenTable({ list, setList }) {
  const setC = (i, patch) => setList((ls) => ls.map((l, j) => (j === i ? { ...l, ...patch } : l)))
  const relink = async (i) => {
    const ch = list[i]
    if (!ch.quote_id) return
    try {
      const l = await api.get(`/api/box-build/link/${ch.quote_id}`)
      setC(i, { spec: l.spec, name: l.name, kind: l.kind })
    } catch (e) { alert(e.message) }
  }
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="small ex-lines">
        <thead><tr><th>Linked quote</th><th>Kind</th><th>Qty per unit</th><th>Make or buy</th><th>Vendor $ each</th><th>Lead (days)</th><th></th></tr></thead>
        <tbody>{list.map((ch, i) => (
          <tr key={i}>
            <td><b>{ch.name}</b>{ch.quote_id ? <span className="muted"> #{ch.quote_id}</span> : ''}</td>
            <td>{KIND_NAMES[ch.kind] || ch.kind}</td>
            <td><input type="number" min="0" step="any" value={ch.qty_per} onChange={(e) => setC(i, { qty_per: Number(e.target.value) || 1 })} style={{ width: 56 }} /></td>
            <td><select value={ch.mode} onChange={(e) => setC(i, { mode: e.target.value })}><option value="make">make (your cost)</option><option value="buy">buy</option></select></td>
            <td>{ch.mode === 'buy' && <input type="number" min="0" step="0.01" value={ch.buy_unit_price ?? ''} onChange={(e) => setC(i, { buy_unit_price: numOrNull(e.target.value) })} style={{ width: 80 }} />}</td>
            <td>{ch.mode === 'buy' && <input type="number" min="0" value={ch.buy_lead_days ?? ''} onChange={(e) => setC(i, { buy_lead_days: numOrNull(e.target.value) })} style={{ width: 56 }} />}</td>
            <td style={{ whiteSpace: 'nowrap' }}>{ch.quote_id && <button className="link" onClick={() => relink(i)} title="Copy the current version of the saved quote">relink</button>} <button className="link" onClick={() => setList((ls) => ls.filter((_, j) => j !== i))}>remove</button></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  )
}

function LinkPicker({ exclude, onPick, onClose }) {
  const [q, setQ] = useState('')
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    const t = setTimeout(() => api.get('/api/pricing/quotes?' + new URLSearchParams({ q })).then((r) => setRows(r.filter((x) => String(x.id) !== String(exclude)))).catch((e) => setErr(e.message)), 250)
    return () => clearTimeout(t)
  }, [q])
  const pick = async (id) => {
    try { onPick(await api.get(`/api/box-build/link/${id}`)) } catch (e) { setErr(e.message) }
  }
  return (
    <div className="panel">
      <div className="row spread"><h2 style={{ margin: 0 }}>Link a saved quote</h2><button className="link" onClick={onClose}>Close</button></div>
      <input placeholder="Search by name, NSN or part number" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: '100%', marginTop: 8 }} autoFocus />
      {err && <div className="err">{err}</div>}
      {!rows ? <p className="muted">Loading…</p> : !rows.length ? <p className="small muted">No saved quotes match. Quote the part on its own tab and save it first.</p> : (
        <div style={{ maxHeight: 320, overflowY: 'auto', marginTop: 8 }}>
          <table className="small"><tbody>{rows.map((r) => (
            <tr key={r.id} className="clickable" onClick={() => pick(r.id)}>
              <td className="mono muted">#{r.id}</td><td><b>{r.name}</b>{r.part_number ? <span className="muted"> {r.part_number}</span> : ''}</td>
              <td>{KIND_NAMES[r.kind] || r.kind}</td><td className="mono">{r.price_breaks?.[0] ? `${usd(r.price_breaks[0].unit_price)} @ ${r.price_breaks[0].quantity}` : ''}</td>
            </tr>
          ))}</tbody></table>
        </div>
      )}
    </div>
  )
}

function TestPanel({ cat, labor, setLabor, counts }) {
  const set = (patch) => setLabor({ ...labor, ...patch })
  const n = (k, label, ph) => <Num label={label} value={labor[k]} placeholder={ph} onChange={(v) => set({ [k]: v })} />
  const ig = cat.config.integration
  const toggleLab = (k) => set({ lab_tests: (labor.lab_tests || []).includes(k) ? labor.lab_tests.filter((x) => x !== k) : [...(labor.lab_tests || []), k] })
  return (
    <div className="panel">
      <h2>Integration and test</h2>
      <div className="grid g3">
        <label className="f">Workmanship<select value={labor.ipc_class || 2} onChange={(e) => set({ ipc_class: Number(e.target.value) })}><option value={2}>Class 2 (standard)</option><option value={3}>Class 3 (high reliability)</option></select></label>
        {n('fasteners', 'Fasteners (blank = estimate)', counts ? String(counts.fasteners) : '')}
        {n('ground_points', 'Ground and bond points', '2')}
        {n('final_inspection_minutes', 'Final inspection (min)', String(ig.final_inspection_minutes))}
        {n('firmware_minutes', 'Load firmware and configure (min)', '0')}
        {n('functional_test_minutes', 'Functional test (min)', '0')}
        {n('burn_in_hours', 'Burn-in (hours)', '0')}
      </div>
      <div className="row" style={{ gap: 16, flexWrap: 'wrap' }}>
        <Check label="Serialize and label" checked={labor.serialize} onChange={(v) => set({ serialize: v })} />
        <Check label="Hipot" checked={labor.hipot} onChange={(v) => set({ hipot: v })} />
        <Check label="Ground bond" checked={labor.ground_bond} onChange={(v) => set({ ground_bond: v })} />
        <Check label="ESS thermal cycling" checked={labor.ess_thermal} onChange={(v) => set({ ess_thermal: v })} />
        <Check label="ESS random vibration" checked={labor.ess_vibration} onChange={(v) => set({ ess_vibration: v })} />
      </div>
      <h3>Outside lab qualification (per lot, placeholders)</h3>
      <div className="row" style={{ gap: 16, flexWrap: 'wrap' }}>
        {Object.entries(cat.lab_tests).map(([k, v]) => <Check key={k} label={v} checked={(labor.lab_tests || []).includes(k)} onChange={() => toggleLab(k)} />)}
      </div>
      <h3>NRE</h3>
      <div className="row" style={{ gap: 16, flexWrap: 'wrap' }}>
        <Check label="Work instructions and traveler" checked={labor.work_instructions} onChange={(v) => set({ work_instructions: v })} />
        <Check label="Test procedure and data sheet" checked={labor.test_procedure} onChange={(v) => set({ test_procedure: v })} />
        <Check label="Assembly drawings and parts list" checked={labor.drawing_package} onChange={(v) => set({ drawing_package: v })} />
      </div>
      <div className="grid g3">
        {n('test_fixture_nre', 'Test fixture $', '0')}
        {n('other_nre', 'Other NRE $', '0')}
      </div>
      <Check label="Include NRE in the unit prices (uncheck to quote NRE as its own line item)" checked={labor.nre_in_price !== false} onChange={(v) => set({ nre_in_price: v })} />
    </div>
  )
}
