import { useMemo, useState } from 'react'
import { api } from '../api'
import { Dropzone, HeadFields, LotOptions, PriceCard, PriceSource, RatesPanel, SavePanel, fetchLive, numOrNull, useQuotePage } from './HarnessQuote'

const blankLine = (device_type = 'other') => ({ ref: '', device_type, part_number: '', manufacturer: '', description: '', qty: 1, length_m: null, unit_price: null, price_source: '', distributor: '', notes: '' })
const CUTOUTS = [['operator_device', 'Operator device holes'], ['hmi', 'HMI cutouts'], ['meter', 'Meter cutouts'], ['round_hole', 'Other round holes'], ['rect_cutout', 'Other rectangular cutouts']]

export default function PanelQuote({ meta, quoteId, oppId, onSaved }) {
  const [lines, setLines] = useState([])
  const [opts, setOpts] = useState({ ul508a: false, documentation: true, crate: true, packaging_level: 'commercial', first_article: false, nameplates: 1, cutouts: {} })
  const [parseInfo, setParseInfo] = useState(null)
  const [busy, setBusy] = useState(false)
  const [live, setLive] = useState('')
  const [showRates, setShowRates] = useState(false)
  const cleanOpts = useMemo(() => {
    const o = Object.fromEntries(Object.entries(opts).filter(([, v]) => v !== '' && v != null))
    o.cutouts = Object.fromEntries(Object.entries(opts.cutouts || {}).filter(([, v]) => v !== '' && v != null))
    return o
  }, [opts])
  const p = useQuotePage({ kind: 'panel', quoteId, oppId, onSaved, payload: { lines, options: cleanOpts }, defaultName: 'control-panel',
    restore: (s) => { setLines(s.lines || []); setOpts((o) => ({ ...o, ...(s.options || {}) })) } })

  const upload = async (file) => {
    if (!file) return
    setBusy(true); p.setErr(''); p.setMsg('')
    const form = new FormData()
    form.append('file', file)
    try {
      const r = await api.upload('/api/electrical/panel/parse', form)
      setLines(r.lines)
      setParseInfo(r)
      p.setSource(r.source || {})
      const d = r.drawing || {}
      p.setHead((h) => ({ ...h, name: h.name || (d.title ? d.title.charAt(0) + d.title.slice(1).toLowerCase() : file.name.replace(/\.[^.]+$/, '')), part_number: h.part_number || d.drawing_number || d.part_number || '' }))
    } catch (e) { p.setErr(e.message) }
    setBusy(false)
  }
  const getLive = async () => {
    setLive('Fetching live prices…')
    const r = await fetchLive(lines, (l) => l.part_number, (l) => l.qty * (p.row?.quantity || 1), p.quantities)
    setLines(r.lines)
    setLive(r.message)
  }

  if (!p.cat) return <p className="muted">{p.err || 'Loading…'}</p>
  const pc = p.cat.panel
  const setL = (i, patch) => setLines((ls) => ls.map((l, j) => (j === i ? { ...l, ...patch } : l)))
  const c = p.est?.counts
  const unmatched = lines.filter((l) => l.device_type === 'other' && l.unit_price == null).length

  return (
    <>
      <div className="panel">
        <Dropzone busy={busy} compact={lines.length > 0} accept=".pdf,.csv,.xlsx,.xlsm,.tsv" onFile={upload}
          title="Drop a panel BOM or drawing PDF" smallText="Drop another BOM or drawing PDF to replace the lines"
          hint="CSV/XLSX with columns like Ref (device tag), Part number, Manufacturer, Description, Qty, Length; or a drawing PDF with the BOM as text." />
        {p.err && <div className="err" style={{ marginTop: 10 }}>{p.err}</div>}
        {parseInfo?.warnings?.length > 0 && !p.est && <ul className="clean small" style={{ marginTop: 10 }}>{parseInfo.warnings.map((w, i) => <li key={i} className="due-soon">{w}</li>)}</ul>}
        <div className="row" style={{ marginTop: 10 }}>
          <button onClick={() => setLines((ls) => [...ls, blankLine()])}>+ Add line</button>
          {lines.length > 0 && <button className="link" onClick={() => { if (confirm('Clear every line?')) { setLines([]); setParseInfo(null) } }}>Clear lines</button>}
          <span className="small muted" style={{ marginLeft: 'auto' }}>{pc.config.note} <button className="link" onClick={() => setShowRates(!showRates)}>{showRates ? 'Hide' : 'Edit'} panel rates and prices</button></span>
        </div>
      </div>

      {showRates && <RatesPanel cfgKey="panel" config={pc.config} title="panel" onSaved={() => { p.loadCatalog(); setShowRates(false); p.setMsg('Panel rates saved.') }}
        labels={{ placeholder_prices: 'Placeholder prices $/each (rail and duct $/m)', mount_minutes: 'Mounting minutes per device', device_terminations: 'Wire landings per device (wire estimate)', cutout_minutes: 'Enclosure cutout minutes', ul508a: 'UL 508A (placeholders)' }} />}

      {lines.length > 0 && (
        <div className="panel">
          <div className="row spread">
            <h2 style={{ margin: 0 }}>Panel BOM ({lines.length})</h2>
            <span className="row">{unmatched > 0 && <span className="small due-soon">{unmatched} line(s) with no device type or price</span>}<button onClick={getLive}>Fetch live prices</button>{live && <span className="small muted">{live}</span>}</span>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table className="small ex-lines">
              <thead><tr><th>Ref</th><th>Type</th><th>Part number / MPN</th><th>Mfr</th><th>Description</th><th>Qty</th><th>Length (m)</th><th>Unit price</th><th></th></tr></thead>
              <tbody>{lines.map((l, i) => {
                const perM = pc.length_priced.includes(l.device_type)
                return (
                  <tr key={i} className={l.device_type === 'other' && l.unit_price == null ? 'ex-unmatched' : l.unit_price == null ? 'ex-low' : ''}>
                    <td><input value={l.ref} onChange={(e) => setL(i, { ref: e.target.value.toUpperCase() })} style={{ width: 54 }} /></td>
                    <td><select value={l.device_type} onChange={(e) => setL(i, { device_type: e.target.value })}>{Object.entries(pc.device_types).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></td>
                    <td><input value={l.part_number} onChange={(e) => setL(i, { part_number: e.target.value })} style={{ width: 140 }} /></td>
                    <td><input value={l.manufacturer || ''} onChange={(e) => setL(i, { manufacturer: e.target.value })} style={{ width: 80 }} /></td>
                    <td><input value={l.description} onChange={(e) => setL(i, { description: e.target.value })} style={{ width: 200 }} /></td>
                    <td><input type="number" min="0" step="any" value={l.qty} onChange={(e) => setL(i, { qty: e.target.value === '' ? 0 : Number(e.target.value) })} style={{ width: 54 }} /></td>
                    <td>{perM && <input type="number" min="0" step="any" value={l.length_m ?? ''} placeholder="qty = m" onChange={(e) => setL(i, { length_m: numOrNull(e.target.value) })} style={{ width: 64 }} />}</td>
                    <td style={{ whiteSpace: 'nowrap' }}><input type="number" min="0" step="0.01" value={l.unit_price ?? ''} placeholder={`${pc.config.placeholder_prices[l.device_type] ?? ''}${perM ? '/m' : ''}`} onChange={(e) => setL(i, { unit_price: numOrNull(e.target.value), price_source: e.target.value === '' ? '' : 'manual' })} style={{ width: 80 }} /> <PriceSource l={l} /></td>
                    <td><button className="link" onClick={() => setLines((ls) => ls.filter((_, j) => j !== i))}>remove</button></td>
                  </tr>
                )
              })}</tbody>
            </table>
          </div>
          <p className="small muted">DIN rail and wire duct are priced per meter: quantity x length, or the quantity read as meters when no length is given.</p>
        </div>
      )}

      {lines.length > 0 && (
        <div className="builder iq">
          <div>
            <div className="panel">
              <h2>Panel</h2>
              <HeadFields p={p} unitLabel="Panel">
                <label className="f">Point-to-point wire count (blank = estimate)<input type="number" min="0" value={opts.wire_count ?? ''} onChange={(e) => setOpts({ ...opts, wire_count: numOrNull(e.target.value) })} /></label>
                <label className="f">I/O points (blank = from I/O modules)<input type="number" min="0" value={opts.io_points ?? ''} onChange={(e) => setOpts({ ...opts, io_points: numOrNull(e.target.value) })} /></label>
                <label className="f">Nameplates<input type="number" min="0" value={opts.nameplates ?? ''} onChange={(e) => setOpts({ ...opts, nameplates: numOrNull(e.target.value) })} /></label>
                <LotOptions opts={opts} setOpts={setOpts} packaging={p.cat.packaging_levels} />
                <label className="check small"><input type="checkbox" checked={!!opts.documentation} onChange={(e) => setOpts({ ...opts, documentation: e.target.checked })} /> As-built drawings and documentation</label>
                <label className="check small"><input type="checkbox" checked={!!opts.crate} onChange={(e) => setOpts({ ...opts, crate: e.target.checked })} /> Crate each panel</label>
                <label className="check small" style={{ gridColumn: 'span 2' }}><input type="checkbox" checked={!!opts.ul508a} onChange={(e) => setOpts({ ...opts, ul508a: e.target.checked })} /> UL 508A labeled panel</label>
              </HeadFields>
              {opts.ul508a && <div className="notice small" style={{ marginTop: 8 }}>{p.cat.ul508a_note}</div>}
              <h3>Enclosure cutouts</h3>
              <div className="grid g3">
                {CUTOUTS.map(([k, name]) => (
                  <label key={k} className="f">{name}
                    <input type="number" min="0" value={opts.cutouts?.[k] ?? ''} placeholder={c ? String(c.cutouts[k]) : ''} onChange={(e) => setOpts({ ...opts, cutouts: { ...opts.cutouts, [k]: numOrNull(e.target.value) } })} />
                  </label>
                ))}
              </div>
              <p className="small muted">Blank counts come from the BOM (one door hole per pilot device, HMI and meter).</p>
            </div>
            {c && (
              <div className="panel">
                <h2>Wiring basis</h2>
                <p className="small"><b>{c.wires}</b> wires: {c.wire_basis}.</p>
                <p className="small muted">{c.io_points} I/O points{c.io_estimated ? ' (estimated from I/O modules)' : ''} · {c.device_tags} device tags · {c.legend_plates} legend plates · {Object.entries(c.meters).map(([k, v]) => `${v} m ${k.replace('_', ' ')}`).join(' · ')}</p>
              </div>
            )}
          </div>
          <div>
            {p.est && p.row ? (
              <PriceCard est={p.est} row={p.row} setPick={p.setPick} unitWord="panel"
                summary={`Control panel · ${lines.length} BOM lines · ${c.wires} wires${opts.ul508a ? ' · UL 508A' : ''}`}>
                <div className="row" style={{ marginTop: 10 }}>
                  <button onClick={p.sheet}>Download purchase list</button>
                  <span className="small muted">for {p.row.quantity} panel(s)</span>
                </div>
              </PriceCard>
            ) : <div className="panel"><p className="muted">{p.err ? '' : 'Pricing…'}</p></div>}
            {p.est && p.row && <SavePanel meta={meta} est={p.est} row={p.row} setPick={p.setPick} save={p.save} setSave={p.setSave} opps={p.opps} quoteId={quoteId} onSave={p.doSave} msg={p.msg} />}
          </div>
        </div>
      )}
    </>
  )
}
