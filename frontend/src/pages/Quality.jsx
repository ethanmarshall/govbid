import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, fmtDue } from '../api'

const label = (s) => (s || '').replace(/_/g, ' ')
const today = () => new Date().toISOString().slice(0, 10)
const pct = (v) => (v == null ? 'n/a' : `${v}%`)
const TABS = [['ncr', 'Nonconformances'], ['car', 'Corrective actions'], ['calibration', 'Calibration'], ['documents', 'Documents'], ['suppliers', 'Suppliers']]

export default function Quality() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || 'ncr'
  const [meta, setMeta] = useState(null)
  const [summ, setSumm] = useState(null)
  const [err, setErr] = useState('')
  const loadSumm = () => api.get('/api/quality/summary').then(setSumm).catch(() => {})
  useEffect(() => { api.get('/api/quality/meta').then(setMeta).catch((e) => setErr(e.message)); loadSumm() }, [])
  if (err) return <div className="err">{err}</div>
  if (!meta) return <p className="muted">Loading…</p>
  const common = { meta, setErr, onChange: loadSumm }
  return (
    <>
      <h1>Quality</h1>
      <p className="sub">A lightweight quality system for a one-person shop: nonconformances, corrective actions, calibration, your quality manual and procedures, and approved suppliers.</p>
      {summ && (
        <div className="grid g4" style={{ marginBottom: 16 }}>
          <div className="stat"><div className="n">{summ.open_ncrs}</div><div className="l">Open NCRs</div></div>
          <div className="stat"><div className={`n ${summ.overdue_cars ? 'due-soon' : ''}`}>{summ.open_cars}</div><div className="l">Open CARs ({summ.overdue_cars} overdue)</div></div>
          <div className="stat"><div className={`n ${summ.cal_overdue ? 'due-soon' : ''}`}>{summ.cal_overdue}</div><div className="l">Instruments overdue ({summ.cal_due_soon} due within 30 days)</div></div>
          <div className="stat"><div className="n">{summ.suppliers_approved}</div><div className="l">Approved suppliers of {summ.suppliers}</div></div>
        </div>
      )}
      {summ?.alerts?.length > 0 && <div className="notice"><ul className="clean">{summ.alerts.map((a, i) => <li key={i}>{a}</li>)}</ul></div>}
      <div className="tabs">
        {TABS.map(([k, l]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => setParams(k === 'ncr' ? {} : { tab: k })}>{l}</button>)}
      </div>
      {tab === 'ncr' && <Ncrs {...common} onCar={() => setParams({ tab: 'car' })} />}
      {tab === 'car' && <Cars {...common} />}
      {tab === 'calibration' && <Calibration {...common} />}
      {tab === 'documents' && <Documents {...common} />}
      {tab === 'suppliers' && <Suppliers {...common} />}
    </>
  )
}

// ------------------------------------------------------------------ NCRs
function Ncrs({ meta, setErr, onChange, onCar }) {
  const [rows, setRows] = useState(null)
  const [jobs, setJobs] = useState([])
  const [status, setStatus] = useState('')
  const [open, setOpen] = useState(null)
  const [adding, setAdding] = useState(false)
  const load = () => api.get(`/api/quality/ncrs${status ? `?status=${status}` : ''}`).then(setRows).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [status])
  useEffect(() => { api.get('/api/jobs').then(setJobs).catch(() => {}) }, [])
  const done = () => { load(); onChange() }
  if (!rows) return <p className="muted">Loading…</p>
  return (
    <>
      <div className="row spread" style={{ marginBottom: 12 }}>
        <div className="row">
          {['', ...meta.ncr_statuses].map((s) => <button key={s} className={`chip ${status === s ? 'on' : ''}`} onClick={() => setStatus(s)}>{s ? label(s) : 'all'}</button>)}
        </div>
        <button className="primary" onClick={() => setAdding(!adding)}>New NCR</button>
      </div>
      {adding && <NcrForm meta={meta} jobs={jobs} setErr={setErr} onDone={() => { setAdding(false); done() }} />}
      <div className="panel" style={{ padding: 0 }}>
        <table>
          <thead><tr><th>NCR</th><th>Part</th><th>Qty</th><th>Job</th><th>Source</th><th>Disposition</th><th>Status</th><th>Opened</th></tr></thead>
          <tbody>
            {rows.map((n) => [
              <tr key={n.id} className="click" onClick={() => setOpen(open === n.id ? null : n.id)}>
                <td className="mono">{n.number}</td>
                <td><div className="t">{n.part}</div><div className="small muted">{n.description.slice(0, 90)}</div></td>
                <td>{n.quantity ?? ''}</td>
                <td className="small">{n.job_id ? <Link to={`/jobs?id=${n.job_id}`} onClick={(e) => e.stopPropagation()}>{n.job_title}</Link> : ''}</td>
                <td className="small">{label(n.source)}</td>
                <td>{n.disposition ? <span className="tag">{label(n.disposition)}</span> : <span className="muted small">pending</span>}</td>
                <td>{label(n.status)}</td>
                <td className="small">{fmtDue(n.opened_date)}</td>
              </tr>,
              open === n.id && <tr key={`e${n.id}`}><td colSpan={8}><NcrForm meta={meta} jobs={jobs} ncr={n} setErr={setErr} onDone={done} onCar={onCar} /></td></tr>,
            ])}
            {!rows.length && <tr><td colSpan={8} className="muted">No nonconformance reports.</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  )
}

