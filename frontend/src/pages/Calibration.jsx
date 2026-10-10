import { useEffect, useRef, useState } from 'react'
import { api } from '../api'

const usd = (n) => (n == null ? '' : `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`)

// Real prices next to the tool's. The median ratio per process corrects every customer price.
export default function Calibration() {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [f, setF] = useState({ material: '6061-T6 aluminum', process: 'auto', name: '', vendor: '', note: '', quantities: '1, 10', prices: '' })
  const file = useRef()
  const load = () => api.get('/api/calibration').then(setD).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [])

  const add = async () => {
    setErr(''); setMsg('')
    const fl = file.current?.files?.[0]
    if (!fl) { setErr('Choose the STEP file you got the real quote for.'); return }
    const form = new FormData()
    form.append('file', fl)
    Object.entries(f).forEach(([k, v]) => form.append(k, v))
    setBusy(true)
    try {
      const r = await api.upload('/api/calibration/benchmark', form)
      setMsg(`Added ${r.added.length} price(s). The tool was ${r.added.map((s) => `${usd(s.tool_unit_price)} vs ${usd(s.actual_unit_price)} at ${s.quantity}`).join(', ')}.`)
      setF({ ...f, prices: '', name: '', note: '' }); file.current.value = ''
      load()
    } catch (e) { setErr(e.message) }
    setBusy(false)
  }
  const toggle = async (s) => { await api.put(`/api/calibration/${s.id}`, { active: !s.active }); load() }
  const del = async (s) => { if (!confirm('Delete this price?')) return; await api.del(`/api/calibration/${s.id}`); load() }

  if (!d) return <p className="muted">{err || 'Loading…'}</p>
  const fs = d.factors
  const procs = Object.entries(fs.processes)
  return (
    <>
      <h1>Calibration</h1>
      <p className="sub">Real prices for real parts, next to what this tool priced them at. Customer prices are multiplied by the median real/tool ratio for their process (with 2 or more prices), or across all processes (with 3 or more). Final prices you set when reviewing customer requests are added here too.</p>

      <div className="panel">
        <h2 style={{ marginTop: 0 }}>Corrections in use</h2>
        {!procs.length ? <p className="small muted">None yet: prices are the tool's own. Add real quotes below.</p> : (
          <table className="small">
            <thead><tr><th>Process</th><th>Real prices</th><th>Real / tool, range</th><th>Correction</th></tr></thead>
            <tbody>{procs.map(([k, p]) => (
              <tr key={k}><td>{p.label}</td><td>{p.samples}</td><td className="mono">{p.spread[0]} to {p.spread[1]}</td>
                <td className="mono">{p.factor ? <b>x{p.factor}</b> : fs.overall.used ? <span className="muted">x{fs.overall.factor} (all processes)</span> : <span className="muted">needs 2</span>}</td></tr>
            ))}</tbody>
          </table>
        )}
        {fs.overall.used && <p className="small muted">Across all processes: x{fs.overall.factor} from {fs.overall.samples} prices.</p>}
      </div>

      <div className="panel">
        <h2 style={{ marginTop: 0 }}>Add a real quote</h2>
        <p className="small muted" style={{ marginTop: 0 }}>Upload the STEP file you got a quote for (Xometry, Protolabs, SendCutSend, a local shop) and enter their unit price at each quantity. Use the same material and process they quoted.</p>
        <div className="grid g3">
          <label className="f">STEP file<input type="file" ref={file} /></label>
          <label className="f">Material<select value={f.material} onChange={(e) => setF({ ...f, material: e.target.value })}>{d.materials.map((m) => <option key={m}>{m}</option>)}</select></label>
          <label className="f">Process<select value={f.process} onChange={(e) => setF({ ...f, process: e.target.value })}>
            <option value="auto">As the tool picks</option><option value="cnc_mill">CNC milling</option><option value="cnc_lathe">CNC turning</option>
            <option value="sheet_metal">Sheet metal</option><option value="3d_print">3D printing</option></select></label>
          <label className="f">Quantities<input value={f.quantities} onChange={(e) => setF({ ...f, quantities: e.target.value })} placeholder="1, 10, 60" /></label>
          <label className="f">Their unit prices, same order<input value={f.prices} onChange={(e) => setF({ ...f, prices: e.target.value })} placeholder="185, 64, 41" /></label>
          <label className="f">Vendor<input value={f.vendor} onChange={(e) => setF({ ...f, vendor: e.target.value })} placeholder="Xometry" /></label>
          <label className="f">Name (optional)<input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
          <label className="f" style={{ gridColumn: 'span 2' }}>Note<input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} placeholder="Standard lead time, anodized black" /></label>
        </div>
        <div className="row" style={{ marginTop: 8 }}><button className="primary" disabled={busy} onClick={add}>{busy ? 'Pricing it…' : 'Add'}</button>{msg && <span className="small okline">{msg}</span>}</div>
        {err && <div className="err">{err}</div>}
      </div>

      <div className="panel">
        <h2 style={{ marginTop: 0 }}>Real prices ({d.samples.length})</h2>
        {!d.samples.length ? <p className="small muted">None yet.</p> : (
          <div style={{ overflowX: 'auto' }}>
            <table className="small">
              <thead><tr><th>Part</th><th>Process</th><th>Qty</th><th>Tool</th><th>Real</th><th>Real / tool</th><th>From</th><th></th></tr></thead>
              <tbody>{d.samples.map((s) => (
                <tr key={s.id} style={{ opacity: s.active ? 1 : 0.5 }}>
                  <td><b>{s.name || '—'}</b><div className="muted">{s.material}{s.note ? `, ${s.note}` : ''}</div></td>
                  <td>{s.process_label}</td><td className="mono">{s.quantity}</td>
                  <td className="mono">{usd(s.tool_unit_price)}</td><td className="mono">{usd(s.actual_unit_price)}</td>
                  <td className="mono">{s.ratio}</td>
                  <td>{s.source === 'review' ? `Review ${s.ref}` : s.vendor || 'Quote'}<div className="muted">{(s.created_at || '').slice(0, 10)}</div></td>
                  <td className="row" style={{ gap: 6 }}><button className="small-btn" onClick={() => toggle(s)}>{s.active ? 'Leave out' : 'Use'}</button><button className="link" onClick={() => del(s)}>Delete</button></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}
