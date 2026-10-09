import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from './api'

const usd = (n) => (n == null ? '' : `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`)
const PROC = { cnc_mill: 'CNC milling', cnc_lathe: 'CNC turning', sheet_metal: 'Sheet metal', '3d_print': '3D printing' }

// Price a part from its PDF drawing alone (no STEP model). The user confirms the sizes the reader found.
export default function DrawingQuote({ drawing, cadOpts, statuses, oppId, onSaved }) {
  const [inp, setInp] = useState({}) // user overrides
  const [qtyText, setQtyText] = useState('1, 10, 50')
  const [r, setR] = useState(null)
  const [err, setErr] = useState('')
  const [pick, setPick] = useState(null)
  const [save, setSave] = useState({ opportunity_id: oppId ? Number(oppId) : null, status: 'draft', notes: '' })
  const [opps, setOpps] = useState([])
  const [msg, setMsg] = useState('')
  const [useAi, setUseAi] = useState(false)
  const [showWhy, setShowWhy] = useState(false)
  const [showSingle, setShowSingle] = useState(false)
  const navigate = useNavigate()
  const timer = useRef()

  useEffect(() => {
    api.get('/api/opportunities?' + new URLSearchParams({ my_naics_only: 'false', limit: 200 })).then((x) => setOpps(x.results)).catch(() => {})
  }, [])

  const quantities = [...new Set(qtyText.split(/[ ,]+/).map(Number).filter((n) => n > 0 && Number.isInteger(n)))].sort((a, b) => a - b)

  useEffect(() => {
    clearTimeout(timer.current)
    timer.current = setTimeout(async () => {
      try {
        const x = await api.post(`/api/drawings/${drawing.drawing_id}/quote`, { overrides: inp, quantities, use_ai: useAi })
        setR(x); setErr('')
        setPick((p) => (x.estimate.price_breaks.some((b) => b.quantity === p) ? p : x.estimate.price_breaks[0]?.quantity))
      } catch (e) { setErr(e.message); if (useAi) setUseAi(false) }
    }, 350)
    return () => clearTimeout(timer.current)
  }, [drawing.drawing_id, JSON.stringify(inp), qtyText, useAi])

  const v = (k) => (k in inp ? inp[k] : r?.inputs?.[k] ?? '')
  const set = (k, val) => setInp((s) => ({ ...s, [k]: val }))
  const num = (k, label, step = '0.001') => (
    <label className="f">{label}<input type="number" step={step} value={v(k) ?? ''} onChange={(e) => set(k, e.target.value === '' ? '' : Number(e.target.value))} /></label>
  )

  const doSave = async () => {
    setMsg(''); setErr('')
    const row = r.estimate.price_breaks.find((b) => b.quantity === pick)
    try {
      const q = await api.post('/api/pricing/quotes', { spec: r.spec, opportunity_id: save.opportunity_id || null, status: save.status, notes: save.notes, quoted_quantity: pick, quoted_unit_price: row?.unit_price ?? null })
      setMsg(`Saved quote #${q.id}.`)
      onSaved?.(q.id)
    } catch (e) { setErr(e.message) }
  }

  const openBox = () => {
    try { sessionStorage.setItem('govbid:box-prefill', JSON.stringify(r.assembly.box_build)) } catch {}
    navigate('/part-quotes?tab=box&from=drawing')
  }
  const asm = r?.assembly
  const hidePrice = asm && !showSingle
  const process = v('process') || 'cnc_mill'
  const isPrint = process === '3d_print'
  const est = r?.estimate
  const row = est?.price_breaks.find((b) => b.quantity === pick) || est?.price_breaks[0]
  const g = r?.geometry || {}

  return (
    <div className="builder iq" style={{ marginTop: 16 }}>
      <div>
        <div className="panel">
          <div className="row spread">
            <h2 style={{ margin: 0 }}>Quote from the drawing</h2>
            {r && <span className={`badge ${r.confidence === 'high' ? 'b-eligible_now' : r.confidence === 'medium' ? 'b-eligible_once_certified' : 'b-not_eligible'}`}>{r.confidence} confidence</span>}
          </div>
          <p className="small muted">No model, so the size and features come from the drawing text. Check the envelope and counts below; every change reprices.</p>
          {r?.export_controlled && <p className="small due-soon">This drawing is marked export controlled{r.distribution ? ` (distribution ${r.distribution})` : ''}. Keep it off outside services.</p>}

          <h3>Process</h3>
          <div className="row" style={{ gap: 6 }}>
            {Object.entries(PROC).map(([p, label]) => (
              <button key={p} className={`chip ${process === p ? 'on' : ''}`} onClick={() => setInp((s) => ({ ...s, process: p, material: p === '3d_print' ? 'PETG' : (isPrint ? '6061-T6 aluminum' : s.material), finishes: p === '3d_print' || isPrint ? [] : s.finishes }))}>{label}</button>
            ))}
          </div>

          <h3>Size (inches)</h3>
          <div className="grid g3">
            {process === 'cnc_lathe' ? <>{num('max_diameter', 'Largest diameter')}{num('length', 'Length')}</> : <>{num('length', 'Length')}{num('width', 'Width')}{num('height', process === 'sheet_metal' ? 'Formed height' : 'Height / thickness')}</>}
            {process === 'sheet_metal' && num('thickness', 'Sheet thickness')}
          </div>

          <h3>Features</h3>
          <div className="grid g3">
            {num('thru_holes', 'Drilled holes', '1')}
            {num('tapped_holes', isPrint ? 'Threaded holes (inserts)' : 'Tapped holes', '1')}
            {process === 'sheet_metal' && num('bends', 'Bends', '1')}
            {process === 'cnc_mill' && num('setups', 'Setups', '1')}
          </div>

          <h3>Material, finish, quantity</h3>
          <div className="grid g3">
            <label className="f">Material
              <select value={v('material')} onChange={(e) => set('material', e.target.value)}>
                {(isPrint ? Object.keys(cadOpts.print_materials) : cadOpts.materials).map((m) => <option key={m}>{m}</option>)}
              </select>
            </label>
            <label className="f">Tolerance
              <select value={v('tolerance') || 'standard'} onChange={(e) => set('tolerance', e.target.value)}>{cadOpts.tolerances.map((t) => <option key={t}>{t}</option>)}</select>
            </label>
            <label className="f">Quantities<input value={qtyText} onChange={(e) => setQtyText(e.target.value)} /></label>
          </div>
          <div className="row" style={{ gap: 6, marginTop: 8 }}>
            {(isPrint ? cadOpts.print_finishes : cadOpts.finishes).map((f) => {
              const on = (v('finishes') || []).includes(f)
              return <button key={f} className={`chip ${on ? 'on' : ''}`} onClick={() => set('finishes', on ? v('finishes').filter((x) => x !== f) : [...(v('finishes') || []), f])}>{f}</button>
            })}
          </div>
          <div className="row" style={{ gap: 16, marginTop: 10 }}>
            <label className="check"><input type="checkbox" checked={!!v('first_article')} onChange={(e) => set('first_article', e.target.checked)} /> First article</label>
            <label className="check"><input type="checkbox" checked={!!v('material_certs')} onChange={(e) => set('material_certs', e.target.checked)} /> Material certs</label>
            {!r?.export_controlled && (
              <label className="check" title="Sends the PDF to Anthropic. Never for ITAR/EAR or limited-distribution drawings.">
                <input type="checkbox" checked={useAi} onChange={(e) => setUseAi(e.target.checked)} /> Read sizes with Claude
              </label>
            )}
          </div>
          {g.evidence?.length > 0 && (
            <>
              <button className="link" style={{ marginTop: 10 }} onClick={() => setShowWhy(!showWhy)}>{showWhy ? 'Hide what was read' : 'What was read from the drawing'}</button>
              {showWhy && <ul className="clean small muted">{g.evidence.map((e, i) => <li key={i}>{e}</li>)}</ul>}
            </>
          )}
        </div>
      </div>

      <div>
        {asm && (
          <div className="panel asm-notice">
            <h2>This is an assembly drawing</h2>
            <p className="small">{asm.message}</p>
            <ul className="clean small muted">{asm.box_build.evidence.slice(0, 12).map((x, i) => <li key={i}>{x}</li>)}</ul>
            <div className="row" style={{ marginTop: 10 }}>
              <button className="primary" onClick={openBox}>Open as a box build</button>
              <button className="link" onClick={() => setShowSingle(!showSingle)}>{showSingle ? 'Hide' : 'Show'} the single-part price anyway</button>
            </div>
          </div>
        )}
        {!hidePrice && <div className="panel price-panel">
          {err && <div className="err">{err}</div>}
          {!est ? <p className="muted">Pricing…</p> : (
            <>
              <div className="small muted">{PROC[process]} · {v('material')} · from drawing {r.spec?.part_number || ''}</div>
              <div className="price-big">{usd(row.unit_price)}<span> / part</span></div>
              <div><b>{usd(row.total_price)}</b> for {row.quantity} · ships in about {row.lead_time_days} days</div>
              <table style={{ marginTop: 12 }}>
                <thead><tr><th>Qty</th><th>Unit price</th><th>Total</th><th>Lead</th></tr></thead>
                <tbody>{est.price_breaks.map((b) => (
                  <tr key={b.quantity} className={`clickable ${b.quantity === row.quantity ? 'sel' : ''}`} onClick={() => setPick(b.quantity)}>
                    <td className="mono">{b.quantity}</td><td className="mono"><b>{usd(b.unit_price)}</b></td><td className="mono">{usd(b.total_price)}</td><td className="mono">{b.lead_time_days}d</td>
                  </tr>
                ))}</tbody>
              </table>
              <ul className="clean small" style={{ marginTop: 10 }}>
                {[...(r.warnings || []), ...est.warnings].map((w, i) => <li key={`w${i}`} className="due-soon">{w}</li>)}
                {r.assumptions.map((a, i) => <li key={`a${i}`}>{a}</li>)}
              </ul>
            </>
          )}
        </div>}
        {est && !hidePrice && (
          <div className="panel">
            <h2>Save quote</h2>
            <div className="grid g2">
              <label className="f" style={{ gridColumn: 'span 2' }}>Opportunity
                <select value={save.opportunity_id || ''} onChange={(e) => setSave({ ...save, opportunity_id: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">Not linked</option>
                  {opps.map((o) => <option key={o.id} value={o.id}>{o.solicitation_number ? `${o.solicitation_number}: ` : ''}{o.title.slice(0, 80)}</option>)}
                </select>
              </label>
              <label className="f">Status<select value={save.status} onChange={(e) => setSave({ ...save, status: e.target.value })}>{statuses.map((s) => <option key={s}>{s}</option>)}</select></label>
              <label className="f">Quoting quantity<select value={row.quantity} onChange={(e) => setPick(Number(e.target.value))}>{est.price_breaks.map((b) => <option key={b.quantity} value={b.quantity}>{b.quantity} at {usd(b.unit_price)}</option>)}</select></label>
              <label className="f" style={{ gridColumn: 'span 2' }}>Notes<textarea value={save.notes} onChange={(e) => setSave({ ...save, notes: e.target.value })} style={{ minHeight: 50 }} placeholder="Quoted from drawing only. Sizes checked against: ..." /></label>
            </div>
            <div className="row" style={{ marginTop: 10 }}>
              <button className="primary" onClick={doSave}>Save quote</button>
              {msg && <span className="small">{msg} <Link to="/part-quotes?tab=saved">Saved quotes</Link></span>}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
