import { useEffect, useRef, useState } from 'react'
import { api } from './api'

const usd = (n) => (n == null ? '' : `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`)
const PROC = { auto: 'Auto', cnc_mill: 'CNC mill', cnc_lathe: 'CNC lathe', sheet_metal: 'Sheet metal', '3d_print': '3D print' }

// A STEP file with several bodies: quote every part, then add welding or assembly.
export default function AssemblyPanel({ file, cadOpts, quantities, statuses, oppId, onSaved }) {
  const [groups, setGroups] = useState(null)
  const [joints, setJoints] = useState([])
  const [rows, setRows] = useState([])
  const [join, setJoin] = useState({ weld_process: 'mig', weld_length_in: 0, weld_joints: 0, fasteners: 0, fastener_unit_cost: 0.25, assembly_minutes: 10, inspection_minutes: 5, first_article: false })
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [save, setSave] = useState({ status: 'draft', notes: '' })
  const timer = useRef()

  const start = async () => {
    setBusy(true); setErr('')
    try {
      const s = await api.post(`/api/cad/${file.file_id}/split`)
      setGroups(s.groups); setJoints(s.joints || [])
      setRows(s.groups.map((g) => ({ file_id: g.file_id, name: g.name, qty: g.qty, process: 'auto', material: g.suggested_process === '3d_print' ? 'PETG' : '6061-T6 aluminum', finishes: [], skip: false, buy: false, buy_unit_price: '' })))
      const weldIn = (s.joints || []).reduce((a, j) => a + (j.contact_length_in || 0), 0)
      setJoin((j) => ({ ...j, weld_length_in: Math.round(weldIn * 10) / 10, weld_joints: (s.joints || []).length }))
    } catch (e) { setErr(e.message) }
    setBusy(false)
  }

  useEffect(() => {
    if (!rows.length) return
    clearTimeout(timer.current)
    timer.current = setTimeout(async () => {
      try {
        const body = { bodies: rows.map((r) => ({ ...r, buy_unit_price: r.buy ? Number(r.buy_unit_price) || 0 : null })), joining: join.weld_process === 'none' ? { ...join, weld_process: 'mig', weld_length_in: 0, weld_joints: 0 } : join, quantities, name: file.filename.replace(/\.(step|stp)$/i, '') }
        setRes(await api.post(`/api/cad/${file.file_id}/assembly-quote`, body)); setErr('')
      } catch (e) { setErr(e.message) }
    }, 400)
    return () => clearTimeout(timer.current)
  }, [JSON.stringify(rows), JSON.stringify(join), quantities.join(',')])

  const upd = (i, patch) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  const doSave = async () => {
    try {
      const q = await api.post('/api/pricing/quotes', { spec: res.spec, opportunity_id: oppId ? Number(oppId) : null, status: save.status, notes: save.notes, quoted_quantity: res.price_breaks[0]?.quantity })
      setMsg(`Saved quote #${q.id}.`); onSaved?.(q.id)
    } catch (e) { setErr(e.message) }
  }

  return (
    <div className="panel">
      <div className="row spread">
        <h2 style={{ margin: 0 }}>Assembly or weldment ({file.geometry.solids} bodies)</h2>
        {!groups && <button className="primary small-btn" onClick={start} disabled={busy}>{busy ? 'Splitting the model…' : 'Quote each part and the assembly'}</button>}
      </div>
      {!groups && <p className="small muted" style={{ marginBottom: 0 }}>This file has more than one solid. The single-part price above treats it as one piece; split it to price every part by its own process, then add welding, fasteners and assembly labor.</p>}
      {err && <div className="err">{err}</div>}
      {groups && (
        <>
          <table className="small" style={{ marginTop: 8 }}>
            <thead><tr><th>Part</th><th>Qty / assy</th><th>Process</th><th>Material</th><th>Buy instead</th><th>Price each</th></tr></thead>
            <tbody>{rows.map((r, i) => {
              const b = res?.bodies?.find((x) => x.file_id === r.file_id)
              return (
                <tr key={r.file_id} style={{ opacity: r.skip ? 0.5 : 1 }}>
                  <td><input value={r.name} onChange={(e) => upd(i, { name: e.target.value })} /><div className="muted">{groups[i].bounding_box.length} × {groups[i].bounding_box.width} × {groups[i].bounding_box.height} in · detected {PROC[groups[i].suggested_process] || groups[i].suggested_process}</div>
                    <label className="check"><input type="checkbox" checked={r.skip} onChange={(e) => upd(i, { skip: e.target.checked })} /> leave out (customer supplied)</label></td>
                  <td><input type="number" min="1" style={{ width: 60 }} value={r.qty} onChange={(e) => upd(i, { qty: Math.max(1, Number(e.target.value) || 1) })} /></td>
                  <td><select value={r.process} onChange={(e) => upd(i, { process: e.target.value, material: e.target.value === '3d_print' ? 'PETG' : (r.process === '3d_print' ? '6061-T6 aluminum' : r.material) })}>{Object.entries(PROC).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></td>
                  <td><select value={r.material} onChange={(e) => upd(i, { material: e.target.value })}>{(r.process === '3d_print' ? Object.keys(cadOpts.print_materials) : cadOpts.materials).map((m) => <option key={m}>{m}</option>)}</select></td>
                  <td><label className="check"><input type="checkbox" checked={r.buy} onChange={(e) => upd(i, { buy: e.target.checked })} /> buy</label>{r.buy && <input type="number" style={{ width: 80 }} placeholder="$ each" value={r.buy_unit_price} onChange={(e) => upd(i, { buy_unit_price: e.target.value })} />}</td>
                  <td className="mono">{b?.error ? <span className="small due-soon">{b.error}</span> : b?.breaks?.[0] ? <>{usd(b.breaks[0].unit_price)}<div className="muted">at {b.breaks[0].parts} pcs</div></> : ''}</td>
                </tr>
              )
            })}</tbody>
          </table>

          <h3>Joining and assembly</h3>
          <div className="grid g4">
            <label className="f">Weld process<select value={join.weld_process} onChange={(e) => setJoin({ ...join, weld_process: e.target.value })}><option value="mig">MIG</option><option value="tig">TIG</option><option value="none">No welding</option></select></label>
            <label className="f">Weld length (in)<input type="number" value={join.weld_length_in} onChange={(e) => setJoin({ ...join, weld_length_in: Number(e.target.value) || 0 })} /></label>
            <label className="f">Weld joints<input type="number" value={join.weld_joints} onChange={(e) => setJoin({ ...join, weld_joints: Number(e.target.value) || 0 })} /></label>
            <label className="f">Fasteners<input type="number" value={join.fasteners} onChange={(e) => setJoin({ ...join, fasteners: Number(e.target.value) || 0 })} /></label>
            <label className="f">Assembly min<input type="number" value={join.assembly_minutes} onChange={(e) => setJoin({ ...join, assembly_minutes: Number(e.target.value) || 0 })} /></label>
            <label className="f">Inspection min<input type="number" value={join.inspection_minutes} onChange={(e) => setJoin({ ...join, inspection_minutes: Number(e.target.value) || 0 })} /></label>
            <label className="check" style={{ alignSelf: 'end' }}><input type="checkbox" checked={join.first_article} onChange={(e) => setJoin({ ...join, first_article: e.target.checked })} /> First article</label>
          </div>
          {joints.length > 0 && <p className="small muted">Weld length starts from the {joints.length} contact seam(s) found between bodies. Adjust it to the drawing's weld symbols.</p>}

          {res && (
            <>
              <table style={{ marginTop: 12 }}>
                <thead><tr><th>Assemblies</th><th>Price each</th><th>Total</th><th>Parts</th><th>Joining</th><th>Lead</th></tr></thead>
                <tbody>{res.price_breaks.map((b) => (
                  <tr key={b.quantity}><td className="mono">{b.quantity}</td><td className="mono"><b>{usd(b.unit_price)}</b></td><td className="mono">{usd(b.total_price)}</td>
                    <td className="mono muted">{usd(b.bodies_price)}</td><td className="mono muted">{usd(b.joining_price)}</td><td className="mono">{b.lead_time_days}d</td></tr>
                ))}</tbody>
              </table>
              {(res.warnings.length > 0 || res.assumptions.length > 0) && (
                <ul className="clean small" style={{ marginTop: 8 }}>
                  {res.warnings.map((w, i) => <li key={`w${i}`} className="due-soon">{w}</li>)}
                  {res.assumptions.map((a, i) => <li key={`a${i}`}>{a}</li>)}
                </ul>
              )}
              <div className="row" style={{ marginTop: 10 }}>
                <select value={save.status} onChange={(e) => setSave({ ...save, status: e.target.value })}>{statuses.map((s) => <option key={s}>{s}</option>)}</select>
                <input style={{ minWidth: 240 }} placeholder="Notes" value={save.notes} onChange={(e) => setSave({ ...save, notes: e.target.value })} />
                <button className="primary" onClick={doSave}>Save assembly quote</button>
                {msg && <span className="small">{msg}</span>}
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}
