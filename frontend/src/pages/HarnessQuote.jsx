import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import QuoteActions from '../QuoteActions'

// ------------------------------------------------------------ shared by HarnessQuote, PanelQuote and LabelQuote
export const usd = (n) => (n == null ? '' : `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`)
export const numOrNull = (v) => (v === '' || v == null ? null : Number(v))

export async function download(url, body, filename) {
  const res = await api.post(url, body)
  const blob = await res.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 2000)
}

export function parseQtys(text) {
  return [...new Set(String(text).split(/[\s,]+/).map(Number).filter((n) => Number.isInteger(n) && n > 0))].sort((a, b) => a - b)
}

// Live distributor prices (POST /api/distributors/price-bom). Returns {lines, message}; never throws.
export async function fetchLive(lines, getMpn, getQty, quantities) {
  const want = lines.map((l, i) => ({ i, mpn: (getMpn(l) || '').trim(), manufacturer: l.manufacturer || undefined, qty: Math.max(1, Math.round(getQty(l) || 1)) })).filter((x) => x.mpn)
  if (!want.length) return { lines, message: 'No lines with a part number (MPN) to price.' }
  let r
  try {
    r = await api.post('/api/distributors/price-bom', { lines: want.map(({ mpn, manufacturer, qty }) => ({ mpn, manufacturer, qty })), quantities })
  } catch (e) {
    if (/^404|^405/.test(e.message)) return { lines, message: 'Live distributor pricing is not installed yet. Manual prices kept.' }
    return { lines, message: `Live pricing failed (${e.message}). Manual prices kept.` }
  }
  if (!r?.configured?.digikey && !r?.configured?.mouser) return { lines, message: 'No distributor API keys are configured (DigiKey or Mouser). Manual prices kept.' }
  const byMpn = {}
  ;(r.results || []).forEach((x) => { byMpn[(x.mpn || '').toUpperCase()] = x })
  let hit = 0
  const miss = []
  const out = lines.map((l, i) => {
    const w = want.find((x) => x.i === i)
    if (!w) return l
    const res = byMpn[w.mpn.toUpperCase()]
    if (res?.best?.unit_price != null) {
      hit += 1
      return { ...l, unit_price: res.best.unit_price, price_source: 'live', distributor: res.best.distributor || '' }
    }
    miss.push(w.mpn)
    return l
  })
  return { lines: out, message: `Live prices found for ${hit} of ${want.length} part(s).${miss.length ? ` Not found: ${miss.slice(0, 6).join(', ')}${miss.length > 6 ? '...' : ''}.` : ''}` }
}

export function PriceSource({ l }) {
  if (l.unit_price == null) return <span className="tag due-soon" title="Placeholder price from your rates. Enter a price or fetch live prices.">placeholder</span>
  if (l.price_source === 'live') return <span className="tag" title="Live distributor price">live {l.distributor}</span>
  return null
}

export function Dropzone({ busy, compact, accept, title, hint, smallText, onFile }) {
  const input = useRef()
  const [drag, setDrag] = useState(false)
  return (
    <div className={`dropzone ${compact ? 'dz-sm' : ''} ${drag ? 'over' : ''}`} onClick={() => input.current.click()}
      onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
      onDrop={(e) => { e.preventDefault(); setDrag(false); onFile(e.dataTransfer.files[0]) }}>
      <input ref={input} type="file" accept={accept} hidden onChange={(e) => { onFile(e.target.files[0]); e.target.value = '' }} />
      {busy ? <div className="big">Reading…</div>
        : compact ? <span className="small">{smallText}</span>
          : <><div className="big">{title}</div><p className="muted">{hint}</p></>}
    </div>
  )
}

