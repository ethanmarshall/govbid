import { useMemo, useState } from 'react'
import { api } from '../api'
import { Dropzone, HeadFields, LotOptions, PriceCard, RatesPanel, SavePanel, numOrNull, usd, useQuotePage } from './HarnessQuote'

const blankLine = (n) => ({ item: String(n), type: 'engraved_laminate', width_in: 1, height_in: 3, text: '', chars: null, color: '', holes: 0, adhesive: false, qty: 1, iuid: false, notes: '' })
const countChars = (t) => String(t || '').replace(/[\s|/]/g, '').length

export default function LabelQuote({ meta, quoteId, oppId, onSaved }) {
  const [lines, setLines] = useState([])
  const [opts, setOpts] = useState({ packaging_level: 'commercial', first_article: false })
  const [parseInfo, setParseInfo] = useState(null)
  const [busy, setBusy] = useState(false)
  const [showRates, setShowRates] = useState(false)
  const cleanOpts = useMemo(() => Object.fromEntries(Object.entries(opts).filter(([, v]) => v !== '' && v != null)), [opts])
  const p = useQuotePage({ kind: 'labels', quoteId, oppId, onSaved, payload: { lines, options: cleanOpts }, defaultName: 'labels',
    restore: (s) => { setLines(s.lines || []); setOpts((o) => ({ ...o, ...(s.options || {}) })) } })

  const upload = async (file) => {
    if (!file) return
    setBusy(true); p.setErr(''); p.setMsg('')
    const form = new FormData()
    form.append('file', file)
    try {
      const r = await api.upload('/api/electrical/labels/parse', form)
      setLines(r.lines)
      setParseInfo(r)
      p.setSource(r.source || {})
      p.setHead((h) => ({ ...h, name: h.name || file.name.replace(/\.[^.]+$/, '') }))
    } catch (e) { p.setErr(e.message) }
    setBusy(false)
  }

  if (!p.cat) return <p className="muted">{p.err || 'Loading…'}</p>
  const lc = p.cat.labels
  const setL = (i, patch) => setLines((ls) => ls.map((l, j) => (j === i ? { ...l, ...patch } : l)))
  const detail = Object.fromEntries((p.est?.line_detail || []).map((d) => [d.item, d]))
  const anyIuid = lines.some((l) => l.iuid)

  return (
    <>
      <div className="panel">
        <Dropzone busy={busy} compact={lines.length > 0} accept=".csv,.xlsx,.xlsm,.tsv,.pdf" onFile={upload}
          title="Drop a label or nameplate list" smallText="Drop another list to replace the lines"
          hint="CSV/XLSX with columns like Item, Type (phenolic, anodized, stainless, polyester, vinyl, heat shrink), Size (2 x 4) or Width and Height, Text, Holes, Adhesive, Qty, IUID." />
        {p.err && <div className="err" style={{ marginTop: 10 }}>{p.err}</div>}
        {parseInfo?.warnings?.length > 0 && !p.est && <ul className="clean small" style={{ marginTop: 10 }}>{parseInfo.warnings.map((w, i) => <li key={i} className="due-soon">{w}</li>)}</ul>}
        <div className="row" style={{ marginTop: 10 }}>
          <button onClick={() => setLines((ls) => [...ls, blankLine(ls.length + 1)])}>+ Add plate or label</button>
          {lines.length > 0 && <button className="link" onClick={() => { if (confirm('Clear every line?')) { setLines([]); setParseInfo(null) } }}>Clear lines</button>}
          <span className="small muted" style={{ marginLeft: 'auto' }}>{lc.config.note} <button className="link" onClick={() => setShowRates(!showRates)}>{showRates ? 'Hide' : 'Edit'} label rates and prices</button></span>
        </div>
      </div>

      {showRates && <RatesPanel cfgKey="labels" config={lc.config} title="label" onSaved={() => { p.loadCatalog(); setShowRates(false); p.setMsg('Label rates saved.') }}
        labels={{ materials: 'Materials (placeholder $/sq in, seconds per character and per sq in)', iuid: 'IUID marks (minutes per mark)' }} />}

      {lines.length > 0 && (
        <div className="panel">
          <h2 style={{ marginTop: 0 }}>Plates and labels ({lines.length})</h2>
          <div style={{ overflowX: 'auto' }}>
            <table className="small ex-lines">
              <thead><tr><th>Item</th><th>Type</th><th>W x H (in)</th><th>Text (use | between lines)</th><th>Chars</th><th>Color</th><th>Holes</th><th>Adhesive</th><th>IUID</th><th>Qty / set</th><th>Each</th><th></th></tr></thead>
              <tbody>{lines.map((l, i) => {
                const d = detail[l.item]
                const bad = !l.type || (l.type !== 'heat_shrink_marker' && !(l.width_in && l.height_in))
                return (
                  <tr key={i} className={bad ? 'ex-unmatched' : ''}>
                    <td><input value={l.item} onChange={(e) => setL(i, { item: e.target.value })} style={{ width: 40 }} /></td>
                    <td><select value={l.type} onChange={(e) => setL(i, { type: e.target.value })}><option value="">pick a type</option>{Object.entries(lc.types).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <input type="number" min="0" step="any" value={l.width_in ?? ''} onChange={(e) => setL(i, { width_in: numOrNull(e.target.value) })} style={{ width: 54 }} />×
                      <input type="number" min="0" step="any" value={l.height_in ?? ''} onChange={(e) => setL(i, { height_in: numOrNull(e.target.value) })} style={{ width: 54 }} />
                    </td>
                    <td><input value={l.text} onChange={(e) => setL(i, { text: e.target.value })} style={{ width: 200 }} /></td>
                    <td><input type="number" min="0" value={l.chars ?? ''} placeholder={String(countChars(l.text))} onChange={(e) => setL(i, { chars: numOrNull(e.target.value) })} style={{ width: 54 }} /></td>
                    <td><input value={l.color} onChange={(e) => setL(i, { color: e.target.value })} style={{ width: 90 }} /></td>
                    <td><input type="number" min="0" value={l.holes} onChange={(e) => setL(i, { holes: Number(e.target.value) || 0 })} style={{ width: 46 }} /></td>
                    <td><input type="checkbox" checked={!!l.adhesive} onChange={(e) => setL(i, { adhesive: e.target.checked })} /></td>
                    <td><input type="checkbox" checked={!!l.iuid} onChange={(e) => setL(i, { iuid: e.target.checked })} /></td>
                    <td><input type="number" min="0" value={l.qty} onChange={(e) => setL(i, { qty: e.target.value === '' ? 0 : Number(e.target.value) })} style={{ width: 54 }} /></td>
                    <td className="mono" title={d ? `material ${usd(d.material_each)}, ${d.marking_seconds_each} s marking, ${d.labor_minutes_each} min labor` : ''}>{d ? usd(d.cost_each) : ''}</td>
                    <td><button className="link" onClick={() => setLines((ls) => ls.filter((_, j) => j !== i))}>remove</button></td>
                  </tr>
                )
              })}</tbody>
            </table>
          </div>
          <p className="small muted">"Each" is cost before G&A and profit. Characters default to the count of non-space characters in the text.</p>
          {anyIuid && (
            <div className="notice small" style={{ marginTop: 8 }}>
              IUID marks: when a contract carries DFARS 252.211-7003, items with a government unit acquisition cost of $5,000 or more (and others the contract lists)
              get a MIL-STD-130 Data Matrix mark. The mark must be verified machine readable per MIL-STD-130 Appendix A (commonly graded B or better with a verifier),
              and the UII data goes to the IUID Registry, normally through the WAWF receiving report for end items. MIL-DTL-15024 (plates, tags and bands for
              identification of equipment) may also be cited for nameplates: read the version the drawing calls out.
            </div>
          )}
        </div>
      )}

      {lines.length > 0 && (
        <div className="builder iq">
          <div>
            <div className="panel">
              <h2>Order</h2>
              <HeadFields p={p} unitLabel="Set">
                <LotOptions opts={opts} setOpts={setOpts} packaging={p.cat.packaging_levels} />
              </HeadFields>
              <p className="small muted">A set is every line at its quantity. Price breaks are per set.</p>
            </div>
          </div>
          <div>
            {p.est && p.row ? (
              <PriceCard est={p.est} row={p.row} setPick={p.setPick} unitWord="set"
                summary={`Labels and plates · ${lines.length} design(s) · ${p.est.pieces_per_set} piece(s) per set`}>
                <div className="row" style={{ marginTop: 10 }}>
                  <button onClick={p.sheet}>Download plate schedule</button>
                  <span className="small muted">for {p.row.quantity} set(s)</span>
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
