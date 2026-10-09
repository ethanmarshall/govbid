import { useRef, useState } from 'react'
import { api } from '../api'

export default function Imports() {
  return (
    <>
      <h1>Import</h1>
      <p className="sub">Bring in sources that cannot be pulled automatically.</p>
      <div className="grid g2">
        <ImportBox
          source="dibbs"
          title="DLA DIBBS RFQs"
          accept=".txt,.csv,.xlsx"
          watchlist
          help={
            <>
              <p>DIBBS blocks automated access, so download the data yourself and drop it here. RFQs over $25K also appear in SAM.gov syncs; DIBBS is where the many small DLA parts buys live.</p>
              <ol className="clean small">
                <li>Go to <a href="https://www.dibbs.bsm.dla.mil/" target="_blank" rel="noreferrer">dibbs.bsm.dla.mil</a> and accept the consent banner.</li>
                <li>Either export an RFQ search (by NSN, FSC or date) to CSV/Excel, or download the daily RFQ index file from the RFQ dates page.</li>
                <li>Upload it here. Results are filtered to the NSN/FSC watchlist on your profile.</li>
              </ol>
              <p className="small muted">The daily index text file is parsed by pattern matching. Spot-check a few rows against DIBBS.</p>
            </>
          }
        />
        <ImportBox
          source="forecast"
          title="Agency procurement forecasts"
          accept=".csv,.xlsx"
          help={
            <>
              <p>Forecasts show buys months before they post, which is when you can shape a set-aside decision by talking to the small business office.</p>
              <ol className="clean small">
                <li>Export forecast data as CSV or Excel from <a href="https://acquisitiongateway.gov/forecast" target="_blank" rel="noreferrer">Acquisition Gateway</a> or an agency OSDBU forecast page (VA, DoD components, DHS).</li>
                <li>Upload it here. Columns like Title, Agency, NAICS, Set Aside and Estimated Value are matched automatically.</li>
              </ol>
            </>
          }
        />
      </div>
      <ManualEntry />
    </>
  )
}

function ImportBox({ source, title, accept, help, watchlist }) {
  const ref = useRef()
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState(null)
  const [err, setErr] = useState('')
  const [useWatch, setUseWatch] = useState(true)
  const go = async () => {
    const f = ref.current.files[0]
    if (!f) return
    setBusy(true); setErr(''); setRes(null)
    const fd = new FormData()
    fd.append('file', f)
    try {
      setRes(await api.upload(`/api/import/${source}?apply_watchlist=${watchlist ? useWatch : false}`, fd))
      ref.current.value = ''
    } catch (e) { setErr(e.message) }
    setBusy(false)
  }
  return (
    <div className="panel">
      <h2>{title}</h2>
      {help}
      <div className="row" style={{ marginTop: 12 }}>
        <input type="file" ref={ref} accept={accept} />
        <button className="primary" onClick={go} disabled={busy}>{busy ? 'Importing…' : 'Import'}</button>
      </div>
      {watchlist && (
        <label className="check" style={{ marginTop: 10 }}>
          <input type="checkbox" checked={useWatch} onChange={(e) => setUseWatch(e.target.checked)} /> Only keep NSNs/FSCs on my watchlist
        </label>
      )}
      {err && <div className="err" style={{ marginTop: 12 }}>{err}</div>}
      {res && <div className="okmsg" style={{ marginTop: 12 }}>Read {res.parsed} rows, kept {res.kept}: {res.added} new, {res.updated} updated.</div>}
    </div>
  )
}

function ManualEntry() {
  const [f, setF] = useState({ title: '', solicitation_number: '', agency: '', set_aside_code: '', naics: '', response_deadline: '', url: '', description: '' })
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const save = async () => {
    setErr(''); setMsg('')
    try {
      const r = await api.post('/api/opportunities', f)
      setMsg(`Added. `)
      setF({ title: '', solicitation_number: '', agency: '', set_aside_code: '', naics: '', response_deadline: '', url: '', description: '' })
      window.location.href = `/opportunities/${r.id}`
    } catch (e) { setErr(e.message) }
  }
  return (
    <div className="panel">
      <h2>Add one manually</h2>
      <p className="small muted">For state and local bids (for example New York OGS SDVOB opportunities), GSA eBuy RFQs, or SBA SubNet subcontracting posts. These sites need a login or have no public API.</p>
      <div className="grid g4">
        <label className="f">Title<input value={f.title} onChange={set('title')} /></label>
        <label className="f">Solicitation #<input value={f.solicitation_number} onChange={set('solicitation_number')} /></label>
        <label className="f">Agency / buyer<input value={f.agency} onChange={set('agency')} /></label>
        <label className="f">Set-aside code<input value={f.set_aside_code} onChange={set('set_aside_code')} placeholder="SDVOSBC, SBA, blank" /></label>
        <label className="f">NAICS<input value={f.naics} onChange={set('naics')} /></label>
        <label className="f">Response due<input type="date" value={f.response_deadline} onChange={set('response_deadline')} /></label>
        <label className="f" style={{ gridColumn: 'span 2' }}>Link<input value={f.url} onChange={set('url')} /></label>
      </div>
      <label className="f" style={{ marginTop: 10 }}>Description<textarea value={f.description} onChange={set('description')} /></label>
      <div className="row" style={{ marginTop: 10 }}>
        <button className="primary" onClick={save} disabled={!f.title}>Add opportunity</button>
        {msg && <span className="small">{msg}</span>}
        {err && <span className="small" style={{ color: 'var(--warn)' }}>{err}</span>}
      </div>
    </div>
  )
}
