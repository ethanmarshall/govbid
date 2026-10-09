import { useEffect, useState } from 'react'
import { api } from './api'

// For 3D printed parts: turn threaded holes in the model into tapered heat-set insert holes.
export default function HeatSetInserts({ file, onFile }) {
  const [info, setInfo] = useState(null)
  const [pick, setPick] = useState({}) // group index -> thread ('' = leave as is)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [result, setResult] = useState(null)

  useEffect(() => {
    setInfo(null); setErr('')
    api.get(`/api/cad/${file.file_id}/holes`).then((d) => {
      setInfo(d)
      setPick(Object.fromEntries(d.groups.map((g, i) => [i, g.guess || ''])))
    }).catch((e) => setErr(e.message))
  }, [file.file_id])

  if (err && !info) return <div className="small muted" style={{ marginTop: 8 }}>{err}</div>
  if (!info) return null
  const converted = info.inserts?.length > 0
  if (!info.groups.length && !converted) return null

  const convert = async () => {
    const selections = info.groups.flatMap((g, i) => (pick[i] ? g.hole_ids.map((id) => ({ hole_id: id, thread: pick[i], from_end: 'auto' })) : []))
    if (!selections.length) { setErr('Pick a thread for at least one hole size.'); return }
    setBusy(true); setErr('')
    try {
      const d = await api.post(`/api/cad/${file.file_id}/inserts`, { selections })
      setResult(d)
      onFile(d)
    } catch (e) { setErr(e.message) }
    setBusy(false)
  }
  const undo = async () => {
    setBusy(true)
    try { onFile(await api.get(`/api/cad/${info.derived_from}`)); setResult(null) } catch (e) { setErr(e.message) }
    setBusy(false)
  }
  const threads = Object.keys(info.threads)

  return (
    <div className="opcard" style={{ marginTop: 10 }}>
      <div className="row spread">
        <b>Heat-set inserts</b>
        {converted && <span className="small">
          <a href={`/api/cad/${file.file_id}/download`}>Download modified STEP</a>{' · '}
          <button className="link" onClick={undo} disabled={busy}>Undo (use original model)</button>
        </span>}
      </div>
      {converted ? (
        <>
          <p className="small" style={{ margin: '6px 0' }}>{(result?.summary || `${info.inserts.length} hole(s) converted to tapered insert holes`).replace(/\.?$/, '.')} Inserts are priced from your shop rates.</p>
          <table className="small"><tbody>
            {info.inserts.map((i, k) => <tr key={k}><td className="mono">{i.thread}</td><td>entry Ø{Number(i.entry_d).toFixed(2)} mm to Ø{Number(i.bottom_d).toFixed(2)} mm, {Number(i.depth).toFixed(1)} mm deep{i.through ? ', through' : ''}</td></tr>)}
          </tbody></table>
          {(result?.warnings || []).map((w, i) => <div key={i} className="small due-soon">{w}</div>)}
        </>
      ) : (
        <>
          <p className="small muted" style={{ margin: '4px 0 8px' }}>Printed threads wear out. Pick the thread for each hole size and the model is rebuilt with tapered holes sized for brass heat-set inserts (PEM tapered insert hole sizes). Through holes stay open past the insert.</p>
          <table className="small">
            <thead><tr><th>Hole</th><th>Count</th><th>Type</th><th>Thread / insert</th></tr></thead>
            <tbody>{info.groups.map((g, i) => (
              <tr key={i}>
                <td className="mono">Ø{g.diameter_mm.toFixed(2)} mm ({g.diameter_in.toFixed(3)} in)</td>
                <td>{g.count}</td>
                <td>{g.through ? 'through' : 'blind'}</td>
                <td>
                  <select value={pick[i] || ''} onChange={(e) => setPick({ ...pick, [i]: e.target.value })}>
                    <option value="">Leave as is</option>
                    {threads.map((t) => <option key={t} value={t}>{t}{g.guess === t ? ' (matches)' : ''}</option>)}
                  </select>
                </td>
              </tr>
            ))}</tbody>
          </table>
          <div className="row" style={{ marginTop: 8 }}>
            <button className="primary small-btn" onClick={convert} disabled={busy}>{busy ? 'Rebuilding the model…' : 'Convert to insert holes'}</button>
            {err && <span className="small due-soon">{err}</span>}
          </div>
        </>
      )}
    </div>
  )
}