function NcrForm({ meta, jobs, ncr, setErr, onDone, onCar }) {
  const init = ncr || { job_id: '', part: '', quantity: '', source: 'in_process', description: '', containment: '', disposition: '', disposition_by: '', root_cause: '', status: 'open', notes: '', opened_date: today(), closed_date: '' }
  const [f, setF] = useState({ ...init, job_id: init.job_id ?? '', quantity: init.quantity ?? '' })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const body = () => ({ ...f, job_id: f.job_id ? Number(f.job_id) : null, quantity: f.quantity === '' ? null : Number(f.quantity) })
  const save = async () => {
    setErr('')
    try {
      if (ncr) await api.put(`/api/quality/ncrs/${ncr.id}`, body())
      else await api.post('/api/quality/ncrs', body())
      onDone()
    } catch (e) { setErr(e.message) }
  }
  const car = async () => {
    setErr('')
    try { await api.post('/api/quality/cars', { ncr_id: ncr.id }); onDone(); onCar() } catch (e) { setErr(e.message) }
  }
  const del = async () => { if (confirm(`Delete ${ncr.number}?`)) { await api.del(`/api/quality/ncrs/${ncr.id}`); onDone() } }
  return (
    <div className={ncr ? '' : 'panel'}>
      {!ncr && <h2>New nonconformance report</h2>}
      <div className="grid g4">
        <label className="f">Job<select value={f.job_id} onChange={set('job_id')}><option value="">None</option>{jobs.map((j) => <option key={j.id} value={j.id}>{j.title}</option>)}</select></label>
        <label className="f">Part<input value={f.part} onChange={set('part')} /></label>
        <label className="f">Quantity<input type="number" value={f.quantity} onChange={set('quantity')} /></label>
        <label className="f">Found at<select value={f.source} onChange={set('source')}>{meta.ncr_sources.map((s) => <option key={s} value={s}>{label(s)}</option>)}</select></label>
      </div>
      <div className="grid g2" style={{ marginTop: 10 }}>
        <label className="f">What is wrong (versus the requirement)<textarea value={f.description} onChange={set('description')} /></label>
        <label className="f">Containment (what else was checked, what was quarantined)<textarea value={f.containment} onChange={set('containment')} /></label>
      </div>
      {ncr && (
        <>
          <div className="grid g4" style={{ marginTop: 10 }}>
            <label className="f">Disposition<select value={f.disposition} onChange={set('disposition')}>{meta.ncr_dispositions.map((s) => <option key={s} value={s}>{s ? label(s) : 'Not decided'}</option>)}</select></label>
            <label className="f">Disposition by / customer approval<input value={f.disposition_by} onChange={set('disposition_by')} /></label>
            <label className="f">Status<select value={f.status} onChange={set('status')}>{meta.ncr_statuses.map((s) => <option key={s} value={s}>{label(s)}</option>)}</select></label>
            <label className="f">Closed<input type="date" value={f.closed_date} onChange={set('closed_date')} /></label>
          </div>
          {['use_as_is', 'repair'].includes(f.disposition) && <p className="small due-soon">Use as is and repair on government contract items usually need the customer's approval. Check the contract before shipping.</p>}
          <div className="grid g2" style={{ marginTop: 10 }}>
            <label className="f">Root cause<textarea value={f.root_cause} onChange={set('root_cause')} /></label>
            <label className="f">Notes<textarea value={f.notes} onChange={set('notes')} /></label>
          </div>
          {ncr.cars.length > 0 && <p className="small">Corrective actions: {ncr.cars.map((c) => `${c.number} (${c.status})`).join(', ')}</p>}
        </>
      )}
      <div className="row" style={{ marginTop: 10 }}>
        <button className="primary" onClick={save}>{ncr ? 'Save' : 'Open NCR'}</button>
        {ncr && <button onClick={car}>Open a corrective action</button>}
        {ncr && <button onClick={del}>Delete</button>}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ CARs
function Cars({ meta, setErr, onChange }) {
  const [rows, setRows] = useState(null)
  const [ncrs, setNcrs] = useState([])
  const [open, setOpen] = useState(null)
  const [adding, setAdding] = useState(false)
  const load = () => api.get('/api/quality/cars').then(setRows).catch((e) => setErr(e.message))
  useEffect(() => { load(); api.get('/api/quality/ncrs').then(setNcrs).catch(() => {}) }, [])
  const done = () => { load(); onChange() }
  if (!rows) return <p className="muted">Loading…</p>
  return (
    <>
      <div className="row spread" style={{ marginBottom: 12 }}>
        <p className="small muted" style={{ margin: 0 }}>Use a corrective action for repeated, costly or customer-found problems. Close it only after the effectiveness check shows it worked.</p>
        <button className="primary" onClick={() => setAdding(!adding)}>New CAR</button>
      </div>
      {adding && <CarForm meta={meta} ncrs={ncrs} setErr={setErr} onDone={() => { setAdding(false); done() }} />}
      <div className="panel" style={{ padding: 0 }}>
        <table>
          <thead><tr><th>CAR</th><th>Problem</th><th>NCR</th><th>Owner</th><th>Due</th><th>Effective</th><th>Status</th></tr></thead>
          <tbody>
            {rows.map((c) => [
              <tr key={c.id} className="click" onClick={() => setOpen(open === c.id ? null : c.id)}>
                <td className="mono">{c.number}</td>
                <td className="small">{c.problem.slice(0, 120)}</td>
                <td className="mono small">{c.ncr_number || ''}</td>
                <td>{c.owner}</td>
                <td className={c.overdue ? 'due-soon' : ''}>{c.due_date ? fmtDue(c.due_date) : ''}{c.overdue && ' (overdue)'}</td>
                <td>{c.effective == null ? '' : c.effective ? 'yes' : 'no'}</td>
                <td>{label(c.status)}</td>
              </tr>,
              open === c.id && <tr key={`e${c.id}`}><td colSpan={7}><CarForm meta={meta} ncrs={ncrs} car={c} setErr={setErr} onDone={done} /></td></tr>,
            ])}
            {!rows.length && <tr><td colSpan={7} className="muted">No corrective actions.</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  )
}

function CarForm({ meta, ncrs, car, setErr, onDone }) {
  const init = car || { ncr_id: '', problem: '', root_cause: '', action: '', owner: '', due_date: '', effectiveness_check: '', effectiveness_date: '', effective: null, status: 'open', closed_date: '' }
  const [f, setF] = useState({ ...init, ncr_id: init.ncr_id ?? '' })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const save = async () => {
    setErr('')
    const body = { ...f, ncr_id: f.ncr_id ? Number(f.ncr_id) : null }
    try {
      if (car) await api.put(`/api/quality/cars/${car.id}`, body)
      else await api.post('/api/quality/cars', body)
      onDone()
    } catch (e) { setErr(e.message) }
  }
  const del = async () => { if (confirm(`Delete ${car.number}?`)) { await api.del(`/api/quality/cars/${car.id}`); onDone() } }
  return (
    <div className={car ? '' : 'panel'}>
      {!car && <h2>New corrective action</h2>}
      <div className="grid g4">
        <label className="f">From NCR<select value={f.ncr_id} onChange={set('ncr_id')}><option value="">None</option>{ncrs.map((n) => <option key={n.id} value={n.id}>{n.number} {n.part}</option>)}</select></label>
        <label className="f">Owner<input value={f.owner} onChange={set('owner')} /></label>
        <label className="f">Due<input type="date" value={f.due_date} onChange={set('due_date')} /></label>
        <label className="f">Status<select value={f.status} onChange={set('status')}>{meta.car_statuses.map((s) => <option key={s} value={s}>{label(s)}</option>)}</select></label>
      </div>
      <div className="grid g3" style={{ marginTop: 10 }}>
        <label className="f">Problem<textarea value={f.problem} onChange={set('problem')} placeholder={f.ncr_id ? 'Blank = copy from the NCR' : ''} /></label>
        <label className="f">Root cause<textarea value={f.root_cause} onChange={set('root_cause')} /></label>
        <label className="f">Action<textarea value={f.action} onChange={set('action')} /></label>
      </div>
      <div className="grid g4" style={{ marginTop: 10 }}>
        <label className="f" style={{ gridColumn: 'span 2' }}>Effectiveness check (how and when you will confirm it worked)<input value={f.effectiveness_check} onChange={set('effectiveness_check')} /></label>
        <label className="f">Checked on<input type="date" value={f.effectiveness_date} onChange={set('effectiveness_date')} /></label>
        <label className="f">Effective?
          <select value={f.effective == null ? '' : String(f.effective)} onChange={(e) => setF({ ...f, effective: e.target.value === '' ? null : e.target.value === 'true' })}>
            <option value="">Not checked</option><option value="true">Yes</option><option value="false">No</option>
          </select>
        </label>
      </div>
      <div className="row" style={{ marginTop: 10 }}>
        <button className="primary" onClick={save}>{car ? 'Save' : 'Open CAR'}</button>
        {car && <button onClick={del}>Delete</button>}
        {car?.closed_date && <span className="small muted">Closed {fmtDue(car.closed_date)}</span>}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ calibration
const CAL_CLASS = { overdue: 'due-soon', due_soon: 'due-soon' }

function Calibration({ meta, setErr, onChange }) {
  const [rows, setRows] = useState(null)
  const [open, setOpen] = useState(null)
  const [adding, setAdding] = useState(false)
  const load = () => api.get('/api/quality/instruments').then(setRows).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [])
  const done = () => { load(); onChange() }
  if (!rows) return <p className="muted">Loading…</p>
  return (
    <>
      <div className="row spread" style={{ marginBottom: 12 }}>
        <p className="small muted" style={{ margin: 0 }}>Next due = last calibration date plus the interval. Do not use an overdue instrument to accept product.</p>
        <button className="primary" onClick={() => setAdding(!adding)}>Add instrument</button>
      </div>
      {adding && <InstrumentForm meta={meta} setErr={setErr} onDone={() => { setAdding(false); done() }} />}
      <div className="panel" style={{ padding: 0 }}>
        <table>
          <thead><tr><th>Instrument</th><th>ID / serial</th><th>Interval</th><th>Last cal</th><th>Next due</th><th>Source</th><th>Status</th></tr></thead>
          <tbody>
            {rows.map((i) => [
              <tr key={i.id} className="click" onClick={() => setOpen(open === i.id ? null : i.id)}>
                <td><div className="t">{i.name}</div><div className="small muted">{i.kind}</div></td>
                <td className="mono small">{i.asset_id}{i.serial && ` / ${i.serial}`}</td>
                <td>{i.interval_days} d</td>
                <td>{i.last_cal_date ? fmtDue(i.last_cal_date) : <span className="muted">none</span>}</td>
                <td className={CAL_CLASS[i.cal_status] || ''}>{i.next_due ? fmtDue(i.next_due) : ''}</td>
                <td className="small">{i.cal_source}</td>
                <td className={CAL_CLASS[i.cal_status] || ''}>{label(i.cal_status)}</td>
              </tr>,
              open === i.id && <tr key={`e${i.id}`}><td colSpan={7}><InstrumentForm meta={meta} inst={i} setErr={setErr} onDone={done} /></td></tr>,
            ])}
            {!rows.length && <tr><td colSpan={7} className="muted">No instruments yet. Add calipers, micrometers, torque wrenches, meters, hipot testers and crimp tools you use for acceptance.</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  )
}

function InstrumentForm({ meta, inst, setErr, onDone }) {
  const init = inst || { name: '', kind: 'Calipers', asset_id: '', serial: '', manufacturer: '', range_resolution: '', location: '', interval_days: 365, last_cal_date: '', cal_source: '', status: 'active', notes: '' }
  const [f, setF] = useState(init)
  const [cal, setCal] = useState({ cal_date: today(), source: inst?.cal_source || '', result: 'pass', notes: '' })
  const [file, setFile] = useState(null)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const save = async () => {
    setErr('')
    const body = { ...f, interval_days: Number(f.interval_days) }
    try {
      if (inst) await api.put(`/api/quality/instruments/${inst.id}`, body)
      else await api.post('/api/quality/instruments', body)
      onDone()
    } catch (e) { setErr(e.message) }
  }
  const record = async () => {
    setErr('')
    const fd = new FormData()
    Object.entries(cal).forEach(([k, v]) => fd.append(k, v))
    if (file) fd.append('file', file)
    try { await api.upload(`/api/quality/instruments/${inst.id}/calibrations`, fd); setFile(null); onDone() } catch (e) { setErr(e.message) }
  }
  const del = async () => { if (confirm(`Delete ${inst.name} and its calibration history?`)) { await api.del(`/api/quality/instruments/${inst.id}`); onDone() } }
  return (
    <div className={inst ? '' : 'panel'}>
      {!inst && <h2>Add instrument</h2>}
      <div className="grid g4">
        <label className="f">Name<input value={f.name} onChange={set('name')} placeholder="6 in digital calipers" /></label>
        <label className="f">Kind<select value={f.kind} onChange={set('kind')}>{meta.instrument_kinds.map((k) => <option key={k}>{k}</option>)}</select></label>
        <label className="f">Your ID tag<input value={f.asset_id} onChange={set('asset_id')} /></label>
        <label className="f">Serial<input value={f.serial} onChange={set('serial')} /></label>
        <label className="f">Manufacturer<input value={f.manufacturer} onChange={set('manufacturer')} /></label>
        <label className="f">Range / resolution<input value={f.range_resolution} onChange={set('range_resolution')} /></label>
        <label className="f">Interval (days)<input type="number" value={f.interval_days} onChange={set('interval_days')} /></label>
        <label className="f">Status<select value={f.status} onChange={set('status')}>{meta.instrument_statuses.map((s) => <option key={s} value={s}>{label(s)}</option>)}</select></label>
        {!inst && <label className="f">Last calibrated<input type="date" value={f.last_cal_date} onChange={set('last_cal_date')} /></label>}
        {!inst && <label className="f">Calibration source<input value={f.cal_source} onChange={set('cal_source')} /></label>}
      </div>
      <label className="f" style={{ marginTop: 10 }}>Notes<input value={f.notes} onChange={set('notes')} /></label>
      <div className="row" style={{ marginTop: 10 }}>
        <button className="primary" onClick={save}>{inst ? 'Save' : 'Add instrument'}</button>
        {inst && <button onClick={del}>Delete</button>}
      </div>
      {inst && (
        <>
          <h3>Record a calibration</h3>
          <div className="row">
            <input type="date" value={cal.cal_date} onChange={(e) => setCal({ ...cal, cal_date: e.target.value })} />
            <input placeholder="Lab or source" value={cal.source} onChange={(e) => setCal({ ...cal, source: e.target.value })} />
            <select value={cal.result} onChange={(e) => setCal({ ...cal, result: e.target.value })}><option value="pass">Pass</option><option value="adjusted">Adjusted</option><option value="fail">Fail (out of service)</option></select>
            <input placeholder="Notes" value={cal.notes} onChange={(e) => setCal({ ...cal, notes: e.target.value })} />
            <input type="file" onChange={(e) => setFile(e.target.files[0] || null)} />
            <button onClick={record}>Record</button>
          </div>
          {cal.result === 'fail' && <p className="small due-soon">Review product accepted with this instrument since its last good calibration, and open an NCR if any may be affected.</p>}
          {inst.history.length > 0 && (
            <ul className="clean small" style={{ marginTop: 10 }}>
              {inst.history.map((h) => <li key={h.index}>{fmtDue(h.date)}: {h.result}{h.source && `, ${h.source}`}{h.notes && `, ${h.notes}`} {h.url && <a href={h.url}>{h.filename}</a>}</li>)}
            </ul>
          )}
        </>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ documents
function Documents({ setErr }) {
  const [docs, setDocs] = useState(null)
  const [sel, setSel] = useState(null)
  const load = () => api.get('/api/quality/documents').then((d) => { setDocs(d); if (!sel && d.length) setSel(d[0].id) }).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [])
  const add = async () => {
    const d = await api.post('/api/quality/documents', { title: 'New procedure', doc_number: '', content: '# New procedure\n\n## 1. Purpose\n\n## 2. Procedure\n1. \n\n## 3. Records\n' })
    await load(); setSel(d.id)
  }
  if (!docs) return <p className="muted">Loading…</p>
  return (
    <div className="builder">
      <div className="panel outline">
        {docs.map((d) => (
          <div key={d.id} className={`oitem ${sel === d.id ? 'sel' : ''}`} onClick={() => setSel(d.id)}>
            <span className="otitle">{d.title}</span>
            <span className="ometa"><span>{d.doc_number}</span><span>Rev {d.version}</span></span>
          </div>
        ))}
        <button style={{ marginTop: 10 }} onClick={add}>New document</button>
        <p className="small muted" style={{ marginTop: 12 }}>Starter templates are generic and written for a one-person shop. Read them, change them to match what you actually do, and set an effective date before you rely on them. They do not make the business ISO 9001 or AS9100 certified.</p>
      </div>
      {sel && <DocEditor key={sel} id={sel} setErr={setErr} onSaved={load} onDeleted={() => { setSel(null); load() }} />}
    </div>
  )
}

function DocEditor({ id, setErr, onSaved, onDeleted }) {
  const [d, setD] = useState(null)
  const [note, setNote] = useState('')
  const [msg, setMsg] = useState('')
  const [view, setView] = useState(null)
  useEffect(() => { api.get(`/api/quality/documents/${id}`).then(setD).catch((e) => setErr(e.message)) }, [id])
  if (!d) return <p className="muted">Loading…</p>
  const set = (k) => (e) => setD({ ...d, [k]: e.target.value })
  const save = async (newRev) => {
    setErr(''); setMsg('')
    try {
      const body = { title: d.title, doc_number: d.doc_number, content: d.content, effective_date: d.effective_date, ...(newRev ? { new_revision: true, change_note: note, version: '' } : { version: d.version }) }
      const r = await api.put(`/api/quality/documents/${id}`, body)
      setD(r); setNote(''); setMsg(newRev ? `Saved as revision ${r.version}. The previous text is in the history.` : 'Saved.')
      onSaved()
    } catch (e) { setErr(e.message) }
  }
  const del = async () => {
    if (!confirm('Delete this document?')) return
    try { await api.del(`/api/quality/documents/${id}`); onDeleted() } catch (e) { setErr(e.message) }
  }
  return (
    <div className="panel">
      {msg && <div className="okmsg">{msg}</div>}
      <div className="grid g4">
        <label className="f" style={{ gridColumn: 'span 2' }}>Title<input value={d.title} onChange={set('title')} /></label>
        <label className="f">Document number<input value={d.doc_number} onChange={set('doc_number')} /></label>
        <label className="f">Revision<input value={d.version} onChange={set('version')} /></label>
        <label className="f">Effective date<input type="date" value={d.effective_date} onChange={set('effective_date')} /></label>
      </div>
      <label className="f" style={{ marginTop: 10 }}>Content (markdown: # headings, - bullets, 1. steps, **bold**)
        <textarea className="mono" style={{ minHeight: 460 }} value={d.content} onChange={set('content')} />
      </label>
      <div className="row" style={{ marginTop: 10 }}>
        <button className="primary" onClick={() => save(false)}>Save changes</button>
        <input placeholder="What changed (for a new revision)" value={note} onChange={(e) => setNote(e.target.value)} style={{ minWidth: 260 }} />
        <button onClick={() => save(true)}>Save as new revision</button>
        <a className="btn" href={`/api/quality/documents/${id}/docx`}>Download Word</a>
        {!d.key && <button onClick={del}>Delete</button>}
      </div>
      {d.history.length > 0 && (
        <>
          <h3>Revision history</h3>
          <table>
            <thead><tr><th>Rev</th><th>Effective</th><th>Change note</th><th>Replaced</th><th></th></tr></thead>
            <tbody>
              {[...d.history].reverse().map((h) => (
                <tr key={h.index}>
                  <td>{h.version}</td><td>{h.effective_date ? fmtDue(h.effective_date) : ''}</td><td>{h.note}</td>
                  <td className="small muted">{h.replaced_at?.slice(0, 10)}</td>
                  <td><button className="link" onClick={() => setView(view === h.index ? null : h.index)}>{view === h.index ? 'hide' : 'view'}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          {view != null && <pre className="desc small" style={{ marginTop: 10 }}>{d.history[view].content}</pre>}
        </>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ suppliers
const STATUS_CLASS = { approved: 'b-eligible_now', conditional: 'b-eligible_once_certified', disapproved: 'b-not_eligible', pending: '' }

function Suppliers({ meta, setErr, onChange }) {
  const [rows, setRows] = useState(null)
  const [open, setOpen] = useState(null)
  const load = () => api.get('/api/quality/suppliers').then(setRows).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [])
  const done = () => { load(); onChange() }
  if (!rows) return <p className="muted">Loading…</p>
  return (
    <>
      <div className="row spread" style={{ marginBottom: 12 }}>
        <p className="small muted" style={{ margin: 0 }}>Vendors come from <Link to="/contacts">Contacts</Link> (kind vendor) and from job POs. Scorecards are computed from the POs on your jobs.</p>
        <div className="row">
          <a className="btn" href="/api/quality/suppliers/asl.xlsx?all=true">Export all</a>
          <a className="btn primary" href="/api/quality/suppliers/asl.xlsx">Approved Supplier List (.xlsx)</a>
        </div>
      </div>
      <div className="panel" style={{ padding: 0 }}>
        <table>
          <thead><tr><th>Supplier</th><th>Status</th><th>Basis</th><th>Certifications</th><th>Orders</th><th>On time</th><th>Acceptance</th><th>Last order</th></tr></thead>
          <tbody>
            {rows.map((s) => [
              <tr key={s.organization_id} className="click" onClick={() => setOpen(open === s.organization_id ? null : s.organization_id)}>
                <td><div className="t">{s.name}</div><div className="small muted">{[s.cage, s.city, s.state].filter(Boolean).join(' · ')}</div></td>
                <td><span className={`badge ${STATUS_CLASS[s.approval.status] || ''}`}>{s.approval.status}</span></td>
                <td className="small">{s.approval.basis.map(label).join(', ')}</td>
                <td className="small">{s.certs.map((c) => <div key={c.id} className={c.state === 'expired' || c.state === 'expiring_soon' ? 'due-soon' : ''}>{c.cert_type}{c.expiration_date && ` (${c.state === 'expired' ? 'expired' : 'exp'} ${c.expiration_date})`}</div>)}</td>
                <td>{s.scorecard.orders}{s.scorecard.late_open > 0 && <div className="small due-soon">{s.scorecard.late_open} late</div>}</td>
                <td>{pct(s.scorecard.on_time_pct)}</td>
                <td>{pct(s.scorecard.acceptance_pct)}</td>
                <td className="small">{s.scorecard.last_order ? fmtDue(s.scorecard.last_order) : ''}</td>
              </tr>,
              open === s.organization_id && <tr key={`e${s.organization_id}`}><td colSpan={8}><SupplierEditor meta={meta} s={s} setErr={setErr} onDone={done} /></td></tr>,
            ])}
            {!rows.length && <tr><td colSpan={8} className="muted">No vendors yet. Add them in Contacts with kind "vendor".</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  )
}

function SupplierEditor({ meta, s, setErr, onDone }) {
  const [a, setA] = useState(s.approval)
  const [c, setC] = useState({ cert_type: meta.supplier_cert_types[0], number: '', issuer: '', expiration_date: '', notes: '' })
  const [file, setFile] = useState(null)
  const set = (k) => (e) => setA({ ...a, [k]: e.target.value })
  const toggle = (b) => setA({ ...a, basis: a.basis.includes(b) ? a.basis.filter((x) => x !== b) : [...a.basis, b] })
  const save = async () => {
    setErr('')
    try { await api.put(`/api/quality/suppliers/${s.organization_id}`, a); onDone() } catch (e) { setErr(e.message) }
  }
  const addCert = async () => {
    setErr('')
    const fd = new FormData()
    Object.entries(c).forEach(([k, v]) => fd.append(k, v))
    if (file) fd.append('file', file)
    try { await api.upload(`/api/quality/suppliers/${s.organization_id}/certs`, fd); setFile(null); setC({ ...c, number: '', issuer: '', expiration_date: '', notes: '' }); onDone() } catch (e) { setErr(e.message) }
  }
  const delCert = async (id) => { if (confirm('Remove this certificate?')) { await api.del(`/api/quality/suppliers/${s.organization_id}/certs/${id}`); onDone() } }
  const sc = s.scorecard
  return (
    <div>
      <div className="grid g4">
        <label className="f">Approval status<select value={a.status} onChange={set('status')}>{meta.approval_statuses.map((x) => <option key={x}>{x}</option>)}</select></label>
        <label className="f">Approval date<input type="date" value={a.approval_date} onChange={set('approval_date')} /></label>
        <label className="f">Re-review due<input type="date" value={a.review_due} onChange={set('review_due')} /></label>
        <label className="f">Approved for (scope)<input value={a.scope} onChange={set('scope')} placeholder="e.g. Type II anodize, 6061 plate" /></label>
      </div>
      <div className="row" style={{ marginTop: 10 }}>
        <span className="small muted">Basis:</span>
        {meta.approval_bases.map((b) => <label key={b} className="check"><input type="checkbox" checked={a.basis.includes(b)} onChange={() => toggle(b)} /> {label(b)}</label>)}
      </div>
      <label className="f" style={{ marginTop: 10 }}>Notes<input value={a.notes} onChange={set('notes')} /></label>
      <div className="row" style={{ marginTop: 10 }}>
        <button className="primary" onClick={save}>Save approval</button>
        <span className="small muted">Scorecard: {sc.orders} orders, {sc.received} received, {sc.on_time}/{sc.on_time_measured} on time, {sc.qty_accepted} accepted / {sc.qty_rejected} rejected, {sc.certs_missing} received without certs.</span>
      </div>
      <h3>Certifications on file</h3>
      {s.certs.length > 0 && (
        <ul className="clean small">
          {s.certs.map((x) => (
            <li key={x.id} className={x.state === 'expired' ? 'due-soon' : ''}>
              {x.cert_type}{x.number && ` #${x.number}`}{x.issuer && `, ${x.issuer}`}{x.expiration_date && `, expires ${x.expiration_date}`} ({label(x.state)})
              {x.url && <> <a href={x.url}>{x.filename}</a></>} <button className="link" onClick={() => delCert(x.id)}>remove</button>
            </li>
          ))}
        </ul>
      )}
      <div className="row" style={{ marginTop: 8 }}>
        <select value={c.cert_type} onChange={(e) => setC({ ...c, cert_type: e.target.value })}>{meta.supplier_cert_types.map((t) => <option key={t}>{t}</option>)}</select>
        <input placeholder="Certificate number" value={c.number} onChange={(e) => setC({ ...c, number: e.target.value })} />
        <input placeholder="Issuer / registrar" value={c.issuer} onChange={(e) => setC({ ...c, issuer: e.target.value })} />
        <label className="small muted">Expires <input type="date" value={c.expiration_date} onChange={(e) => setC({ ...c, expiration_date: e.target.value })} /></label>
        <input type="file" onChange={(e) => setFile(e.target.files[0] || null)} />
        <button onClick={addCert}>Add certificate</button>
      </div>
    </div>
  )
}
