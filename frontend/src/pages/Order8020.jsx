import { useState } from 'react'

// 80/20 design checks and the order list in 80/20 part numbers (from app/catalog_8020.py, catalog 24 page labels).
const LEVEL = { error: 'Fix before ordering', warn: 'Check', info: 'Note' }

export function DesignChecks({ checks }) {
  if (!checks?.length) return <p className="small muted">No problems found against the 80/20 catalog rules.</p>
  const order = { error: 0, warn: 1, info: 2 }
  return (
    <ul className="clean small" style={{ margin: 0 }}>
      {[...checks].sort((a, b) => order[a.level] - order[b.level]).map((c, i) => (
        <li key={i} style={{ marginBottom: 4 }}>
          <b className={c.level === 'info' ? '' : 'due-soon'}>{LEVEL[c.level] || c.level}:</b> {c.text}
          {c.page && <span className="muted"> (catalog p. {c.page})</span>}
        </li>
      ))}
    </ul>
  )
}

export function Order8020({ order, builds = 1 }) {
  const [copied, setCopied] = useState(false)
  if (!order?.rows?.length) return null
  const text = order.rows.map((r) => `${r.qty}\t${r.part_number}\t${r.description}${r.callout ? `\t${r.callout}` : ''}`).join('\n')
  const copy = async () => { try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000) } catch { /* clipboard blocked */ } }
  return (
    <div>
      <div className="row spread" style={{ alignItems: 'baseline' }}>
        <span className="small muted">For {builds} build{builds === 1 ? '' : 's'}. Profiles are ordered cut to length with the machining services listed.</span>
        <button className="small-btn" onClick={copy}>{copied ? 'Copied' : 'Copy order list'}</button>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table className="small">
          <thead><tr><th>Qty</th><th>80/20 part</th><th>Description</th><th>Machining services</th></tr></thead>
          <tbody>{order.rows.map((r, i) => (
            <tr key={i}><td className="mono">{r.qty}</td><td className="mono">{r.part_number}</td><td>{r.description}</td><td className="small">{r.callout}</td></tr>
          ))}</tbody>
        </table>
      </div>
      {order.unknown?.length > 0 && <p className="small due-soon">No 80/20 part number here for: {order.unknown.join(', ')}. Pick these by hand.</p>}
      {order.notes?.length > 0 && <ul className="clean small muted" style={{ marginTop: 6 }}>{order.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>}
    </div>
  )
}
