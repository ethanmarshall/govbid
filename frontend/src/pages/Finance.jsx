import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, fmtDue, qs } from '../api'

const usd = (n) => (n == null || n === '' ? '' : `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`)
const today = () => new Date().toISOString().slice(0, 10)
const STATUS_LABEL = { draft: 'Draft', submitted: 'Submitted', rejected: 'Rejected', accepted: 'Accepted', paid: 'Paid' }

export default function Finance() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || 'invoices'
  const [meta, setMeta] = useState(null)
  const [err, setErr] = useState('')
  const loadMeta = () => api.get('/api/finance/meta').then(setMeta).catch((e) => setErr(e.message))
  useEffect(() => { loadMeta() }, [])
  if (err) return <div className="err">{err}</div>
  if (!meta) return <p className="muted">Loading…</p>
  const go = (t, extra = {}) => setParams({ tab: t, ...extra })
  return (
    <>
      <h1>Finance</h1>
      <p className="sub">Track what you submit in PIEE (WAWF), when the Prompt Payment Act says you should be paid, bookkeeping exports and your loans. This app does not log in to PIEE; you record each step here after doing it there. Everything stays on this computer.</p>
      <div className="tabs">
        {[['invoices', 'Invoices'], ['aging', 'Aging'], ['exports', 'Exports'], ['loans', 'Loans']].map(([k, l]) => (
          <button key={k} className={tab === k ? 'on' : ''} onClick={() => go(k)}>{l}</button>
        ))}
      </div>
      {tab === 'invoices' && <Invoices meta={meta} selId={params.get('id')} onSelect={(id) => go('invoices', id ? { id } : {})} reloadMeta={loadMeta} />}
      {tab === 'aging' && <Aging onOpen={(id) => go('invoices', { id })} />}
      {tab === 'exports' && <Exports />}
      {tab === 'loans' && <Loans meta={meta} selId={params.get('id')} onSelect={(id) => go('loans', id ? { id } : {})} />}
    </>
  )
}

