import { useEffect, useState } from 'react'
import { api } from '../api'

const usd = (n) => `$${Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const TERMS = [[0, 'Due on receipt'], [15, 'Net 15'], [30, 'Net 30'], [45, 'Net 45'], [60, 'Net 60']]

// Customers who made an account on the public site. Approving terms lets them order on an invoice and pay later;
// without terms, invoices are due on receipt and the work starts when they are paid.
export default function CustomerAccounts() {
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const load = () => api.get('/api/portal/customers').then(setRows).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [])
  const put = async (c, body, done) => {
    setErr(''); setMsg('')
    try { await api.put(`/api/portal/customers/${c.id}`, body); setMsg(done); load() } catch (e) { setErr(e.message) }
  }
  if (!rows) return <p className="muted">{err || 'Loading…'}</p>
  const asks = rows.filter((c) => c.terms_requested_at && !c.net_terms_days)
  return (
    <>
      <h1>Customer accounts</h1>
      <p className="sub">Accounts customers made on your site. Give terms only to customers you have checked: net terms mean you build and ship before you are paid. Everyone else gets an invoice due on receipt, and you start when it is paid.</p>
      {err && <div className="err">{err}</div>}
      {msg && <p className="small okline">{msg}</p>}
      {asks.length > 0 && (
        <div className="panel">
          <h2 style={{ marginTop: 0 }}>Asking for terms ({asks.length})</h2>
          {asks.map((c) => (
            <div key={c.id} style={{ borderTop: '1px solid var(--line, #ddd)', padding: '10px 0' }}>
              <b>{c.company || c.name}</b> <span className="muted small">{c.name}, <a href={`mailto:${c.email}`}>{c.email}</a>{c.phone ? `, ${c.phone}` : ''}, asked {c.terms_requested_at.slice(0, 10)}</span>
              <p className="small" style={{ whiteSpace: 'pre-wrap', margin: '6px 0' }}>{c.terms_request_note || 'No note.'}</p>
              <p className="small muted" style={{ margin: '0 0 6px' }}>Before approving: check the company is real (SAM.gov, state business search, its website), call a supplier reference, and consider a credit report. {c.orders ? `${c.orders} order(s) so far, ${usd(c.ordered_total)}.` : 'No orders yet.'}</p>
              <div className="row">
                <button className="primary" onClick={() => put(c, { net_terms_days: 30 }, `${c.company || c.name} approved for net 30.`)}>Approve net 30</button>
                <button onClick={() => put(c, { decline_terms: true }, 'Request declined. Email them to let them know.')}>Decline</button>
              </div>
            </div>
          ))}
        </div>
      )}
      <div className="panel">
        <h2 style={{ marginTop: 0 }}>All accounts ({rows.length})</h2>
        {!rows.length ? <p className="small muted">No customer accounts yet.</p> : (
          <div style={{ overflowX: 'auto' }}>
            <table className="small">
              <thead><tr><th>Customer</th><th>Since</th><th>Orders</th><th>Ordered</th><th>Unpaid invoices</th><th>Terms</th><th>Your notes</th><th></th></tr></thead>
              <tbody>{rows.map((c) => (
                <tr key={c.id} style={{ opacity: c.active ? 1 : 0.5 }}>
                  <td><b>{c.company || c.name}</b><div className="muted">{c.name}, <a href={`mailto:${c.email}`}>{c.email}</a>{c.phone ? `, ${c.phone}` : ''}</div></td>
                  <td>{c.since}<div className="muted">{c.last_login ? `seen ${c.last_login.slice(0, 10)}` : ''}</div></td>
                  <td className="mono">{c.orders}<span className="muted"> of {c.requests}</span></td>
                  <td className="mono">{usd(c.ordered_total)}</td>
                  <td className="mono">{c.owed ? usd(c.owed) : ''}</td>
                  <td><select value={c.net_terms_days} onChange={(e) => put(c, { net_terms_days: Number(e.target.value) }, `Terms for ${c.company || c.name}: ${TERMS.find(([d]) => d === Number(e.target.value))[1]}.`)}>
                    {TERMS.map(([d, l]) => <option key={d} value={d}>{l}</option>)}</select></td>
                  <td><Notes c={c} save={(v) => put(c, { staff_notes: v }, 'Notes saved.')} /></td>
                  <td><button className="link" onClick={() => { if (!c.active || confirm(`Turn off ${c.email}? They are signed out and cannot sign in.`)) put(c, { active: !c.active }, c.active ? 'Account turned off.' : 'Account turned on.') }}>{c.active ? 'Turn off' : 'Turn on'}</button></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}

function Notes({ c, save }) {
  const [v, setV] = useState(c.staff_notes)
  useEffect(() => setV(c.staff_notes), [c.staff_notes])
  return <input value={v} placeholder="Credit checked, references" onChange={(e) => setV(e.target.value)} onBlur={() => v !== c.staff_notes && save(v)} style={{ minWidth: 160 }} />
}
