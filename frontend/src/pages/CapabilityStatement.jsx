import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'

const lines = (s) => s.split('\n').map((x) => x.trim()).filter(Boolean)
const FIELDS = ['tagline', 'overview', 'competencies', 'differentiators', 'past_performance_ids', 'contact_name', 'contact_title', 'contact_phone', 'contact_email', 'website']

export default function CapabilityStatement() {
  const [info, setInfo] = useState(null)
  const [form, setForm] = useState(null)
  const [text, setText] = useState({ competencies: '', differentiators: '' })
  const [opps, setOpps] = useState([])
  const [oppId, setOppId] = useState('')
  const [pdfUrl, setPdfUrl] = useState('')
  const [fit, setFit] = useState(null)
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [logoVer, setLogoVer] = useState(0)
  const pdfRef = useRef(null)
  const logoRef = useRef()

  const applySettings = (s) => {
    setForm(Object.fromEntries(FIELDS.map((k) => [k, s[k]])))
    setText({ competencies: (s.competencies || []).join('\n'), differentiators: (s.differentiators || []).join('\n') })
  }

  useEffect(() => {
    api.get('/api/writing/capability').then((d) => { setInfo(d); applySettings(d.settings) }).catch((e) => setErr(e.message))
    api.get('/api/writing/capability/opportunities').then(setOpps).catch(() => {})
  }, [])

  const body = () => form && ({
    ...form,
    competencies: lines(text.competencies),
    differentiators: lines(text.differentiators),
  })

  // Live preview, debounced
  useEffect(() => {
    if (!form) return
    const t = setTimeout(async () => {
      try {
        const res = await api.post('/api/writing/capability/pdf', { settings: body(), opp_id: oppId ? Number(oppId) : null })
        setFit({ shrunk: res.headers.get('X-Fit-Shrunk') === '1', overflow: res.headers.get('X-Fit-Overflow') === '1', scale: res.headers.get('X-Fit-Scale') })
        const url = URL.createObjectURL(await res.blob())
        if (pdfRef.current) URL.revokeObjectURL(pdfRef.current)
        pdfRef.current = url
        setPdfUrl(url)
      } catch (e) { setErr(e.message) }
    }, 700)
    return () => clearTimeout(t)
  }, [form, text, oppId, logoVer])

  if (err && !info) return <div className="err">{err}</div>
  if (!info || !form) return <p className="muted">Loading…</p>

  const set = (k) => (e) => { setForm({ ...form, [k]: e.target.value }); setDirty(true) }
  const setT = (k) => (e) => { setText({ ...text, [k]: e.target.value }); setDirty(true) }
  const togglePP = (id) => {
    const ids = form.past_performance_ids.includes(id) ? form.past_performance_ids.filter((x) => x !== id) : [...form.past_performance_ids, id]
    setForm({ ...form, past_performance_ids: ids }); setDirty(true)
  }
  const movePP = (id, d) => {
    const ids = [...form.past_performance_ids]
    const i = ids.indexOf(id)
    const j = i + d
    if (i < 0 || j < 0 || j >= ids.length) return
    ;[ids[i], ids[j]] = [ids[j], ids[i]]
    setForm({ ...form, past_performance_ids: ids }); setDirty(true)
  }

  const run = async (label, fn) => {
    setBusy(label); setErr(''); setMsg('')
    try { await fn() } catch (e) { setErr(e.message) }
    setBusy('')
  }

  const save = () => run('save', async () => {
    const s = await api.put('/api/writing/capability', body())
    applySettings(s); setDirty(false); setMsg('Saved.')
  })

  const tailor = () => run('tailor', async () => {
    const t = await api.post('/api/writing/capability/tailor', { opp_id: Number(oppId), settings: body() })
    setForm({ ...form, tagline: t.tagline, past_performance_ids: t.past_performance_ids })
    setText({ ...text, competencies: t.competencies.join('\n') })
    setDirty(true)
    setMsg(`Loaded ${t.method === 'claude' ? 'Claude-suggested wording' : 'keyword-based ordering'} into the editor. Review it, then save if you want to keep it.${t.warning ? ' ' + t.warning : ''}`)
  })

  const uploadLogo = () => run('logo', async () => {
    const f = logoRef.current.files[0]
    if (!f) return
    const fd = new FormData()
    fd.append('file', f)
    await api.upload('/api/writing/capability/logo', fd)
    logoRef.current.value = ''
    setInfo({ ...info, settings: { ...info.settings, logo_file: 'set' } })
    setLogoVer((v) => v + 1)
  })
  const removeLogo = () => run('logo', async () => {
    await api.del('/api/writing/capability/logo')
    setInfo({ ...info, settings: { ...info.settings, logo_file: '' } })
    setLogoVer((v) => v + 1)
  })

  const fileBase = `${(info.company.name || 'Company').replace(/[^A-Za-z0-9._-]+/g, '_')}_Capability_Statement`
  const downloadPdf = () => {
    if (!pdfUrl) return
    const a = document.createElement('a')
    a.href = pdfUrl
    a.download = `${fileBase}.pdf`
    a.click()
  }
  const downloadDocx = () => run('docx', async () => {
    const res = await api.post('/api/writing/capability/docx', { settings: body(), opp_id: oppId ? Number(oppId) : null })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(await res.blob())
    a.download = `${fileBase}.docx`
    a.click()
    setTimeout(() => URL.revokeObjectURL(a.href), 2000)
  })

  const c = info.company
  const ppById = Object.fromEntries(info.past_performance.map((p) => [p.id, p]))

  return (
    <>
      <div className="row spread">
        <div>
          <h1>Capability statement</h1>
          <p className="sub">One page, letter size. Company data comes from your <Link to="/profile">profile</Link>; past performance from the <Link to="/past-performance">past performance log</Link>.</p>
        </div>
        <div className="row">
          <button onClick={downloadPdf} disabled={!pdfUrl}>Download PDF</button>
          <button onClick={downloadDocx} disabled={!!busy}>{busy === 'docx' ? 'Building…' : 'Download .docx'}</button>
          <button className="primary" onClick={save} disabled={busy === 'save' || !dirty}>{dirty ? 'Save' : 'Saved'}</button>
        </div>
      </div>

      {err && <div className="err">{err}</div>}
      {msg && <div className="okmsg">{msg}</div>}

      <div className="cap-layout">
        <div className="cap-editor">
          <div className="panel">
            <h3 style={{ marginTop: 0 }}>Tailor to an opportunity</h3>
            <div className="row">
              <select value={oppId} onChange={(e) => setOppId(e.target.value)} style={{ flex: 1, minWidth: 0 }}>
                <option value="">General (not tailored)</option>
                {opps.map((o) => <option key={o.id} value={o.id}>{o.pipeline ? '★ ' : ''}{o.label}</option>)}
              </select>
              <button onClick={tailor} disabled={!oppId || !!busy}>{busy === 'tailor' ? 'Working…' : info.ai_configured ? 'Suggest wording (Claude)' : 'Load suggested order'}</button>
            </div>
            <p className="small muted" style={{ marginBottom: 0 }}>With an opportunity picked, the preview puts the most relevant competencies first and picks the best-matching past performance. Your saved statement is not changed unless you load the suggestions and save.</p>
          </div>

          <div className="panel">
            <h3 style={{ marginTop: 0 }}>Header</h3>
            <label className="f">Tagline<input value={form.tagline} onChange={set('tagline')} maxLength={160} placeholder="What you do, in one line" /></label>
            <label className="f" style={{ marginTop: 10 }}>Overview (optional, one or two sentences)<textarea rows={2} value={form.overview} onChange={set('overview')} /></label>
            <div className="row" style={{ marginTop: 10 }}>
              <span className="small muted">Logo: {info.settings.logo_file ? 'uploaded' : 'none'}</span>
              <input type="file" accept=".png,.jpg,.jpeg" ref={logoRef} onChange={uploadLogo} />
              {info.settings.logo_file && <button className="link small" onClick={removeLogo}>Remove logo</button>}
            </div>
          </div>

          <div className="panel">
            <h3 style={{ marginTop: 0 }}>Left column</h3>
            <label className="f">Core competencies (one per line)<textarea rows={6} value={text.competencies} onChange={setT('competencies')} /></label>
            {!text.competencies.trim() && c.keywords.length > 0 && (
              <button className="link small" onClick={() => { setText({ ...text, competencies: c.keywords.join('\n') }); setDirty(true) }}>Start from your profile keywords</button>
            )}
            <label className="f" style={{ marginTop: 10 }}>Differentiators (one per line)<textarea rows={4} value={text.differentiators} onChange={setT('differentiators')} /></label>
          </div>

          <div className="panel">
            <h3 style={{ marginTop: 0 }}>Past performance highlights</h3>
            {info.past_performance.length === 0 && <p className="small muted">No records yet. Add them in the <Link to="/past-performance">past performance log</Link>.</p>}
            {form.past_performance_ids.filter((id) => ppById[id]).map((id, i) => (
              <div key={id} className="row small cap-pp sel">
                <span className="mono">{i + 1}.</span>
                <span style={{ flex: 1 }}>{ppById[id].title} <span className="muted">{ppById[id].customer}</span></span>
                <button className="link small" onClick={() => movePP(id, -1)}>↑</button>
                <button className="link small" onClick={() => movePP(id, 1)}>↓</button>
                <button className="link small" onClick={() => togglePP(id)}>Remove</button>
              </div>
            ))}
            {info.past_performance.filter((p) => !form.past_performance_ids.includes(p.id)).map((p) => (
              <label key={p.id} className="check cap-pp">
                <input type="checkbox" checked={false} onChange={() => togglePP(p.id)} />
                <span>{p.title} <span className="muted small">{p.customer}{p.role === 'employment' || p.role === 'personal_project' ? ` (${p.role.replace('_', ' ')})` : ''}</span></span>
              </label>
            ))}
            <p className="small muted" style={{ marginBottom: 0 }}>Three is usually right for one page. Each entry shows its role (prime, sub, prior employment) as recorded.</p>
          </div>

          <div className="panel">
            <h3 style={{ marginTop: 0 }}>Contact</h3>
            <div className="grid g2">
              <label className="f">Name<input value={form.contact_name} onChange={set('contact_name')} /></label>
              <label className="f">Title<input value={form.contact_title} onChange={set('contact_title')} /></label>
              <label className="f">Phone<input value={form.contact_phone} onChange={set('contact_phone')} /></label>
              <label className="f">Email<input value={form.contact_email} onChange={set('contact_email')} /></label>
              <label className="f">Website<input value={form.website} onChange={set('website')} /></label>
            </div>
          </div>

          <div className="panel">
            <h3 style={{ marginTop: 0 }}>From your profile</h3>
            <table className="small"><tbody>
              <tr><th>Company</th><td>{c.name || <span className="due-soon">not set</span>}</td></tr>
              <tr><th>UEI / CAGE</th><td className="mono">{c.uei || '—'} / {c.cage || '—'}</td></tr>
              <tr><th>Certifications</th><td>{c.certifications.join('; ') || 'none claimed'}</td></tr>
              <tr><th>NAICS</th><td>{c.naics.join('; ') || '—'}</td></tr>
              <tr><th>PSC / FSC</th><td>{c.psc.join('; ') || '—'}</td></tr>
            </tbody></table>
            <p className="small muted" style={{ marginBottom: 0 }}>Pending certifications are shown as pending. Change them on the <Link to="/profile">profile</Link> page.</p>
          </div>
        </div>

        <div className="cap-preview">
          {fit?.overflow && <div className="err">The content does not fit on one page even at {Math.round(fit.scale * 100)}% type size. Shorten competencies or past performance; the overflow is cut off.</div>}
          {fit && !fit.overflow && fit.shrunk && <div className="notice">Type reduced to {Math.round(fit.scale * 100)}% to fit one page.</div>}
          {pdfUrl ? <iframe title="Capability statement preview" src={pdfUrl} className="cap-frame" /> : <p className="muted">Building preview…</p>}
        </div>
      </div>
    </>
  )
}