export function CostLines({ lines }) {
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

// Big price, breaks table, warnings, assumptions, cost breakdown
export function PriceCard({ est, row, setPick, unitWord, summary, children }) {
  const [detail, setDetail] = useState(false)
  return (
    <div className="panel price-panel">
      <div className="small muted">{summary}</div>
      <div className="price-big">{usd(row.unit_price)}<span> / {unitWord}</span></div>
      <div className="row spread">
        <div><b>{usd(row.total_price)}</b> for {row.quantity} · ships in about {row.lead_time_days} days</div>
        <div className="small muted">margin {row.margin_pct}%</div>
      </div>
      <table style={{ marginTop: 12 }}>
        <thead><tr><th>Qty</th><th>Price / {unitWord}</th><th>Total</th><th>Lead</th></tr></thead>
        <tbody>{est.price_breaks.map((b) => (
          <tr key={b.quantity} className={`clickable ${b.quantity === row.quantity ? 'sel' : ''}`} onClick={() => setPick(b.quantity)}>
            <td className="mono">{b.quantity}</td><td className="mono"><b>{usd(b.unit_price)}</b></td><td className="mono">{usd(b.total_price)}</td><td className="mono">{b.lead_time_days}d</td>
          </tr>))}</tbody>
      </table>
      <ul className="clean small" style={{ marginTop: 10 }}>
        {est.warnings.map((w, i) => <li key={`w${i}`} className="due-soon">{w}</li>)}
        {est.assumptions.slice(0, detail ? 99 : 2).map((a, i) => <li key={`a${i}`}>{a}</li>)}
      </ul>
      <button className="link" onClick={() => setDetail(!detail)}>{detail ? 'Hide cost breakdown' : 'Show cost breakdown'}</button>
      {detail && (
        <>
          <h3>Per {unitWord} ({usd(est.per_part_cost)})</h3>
          <CostLines lines={est.per_part_lines} />
          <h3>Per lot ({usd(est.per_lot_cost)})</h3>
          <CostLines lines={est.per_lot_lines} />
          <p className="small muted">G&A {Math.round(est.ga_rate * 100)}% · profit {Math.round(est.profit_rate * 100)}% · {est.config_note}</p>
        </>
      )}
      {children}
    </div>
  )
}

export function useOpps() {
  const [opps, setOpps] = useState([])
  useEffect(() => { api.get('/api/opportunities?' + new URLSearchParams({ my_naics_only: 'false', limit: 200 })).then((r) => setOpps(r.results || [])).catch(() => {}) }, [])
  return opps
}

export function SavePanel({ meta, est, row, setPick, save, setSave, opps, quoteId, onSave, msg }) {
  return (
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
        <button className="primary" onClick={onSave}>{quoteId ? 'Update quote' : 'Save quote'}</button>
        {msg && <span className="small okline">{msg}</span>}
        {save.opportunity_id && <Link className="small" to={`/opportunities/${save.opportunity_id}`}>Open opportunity</Link>}
      </div>
      {quoteId && <QuoteActions quoteId={quoteId} refreshKey={msg} />}
    </div>
  )
}

// Editable tree of numeric rates. Saved under the shop-rate config key `cfgKey`.
export function RatesPanel({ cfgKey, config, title, labels = {}, onSaved }) {
  const [d, setD] = useState(() => structuredClone(config))
  const [err, setErr] = useState('')
  const set = (path, v) => setD((old) => {
    const out = structuredClone(old)
    let cur = out
    path.slice(0, -1).forEach((k) => { cur = cur[k] })
    cur[path.at(-1)] = v
    return out
  })
  const nice = (k) => labels[k] || k.replace(/_/g, ' ')
  const leafRows = (obj, path) => Object.entries(obj).filter(([k, v]) => typeof v === 'number' && k !== 'note').map(([k, v]) => (
    <tr key={k}><td>{nice(k)}</td><td><input type="number" step="any" min="0" value={v ?? ''} onChange={(e) => set([...path, k], e.target.value === '' ? 0 : Number(e.target.value))} style={{ width: 80 }} /></td></tr>
  ))
  const groups = Object.entries(d).filter(([, v]) => v && typeof v === 'object')
  const saveRates = async () => {
    setErr('')
    try { await api.put('/api/pricing/config', { changes: { [cfgKey]: d } }); onSaved() } catch (e) { setErr(e.message) }
  }
  return (
    <div className="panel">
      <div className="notice">{d.note} These {title} rates are saved with your shop rates. Prices marked placeholder are not market data.</div>
      {err && <div className="err">{err}</div>}
      <div className="grid g3">
        <div><h3>General</h3><table className="small"><tbody>{leafRows(d, [])}</tbody></table></div>
        {groups.map(([g, v]) => {
          const nested = Object.entries(v).filter(([, x]) => x && typeof x === 'object')
          return (
            <div key={g}>
              <h3>{nice(g)}</h3>
              <div style={{ maxHeight: 280, overflowY: 'auto' }}>
                <table className="small"><tbody>{leafRows(v, [g])}</tbody></table>
                {nested.map(([n, x]) => (
                  <div key={n}><div className="small muted" style={{ marginTop: 6 }}>{x.label || nice(n)}</div><table className="small"><tbody>{leafRows(x, [g, n])}</tbody></table></div>
                ))}
              </div>
            </div>
          )
        })}
      </div>
      <div className="row" style={{ marginTop: 12 }}>
        <button className="primary" onClick={saveRates}>Save {title} rates</button>
        <button onClick={() => setD(structuredClone(config))}>Undo changes</button>
      </div>
    </div>
  )
}

// Common quote page state: catalog, reopen, opportunity prefill, debounced re-price, save, sheet
export function useQuotePage({ kind, quoteId, oppId, onSaved, payload, restore, defaultName, apiBase, catalogUrl = '/api/electrical/catalog', ready }) {
  const base = apiBase || `/api/electrical/${kind}`
  const [cat, setCat] = useState(null)
  const [qtyText, setQtyText] = useState('1, 5, 10')
  const [head, setHead] = useState({ name: '', part_number: '', nsn: '' })
  const [source, setSource] = useState({})
  const [est, setEst] = useState(null)
  const [pick, setPick] = useState(null)
  const [save, setSave] = useState({ opportunity_id: oppId ? Number(oppId) : null, status: 'draft', notes: '' })
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const opps = useOpps()
  const timer = useRef()
  const loadCatalog = () => api.get(catalogUrl).then(setCat).catch((e) => setErr(e.message))
  useEffect(() => { loadCatalog() }, [])
  useEffect(() => {
    if (!quoteId) return
    api.get(`${base}/quotes/${quoteId}`).then((q) => {
      const s = q.spec
      restore(s)
      setQtyText((s.quantities || [1]).join(', '))
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
  const quantities = useMemo(() => parseQtys(qtyText), [qtyText])
  const body = { ...payload, quantities, name: head.name, part_number: head.part_number, nsn: head.nsn }
  const hasLines = ready ?? ((payload.lines?.length || 0) + (payload.wires?.length || 0) + (payload.bom?.length || 0) > 0)
  useEffect(() => {
    clearTimeout(timer.current)
    if (!hasLines || !quantities.length) { setEst(null); return }
    timer.current = setTimeout(() => {
      api.post(`${base}/quote`, body).then((r) => { setEst(r); setErr('') }).catch((e) => setErr(e.message))
    }, 300)
    return () => clearTimeout(timer.current)
  }, [JSON.stringify(body), cat])
  const row = est ? (est.price_breaks.find((b) => b.quantity === pick) || est.price_breaks[0]) : null
  const doSave = async () => {
    setMsg(''); setErr('')
    try {
      const q = await api.post(`${base}/save`, { ...body, source, opportunity_id: save.opportunity_id || null, status: save.status, notes: save.notes,
        quoted_quantity: row?.quantity ?? null, quoted_unit_price: row?.unit_price ?? null, quote_id: quoteId ? Number(quoteId) : null })
      setMsg(`Saved quote #${q.id}.`)
      if (!quoteId) onSaved(q.id)
    } catch (e) { setErr(e.message) }
  }
  const sheet = () => {
    const slug = (head.name || defaultName).replace(/[^A-Za-z0-9_-]+/g, '-').slice(0, 60)
    download(`${base}/sheet.xlsx`, { ...body, builds: row?.quantity || quantities[0] || 1, title: head.name }, `${slug}.xlsx`).catch((e) => setErr(e.message))
  }
  return { cat, loadCatalog, qtyText, setQtyText, quantities, head, setHead, source, setSource, est, row, pick, setPick, save, setSave, err, setErr, msg, setMsg, opps, doSave, sheet }
}

export function HeadFields({ p, unitLabel, children }) {
  return (
    <div className="grid g2">
      <label className="f">Name<input value={p.head.name} onChange={(e) => p.setHead({ ...p.head, name: e.target.value })} /></label>
      <label className="f">Part / drawing number<input value={p.head.part_number} onChange={(e) => p.setHead({ ...p.head, part_number: e.target.value })} /></label>
      <label className="f">NSN<input value={p.head.nsn} onChange={(e) => p.setHead({ ...p.head, nsn: e.target.value })} /></label>
      <label className="f">{unitLabel} quantities<input value={p.qtyText} onChange={(e) => p.setQtyText(e.target.value)} placeholder="1, 5, 10" /></label>
      {children}
    </div>
  )
}

export function LotOptions({ opts, setOpts, packaging }) {
  return (
    <>
      <label className="f">Packaging<select value={opts.packaging_level || 'commercial'} onChange={(e) => setOpts({ ...opts, packaging_level: e.target.value })}>{packaging.map((p) => <option key={p}>{p}</option>)}</select></label>
      <label className="f">Freight per lot $ (blank = default)<input type="number" min="0" value={opts.freight_per_lot ?? ''} onChange={(e) => setOpts({ ...opts, freight_per_lot: e.target.value === '' ? undefined : Number(e.target.value) })} /></label>
      <label className="check small" style={{ gridColumn: 'span 2' }}><input type="checkbox" checked={!!opts.first_article} onChange={(e) => setOpts({ ...opts, first_article: e.target.checked })} /> First article inspection</label>
    </>
  )
}

// ------------------------------------------------------------ harness page
const TERMS = ['', 'crimp', 'solder', 'lug', 'splice', 'open']
const BOM_KINDS = ['connector', 'contact', 'backshell', 'accessory', 'other']
const blankWire = (n) => ({ wire_id: `W${n}`, from_ref: '', from_pin: '', to_ref: '', to_pin: '', gauge: '22', color: '', length_in: null, spec: 'M22759/16', shielded: false, twisted: false, from_term: '', to_term: '', signal: '', notes: '' })
const blankBom = (kind = 'connector') => ({ ref: '', kind, part_number: '', manufacturer: '', description: '', qty: kind === 'contact' ? null : 1, contact_size: '', unit_price: null, price_source: '', distributor: '', notes: '' })

export default function HarnessQuote({ meta, quoteId, oppId, onSaved }) {
  const [wires, setWires] = useState([])
  const [bom, setBom] = useState([])
  const [opts, setOpts] = useState({ workmanship: 'class_3', hipot: true, mark_wires: true, packaging_level: 'commercial', first_article: false })
  const [parseInfo, setParseInfo] = useState(null)
  const [busy, setBusy] = useState(false)
  const [live, setLive] = useState('')
  const [showRates, setShowRates] = useState(false)
  const cleanOpts = useMemo(() => Object.fromEntries(Object.entries(opts).filter(([, v]) => v !== '' && v != null)), [opts])
  const p = useQuotePage({ kind: 'harness', quoteId, oppId, onSaved, payload: { wires, bom, options: cleanOpts }, defaultName: 'harness',
    restore: (s) => { setWires(s.wires || []); setBom(s.bom || []); setOpts((o) => ({ ...o, ...(s.options || {}) })) } })

  const upload = async (file) => {
    if (!file) return
    setBusy(true); p.setErr(''); p.setMsg('')
    const form = new FormData()
    form.append('file', file)
    try {
      const r = await api.upload('/api/electrical/harness/parse', form)
      if (r.wires.length) setWires(r.wires)
      if (r.bom.length) setBom(r.bom)
      setParseInfo(r)
      p.setSource(r.source || {})
      const d = r.drawing || {}
      p.setHead((h) => ({ ...h, name: h.name || (d.title ? d.title.charAt(0) + d.title.slice(1).toLowerCase() : file.name.replace(/\.[^.]+$/, '')), part_number: h.part_number || d.drawing_number || d.part_number || '' }))
    } catch (e) { p.setErr(e.message) }
    setBusy(false)
  }
  const getLive = async () => {
    setLive('Fetching live prices…')
    const r = await fetchLive(bom, (l) => (l.kind === 'accessory' || l.kind === 'other' || l.kind === 'connector' || l.kind === 'backshell' || l.kind === 'contact') ? l.part_number : '',
      (l) => (l.qty == null ? (p.est?.counts?.crimp || 1) : l.qty) * (p.row?.quantity || 1), p.quantities)
    setBom(r.lines)
    setLive(r.message)
  }

  if (!p.cat) return <p className="muted">{p.err || 'Loading…'}</p>
  const hc = p.cat.harness
  const connectors = new Set(bom.filter((b) => b.kind === 'connector').flatMap((b) => (b.ref || '').toUpperCase().split(/[,;\s]+/).filter(Boolean)))
  const setW = (i, patch) => setWires((ws) => ws.map((w, j) => (j === i ? { ...w, ...patch } : w)))
  const setB = (i, patch) => setBom((bs) => bs.map((b, j) => (j === i ? { ...b, ...patch } : b)))
  const any = wires.length + bom.length > 0
  const cls = (w) => {
    const bad = !w.gauge || !w.length_in || !w.from_ref || !w.to_ref
    const missing = connectors.size && [['from', w.from_ref], ['to', w.to_ref]].some(([s, r]) => r && !connectors.has(r.toUpperCase()) && !['lug', 'splice', 'open'].includes(w[`${s}_term`]) && !/^(SP|E|GND|TB|TS|GS)\d/i.test(r))
    return bad || missing ? 'ex-unmatched' : ''
  }

  return (
    <>
      <div className="panel">
        <Dropzone busy={busy} compact={any} accept=".pdf,.csv,.xlsx,.xlsm,.tsv" onFile={upload}
          title="Drop a wire list, connector list or harness drawing" smallText="Drop another wire list, connector list or drawing PDF to replace those lines"
          hint="CSV/XLSX with columns like Wire ID, From (P1-3), To, Gauge AWG, Color, Length, Wire spec, Shield; or Ref, Part number, Description, Qty, Backshell, Contacts. A drawing PDF with those tables as text also works." />
        {p.err && <div className="err" style={{ marginTop: 10 }}>{p.err}</div>}
        {parseInfo?.warnings?.length > 0 && !p.est && <ul className="clean small" style={{ marginTop: 10 }}>{parseInfo.warnings.map((w, i) => <li key={i} className="due-soon">{w}</li>)}</ul>}
        <div className="row" style={{ marginTop: 10 }}>
          <button onClick={() => setWires((ws) => [...ws, blankWire(ws.length + 1)])}>+ Wire</button>
          <button onClick={() => setBom((bs) => [...bs, blankBom()])}>+ Connector / part</button>
          {any && <button className="link" onClick={() => { if (confirm('Clear every wire and BOM line?')) { setWires([]); setBom([]); setParseInfo(null) } }}>Clear</button>}
          <span className="small muted" style={{ marginLeft: 'auto' }}>{hc.config.note} <button className="link" onClick={() => setShowRates(!showRates)}>{showRates ? 'Hide' : 'Edit'} harness rates and prices</button></span>
        </div>
      </div>

      {showRates && <RatesPanel cfgKey="harness" config={hc.config} title="harness" onSaved={() => { p.loadCatalog(); setShowRates(false); p.setMsg('Harness rates saved.') }}
        labels={{ wire_per_ft: 'Wire $/ft by spec and AWG (placeholder)', wire_default_per_ft: 'Generic wire $/ft by AWG (placeholder)', placeholder_prices: 'Placeholder part prices $/each', minutes: 'Labor minutes', workmanship_multiplier: 'Workmanship class labor multiplier (your assumption)' }} />}

      {wires.length > 0 && (
        <div className="panel">
          <h2 style={{ marginTop: 0 }}>Wire list ({wires.length})</h2>
          <div style={{ overflowX: 'auto' }}>
            <table className="small ex-lines">
              <thead><tr><th>Wire</th><th>From</th><th>To</th><th>AWG</th><th>Color</th><th>Length (in)</th><th>Spec</th><th>Shield / twist</th><th>Termination</th><th>Signal</th><th></th></tr></thead>
              <tbody>{wires.map((w, i) => (
                <tr key={i} className={cls(w)}>
                  <td><input value={w.wire_id} onChange={(e) => setW(i, { wire_id: e.target.value })} style={{ width: 56 }} /></td>
                  <td style={{ whiteSpace: 'nowrap' }}><input value={w.from_ref} onChange={(e) => setW(i, { from_ref: e.target.value.toUpperCase() })} style={{ width: 46 }} placeholder="P1" />-<input value={w.from_pin} onChange={(e) => setW(i, { from_pin: e.target.value.toUpperCase() })} style={{ width: 34 }} /></td>
                  <td style={{ whiteSpace: 'nowrap' }}><input value={w.to_ref} onChange={(e) => setW(i, { to_ref: e.target.value.toUpperCase() })} style={{ width: 46 }} placeholder="J2" />-<input value={w.to_pin} onChange={(e) => setW(i, { to_pin: e.target.value.toUpperCase() })} style={{ width: 34 }} /></td>
                  <td><select value={w.gauge} onChange={(e) => setW(i, { gauge: e.target.value })}><option value="">?</option>{hc.gauges.map((g) => <option key={g}>{g}</option>)}</select></td>
                  <td><input value={w.color} onChange={(e) => setW(i, { color: e.target.value.toUpperCase() })} style={{ width: 50 }} /></td>
                  <td><input type="number" min="0" step="any" value={w.length_in ?? ''} onChange={(e) => setW(i, { length_in: numOrNull(e.target.value) })} style={{ width: 64 }} /></td>
                  <td><input list="hx-specs" value={w.spec} onChange={(e) => setW(i, { spec: e.target.value })} style={{ width: 100 }} /></td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <label className="check"><input type="checkbox" checked={!!w.shielded} onChange={(e) => setW(i, { shielded: e.target.checked })} />SH</label>
                    <label className="check"><input type="checkbox" checked={!!w.twisted} onChange={(e) => setW(i, { twisted: e.target.checked })} />TW</label>
                  </td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    {['from_term', 'to_term'].map((k) => <select key={k} value={w[k] || ''} onChange={(e) => setW(i, { [k]: e.target.value })} title={k === 'from_term' ? 'From end' : 'To end'}>{TERMS.map((t) => <option key={t} value={t}>{t || 'auto'}</option>)}</select>)}
                  </td>
                  <td><input value={w.signal || ''} onChange={(e) => setW(i, { signal: e.target.value })} style={{ width: 90 }} /></td>
                  <td><button className="link" onClick={() => setWires((ws) => ws.filter((_, j) => j !== i))}>remove</button></td>
                </tr>))}</tbody>
            </table>
            <datalist id="hx-specs">{hc.wire_specs.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</datalist>
          </div>
          <p className="small muted">Highlighted rows are missing a gauge, length or end, or point to a connector that is not in the BOM. Termination "auto" means crimp into a connector, a lug on TB/E/GND points and a splice on SP points.</p>
        </div>
      )}

      {bom.length > 0 && (
        <div className="panel">
          <div className="row spread">
            <h2 style={{ margin: 0 }}>Connectors and parts ({bom.length})</h2>
            <span className="row"><button onClick={getLive}>Fetch live prices</button>{live && <span className="small muted">{live}</span>}</span>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table className="small ex-lines">
              <thead><tr><th>Ref</th><th>Kind</th><th>Part number / MPN</th><th>Mfr</th><th>Description</th><th>Qty</th><th>Contact size</th><th>Unit price</th><th></th></tr></thead>
              <tbody>{bom.map((b, i) => (
                <tr key={i} className={b.unit_price == null ? 'ex-low' : ''}>
                  <td><input value={b.ref} onChange={(e) => setB(i, { ref: e.target.value.toUpperCase() })} style={{ width: 54 }} /></td>
                  <td><select value={b.kind} onChange={(e) => setB(i, { kind: e.target.value })}>{BOM_KINDS.map((k) => <option key={k}>{k}</option>)}</select></td>
                  <td><input value={b.part_number} onChange={(e) => setB(i, { part_number: e.target.value })} style={{ width: 150 }} /></td>
                  <td><input value={b.manufacturer || ''} onChange={(e) => setB(i, { manufacturer: e.target.value })} style={{ width: 70 }} /></td>
                  <td><input value={b.description} onChange={(e) => setB(i, { description: e.target.value })} style={{ width: 180 }} /></td>
                  <td><input type="number" min="0" value={b.qty ?? ''} placeholder={b.kind === 'contact' ? 'auto' : ''} onChange={(e) => setB(i, { qty: numOrNull(e.target.value) })} style={{ width: 54 }} title={b.kind === 'contact' ? 'Blank counts the crimp ends at this ref from the wire list' : ''} /></td>
                  <td>{['connector', 'contact'].includes(b.kind) && <select value={b.contact_size || ''} onChange={(e) => setB(i, { contact_size: e.target.value })}><option value="">?</option>{Object.entries(hc.contact_sizes).map(([s, [a, z]]) => <option key={s} value={s}>{s} ({a}-{z} AWG)</option>)}</select>}</td>
                  <td style={{ whiteSpace: 'nowrap' }}><input type="number" min="0" step="0.01" value={b.unit_price ?? ''} placeholder={`${hc.config.placeholder_prices[b.kind] ?? ''}`} onChange={(e) => setB(i, { unit_price: numOrNull(e.target.value), price_source: e.target.value === '' ? '' : 'manual' })} style={{ width: 74 }} /> <PriceSource l={b} /></td>
                  <td><button className="link" onClick={() => setBom((bs) => bs.filter((_, j) => j !== i))}>remove</button></td>
                </tr>))}</tbody>
            </table>
          </div>
          <p className="small muted">Contact size ranges: {hc.contact_size_source}. Blank prices use the placeholder shown.</p>
        </div>
      )}

      {any && (
        <div className="builder iq">
          <div>
            <div className="panel">
              <h2>Harness</h2>
              <HeadFields p={p} unitLabel="Harness">
                <label className="f" style={{ gridColumn: 'span 2' }}>Workmanship (IPC/WHMA-A-620 class)
                  <select value={opts.workmanship} onChange={(e) => setOpts({ ...opts, workmanship: e.target.value })}>
                    {Object.entries(hc.workmanship).map(([k, v]) => <option key={k} value={k}>{v} (labor x{hc.config.workmanship_multiplier[k]})</option>)}
                  </select>
                </label>
                <label className="f">Branches (blank = one per connector)<input type="number" min="0" value={opts.branches ?? ''} onChange={(e) => setOpts({ ...opts, branches: numOrNull(e.target.value) })} /></label>
                <label className="f">Cable ties (blank = estimate)<input type="number" min="0" value={opts.ties ?? ''} onChange={(e) => setOpts({ ...opts, ties: numOrNull(e.target.value) })} /></label>
                <label className="f">Heat shrink pieces (blank = estimate)<input type="number" min="0" value={opts.heat_shrink ?? ''} onChange={(e) => setOpts({ ...opts, heat_shrink: numOrNull(e.target.value) })} /></label>
                <label className="f">Sleeving ft / lacing ft
                  <span className="row" style={{ gap: 4, flexWrap: 'nowrap' }}>
                    <input type="number" min="0" value={opts.sleeving_ft ?? ''} onChange={(e) => setOpts({ ...opts, sleeving_ft: numOrNull(e.target.value) })} />
                    <input type="number" min="0" value={opts.lacing_ft ?? ''} onChange={(e) => setOpts({ ...opts, lacing_ft: numOrNull(e.target.value) })} />
                  </span>
                </label>
                <LotOptions opts={opts} setOpts={setOpts} packaging={p.cat.packaging_levels} />
                <label className="check small"><input type="checkbox" checked={!!opts.hipot} onChange={(e) => setOpts({ ...opts, hipot: e.target.checked })} /> Hipot / insulation resistance test</label>
                <label className="check small"><input type="checkbox" checked={!!opts.mark_wires} onChange={(e) => setOpts({ ...opts, mark_wires: e.target.checked })} /> Mark wires at both ends</label>
              </HeadFields>
              <p className="small muted">{hc.workmanship_source}</p>
            </div>
            {p.est && <PinOut rows={p.est.pinout} />}
          </div>
          <div>
            {p.est && p.row ? (
              <PriceCard est={p.est} row={p.row} setPick={p.setPick} unitWord="harness"
                summary={`Cable harness · ${p.est.counts.wires} wires · ${p.est.counts.crimp} crimps · ${p.est.counts.insert} insertions · ${p.est.labor_minutes} labor min`}>
                <div className="row" style={{ marginTop: 10 }}>
                  <button onClick={p.sheet}>Download cut list and pin-out</button>
                  <span className="small muted">for {p.row.quantity} harness(es)</span>
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

function PinOut({ rows }) {
  const [open, setOpen] = useState(false)
  if (!rows?.length) return null
  const refs = [...new Set(rows.map((r) => r.ref))]
  return (
    <div className="panel">
      <div className="row spread"><h2 style={{ margin: 0 }}>Pin-out</h2><button className="link" onClick={() => setOpen(!open)}>{open ? 'Hide' : `Show ${refs.length} connector(s)`}</button></div>
      {open && refs.map((ref) => (
        <div key={ref}>
          <h3>{ref}</h3>
          <table className="small">
            <thead><tr><th>Pin</th><th>Wire</th><th>AWG</th><th>Color</th><th>Term</th><th>Mates to</th><th>Signal</th></tr></thead>
            <tbody>{rows.filter((r) => r.ref === ref).map((r, i) => (
              <tr key={i}><td className="mono">{r.pin}</td><td className="mono">{r.wire_id}</td><td>{r.gauge}</td><td>{r.color}</td><td>{r.termination}</td><td className="mono">{r.mates_to}</td><td>{r.signal}</td></tr>
            ))}</tbody>
          </table>
        </div>
      ))}
    </div>
  )
}