// ------------------------------------------------------------------ invoices
function Invoices({ meta, selId, onSelect, reloadMeta }) {
  const [rows, setRows] = useState(null)
  const [jobs, setJobs] = useState([])
  const [filter, setFilter] = useState('')
  const [jobPick, setJobPick] = useState('')
  const [err, setErr] = useState('')
  const load = () => api.get(`/api/finance/invoices?${qs({ status: filter })}`).then(setRows).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [filter])
  useEffect(() => { api.get('/api/finance/jobs').then(setJobs).catch(() => {}) }, [])

  const create = async () => {
    setErr('')
    try {
      const inv = await api.post('/api/finance/invoices', jobPick ? { job_id: Number(jobPick) } : {})
      await load(); reloadMeta(); onSelect(inv.id)
    } catch (e) { setErr(e.message) }
  }

  return (
    <>
      {err && <div className="err">{err}</div>}
      <RateNotice meta={meta} />
      <div className="panel">
        <div className="row spread">
          <div className="row">
            {['', ...meta.statuses].map((s) => (
              <button key={s || 'all'} className={`chip ${filter === s ? 'on' : ''}`} onClick={() => setFilter(s)}>{s ? STATUS_LABEL[s] : 'All'}</button>
            ))}
          </div>
          <div className="row">
            <select value={jobPick} onChange={(e) => setJobPick(e.target.value)}>
              <option value="">No job (blank invoice)</option>
              {jobs.map((j) => <option key={j.id} value={j.id}>{j.title || `Job ${j.id}`} {j.contract_number ? `(${j.contract_number})` : ''}</option>)}
            </select>
            <button className="primary" onClick={create}>New invoice ({meta.settings.next_number_preview})</button>
          </div>
        </div>
        {rows == null ? <p className="muted">Loading…</p> : rows.length === 0 ? <p className="muted">No invoices yet. Pick a job to copy its contract number, CLINs and ship date.</p> : (
          <table>
            <thead><tr><th>Number</th><th>Customer</th><th>Contract</th><th>Type</th><th>Status</th><th>Submitted</th><th>Payment due</th><th style={{ textAlign: 'right' }}>Total</th><th style={{ textAlign: 'right' }}>Balance</th></tr></thead>
            <tbody>
              {rows.map((r) => {
                const late = r.interest.days_late > 0 && r.status !== 'paid'
                return (
                  <tr key={r.id} onClick={() => onSelect(r.id)} style={{ cursor: 'pointer', background: String(r.id) === String(selId) ? '#f1ece3' : undefined }}>
                    <td className="mono">{r.number}</td>
                    <td>{r.customer}</td>
                    <td className="mono">{r.contract_number}{r.delivery_order ? ` / ${r.delivery_order}` : ''}</td>
                    <td className="small">{r.doc_type_label}</td>
                    <td><span className="tag">{STATUS_LABEL[r.status]}</span></td>
                    <td>{r.submitted_date ? fmtDue(r.submitted_date) : ''}</td>
                    <td className={late ? 'due-soon' : ''}>{r.prompt_payment.due_date ? fmtDue(r.prompt_payment.due_date) : ''}{late ? ` (${r.interest.days_late}d late)` : ''}</td>
                    <td style={{ textAlign: 'right' }}>{usd(r.total)}</td>
                    <td style={{ textAlign: 'right' }}>{r.status === 'draft' ? '' : usd(r.balance)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
      {selId && <InvoiceEditor key={selId} id={selId} meta={meta} jobs={jobs} onChanged={load} onClose={() => onSelect(null)} />}
      <SettingsPanel meta={meta} onSaved={reloadMeta} />
    </>
  )
}

function RateNotice({ meta }) {
  return (
    <div className="notice small">
      Prompt Payment interest rate: {meta.current_rate == null ? 'not set' : meta.current_rate_note}. Treasury sets it every six months at{' '}
      <a href={meta.rate_source_url} target="_blank" rel="noreferrer">fiscal.treasury.gov</a>. Add each new period in the settings at the bottom of this tab.
    </div>
  )
}

function InvoiceEditor({ id, meta, jobs, onChanged, onClose }) {
  const [inv, setInv] = useState(null)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [act, setAct] = useState({ status: 'submitted', date: today(), note: '', amount_paid: '', interest_paid: '' })
  useEffect(() => { api.get(`/api/finance/invoices/${id}`).then(setInv).catch((e) => setErr(e.message)) }, [id])
  if (err && !inv) return <div className="err">{err}</div>
  if (!inv) return <p className="muted">Loading…</p>

  const set = (k) => (e) => setInv({ ...inv, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const setLine = (i, k, v) => setInv({ ...inv, lines: inv.lines.map((l, j) => (j === i ? { ...l, [k]: v } : l)) })
  const total = inv.lines.reduce((s, l) => s + (l.quantity !== '' && l.quantity != null && l.unit_price !== '' && l.unit_price != null ? Number(l.quantity) * Number(l.unit_price) : Number(l.amount || 0)), 0)
  const docType = meta.doc_types.find((d) => d.key === inv.doc_type)
  const pp = inv.prompt_payment

  const save = async () => {
    setMsg(''); setErr('')
    try {
      const body = { ...inv, acceptance_period_days: Number(inv.acceptance_period_days) || 7, job_id: inv.job_id ? Number(inv.job_id) : null,
        amount_paid: inv.amount_paid === '' ? null : inv.amount_paid, interest_paid: inv.interest_paid === '' ? null : inv.interest_paid }
      setInv(await api.put(`/api/finance/invoices/${id}`, body)); setMsg('Saved.'); onChanged()
    } catch (e) { setErr(e.message) }
  }
  const record = async () => {
    setMsg(''); setErr('')
    try {
      const body = { status: act.status, date: act.date, note: act.note }
      if (act.status === 'rejected') body.rejection_reason = act.note
      if (act.status === 'paid') {
        if (act.amount_paid !== '') body.amount_paid = Number(act.amount_paid)
        if (act.interest_paid !== '') body.interest_paid = Number(act.interest_paid)
      }
      setInv(await api.post(`/api/finance/invoices/${id}/status`, body)); setMsg(`Recorded: ${STATUS_LABEL[act.status]}.`); onChanged()
    } catch (e) { setErr(e.message) }
  }
  const remove = async () => {
    if (!confirm(`Delete invoice ${inv.number}?`)) return
    await api.del(`/api/finance/invoices/${id}`); onChanged(); onClose()
  }

  return (
    <div className="panel">
      <div className="row spread">
        <h2 style={{ margin: 0 }}>Invoice {inv.number} <span className="tag">{STATUS_LABEL[inv.status]}</span></h2>
        <div className="row">
          <a href={`/api/finance/invoices/${id}/document.docx`}><button>Invoice document (.docx)</button></a>
          <button className="link" onClick={remove}>Delete</button>
          <button className="link" onClick={onClose}>Close</button>
        </div>
      </div>
      {msg && <div className="okmsg">{msg}</div>}
      {err && <div className="err">{err}</div>}
      {inv.status === 'rejected' && <div className="err">Rejected in PIEE{inv.rejection_reason ? `: ${inv.rejection_reason}` : ''}. Correct it, resubmit in PIEE, then record "Submitted" with the resubmission date. The payment clock restarts from the new receipt.</div>}

      <div className="grid g4">
        <label className="f">Invoice number<input value={inv.number} onChange={set('number')} /></label>
        <label className="f">Job
          <select value={inv.job_id || ''} onChange={set('job_id')}>
            <option value="">None</option>
            {jobs.map((j) => <option key={j.id} value={j.id}>{j.title || `Job ${j.id}`}</option>)}
          </select>
        </label>
        <label className="f">Customer<input value={inv.customer} onChange={set('customer')} /></label>
        <label className="f">PIEE document type
          <select value={inv.doc_type} onChange={set('doc_type')}>
            {meta.doc_types.map((d) => <option key={d.key} value={d.key}>{d.label}</option>)}
          </select>
        </label>
        <label className="f">Contract number<input className="mono" value={inv.contract_number} onChange={set('contract_number')} /></label>
        <label className="f">Delivery / task order<input className="mono" value={inv.delivery_order} onChange={set('delivery_order')} /></label>
        <label className="f">Shipment number<input className="mono" value={inv.shipment_number} onChange={set('shipment_number')} /></label>
        <label className="f">Invoice date<input type="date" value={inv.invoice_date} onChange={set('invoice_date')} /></label>
      </div>
      {docType && <p className="small muted">{docType.when}{docType.source ? ` (${docType.source})` : ''} The contract's WAWF payment instructions (DFARS 252.232-7006) have the final say.</p>}
      {inv.job_id && <p className="small"><Link to={`/jobs?id=${inv.job_id}`}>Open the job</Link></p>}

      <h3>Lines</h3>
      <table>
        <thead><tr><th>CLIN</th><th>Description</th><th>Qty</th><th>Unit</th><th>Unit price</th><th style={{ textAlign: 'right' }}>Amount</th><th /></tr></thead>
        <tbody>
          {inv.lines.map((l, i) => (
            <tr key={i}>
              <td><input className="mono" style={{ width: 70 }} value={l.clin} onChange={(e) => setLine(i, 'clin', e.target.value)} /></td>
              <td><input style={{ width: '100%' }} value={l.description} onChange={(e) => setLine(i, 'description', e.target.value)} /></td>
              <td><input type="number" style={{ width: 80 }} value={l.quantity ?? ''} onChange={(e) => setLine(i, 'quantity', e.target.value)} /></td>
              <td><input style={{ width: 50 }} value={l.unit} onChange={(e) => setLine(i, 'unit', e.target.value)} /></td>
              <td><input type="number" step="0.01" style={{ width: 100 }} value={l.unit_price ?? ''} onChange={(e) => setLine(i, 'unit_price', e.target.value)} /></td>
              <td style={{ textAlign: 'right' }}>{usd(l.quantity !== '' && l.quantity != null && l.unit_price !== '' && l.unit_price != null ? Number(l.quantity) * Number(l.unit_price) : l.amount)}</td>
              <td><button className="link" onClick={() => setInv({ ...inv, lines: inv.lines.filter((_, j) => j !== i) })}>Remove</button></td>
            </tr>
          ))}
          <tr><td colSpan={5}><button className="link" onClick={() => setInv({ ...inv, lines: [...inv.lines, { clin: '', description: '', quantity: 1, unit: 'EA', unit_price: '', amount: 0 }] })}>Add line</button></td>
            <td style={{ textAlign: 'right', fontWeight: 600 }}>{usd(total)}</td><td /></tr>
        </tbody>
      </table>

      <h3>Dates and Prompt Payment</h3>
      <div className="grid g4">
        <label className="f">Ship / service completion date<input type="date" value={inv.ship_date} onChange={set('ship_date')} /></label>
        <label className="f">Submitted in PIEE<input type="date" value={inv.submitted_date} onChange={set('submitted_date')} /></label>
        <label className="f">Acceptance date<input type="date" value={inv.acceptance_date} onChange={set('acceptance_date')} /></label>
        <label className="f">Acceptance period (days)<input type="number" value={inv.acceptance_period_days} onChange={set('acceptance_period_days')} /></label>
        <label className="f">Payment date set by contract (optional)<input type="date" value={inv.due_date_override} onChange={set('due_date_override')} /></label>
        <label className="f">Paid date<input type="date" value={inv.paid_date} onChange={set('paid_date')} /></label>
        <label className="f">Amount paid<input type="number" step="0.01" value={inv.amount_paid ?? ''} onChange={set('amount_paid')} /></label>
        <label className="f">Interest received<input type="number" step="0.01" value={inv.interest_paid ?? ''} onChange={set('interest_paid')} /></label>
      </div>
      <label className="row small" style={{ marginTop: 8 }}><input type="checkbox" checked={inv.disputed} onChange={set('disputed')} /> Disagreement over quantity, quality or compliance (no constructive acceptance)</label>
      <div className="grid g2" style={{ marginTop: 10 }}>
        <label className="f">Notes<textarea rows={2} value={inv.notes} onChange={set('notes')} /></label>
        <label className="f">Rejection reason<textarea rows={2} value={inv.rejection_reason} onChange={set('rejection_reason')} /></label>
      </div>
      <div className="row" style={{ marginTop: 10 }}><button className="primary" onClick={save}>Save invoice</button><span className="small muted">Prompt Payment figures below update after saving.</span></div>

      <div className="guidance">
        {pp.due_date ? (
          <>
            <div><b>Payment due {fmtDue(pp.due_date)}</b>{pp.estimate ? ' (estimate until acceptance is recorded)' : ''}. {pp.basis}</div>
            {pp.penalty_free_through !== pp.due_date && <div>Falls on a weekend or holiday, so payment by {fmtDue(pp.penalty_free_through)} carries no interest.</div>}
            <div>Accelerated payment goal for small business: {fmtDue(pp.accelerated_goal)} (FAR 32.009-1, a goal only).</div>
            {inv.interest.days_late > 0 && (
              <div className="due-soon">
                {inv.interest.days_late} days late. Late payment interest {inv.status === 'paid' ? 'owed' : 'accrued so far'}: {inv.interest.rate == null ? 'needs a stored rate' : usd(inv.interest.payable)} {inv.interest.rate_note ? `at ${inv.interest.rate_note}` : ''}. {inv.interest.note}
              </div>
            )}
          </>
        ) : <div>{pp.basis} Record the PIEE submission to start the payment clock.</div>}
      </div>

      <h3>Record a PIEE step</h3>
      <div className="row">
        <select value={act.status} onChange={(e) => setAct({ ...act, status: e.target.value })}>
          {meta.statuses.filter((s) => s !== 'draft').map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
        </select>
        <input type="date" value={act.date} onChange={(e) => setAct({ ...act, date: e.target.value })} />
        <input placeholder={act.status === 'rejected' ? 'Rejection reason' : 'Note'} value={act.note} onChange={(e) => setAct({ ...act, note: e.target.value })} style={{ minWidth: 240 }} />
        {act.status === 'paid' && <>
          <input type="number" step="0.01" placeholder={`Amount (${usd(inv.total)})`} value={act.amount_paid} onChange={(e) => setAct({ ...act, amount_paid: e.target.value })} style={{ width: 140 }} />
          <input type="number" step="0.01" placeholder="Interest received" value={act.interest_paid} onChange={(e) => setAct({ ...act, interest_paid: e.target.value })} style={{ width: 140 }} />
        </>}
        <button onClick={record}>Record</button>
      </div>
      {inv.history.length > 0 && (
        <ul className="clean small" style={{ marginTop: 10 }}>
          {inv.history.map((h, i) => <li key={i}><span className="mono">{h.date}</span> {STATUS_LABEL[h.status] || h.status}{h.note ? `: ${h.note}` : ''}</li>)}
        </ul>
      )}
    </div>
  )
}

function SettingsPanel({ meta, onSaved }) {
  const [s, setS] = useState(meta.settings)
  const [open, setOpen] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const set = (k) => (e) => setS({ ...s, [k]: e.target.value })
  const setRate = (i, k, v) => setS({ ...s, prompt_pay_rates: s.prompt_pay_rates.map((r, j) => (j === i ? { ...r, [k]: v } : r)) })
  const save = async () => {
    setMsg(''); setErr('')
    try {
      const body = { ...s, next_invoice_seq: Number(s.next_invoice_seq), seq_width: Number(s.seq_width),
        prompt_pay_rates: s.prompt_pay_rates.filter((r) => r.start && r.rate !== '').map((r) => ({ ...r, rate: Number(r.rate) })) }
      setS(await api.put('/api/finance/settings', body)); setMsg('Settings saved.'); onSaved()
    } catch (e) { setErr(e.message) }
  }
  return (
    <div className="panel">
      <div className="row spread"><h3 style={{ margin: 0 }}>Invoice numbering and Prompt Payment rate</h3><button className="link" onClick={() => setOpen(!open)}>{open ? 'Hide' : 'Show'}</button></div>
      {open && <>
        {msg && <div className="okmsg">{msg}</div>}
        {err && <div className="err">{err}</div>}
        <div className="grid g4" style={{ marginTop: 10 }}>
          <label className="f">Prefix<input value={s.invoice_prefix} onChange={set('invoice_prefix')} /></label>
          <label className="f">Next number<input type="number" value={s.next_invoice_seq} onChange={set('next_invoice_seq')} /></label>
          <label className="f">Digits<input type="number" value={s.seq_width} onChange={set('seq_width')} /></label>
          <label className="f">Payment terms<input value={s.payment_terms} onChange={set('payment_terms')} /></label>
        </div>
        <div className="grid g2" style={{ marginTop: 10 }}>
          <label className="f">Remit-to address (printed on invoice documents)<textarea rows={3} value={s.remit_to} onChange={set('remit_to')} /></label>
          <label className="f">Invoice footer<textarea rows={3} value={s.invoice_footer} onChange={set('invoice_footer')} /></label>
        </div>
        <h3>Prompt Payment interest rates</h3>
        <p className="small muted">Copy each period from <a href={meta.rate_source_url} target="_blank" rel="noreferrer">fiscal.treasury.gov/prompt-payment/rates.html</a>. Late interest uses the rate in effect the day after the due date.</p>
        <table>
          <thead><tr><th>Start</th><th>End</th><th>Rate %</th><th>Source</th><th /></tr></thead>
          <tbody>
            {s.prompt_pay_rates.map((r, i) => (
              <tr key={i}>
                <td><input type="date" value={r.start} onChange={(e) => setRate(i, 'start', e.target.value)} /></td>
                <td><input type="date" value={r.end} onChange={(e) => setRate(i, 'end', e.target.value)} /></td>
                <td><input type="number" step="0.001" style={{ width: 90 }} value={r.rate} onChange={(e) => setRate(i, 'rate', e.target.value)} /></td>
                <td><input value={r.source || ''} onChange={(e) => setRate(i, 'source', e.target.value)} /></td>
                <td><button className="link" onClick={() => setS({ ...s, prompt_pay_rates: s.prompt_pay_rates.filter((_, j) => j !== i) })}>Remove</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="row" style={{ marginTop: 10 }}>
          <button onClick={() => setS({ ...s, prompt_pay_rates: [...s.prompt_pay_rates, { start: '', end: '', rate: '', source: 'fiscal.treasury.gov' }] })}>Add rate period</button>
          <button className="primary" onClick={save}>Save settings</button>
        </div>
        <h3>Rules used</h3>
        <ul className="small">{meta.rules.map((r, i) => <li key={i}>{r}</li>)}</ul>
      </>}
    </div>
  )
}

// ------------------------------------------------------------------ aging
const SUB_LABELS = { '0-30': '0 to 30 days', '31-60': '31 to 60 days', '61-90': '61 to 90 days', '90+': 'Over 90 days' }
const DUE_LABELS = { not_due: 'Not yet due', '1-15': '1 to 15 days late', '16-30': '16 to 30 days late', '31-60': '31 to 60 days late', '60+': 'Over 60 days late' }

function Aging({ onOpen }) {
  const [a, setA] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { api.get('/api/finance/aging').then(setA).catch((e) => setErr(e.message)) }, [])
  if (err) return <div className="err">{err}</div>
  if (!a) return <p className="muted">Loading…</p>
  const st = a.payment_stats
  return (
    <>
      <div className="grid g4" style={{ marginBottom: 16 }}>
        <div className="stat"><div className="n">{usd(a.total_outstanding)}</div><div className="l">Outstanding ({a.invoices.length} invoices)</div></div>
        <div className="stat"><div className={`n ${a.total_past_due ? 'due-soon' : ''}`}>{usd(a.total_past_due)}</div><div className="l">Past payment due date</div></div>
        <div className="stat"><div className="n">{st.count ? `${st.average_days} d` : 'n/a'}</div><div className="l">Average submit to paid{st.count ? ` (median ${st.median_days}, ${st.min_days} to ${st.max_days})` : ''}</div></div>
        <div className="stat"><div className="n">{st.count ? `${st.on_time_pct}%` : 'n/a'}</div><div className="l">Paid on time{st.count ? ` (${st.on_time} of ${st.count})` : ''}</div></div>
      </div>
      <div className="grid g2">
        <div className="panel">
          <h3>By days since PIEE submission</h3>
          <table><tbody>{Object.entries(a.by_submission_age).map(([k, v]) => <tr key={k}><td>{SUB_LABELS[k]}</td><td>{v.count}</td><td style={{ textAlign: 'right' }}>{usd(v.amount)}</td></tr>)}</tbody></table>
        </div>
        <div className="panel">
          <h3>By days past payment due date</h3>
          <table><tbody>{Object.entries(a.by_past_due).map(([k, v]) => <tr key={k} className={k !== 'not_due' && v.count ? 'due-soon' : ''}><td>{DUE_LABELS[k]}</td><td>{v.count}</td><td style={{ textAlign: 'right' }}>{usd(v.amount)}</td></tr>)}</tbody></table>
          {a.interest_accrued > 0 && <p className="small">Estimated late interest accrued if paid today: {usd(a.interest_accrued)}. The paying office adds it automatically.</p>}
        </div>
      </div>
      <div className="panel">
        <h3>Outstanding invoices</h3>
        {a.invoices.length === 0 ? <p className="muted">Nothing outstanding.</p> : (
          <table>
            <thead><tr><th>Number</th><th>Customer</th><th>Submitted</th><th>Days out</th><th>Payment due</th><th>Days late</th><th style={{ textAlign: 'right' }}>Balance</th></tr></thead>
            <tbody>{a.invoices.map((r) => (
              <tr key={r.id} onClick={() => onOpen(r.id)} style={{ cursor: 'pointer' }}>
                <td className="mono">{r.number}</td><td>{r.customer}</td><td>{fmtDue(r.submitted_date)}</td><td>{r.days_since_submission}</td>
                <td>{fmtDue(r.prompt_payment.due_date)}</td><td className={r.days_past_due ? 'due-soon' : ''}>{r.days_past_due || ''}</td>
                <td style={{ textAlign: 'right' }}>{usd(r.balance)}</td>
              </tr>
            ))}</tbody>
          </table>
        )}
      </div>
      {a.rejected.length > 0 && (
        <div className="panel">
          <h3>Rejected, waiting to be resubmitted</h3>
          <ul className="clean">{a.rejected.map((r) => <li key={r.id}><button className="link" onClick={() => onOpen(r.id)}>{r.number}</button> {r.customer} {usd(r.total)}{r.rejection_reason ? `: ${r.rejection_reason}` : ''}</li>)}</ul>
        </div>
      )}
    </>
  )
}

// ------------------------------------------------------------------ exports
function Exports() {
  const [range, setRange] = useState({ start: '', end: '' })
  const [drafts, setDrafts] = useState(false)
  const q = qs({ ...range })
  const qi = qs({ ...range, include_drafts: drafts ? 'true' : '' })
  const files = [
    { name: 'QuickBooks Online invoices', href: `/api/finance/export/quickbooks-invoices.csv?${qi}`,
      note: 'One row per invoice line, dates as MM/DD/YYYY. QuickBooks requires invoice number, customer, invoice date, due date and item amount, and lets you map columns during import (Settings > Import data > Invoices). Header names follow the style of QuickBooks\' sample file; compare with its "Download sample csv" if a column does not map. Limits: 100 invoices and 1,000 rows per file, and import is unavailable if sales tax is turned on.' },
    { name: 'Wave payments (bank-style transactions)', href: `/api/finance/export/wave-payments.csv?${q}`,
      note: 'Date, Description, Amount for each payment received (interest included). Upload in Wave under Accounting > Transactions > More > Upload transactions and pick these three columns. Wave does not document a CSV invoice import, so use the generic invoice file for reference.' },
    { name: 'Invoices (generic CSV)', href: `/api/finance/export/invoices.csv?${qi}`, note: 'Generic format, not tied to any accounting program. One row per line with PIEE type, dates and totals.' },
    { name: 'Payments received (generic CSV)', href: `/api/finance/export/payments.csv?${q}`, note: 'Generic format. Paid date, invoice, amounts, interest received and days to pay. Filtered by paid date.' },
    { name: 'Loan payments (generic CSV)', href: `/api/finance/export/loan-payments.csv?${q}`, note: 'Generic format. Each loan payment with the principal and interest split, for your bookkeeper.' },
  ]
  return (
    <>
      <div className="panel">
        <div className="row">
          <label className="f">From<input type="date" value={range.start} onChange={(e) => setRange({ ...range, start: e.target.value })} /></label>
          <label className="f">To<input type="date" value={range.end} onChange={(e) => setRange({ ...range, end: e.target.value })} /></label>
          <label className="row small"><input type="checkbox" checked={drafts} onChange={(e) => setDrafts(e.target.checked)} /> Include drafts</label>
        </div>
        <p className="small muted">Invoices filter by invoice date (or submitted date if blank). Payments filter by paid date.</p>
      </div>
      {files.map((f) => (
        <div className="panel" key={f.name}>
          <div className="row spread"><h3 style={{ margin: 0 }}>{f.name}</h3><a href={f.href}><button>Download CSV</button></a></div>
          <p className="small muted" style={{ marginBottom: 0 }}>{f.note}</p>
        </div>
      ))}
    </>
  )
}

// ------------------------------------------------------------------ loans
const blankLoan = { lender: '', program: 'sba_7a', principal: '', rate_type: 'fixed', rate: '', rate_base: '', term_months: 120, start_date: '', first_payment_date: '', amortizing: true, payment_amount: '', balance_basis: 'principal', day_count: 'monthly', status: 'active', notes: '' }

function Loans({ meta, selId, onSelect }) {
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  const [adding, setAdding] = useState(false)
  const load = () => api.get('/api/finance/loans').then(setRows).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [])
  if (err) return <div className="err">{err}</div>
  if (!rows) return <p className="muted">Loading…</p>
  const totalBal = rows.filter((l) => l.status !== 'paid_off').reduce((s, l) => s + l.balance, 0)
  const sel = rows.find((l) => String(l.id) === String(selId))
  return (
    <>
      <div className="panel">
        <div className="row spread">
          <div><b>{usd(totalBal)}</b> <span className="muted">owed across {rows.filter((l) => l.status !== 'paid_off').length} active loans</span></div>
          <button className="primary" onClick={() => { setAdding(true); onSelect(null) }}>Add loan</button>
        </div>
        {rows.length > 0 && (
          <table style={{ marginTop: 10 }}>
            <thead><tr><th>Lender</th><th>Program</th><th>Rate</th><th style={{ textAlign: 'right' }}>Amount</th><th style={{ textAlign: 'right' }}>Balance</th><th style={{ textAlign: 'right' }}>Payment</th><th>Next payment</th></tr></thead>
            <tbody>{rows.map((l) => (
              <tr key={l.id} onClick={() => { setAdding(false); onSelect(l.id) }} style={{ cursor: 'pointer', background: sel?.id === l.id ? '#f1ece3' : undefined }}>
                <td>{l.lender}</td><td>{l.program_label}</td><td>{l.rate}%{l.rate_type === 'variable' ? ` (${l.rate_base || 'variable'})` : ''}</td>
                <td style={{ textAlign: 'right' }}>{usd(l.principal)}</td><td style={{ textAlign: 'right' }}>{usd(l.balance)}</td>
                <td style={{ textAlign: 'right' }}>{usd(l.payment)}</td><td>{l.next_payment_date ? fmtDue(l.next_payment_date) : ''}</td>
              </tr>
            ))}</tbody>
          </table>
        )}
      </div>
      {adding && <LoanForm meta={meta} loan={blankLoan} onSaved={(l) => { setAdding(false); load(); onSelect(l.id) }} onCancel={() => setAdding(false)} />}
      {sel && <LoanDetail key={sel.id} meta={meta} loan={sel} onChanged={load} onDeleted={() => { load(); onSelect(null) }} />}
      <UseOfFunds rows={rows} />
    </>
  )
}

function LoanForm({ meta, loan, onSaved, onCancel }) {
  const [l, setL] = useState({ ...loan, payment_amount: loan.payment_amount ?? '' })
  const [err, setErr] = useState('')
  const set = (k) => (e) => {
    const v = e.target.type === 'checkbox' ? e.target.checked : e.target.value
    const next = { ...l, [k]: v }
    if (k === 'program' && !loan.id) {
      const loc = v === 'line_of_credit'
      next.amortizing = !loc; next.balance_basis = loc ? 'draws' : 'principal'
    }
    setL(next)
  }
  const calc = useMemo(() => {
    const P = Number(l.principal), r = Number(l.rate) / 1200, n = Number(l.term_months)
    if (!P || !n) return null
    return r ? P * r / (1 - (1 + r) ** -n) : P / n
  }, [l.principal, l.rate, l.term_months])
  const save = async () => {
    setErr('')
    const body = { ...l, principal: Number(l.principal) || 0, rate: Number(l.rate) || 0, term_months: Number(l.term_months) || 0,
      payment_amount: l.payment_amount === '' ? null : Number(l.payment_amount) }
    try { onSaved(loan.id ? await api.put(`/api/finance/loans/${loan.id}`, body) : await api.post('/api/finance/loans', body)) } catch (e) { setErr(e.message) }
  }
  return (
    <div className="panel">
      <h3 style={{ marginTop: 0 }}>{loan.id ? 'Edit loan' : 'New loan'}</h3>
      {err && <div className="err">{err}</div>}
      <div className="grid g4">
        <label className="f">Lender<input value={l.lender} onChange={set('lender')} /></label>
        <label className="f">Program<select value={l.program} onChange={set('program')}>{meta.programs.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}</select></label>
        <label className="f">{l.balance_basis === 'draws' ? 'Credit limit' : 'Loan amount'}<input type="number" value={l.principal} onChange={set('principal')} /></label>
        <label className="f">Term (months)<input type="number" value={l.term_months} onChange={set('term_months')} /></label>
        <label className="f">Rate type<select value={l.rate_type} onChange={set('rate_type')}><option value="fixed">Fixed</option><option value="variable">Variable</option></select></label>
        <label className="f">Current rate (annual %)<input type="number" step="0.001" value={l.rate} onChange={set('rate')} /></label>
        <label className="f">Rate base (variable)<input placeholder="Prime + 2.75%, adjusts quarterly" value={l.rate_base} onChange={set('rate_base')} /></label>
        <label className="f">Status<select value={l.status} onChange={set('status')}><option value="active">Active</option><option value="paid_off">Paid off</option></select></label>
        <label className="f">Start date<input type="date" value={l.start_date} onChange={set('start_date')} /></label>
        <label className="f">First payment date<input type="date" value={l.first_payment_date} onChange={set('first_payment_date')} /></label>
        <label className="f">Payment amount (blank = computed{calc ? ` ${usd(calc)}` : ''})<input type="number" step="0.01" value={l.payment_amount} onChange={set('payment_amount')} /></label>
        <label className="f">Balance from<select value={l.balance_basis} onChange={set('balance_basis')}><option value="principal">Loan amount (term loan)</option><option value="draws">Draws (line of credit)</option></select></label>
        <label className="f">Interest method<select value={l.day_count} onChange={set('day_count')}><option value="monthly">Monthly (rate / 12)</option><option value="actual_365">Daily, actual/365</option><option value="actual_360">Daily, actual/360</option></select></label>
      </div>
      <label className="row small" style={{ marginTop: 8 }}><input type="checkbox" checked={l.amortizing} onChange={set('amortizing')} /> Amortizing (level payments of principal and interest). Uncheck for interest only.</label>
      <label className="f" style={{ marginTop: 8 }}>Notes<textarea rows={2} value={l.notes} onChange={set('notes')} /></label>
      <p className="small muted">Check the interest method against your note or lender statement. If a payment split on your statement differs, enter the statement's principal and interest on that payment.</p>
      <div className="row"><button className="primary" onClick={save}>Save loan</button>{onCancel && <button className="link" onClick={onCancel}>Cancel</button>}</div>
    </div>
  )
}

function LoanDetail({ meta, loan, onChanged, onDeleted }) {
  const [view, setView] = useState('activity')
  const [sched, setSched] = useState(null)
  const [draw, setDraw] = useState({ date: today(), amount: '', purpose: '' })
  const [pay, setPay] = useState({ date: today(), amount: '', principal_override: '', interest_override: '', note: '' })
  const [err, setErr] = useState('')
  useEffect(() => { if (view === 'schedule') api.get(`/api/finance/loans/${loan.id}/schedule`).then(setSched).catch((e) => setErr(e.message)) }, [view, loan])
  const run = async (fn) => { setErr(''); try { await fn(); onChanged() } catch (e) { setErr(e.message) } }
  const addDraw = () => run(async () => { await api.post(`/api/finance/loans/${loan.id}/draws`, { ...draw, amount: Number(draw.amount) }); setDraw({ ...draw, amount: '', purpose: '' }) })
  const addPay = () => run(async () => {
    await api.post(`/api/finance/loans/${loan.id}/payments`, { date: pay.date, amount: Number(pay.amount), note: pay.note,
      principal_override: pay.principal_override === '' ? null : Number(pay.principal_override), interest_override: pay.interest_override === '' ? null : Number(pay.interest_override) })
    setPay({ ...pay, amount: '', principal_override: '', interest_override: '', note: '' })
  })
  const remove = async () => { if (confirm('Delete this loan and its draws and payments?')) { await api.del(`/api/finance/loans/${loan.id}`); onDeleted() } }
  return (
    <div className="panel">
      <div className="row spread">
        <h2 style={{ margin: 0 }}>{loan.lender || 'Loan'} <span className="tag">{loan.program_label}</span></h2>
        <button className="link" onClick={remove}>Delete loan</button>
      </div>
      {err && <div className="err">{err}</div>}
      <div className="grid g4" style={{ margin: '12px 0' }}>
        <div className="stat"><div className="n">{usd(loan.balance)}</div><div className="l">Current balance{loan.available != null ? ` (${usd(loan.available)} available)` : ''}</div></div>
        <div className="stat"><div className="n">{usd(loan.payment)}</div><div className="l">{loan.payment_amount != null ? 'Payment (entered)' : loan.amortizing ? 'Payment (computed)' : 'Interest-only estimate'}</div></div>
        <div className="stat"><div className="n">{loan.next_payment_date ? fmtDue(loan.next_payment_date) : 'n/a'}</div><div className="l">Next payment</div></div>
        <div className="stat"><div className="n">{usd(loan.interest_paid)}</div><div className="l">Interest paid ({usd(loan.principal_paid)} principal)</div></div>
      </div>
      <div className="tabs">
        {[['activity', 'Draws and payments'], ['schedule', 'Amortization schedule'], ['edit', 'Edit']].map(([k, lab]) => <button key={k} className={view === k ? 'on' : ''} onClick={() => setView(k)}>{lab}</button>)}
      </div>
      {view === 'edit' && <LoanForm meta={meta} loan={loan} onSaved={() => { onChanged(); setView('activity') }} />}
      {view === 'activity' && (
        <div className="grid g2">
          <div>
            <h3>Draws</h3>
            <div className="row">
              <input type="date" value={draw.date} onChange={(e) => setDraw({ ...draw, date: e.target.value })} />
              <input type="number" placeholder="Amount" style={{ width: 110 }} value={draw.amount} onChange={(e) => setDraw({ ...draw, amount: e.target.value })} />
              <input list="fund-purposes" placeholder="Purpose" value={draw.purpose} onChange={(e) => setDraw({ ...draw, purpose: e.target.value })} />
              <datalist id="fund-purposes">{meta.fund_purposes.map((p) => <option key={p} value={p} />)}</datalist>
              <button onClick={addDraw} disabled={!draw.amount}>Add</button>
            </div>
            <table style={{ marginTop: 8 }}><tbody>{loan.draws.map((d) => (
              <tr key={d.id}><td className="mono">{d.date}</td><td>{d.purpose}</td><td style={{ textAlign: 'right' }}>{usd(d.amount)}</td>
                <td><button className="link" onClick={() => run(() => api.del(`/api/finance/loans/${loan.id}/draws/${d.id}`))}>Remove</button></td></tr>
            ))}</tbody></table>
            {loan.use_of_funds.length > 0 && <><h3>Use of funds</h3><FundsTable items={loan.use_of_funds} /></>}
          </div>
          <div>
            <h3>Payments</h3>
            <div className="row">
              <input type="date" value={pay.date} onChange={(e) => setPay({ ...pay, date: e.target.value })} />
              <input type="number" step="0.01" placeholder={`Amount (${usd(loan.payment)})`} style={{ width: 140 }} value={pay.amount} onChange={(e) => setPay({ ...pay, amount: e.target.value })} />
              <input type="number" step="0.01" placeholder="Principal (optional)" style={{ width: 140 }} value={pay.principal_override} onChange={(e) => setPay({ ...pay, principal_override: e.target.value })} />
              <input type="number" step="0.01" placeholder="Interest (optional)" style={{ width: 130 }} value={pay.interest_override} onChange={(e) => setPay({ ...pay, interest_override: e.target.value })} />
              <button onClick={addPay} disabled={!pay.amount}>Add</button>
            </div>
            <table style={{ marginTop: 8 }}>
              <thead><tr><th>Date</th><th style={{ textAlign: 'right' }}>Amount</th><th style={{ textAlign: 'right' }}>Principal</th><th style={{ textAlign: 'right' }}>Interest</th><th style={{ textAlign: 'right' }}>Balance</th><th /></tr></thead>
              <tbody>{loan.payments.map((p) => (
                <tr key={p.id}><td className="mono">{p.date}</td><td style={{ textAlign: 'right' }}>{usd(p.amount)}</td><td style={{ textAlign: 'right' }}>{usd(p.principal)}</td>
                  <td style={{ textAlign: 'right' }}>{usd(p.interest)}{p.entered_split ? '' : '*'}</td><td style={{ textAlign: 'right' }}>{usd(p.balance_after)}</td>
                  <td><button className="link" onClick={() => run(() => api.del(`/api/finance/loans/${loan.id}/payments/${p.id}`))}>Remove</button></td></tr>
              ))}</tbody>
            </table>
            {loan.payments.some((p) => !p.entered_split) && <p className="small muted">* Split computed by the app. Enter the lender's numbers to override.</p>}
          </div>
        </div>
      )}
      {view === 'schedule' && (sched == null ? <p className="muted">Loading…</p> : (
        <>
          <p className="small">{sched.note} Payment {usd(sched.payment)}. Total interest over the schedule: {usd(sched.total_interest)}.</p>
          <div style={{ maxHeight: 420, overflow: 'auto' }}>
            <table>
              <thead><tr><th>#</th><th>Date</th><th style={{ textAlign: 'right' }}>Payment</th><th style={{ textAlign: 'right' }}>Interest</th><th style={{ textAlign: 'right' }}>Principal</th><th style={{ textAlign: 'right' }}>Balance</th></tr></thead>
              <tbody>{sched.rows.map((r) => (
                <tr key={r.n}><td>{r.n}</td><td className="mono">{r.date}</td><td style={{ textAlign: 'right' }}>{usd(r.payment)}</td><td style={{ textAlign: 'right' }}>{usd(r.interest)}</td>
                  <td style={{ textAlign: 'right' }}>{usd(r.principal)}</td><td style={{ textAlign: 'right' }}>{usd(r.balance)}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </>
      ))}
    </div>
  )
}

function FundsTable({ items }) {
  return (
    <table><tbody>{items.map((u) => (
      <tr key={u.purpose}><td>{u.purpose}</td><td style={{ textAlign: 'right' }}>{usd(u.amount)}</td><td style={{ width: 160 }}><div className="bar"><span style={{ width: `${u.pct}%` }} /></div></td><td className="small">{u.pct}%</td></tr>
    ))}</tbody></table>
  )
}

function UseOfFunds({ rows }) {
  const [all, setAll] = useState(null)
  useEffect(() => { api.get('/api/finance/loans/use-of-funds').then(setAll).catch(() => {}) }, [rows])
  if (!all || all.length === 0) return null
  return <div className="panel"><h3 style={{ marginTop: 0 }}>Use of funds, all loans</h3><FundsTable items={all} /></div>
}
