import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, fmtDue } from '../api'

const usd = (n) => (n == null || n === '' ? '' : `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`)
const label = (s) => (s || '').replace(/_/g, ' ')
const today = () => new Date().toISOString().slice(0, 10)
const numOrNull = (v) => (v === '' || v == null ? null : Number(v))

export default function Jobs() {
  const [params, setParams] = useSearchParams()
  const [meta, setMeta] = useState(null)
  useEffect(() => { api.get('/api/jobs/meta').then(setMeta) }, [])
  if (!meta) return <p className="muted">Loading…</p>
  const id = params.get('id')
  const open = (jid, tab) => setParams(jid ? { id: jid, ...(tab ? { tab } : {}) } : {})
  return id
    ? <JobDetail key={id} id={id} meta={meta} tab={params.get('tab') || 'overview'} onTab={(t) => open(id, t)} onBack={() => open(null)} />
    : <JobList meta={meta} onOpen={open} fromOpp={params.get('from_opp')} />
}

// ------------------------------------------------------------------ list
function JobList({ meta, onOpen, fromOpp }) {
  const [rows, setRows] = useState(null)
  const [m, setM] = useState(null)
  const [status, setStatus] = useState('open')
  const [q, setQ] = useState('')
  const [err, setErr] = useState('')
  const [adding, setAdding] = useState(fromOpp ? 'opp' : '')
  const load = () => {
    api.get('/api/jobs').then(setRows).catch((e) => setErr(e.message))
    api.get('/api/jobs/metrics').then(setM).catch(() => {})
  }
  useEffect(load, [])

  const shown = useMemo(() => (rows || []).filter((r) =>
    (status === 'all' || (status === 'open' ? meta.open_statuses.includes(r.status) : r.status === status)) &&
    (!q || `${r.title} ${r.customer} ${r.contract_number}`.toLowerCase().includes(q.toLowerCase()))), [rows, status, q])

  if (err) return <div className="err">{err}</div>
  if (!rows) return <p className="muted">Loading…</p>
  return (
    <>
      <h1>Jobs</h1>
      <p className="sub">Awarded work from contract to shipment: CLINs, traveler, vendor POs, quality records and the Certificate of Conformance.</p>
      {m && (
        <div className="grid g4" style={{ marginBottom: 16 }}>
          <div className="stat"><div className="n">{m.open_count}</div><div className="l">Open jobs</div></div>
          <div className="stat"><div className="n">{usd(m.open_value) || '$0.00'}</div><div className="l">Open value (not yet shipped)</div></div>
          <div className="stat"><div className="n">{m.on_time_pct == null ? 'n/a' : `${m.on_time_pct}%`}</div><div className="l">On-time delivery ({m.on_time} of {m.shipped_measured} shipped)</div></div>
          <div className="stat"><div className={`n ${m.late_count ? 'due-soon' : ''}`}>{m.late_count}</div><div className="l">Late jobs</div></div>
        </div>
      )}
      <div className="row spread" style={{ marginBottom: 12 }}>
        <div className="row">
          {['open', ...meta.statuses, 'all'].map((s) => (
            <button key={s} className={`chip ${status === s ? 'on' : ''}`} onClick={() => setStatus(s)}>
              {label(s)}{s !== 'open' && s !== 'all' && m ? ` (${m.by_status[s] || 0})` : ''}
            </button>
          ))}
        </div>
        <div className="row">
          <input placeholder="Search title, customer, contract" value={q} onChange={(e) => setQ(e.target.value)} />
          <button onClick={() => setAdding(adding === 'opp' ? '' : 'opp')}>From opportunity</button>
          <button className="primary" onClick={() => setAdding(adding === 'new' ? '' : 'new')}>New job</button>
        </div>
      </div>
      {adding === 'new' && <NewJob onCreated={(j) => onOpen(j.id)} onCancel={() => setAdding('')} />}
      {adding === 'opp' && <FromOpportunity jobs={rows} preset={fromOpp} onCreated={(j) => onOpen(j.id)} onCancel={() => setAdding('')} />}
      <div className="panel" style={{ padding: 0 }}>
        <table>
          <thead><tr><th>Job</th><th>Contract</th><th>Due</th><th>Status</th><th>Value</th><th>Traveler</th></tr></thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.id} className="click" onClick={() => onOpen(r.id)}>
                <td><div className="t">{r.title}</div><div className="small muted">{r.customer}</div></td>
                <td className="mono">{r.contract_number || <span className="muted">not entered</span>}{r.delivery_order && ` / ${r.delivery_order}`}</td>
                <td className={r.late ? 'due-soon' : ''}>{r.due_date ? fmtDue(r.due_date) : <span className="muted">n/a</span>}{r.late && ' (late)'}
                  {r.shipped_date && <div className="small muted">shipped {fmtDue(r.shipped_date)}</div>}</td>
                <td><span className="tag">{label(r.status)}</span></td>
                <td>{usd(r.value ?? r.clin_total)}</td>
                <td className="small">{r.traveler_progress.total ? `${r.traveler_progress.done} / ${r.traveler_progress.total} done` : <span className="muted">none</span>}</td>
              </tr>
            ))}
            {!shown.length && <tr><td colSpan={6} className="muted">No jobs here yet. Start one from a won opportunity or add it by hand.</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  )
}

