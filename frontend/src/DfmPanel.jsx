import { useEffect, useState } from 'react'
import { api } from './api'

const SEV = { cost: 'due-soon', warn: 'due-soon', info: 'muted' }
const SEV_LABEL = { cost: 'Adds cost', warn: 'Risk', info: 'Note' }

// Manufacturability review of the uploaded model for the chosen process.
export default function DfmPanel({ fileId, process, material }) {
  const [r, setR] = useState(null)
  const [err, setErr] = useState('')
  const [open, setOpen] = useState(true)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    setR(null); setErr('')
    const t = setTimeout(() => {
      api.get(`/api/cad/${fileId}/dfm?` + new URLSearchParams({ process: process || 'auto', material: material || '' }))
        .then(setR).catch((e) => setErr(e.message))
    }, 400)
    return () => clearTimeout(t)
  }, [fileId, process, material])

  if (err) return <div className="panel small muted">Manufacturability check unavailable: {err}</div>
  if (!r) return <div className="panel small muted">Checking manufacturability…</div>
  const n = r.findings.length
  const copy = async () => { try { await navigator.clipboard.writeText(r.note); setCopied(true); setTimeout(() => setCopied(false), 1500) } catch {} }

  return (
    <div className="panel">
      <div className="row spread">
        <h2 style={{ margin: 0 }}>Manufacturability</h2>
        <div className="row">
          {n > 0 && <button className="link" onClick={copy}>{copied ? 'Copied' : 'Copy note for the customer'}</button>}
          <button className="link" onClick={() => setOpen(!open)}>{open ? 'Hide' : `Show (${n})`}</button>
        </div>
      </div>
      {n === 0 && <p className="small okline" style={{ marginBottom: 0 }}>No problems found for {String(r.process).replace('_', ' ')}.</p>}
      {open && n > 0 && (
        <ul className="clean dfm-list">
          {r.findings.map((f) => (
            <li key={f.id}>
              <div><span className={`badge ${f.severity === 'info' ? 'b-not_eligible' : 'b-eligible_once_certified'}`}>{SEV_LABEL[f.severity] || f.severity}</span> <b>{f.title}</b>{f.cost_effect && <span className={`small ${SEV[f.severity]}`}> · {f.cost_effect}</span>}</div>
              <div className="small">{f.detail}</div>
              {f.suggestion && <div className="small muted">Fix: {f.suggestion}</div>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
