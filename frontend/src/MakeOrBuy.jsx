import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from './api'

const usd = (n) => (n == null ? '' : `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`)
const LEVEL = { ok: 'okline', info: 'muted', warn: 'due-soon', bad: 'due-soon' }

// "10: 42.50, 100: 18" -> [{quantity: 10, unit_price: 42.5}, ...]
const parsePrices = (t) => t.split(/[,;\n]+/).map((x) => x.trim()).filter(Boolean).map((x) => {
  const m = x.match(/^(\d+)\s*(?:pcs?|ea)?\s*[:@=x]?\s*\$?\s*([\d.]+)$/i)
  return m ? { quantity: Number(m[1]), unit_price: Number(m[2]) } : null
})

const blank = { organization_id: '', vendor_name: '', prices: '', tooling_charge: '', freight: '', lead_days: '', quote_ref: '', notes: '' }

export default function MakeOrBuy({ quoteId, refreshKey }) {
  const [d, setD] = useState(null)
  const [orgs, setOrgs] = useState([])
  const [f, setF] = useState(blank)
  const [editing, setEditing] = useState(null)
  const [err, setErr] = useState('')
  const [open, setOpen] = useState(false)

  const load = () => api.get(`/api/pricing/quotes/${quoteId}/make-or-buy`).then((r) => { setD(r); if (r.vendor_quotes.length) setOpen(true) }).catch((e) => setErr(e.message))
  useEffect(() => { if (quoteId) load() }, [quoteId, refreshKey])
  useEffect(() => {
    api.get('/api/crm/organizations?kind=vendor').then((v) => {
      api.get('/api/crm/organizations?kind=teaming_partner').then((t) => setOrgs([...v, ...t])).catch(() => setOrgs(v))
    }).catch(() => {})
  }, [])
  if (!quoteId || !d) return null

  const submit = async () => {
    setErr('')
    const prices = parsePrices(f.prices)
    if (!prices.length || prices.some((p) => !p)) { setErr('Enter prices as quantity: unit price, separated by commas. Example: 10: 42.50, 100: 18'); return }
    const body = {
      organization_id: f.organization_id ? Number(f.organization_id) : null, vendor_name: f.vendor_name, prices,
      tooling_charge: Number(f.tooling_charge) || 0, freight: Number(f.freight) || 0,
      lead_days: f.lead_days === '' ? null : Number(f.lead_days), quote_ref: f.quote_ref, notes: f.notes,
    }
    try {
      setD(editing ? await api.put(`/api/pricing/quotes/${quoteId}/vendor-quotes/${editing}`, body) : await api.post(`/api/pricing/quotes/${quoteId}/vendor-quotes`, body))
      setF(blank); setEditing(null)
    } catch (e) { setErr(e.message) }
  }
  const edit = (v) => {
    setEditing(v.id)
    setF({ organization_id: v.organization_id || '', vendor_name: v.organization_id ? '' : v.vendor_name, prices: v.prices.map((p) => `${p.quantity}: ${p.unit_price}`).join(', '),
      tooling_charge: v.tooling_charge || '', freight: v.freight || '', lead_days: v.lead_days ?? '', quote_ref: v.quote_ref, notes: v.notes })
  }
  const del = async (v) => { if (confirm(`Delete the quote from ${v.vendor_name}?`)) setD(await api.del(`/api/pricing/quotes/${quoteId}/vendor-quotes/${v.id}`)) }

  return (
    <div className="panel">
      <div className="row spread">
        <h2 style={{ margin: 0 }}>Make or buy</h2>
        <button className="link" onClick={() => setOpen(!open)}>{open ? 'Hide' : d.vendor_quotes.length ? `${d.vendor_quotes.length} vendor quote(s)` : 'Add an outside shop quote'}</button>
      </div>
      {!open && <p className="small muted" style={{ marginBottom: 0 }}>Compare this estimate with what a machine shop or fabricator would charge you, plus your {Math.round(d.markup * 100)}% markup and handling.</p>}
      {open && (
        <>
          {err && <div className="err">{err}</div>}
          {d.comparison.some((r) => r.buy.length) && (
            <table style={{ marginTop: 10 }}>
              <thead><tr><th>Qty</th><th>Make (your price)</th><th>Buy (best vendor, your price)</th><th>Cheaper</th></tr></thead>
              <tbody>
                {d.comparison.map((r) => (
                  <tr key={r.quantity}>
                    <td className="mono">{r.quantity}</td>
                    <td className="mono">{usd(r.make.unit_price)} <span className="muted small">{r.make.lead_time_days}d</span></td>
                    <td className="mono">{r.best_buy ? <>{usd(r.best_buy.unit_price)} <span className="muted small">{r.best_buy.vendor} at {usd(r.best_buy.vendor_unit)}{r.best_buy.lead_time_days != null ? `, ${r.best_buy.lead_time_days}d` : ''}</span></> : '—'}</td>
                    <td><span className={`badge ${r.cheaper === 'buy' ? 'b-eligible_once_certified' : 'b-eligible_now'}`}>{r.cheaper === 'buy' ? 'Buy' : 'Make'}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {d.vendor_quotes.map((v) => (
            <div key={v.id} className="opcard">
              <div className="row spread">
                <b>{v.vendor_name}{v.quote_ref && <span className="muted small"> · {v.quote_ref}</span>}</b>
                <div className="row"><button className="link" onClick={() => edit(v)}>Edit</button><button className="link" onClick={() => del(v)}>Delete</button></div>
              </div>
              <div className="small mono">{v.prices.map((p) => `${p.quantity} @ ${usd(p.unit_price)}`).join('   ')}{v.tooling_charge ? `   tooling ${usd(v.tooling_charge)}` : ''}{v.freight ? `   freight ${usd(v.freight)}` : ''}{v.lead_days != null ? `   ${v.lead_days} days` : ''}</div>
              <ul className="clean small" style={{ marginTop: 6 }}>
                {(d.nmr[String(v.id)] || []).map((n, i) => <li key={i} className={LEVEL[n.level]}>{n.text}</li>)}
              </ul>
            </div>
          ))}
          {!d.vendor_quotes.length && <ul className="clean small" style={{ marginTop: 8 }}>{d.nmr_general.map((n, i) => <li key={i} className={LEVEL[n.level]}>{n.text}</li>)}</ul>}

          <h3>{editing ? 'Edit vendor quote' : 'Add a vendor quote'}</h3>
          <div className="grid g3">
            <label className="f">Saved vendor
              <select value={f.organization_id} onChange={(e) => setF({ ...f, organization_id: e.target.value })}>
                <option value="">Not saved (type a name)</option>
                {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
              </select>
            </label>
            {!f.organization_id && <label className="f">Vendor name<input value={f.vendor_name} onChange={(e) => setF({ ...f, vendor_name: e.target.value })} placeholder="Shop name" /></label>}
            <label className="f" style={{ gridColumn: f.organization_id ? 'span 2' : 'span 1' }}>Prices (qty: unit price)<input value={f.prices} onChange={(e) => setF({ ...f, prices: e.target.value })} placeholder="10: 42.50, 100: 18" /></label>
            <label className="f">Tooling / setup $<input type="number" value={f.tooling_charge} onChange={(e) => setF({ ...f, tooling_charge: e.target.value })} /></label>
            <label className="f">Inbound freight $<input type="number" value={f.freight} onChange={(e) => setF({ ...f, freight: e.target.value })} /></label>
            <label className="f">Lead time (days)<input type="number" value={f.lead_days} onChange={(e) => setF({ ...f, lead_days: e.target.value })} /></label>
            <label className="f">Their quote #<input value={f.quote_ref} onChange={(e) => setF({ ...f, quote_ref: e.target.value })} /></label>
            <label className="f" style={{ gridColumn: 'span 2' }}>Notes<input value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} placeholder="Material certs included, ships in 3 weeks" /></label>
          </div>
          <div className="row" style={{ marginTop: 8 }}>
            <button className="primary" onClick={submit}>{editing ? 'Update' : 'Add vendor quote'}</button>
            {editing && <button className="link" onClick={() => { setEditing(null); setF(blank) }}>Cancel</button>}
            <span className="small muted">Save vendors in <Link to="/contacts">Contacts</Link> with their size and manufacturer status so the set-aside check can use them.</span>
          </div>
        </>
      )}
    </div>
  )
}