function NewJob({ onCreated, onCancel }) {
  const [f, setF] = useState({ title: '', customer: '', contract_number: '', award_date: today(), due_date: '' })
  const [err, setErr] = useState('')
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const save = async () => {
    try { onCreated(await api.post('/api/jobs', f)) } catch (e) { setErr(e.message) }
  }
  return (
    <div className="panel">
      <h2>New job</h2>
      {err && <div className="err">{err}</div>}
      <div className="grid g3">
        <label className="f">Title<input value={f.title} onChange={set('title')} /></label>
        <label className="f">Customer (agency, buying office or prime)<input value={f.customer} onChange={set('customer')} /></label>
        <label className="f">Contract number<input value={f.contract_number} onChange={set('contract_number')} /></label>
        <label className="f">Award date<input type="date" value={f.award_date} onChange={set('award_date')} /></label>
        <label className="f">Delivery due<input type="date" value={f.due_date} onChange={set('due_date')} /></label>
      </div>
      <div className="row" style={{ marginTop: 12 }}>
        <button className="primary" onClick={save} disabled={!f.title}>Create job</button>
        <button onClick={onCancel}>Cancel</button>
      </div>
    </div>
  )
}

function FromOpportunity({ jobs, preset, onCreated, onCancel }) {
  const [pipe, setPipe] = useState(null)
  const [f, setF] = useState({ opp: preset || '', contract_number: '', award_date: today(), due_date: '' })
  const [err, setErr] = useState('')
  useEffect(() => { api.get('/api/pipeline').then(setPipe).catch((e) => setErr(e.message)) }, [])
  const taken = new Set(jobs.map((j) => j.opportunity_id).filter(Boolean))
  const choices = (pipe || []).filter((r) => !taken.has(r.id) && ['bidding', 'submitted', 'won'].includes(r.pipeline.stage))
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const go = async () => {
    setErr('')
    try {
      onCreated(await api.post(`/api/jobs/from-opportunity/${f.opp}`, { contract_number: f.contract_number, award_date: f.award_date, due_date: f.due_date }))
    } catch (e) { setErr(e.message) }
  }
  return (
    <div className="panel">
      <h2>Start a job from a won opportunity</h2>
      <p className="small muted">Copies the title, agency, NSN and quantity, takes the unit price and lead time from the latest linked part quote, builds a traveler from the quote's operations, and marks the pipeline entry and quote as won.</p>
      {err && <div className="err">{err}</div>}
      <div className="grid g4">
        <label className="f">Opportunity
          <select value={f.opp} onChange={set('opp')}>
            <option value="">Choose…</option>
            {choices.map((r) => <option key={r.id} value={r.id}>{r.solicitation_number ? `${r.solicitation_number}: ` : ''}{r.title.slice(0, 80)} ({r.pipeline.stage})</option>)}
            {preset && !choices.some((r) => String(r.id) === String(preset)) && <option value={preset}>Opportunity {preset}</option>}
          </select>
        </label>
        <label className="f">Contract number (from the award)<input value={f.contract_number} onChange={set('contract_number')} /></label>
        <label className="f">Award date<input type="date" value={f.award_date} onChange={set('award_date')} /></label>
        <label className="f">Delivery due (blank = quote lead time)<input type="date" value={f.due_date} onChange={set('due_date')} /></label>
      </div>
      {pipe && !choices.length && !preset && <p className="small muted">No bidding, submitted or won opportunities without a job. Track one in the pipeline first.</p>}
      <div className="row" style={{ marginTop: 12 }}>
        <button className="primary" onClick={go} disabled={!f.opp}>Create job</button>
        <button onClick={onCancel}>Cancel</button>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ detail
const TABS = [['overview', 'Overview'], ['traveler', 'Traveler'], ['purchases', 'Purchases'], ['records', 'Records'], ['shipping', 'Shipping']]

function JobDetail({ id, meta, tab, onTab, onBack }) {
  const [job, setJob] = useState(null)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const load = () => api.get(`/api/jobs/${id}`).then(setJob).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [id])

  const save = async (patch, note = 'Saved.') => {
    setErr(''); setMsg('')
    try { setJob(await api.put(`/api/jobs/${id}`, patch)); setMsg(note) } catch (e) { setErr(e.message) }
  }
  const remove = async () => {
    if (!confirm('Delete this job with its traveler, POs and uploaded records?')) return
    await api.del(`/api/jobs/${id}`)
    onBack()
  }

  if (err && !job) return <div className="err">{err}</div>
  if (!job) return <p className="muted">Loading…</p>
  return (
    <>
      <div className="row spread">
        <button className="link" onClick={onBack}>← All jobs</button>
        <button onClick={remove}>Delete job</button>
      </div>
      <div className="row spread" style={{ margin: '8px 0 4px' }}>
        <h1 style={{ margin: 0 }}>{job.title}</h1>
        <div className="row">
          {job.late && <span className="due-soon">Late</span>}
          <select value={job.status} onChange={(e) => save({ status: e.target.value }, 'Status updated.')}>
            {meta.statuses.map((s) => <option key={s} value={s}>{label(s)}</option>)}
          </select>
        </div>
      </div>
      <p className="sub">
        {job.customer || 'No customer'} · {job.contract_number || 'contract number not entered'} · due {job.due_date ? fmtDue(job.due_date) : 'n/a'} · {usd(job.value ?? job.clin_total)}
        {job.opportunity && <> · <Link to={`/opportunities/${job.opportunity.id}`}>opportunity</Link></>}
        {job.part_quote_id && <> · <Link to={`/part-quotes?tab=quote&id=${job.part_quote_id}`}>quote #{job.part_quote_id}</Link></>}
      </p>
      {msg && <div className="okmsg">{msg}</div>}
      {err && <div className="err">{err}</div>}
      <div className="tabs">
        {TABS.map(([k, l]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => onTab(k)}>{l}{k === 'traveler' && job.traveler_progress.total ? ` (${job.traveler_progress.done}/${job.traveler_progress.total})` : ''}{k === 'purchases' && job.purchases.length ? ` (${job.purchases.length})` : ''}{k === 'records' && job.records.length ? ` (${job.records.length})` : ''}</button>)}
      </div>
      {tab === 'overview' && <Overview job={job} onSave={save} />}
      {tab === 'traveler' && <Traveler job={job} meta={meta} reload={load} setErr={setErr} />}
      {tab === 'purchases' && <Purchases job={job} reload={load} setErr={setErr} />}
      {tab === 'records' && <Records job={job} meta={meta} reload={load} setErr={setErr} />}
      {tab === 'shipping' && <Shipping job={job} onSave={save} />}
    </>
  )
}

function Overview({ job, onSave }) {
  const fields = ['title', 'customer', 'contract_number', 'delivery_order', 'award_date', 'due_date', 'value', 'notes']
  const [f, setF] = useState(() => Object.fromEntries(fields.map((k) => [k, job[k] ?? ''])))
  const [clins, setClins] = useState(job.clins)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const setClin = (i, k, v) => setClins(clins.map((c, j) => (j === i ? { ...c, [k]: v } : c)))
  const addClin = () => setClins([...clins, { clin: String(clins.length + 1).padStart(4, '0'), description: '', nsn: '', part_number: '', quantity: '', unit: 'EA', unit_price: '', due_date: '' }])
  const total = clins.reduce((a, c) => a + (Number(c.quantity) || 0) * (Number(c.unit_price) || 0), 0)
  const save = () => {
    const body = { ...f, clins }
    if (f.value === '' || f.value == null) delete body.value
    else body.value = Number(f.value)
    onSave(body)
  }
  return (
    <>
      <div className="panel">
        <div className="grid g3">
          <label className="f">Title<input value={f.title} onChange={set('title')} /></label>
          <label className="f">Customer<input value={f.customer} onChange={set('customer')} /></label>
          <label className="f">Contract number (PIID)<input value={f.contract_number} onChange={set('contract_number')} /></label>
          <label className="f">Delivery / task order<input value={f.delivery_order} onChange={set('delivery_order')} /></label>
          <label className="f">Award date<input type="date" value={f.award_date} onChange={set('award_date')} /></label>
          <label className="f">Delivery due<input type="date" value={f.due_date} onChange={set('due_date')} /></label>
          <label className="f">Contract value (blank = CLIN total)<input type="number" step="0.01" value={f.value} onChange={set('value')} placeholder={total.toFixed(2)} /></label>
        </div>
        <label className="f" style={{ marginTop: 12 }}>Notes<textarea value={f.notes} onChange={set('notes')} /></label>
      </div>
      <div className="panel">
        <div className="row spread"><h2>CLINs</h2><span className="small muted">CLIN total {usd(total)}</span></div>
        <table>
          <thead><tr><th>CLIN</th><th>Description</th><th>NSN</th><th>Part number</th><th>Qty</th><th>Unit</th><th>Unit price</th><th>Extended</th><th>Due</th><th></th></tr></thead>
          <tbody>
            {clins.map((c, i) => (
              <tr key={i}>
                <td><input style={{ width: 60 }} value={c.clin} onChange={(e) => setClin(i, 'clin', e.target.value)} /></td>
                <td><input value={c.description} onChange={(e) => setClin(i, 'description', e.target.value)} /></td>
                <td><input style={{ width: 130 }} className="mono" value={c.nsn} onChange={(e) => setClin(i, 'nsn', e.target.value)} /></td>
                <td><input style={{ width: 110 }} value={c.part_number} onChange={(e) => setClin(i, 'part_number', e.target.value)} /></td>
                <td><input style={{ width: 70 }} type="number" value={c.quantity ?? ''} onChange={(e) => setClin(i, 'quantity', e.target.value)} /></td>
                <td><input style={{ width: 46 }} value={c.unit} onChange={(e) => setClin(i, 'unit', e.target.value)} /></td>
                <td><input style={{ width: 90 }} type="number" step="0.01" value={c.unit_price ?? ''} onChange={(e) => setClin(i, 'unit_price', e.target.value)} /></td>
                <td>{usd((Number(c.quantity) || 0) * (Number(c.unit_price) || 0))}</td>
                <td><input type="date" value={c.due_date || ''} onChange={(e) => setClin(i, 'due_date', e.target.value)} /></td>
                <td><button className="link" onClick={() => setClins(clins.filter((_, j) => j !== i))}>remove</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="row" style={{ marginTop: 10 }}>
          <button onClick={addClin}>Add CLIN</button>
          <button className="primary" onClick={save}>Save job</button>
        </div>
      </div>
    </>
  )
}

// ------------------------------------------------------------------ traveler
function Traveler({ job, meta, reload, setErr }) {
  const ops = job.operations
  const run = async (fn) => { setErr(''); try { await fn(); reload() } catch (e) { setErr(e.message) } }
  const template = (t) => {
    if (ops.length && !confirm('Replace the current traveler steps?')) return
    run(() => api.post(`/api/jobs/${job.id}/traveler/template`, { template: t, replace: true }))
  }
  const move = (i, d) => {
    const ids = ops.map((o) => o.id)
    const j = i + d
    if (j < 0 || j >= ids.length) return
    ;[ids[i], ids[j]] = [ids[j], ids[i]]
    run(() => api.post(`/api/jobs/${job.id}/operations/reorder`, { ids }))
  }
  return (
    <div className="panel">
      <div className="row spread">
        <h2>Traveler</h2>
        <div className="row">
          <span className="small muted">Rebuild from:</span>
          {job.part_quote_id && <button onClick={() => template('quote')}>Quote operations</button>}
          <button onClick={() => template('standard')}>Standard steps</button>
          <button onClick={() => template('blank')}>Blank</button>
        </div>
      </div>
      <p className="small muted">Sign off each step with your initials when it is complete. Signing off marks the step done and stamps today's date if none is entered.</p>
      <table>
        <thead><tr><th>#</th><th>Operation</th><th>Work center / vendor</th><th>Planned</th><th>Status</th><th>Initials</th><th>Signed</th><th>Good</th><th>Rej</th><th>Notes</th><th></th></tr></thead>
        <tbody>
          {ops.map((o, i) => <OpRow key={o.id} o={o} i={i} meta={meta} jobId={job.id} run={run} onMove={move} last={i === ops.length - 1} />)}
          {!ops.length && <tr><td colSpan={11} className="muted">No steps yet. Build one from a template or add steps below.</td></tr>}
        </tbody>
      </table>
      <button style={{ marginTop: 10 }} onClick={() => run(() => api.post(`/api/jobs/${job.id}/operations`, { name: 'New step' }))}>Add step</button>
    </div>
  )
}

function OpRow({ o, i, meta, jobId, run, onMove, last }) {
  const [d, setD] = useState(o)
  useEffect(() => setD(o), [o])
  const put = (patch) => run(() => api.put(`/api/jobs/${jobId}/operations/${o.id}`, patch))
  const blur = (k, conv = (v) => v) => () => { if (d[k] !== o[k]) put({ [k]: conv(d[k]) }) }
  const inp = (k, props = {}, conv) => <input value={d[k] ?? ''} onChange={(e) => setD({ ...d, [k]: e.target.value })} onBlur={blur(k, conv)} {...props} />
  return (
    <tr>
      <td className="small muted">{i + 1}
        <div><button className="link" disabled={i === 0} onClick={() => onMove(i, -1)}>↑</button> <button className="link" disabled={last} onClick={() => onMove(i, 1)}>↓</button></div>
      </td>
      <td>{inp('name', { style: { minWidth: 220 } })}</td>
      <td>{inp('work_center', { style: { width: 120 } })}</td>
      <td><input type="date" value={d.planned_date || ''} onChange={(e) => put({ planned_date: e.target.value })} /></td>
      <td><select value={d.status} onChange={(e) => put({ status: e.target.value })}>{meta.operation_statuses.map((s) => <option key={s} value={s}>{label(s)}</option>)}</select></td>
      <td>{inp('signoff_initials', { style: { width: 50 } })}</td>
      <td><input type="date" value={d.signoff_date || ''} onChange={(e) => put({ signoff_date: e.target.value })} /></td>
      <td>{inp('qty_good', { type: 'number', style: { width: 60 } }, numOrNull)}</td>
      <td>{inp('qty_rejected', { type: 'number', style: { width: 55 } }, numOrNull)}</td>
      <td>{inp('notes', { style: { width: 160 } })}</td>
      <td><button className="link" onClick={() => confirm('Delete this step?') && run(() => api.del(`/api/jobs/${jobId}/operations/${o.id}`))}>delete</button></td>
    </tr>
  )
}

// ------------------------------------------------------------------ purchases
function Purchases({ job, reload, setErr }) {
  const [vendors, setVendors] = useState([])
  const blank = { organization_id: '', vendor_name: '', po_number: '', description: '', quantity: '', unit_price: '', ordered_date: today(), promised_date: '' }
  const [f, setF] = useState(blank)
  useEffect(() => { api.get('/api/crm/organizations?kind=vendor').then(setVendors).catch(() => {}) }, [])
  const run = async (fn) => { setErr(''); try { await fn(); reload() } catch (e) { setErr(e.message) } }
  const add = () => run(async () => {
    await api.post(`/api/jobs/${job.id}/purchases`, {
      ...f, organization_id: f.organization_id ? Number(f.organization_id) : null, quantity: numOrNull(f.quantity), unit_price: numOrNull(f.unit_price),
    })
    setF(blank)
  })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  return (
    <>
      <div className="panel">
        <h2>Purchase orders</h2>
        <p className="small muted">Receipts feed the supplier scorecard on the Quality page: on time means received on or before the promised date; acceptance counts accepted versus rejected quantity. A receipt with accepted left blank accepts the full quantity less any rejects.</p>
        <table>
          <thead><tr><th>Vendor / PO</th><th>Description</th><th>Qty</th><th>Unit $</th><th>Ordered</th><th>Promised</th><th>Received</th><th>Accepted</th><th>Rejected</th><th>Certs</th><th>Notes</th><th></th></tr></thead>
          <tbody>
            {job.purchases.map((p) => <PoRow key={p.id} p={p} jobId={job.id} run={run} />)}
            {!job.purchases.length && <tr><td colSpan={12} className="muted">No purchase orders yet.</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="panel">
        <h2>Add a PO</h2>
        <div className="grid g4">
          <label className="f">Vendor (from Contacts)
            <select value={f.organization_id} onChange={set('organization_id')}>
              <option value="">Other (type a name)</option>
              {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
            </select>
          </label>
          {!f.organization_id && <label className="f">Vendor name<input value={f.vendor_name} onChange={set('vendor_name')} /></label>}
          <label className="f">PO number<input value={f.po_number} onChange={set('po_number')} /></label>
          <label className="f">Description<input value={f.description} onChange={set('description')} /></label>
          <label className="f">Quantity<input type="number" value={f.quantity} onChange={set('quantity')} /></label>
          <label className="f">Unit price<input type="number" step="0.01" value={f.unit_price} onChange={set('unit_price')} /></label>
          <label className="f">Ordered<input type="date" value={f.ordered_date} onChange={set('ordered_date')} /></label>
          <label className="f">Promised<input type="date" value={f.promised_date} onChange={set('promised_date')} /></label>
        </div>
        <button className="primary" style={{ marginTop: 12 }} onClick={add} disabled={!f.organization_id && !f.vendor_name}>Add PO</button>
      </div>
    </>
  )
}

function PoRow({ p, jobId, run }) {
  const [d, setD] = useState(p)
  useEffect(() => setD(p), [p])
  const put = (patch) => run(() => api.put(`/api/jobs/${jobId}/purchases/${p.id}`, patch))
  const inp = (k, props = {}, conv = (v) => v) => (
    <input value={d[k] ?? ''} onChange={(e) => setD({ ...d, [k]: e.target.value })} onBlur={() => { if (String(d[k] ?? '') !== String(p[k] ?? '')) put({ [k]: conv(d[k]) }) }} {...props} />
  )
  const date = (k) => <input type="date" value={d[k] || ''} onChange={(e) => put({ [k]: e.target.value })} />
  return (
    <tr>
      <td><div className="t">{p.vendor_name}</div>{inp('po_number', { style: { width: 100 }, placeholder: 'PO #' })}</td>
      <td>{inp('description', { style: { width: 160 } })}</td>
      <td>{inp('quantity', { type: 'number', style: { width: 60 } }, numOrNull)}</td>
      <td>{inp('unit_price', { type: 'number', step: '0.01', style: { width: 75 } }, numOrNull)}</td>
      <td>{date('ordered_date')}</td>
      <td className={p.overdue ? 'due-soon' : ''}>{date('promised_date')}{p.overdue && <div className="small">overdue</div>}</td>
      <td>{date('received_date')}{p.on_time === false && <div className="small due-soon">late</div>}</td>
      <td>{inp('qty_accepted', { type: 'number', style: { width: 60 } }, numOrNull)}</td>
      <td>{inp('qty_rejected', { type: 'number', style: { width: 60 } }, numOrNull)}</td>
      <td><input type="checkbox" checked={p.certs_received} onChange={(e) => put({ certs_received: e.target.checked })} /></td>
      <td>{inp('notes', { style: { width: 130 } })}</td>
      <td><button className="link" onClick={() => confirm('Delete this PO?') && run(() => api.del(`/api/jobs/${jobId}/purchases/${p.id}`))}>delete</button></td>
    </tr>
  )
}

// ------------------------------------------------------------------ records
function Records({ job, meta, reload, setErr }) {
  const [type, setType] = useState('material_cert')
  const [clin, setClin] = useState('')
  const [notes, setNotes] = useState('')
  const [file, setFile] = useState(null)
  const [coc, setCoc] = useState({ clin: job.clins[0]?.clin || '', fmt: 'docx' })
  const [busy, setBusy] = useState(false)
  const upload = async () => {
    setErr(''); setBusy(true)
    try {
      const fd = new FormData()
      fd.append('file', file); fd.append('doc_type', type); fd.append('clin', clin); fd.append('notes', notes)
      await api.upload(`/api/jobs/${job.id}/records`, fd)
      setFile(null); setNotes('')
      reload()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const cocUrl = (save) => `/api/jobs/${job.id}/coc?${new URLSearchParams({ clin: coc.clin, fmt: coc.fmt, ...(save ? { save: 'true' } : {}) })}`
  const fileCoc = async () => {
    setErr('')
    try { await api.get(cocUrl(true)); reload() } catch (e) { setErr(e.message) }
  }
  return (
    <>
      <div className="panel">
        <h2>Certificate of Conformance</h2>
        <p className="small muted">Fills in your company name and CAGE from the profile, the contract, CLIN, NSN, part number, quantity, ship date and carrier, with the FAR 52.246-15 conformance statement and a signature block. Under that clause a C of C replaces government inspection only when the contract allows it and the contract administration office has authorized it in writing. Sign it only after final inspection.</p>
        <div className="row">
          <select value={coc.clin} onChange={(e) => setCoc({ ...coc, clin: e.target.value })}>
            {job.clins.map((c) => <option key={c.clin} value={c.clin}>CLIN {c.clin}</option>)}
            {!job.clins.length && <option value="">No CLINs</option>}
          </select>
          <select value={coc.fmt} onChange={(e) => setCoc({ ...coc, fmt: e.target.value })}><option value="docx">Word (.docx)</option><option value="pdf">PDF</option></select>
          <a className="btn primary" href={cocUrl(false)}>Download</a>
          <button onClick={fileCoc}>Generate and file in records</button>
        </div>
        {(!job.contract_number || !job.shipped_date) && <p className="small due-soon">Enter the contract number (Overview) and ship date (Shipping) first, or the certificate will have blanks.</p>}
      </div>
      <div className="panel">
        <h2>Records</h2>
        <div className="row" style={{ marginBottom: 12 }}>
          <select value={type} onChange={(e) => setType(e.target.value)}>{meta.record_types.map((t) => <option key={t} value={t}>{label(t)}</option>)}</select>
          <select value={clin} onChange={(e) => setClin(e.target.value)}><option value="">All CLINs</option>{job.clins.map((c) => <option key={c.clin} value={c.clin}>CLIN {c.clin}</option>)}</select>
          <input placeholder="Notes (heat lot, report number)" value={notes} onChange={(e) => setNotes(e.target.value)} />
          <input type="file" onChange={(e) => setFile(e.target.files[0] || null)} />
          <button className="primary" disabled={!file || busy} onClick={upload}>{busy ? 'Uploading…' : 'Upload'}</button>
        </div>
        <table>
          <thead><tr><th>Type</th><th>File</th><th>CLIN</th><th>Notes</th><th>Uploaded</th><th></th></tr></thead>
          <tbody>
            {job.records.map((r) => (
              <tr key={r.id}>
                <td><span className="tag">{label(r.doc_type)}</span></td>
                <td><a href={r.url}>{r.filename}</a></td>
                <td>{r.clin}</td>
                <td className="small">{r.notes}</td>
                <td className="small muted">{r.uploaded_at?.slice(0, 10)}</td>
                <td><button className="link" onClick={async () => { if (confirm('Delete this record?')) { await api.del(`/api/jobs/${job.id}/records/${r.id}`); reload() } }}>delete</button></td>
              </tr>
            ))}
            {!job.records.length && <tr><td colSpan={6} className="muted">No records yet: add material certs, inspection reports, first article reports and signed C of Cs here.</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  )
}

// ------------------------------------------------------------------ shipping
function Shipping({ job, onSave }) {
  const keys = ['fob', 'inspection_acceptance', 'shipped_date', 'carrier', 'tracking_number', 'cage_ship_to', 'packaging_level', 'packaging_notes', 'iuid_required']
  const [f, setF] = useState(() => Object.fromEntries(keys.map((k) => [k, job[k] ?? ''])))
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  return (
    <div className="panel">
      <div className="grid g3">
        <label className="f">FOB
          <select value={f.fob} onChange={set('fob')}><option value="">Not set</option><option value="origin">Origin</option><option value="destination">Destination</option></select>
        </label>
        <label className="f">Inspection and acceptance
          <select value={f.inspection_acceptance} onChange={set('inspection_acceptance')}><option value="">Not set</option><option value="origin">Origin</option><option value="destination">Destination</option></select>
        </label>
        <label className="f">Ship-to DoDAAC / CAGE<input value={f.cage_ship_to} onChange={set('cage_ship_to')} /></label>
        <label className="f">Shipped date<input type="date" value={f.shipped_date} onChange={set('shipped_date')} /></label>
        <label className="f">Carrier<input value={f.carrier} onChange={set('carrier')} /></label>
        <label className="f">Tracking / bill of lading<input value={f.tracking_number} onChange={set('tracking_number')} /></label>
        <label className="f">Packaging level<input value={f.packaging_level} onChange={set('packaging_level')} placeholder="commercial, or the MIL-STD-2073 level from the contract" /></label>
      </div>
      <label className="f" style={{ marginTop: 12 }}>Packaging and marking notes (MIL-STD-129 marking, MIL-STD-2073 packaging codes, as written in the contract)
        <textarea value={f.packaging_notes} onChange={set('packaging_notes')} />
      </label>
      <label className="check" style={{ marginTop: 10 }}>
        <input type="checkbox" checked={!!f.iuid_required} onChange={(e) => setF({ ...f, iuid_required: e.target.checked })} /> IUID marking required
      </label>
      <p className="small muted">Entering a ship date moves an open job to shipped. On-time delivery compares the ship date with the due date.</p>
      <button className="primary" onClick={() => onSave(f, 'Shipping details saved.')}>Save shipping</button>
    </div>
  )
}
