import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, qs, fmtDue } from '../api'

const KIND_LABEL = { prime: 'Prime', agency: 'Agency', vendor: 'Vendor', teaming_partner: 'Teaming partner', apex_sbdc: 'APEX / SBDC', other: 'Other' }
const STAGE_LABEL = { identified: 'Identified', contacted: 'Contacted', meeting: 'Meeting', registered_supplier: 'Registered supplier', active: 'Active', inactive: 'Inactive' }
const BT_LABEL = { '': 'Any', sdvosb: 'SDVOSB', vosb: 'VOSB', wosb: 'WOSB', hubzone: 'HUBZone', '8a': '8(a)', small: 'Any small (needs NAICS)' }
const today = () => new Date().toISOString().slice(0, 10)
const list = (s) => s.split(/[,\n]/).map((x) => x.trim()).filter(Boolean)
const btTags = (bt) => Object.entries(bt || {}).filter(([, v]) => v === true).map(([k]) => k)

export default function Contacts() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || 'orgs'
  const [meta, setMeta] = useState(null)
  useEffect(() => { api.get('/api/crm/meta').then(setMeta) }, [])
  if (!meta) return <p className="muted">Loading…</p>
  const go = (t, extra = {}) => setParams({ ...(t === 'orgs' ? {} : { tab: t }), ...extra })
  return (
    <>
      <h1>Contacts</h1>
      <p className="sub">Primes, agencies, vendors and teaming partners, with an interaction log and follow-up reminders.</p>
      <div className="tabs">
        <button className={tab === 'orgs' ? 'on' : ''} onClick={() => go('orgs')}>Organizations</button>
        <button className={tab === 'followups' ? 'on' : ''} onClick={() => go('followups')}>Follow-ups</button>
        <button className={tab === 'teaming' ? 'on' : ''} onClick={() => go('teaming')}>Find teaming partners</button>
      </div>
      {tab === 'orgs' && <Organizations meta={meta} selected={params.get('id')} onSelect={(id) => go('orgs', id ? { id } : {})} />}
      {tab === 'followups' && <FollowUps onOpen={(id) => go('orgs', { id })} />}
      {tab === 'teaming' && <Teaming onOpen={(id) => go('orgs', { id })} />}
    </>
  )
}

// ------------------------------------------------------------------ organizations
function Organizations({ meta, selected, onSelect }) {
  const [f, setF] = useState({ kind: '', stage: '', q: '' })
  const [rows, setRows] = useState(null)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const load = () => api.get('/api/crm/organizations?' + qs(f)).then(setRows).catch((e) => setErr(e.message))
  useEffect(() => { const t = setTimeout(load, 200); return () => clearTimeout(t) }, [f.kind, f.stage, f.q])

  const seed = async () => {
    setMsg(''); setErr('')
    try {
      const r = await api.post('/api/crm/seed')
      setMsg(r.added ? `Added ${r.added} starter organizations.` : 'The starter list is already loaded.')
      load()
    } catch (e) { setErr(e.message) }
  }
  const add = async () => {
    const name = window.prompt('Organization name')
    if (!name) return
    try { const o = await api.post('/api/crm/organizations', { name }); await load(); onSelect(o.id) } catch (e) { setErr(e.message) }
  }

  return (
    <>
      {msg && <div className="okmsg">{msg}</div>}
      {err && <div className="err">{err}</div>}
      <div className="row spread" style={{ marginBottom: 12 }}>
        <div className="row">
          <input placeholder="Search name, notes, UEI, city" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} style={{ minWidth: 240 }} />
          <select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
            <option value="">All kinds</option>
            {meta.kinds.map((k) => <option key={k} value={k}>{KIND_LABEL[k] || k}</option>)}
          </select>
          <select value={f.stage} onChange={(e) => setF({ ...f, stage: e.target.value })}>
            <option value="">All stages</option>
            {meta.stages.map((s) => <option key={s} value={s}>{STAGE_LABEL[s] || s}</option>)}
          </select>
        </div>
        <div className="row">
          <button onClick={seed}>Load starter list</button>
          <button className="primary" onClick={add}>Add organization</button>
        </div>
      </div>
      <div className={selected ? 'crm-split' : ''}>
        <div className="panel" style={{ padding: 0, overflowX: 'auto' }}>
          {!rows ? <p className="muted" style={{ padding: 16 }}>Loading…</p> : !rows.length ? (
            <p className="muted" style={{ padding: 16 }}>No organizations yet. Load the starter list or add one.</p>
          ) : (
            <table>
              <thead><tr><th>Name</th><th>Kind</th><th>Stage</th>{!selected && <th>Location</th>}<th>Next follow-up</th></tr></thead>
              <tbody>
                {rows.map((o) => {
                  const due = o.next_follow_up
                  return (
                    <tr key={o.id} className={'click' + (String(o.id) === String(selected) ? ' sel' : '')} onClick={() => onSelect(o.id)}>
                      <td><div className="t">{o.name}</div>{btTags(o.business_types).length > 0 && <div className="small muted">{btTags(o.business_types).join(' · ')}</div>}</td>
                      <td className="small">{KIND_LABEL[o.kind] || o.kind}</td>
                      <td><span className="tag">{STAGE_LABEL[o.stage] || o.stage}</span></td>
                      {!selected && <td className="small">{[o.city, o.state].filter(Boolean).join(', ')}</td>}
                      <td className={'small' + (due && due <= today() ? ' due-soon' : '')}>{due ? fmtDue(due) : ''}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
        {selected && <OrgEditor key={selected} id={selected} meta={meta} onChanged={load} onClose={() => onSelect(null)} />}
      </div>
    </>
  )
}

const blankInteraction = () => ({ date: today(), kind: 'email', summary: '', next_step: '', follow_up_date: '', contact_id: '', done: false })

function OrgEditor({ id, meta, onChanged, onClose }) {
  const [o, setO] = useState(null)
  const [text, setText] = useState({ naics: '', tags: '' })
  const [contact, setContact] = useState(null) // {id?, name, title, email, phone, notes}
  const [ix, setIx] = useState(blankInteraction)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const apply = (d) => { setO(d); setText({ naics: (d.naics_codes || []).join(', '), tags: (d.tags || []).join(', ') }) }
  const reload = () => api.get(`/api/crm/organizations/${id}`).then(apply).catch((e) => setErr(e.message))
  useEffect(() => { reload() }, [id])
  if (err && !o) return <div className="err">{err}</div>
  if (!o) return <div className="panel muted">Loading…</div>

  const set = (k) => (e) => setO({ ...o, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const wrap = async (fn, okText) => {
    setMsg(''); setErr('')
    try { await fn(); if (okText) setMsg(okText); onChanged() } catch (e) { setErr(e.message) }
  }
  const save = () => wrap(async () => {
    const { contacts, interactions, next_follow_up, contact_count, created_at, updated_at, source, id: _, ...body } = o
    apply(await api.put(`/api/crm/organizations/${id}`, { ...body, naics_codes: list(text.naics), tags: list(text.tags) }))
  }, 'Saved.')
  const remove = () => {
    if (!window.confirm(`Delete ${o.name} with its contacts and interaction log?`)) return
    wrap(async () => { await api.del(`/api/crm/organizations/${id}`); onClose() })
  }
  const saveContact = () => wrap(async () => {
    const { id: cid, organization_id, ...body } = contact
    if (cid) await api.put(`/api/crm/organizations/${id}/contacts/${cid}`, body)
    else await api.post(`/api/crm/organizations/${id}/contacts`, body)
    setContact(null); await reload()
  })
  const delContact = (c) => window.confirm(`Remove ${c.name}?`) && wrap(async () => { await api.del(`/api/crm/organizations/${id}/contacts/${c.id}`); await reload() })
  const addIx = () => wrap(async () => {
    await api.post(`/api/crm/organizations/${id}/interactions`, { ...ix, contact_id: ix.contact_id ? Number(ix.contact_id) : null })
    setIx(blankInteraction()); await reload()
  })
  const toggleIx = (i) => wrap(async () => { await api.put(`/api/crm/interactions/${i.id}`, { done: !i.done }); await reload() })
  const delIx = (i) => window.confirm('Delete this log entry?') && wrap(async () => { await api.del(`/api/crm/interactions/${i.id}`); await reload() })
  const contactName = (cid) => o.contacts.find((c) => c.id === cid)?.name

  return (
    <div className="panel">
      <div className="row spread">
        <input className="title-input" value={o.name} onChange={set('name')} />
        <button className="link" onClick={onClose}>Close</button>
      </div>
      {msg && <div className="okmsg">{msg}</div>}
      {err && <div className="err">{err}</div>}
      <div className="grid g2" style={{ marginTop: 8 }}>
        <label className="f">Kind<select value={o.kind} onChange={set('kind')}>{meta.kinds.map((k) => <option key={k} value={k}>{KIND_LABEL[k] || k}</option>)}</select></label>
        <label className="f">Stage<select value={o.stage} onChange={set('stage')}>{meta.stages.map((s) => <option key={s} value={s}>{STAGE_LABEL[s] || s}</option>)}</select></label>
        <label className="f">Website<input value={o.website} onChange={set('website')} /></label>
        <label className="f">Supplier portal / small business office<input value={o.supplier_portal} onChange={set('supplier_portal')} /></label>
        <label className="f">UEI<input className="mono" value={o.uei} onChange={set('uei')} /></label>
        <label className="f">CAGE<input className="mono" value={o.cage} onChange={set('cage')} /></label>
        <label className="f">City<input value={o.city} onChange={set('city')} /></label>
        <label className="f">State<input value={o.state} maxLength={2} onChange={set('state')} /></label>
        <label className="f">NAICS codes<input value={text.naics} onChange={(e) => setText({ ...text, naics: e.target.value })} /></label>
        <label className="f">Tags<input value={text.tags} onChange={(e) => setText({ ...text, tags: e.target.value })} /></label>
      </div>
      <div className="row" style={{ marginTop: 10 }}>
        {(o.website || o.supplier_portal) && <span className="small">
          {o.website && <a href={o.website} target="_blank" rel="noreferrer">Website</a>}
          {o.website && o.supplier_portal && ' · '}
          {o.supplier_portal && <a href={o.supplier_portal} target="_blank" rel="noreferrer">Supplier portal</a>}
        </span>}
        <label className="check"><input type="checkbox" checked={o.is_manufacturer} onChange={set('is_manufacturer')} /> Manufacturer</label>
        {['SB', 'SDVOSB', 'VOSB', 'WOSB', 'HUBZone', '8A'].map((t) => (
          <label key={t} className="check small"><input type="checkbox" checked={!!(o.business_types || {})[t]} onChange={(e) => setO({ ...o, business_types: { ...(o.business_types || {}), [t]: e.target.checked } })} /> {t === 'SB' ? 'Small business' : t}</label>
        ))}
        {o.source !== 'manual' && <span className="small muted">Source: {o.source}</span>}
      </div>
      <label className="f" style={{ marginTop: 10 }}>Capabilities<textarea value={o.capabilities} onChange={set('capabilities')} style={{ minHeight: 50 }} /></label>
      <label className="f" style={{ marginTop: 10 }}>Notes<textarea value={o.notes} onChange={set('notes')} /></label>
      <div className="row spread" style={{ marginTop: 10 }}>
        <button className="primary" onClick={save}>Save</button>
        <button className="link" style={{ color: 'var(--no)' }} onClick={remove}>Delete organization</button>
      </div>

      <h3>Contacts</h3>
      {o.contacts.length === 0 && !contact && <p className="small muted">No contacts yet.</p>}
      <ul className="clean">
        {o.contacts.map((c) => (
          <li key={c.id}>
            <b>{c.name}</b>{c.title && `, ${c.title}`}
            {c.email && <> · <a href={`mailto:${c.email}`}>{c.email}</a></>}
            {c.phone && ` · ${c.phone}`}
            {' '}<button className="link small" onClick={() => setContact(c)}>edit</button>
            {' '}<button className="link small" onClick={() => delContact(c)}>remove</button>
            {c.notes && <div className="small muted">{c.notes}</div>}
          </li>
        ))}
      </ul>
      {contact ? (
        <div className="crm-box">
          <div className="grid g2">
            {['name', 'title', 'email', 'phone'].map((k) => (
              <label key={k} className="f">{k[0].toUpperCase() + k.slice(1)}<input value={contact[k] || ''} onChange={(e) => setContact({ ...contact, [k]: e.target.value })} /></label>
            ))}
          </div>
          <label className="f" style={{ marginTop: 8 }}>Notes<input value={contact.notes || ''} onChange={(e) => setContact({ ...contact, notes: e.target.value })} /></label>
          <div className="row" style={{ marginTop: 8 }}>
            <button className="primary" disabled={!contact.name} onClick={saveContact}>{contact.id ? 'Save contact' : 'Add contact'}</button>
            <button onClick={() => setContact(null)}>Cancel</button>
          </div>
        </div>
      ) : <button style={{ marginTop: 6 }} onClick={() => setContact({ name: '', title: '', email: '', phone: '', notes: '' })}>Add contact</button>}

      <h3>Interaction log</h3>
      <div className="crm-box">
        <div className="grid g3">
          <label className="f">Date<input type="date" value={ix.date} onChange={(e) => setIx({ ...ix, date: e.target.value })} /></label>
          <label className="f">Kind<select value={ix.kind} onChange={(e) => setIx({ ...ix, kind: e.target.value })}>{meta.interaction_kinds.map((k) => <option key={k}>{k}</option>)}</select></label>
          <label className="f">Contact<select value={ix.contact_id} onChange={(e) => setIx({ ...ix, contact_id: e.target.value })}>
            <option value="">(none)</option>{o.contacts.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select></label>
        </div>
        <label className="f" style={{ marginTop: 8 }}>Summary<textarea style={{ minHeight: 50 }} value={ix.summary} onChange={(e) => setIx({ ...ix, summary: e.target.value })} /></label>
        <div className="grid g2" style={{ marginTop: 8 }}>
          <label className="f">Next step<input value={ix.next_step} onChange={(e) => setIx({ ...ix, next_step: e.target.value })} /></label>
          <label className="f">Follow-up date<input type="date" value={ix.follow_up_date} onChange={(e) => setIx({ ...ix, follow_up_date: e.target.value })} /></label>
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <label className="check"><input type="checkbox" checked={ix.done} onChange={(e) => setIx({ ...ix, done: e.target.checked })} /> Done (no follow-up needed)</label>
          <button className="primary" disabled={!ix.summary && !ix.next_step} onClick={addIx}>Add to log</button>
        </div>
      </div>
      {o.interactions.length === 0 ? <p className="small muted">Nothing logged yet.</p> : (
        <table style={{ marginTop: 8 }}>
          <tbody>
            {o.interactions.map((i) => {
              const overdue = !i.done && i.follow_up_date && i.follow_up_date < today()
              return (
                <tr key={i.id}>
                  <td className="small mono" style={{ whiteSpace: 'nowrap' }}>{i.date}<div className="muted">{i.kind}</div></td>
                  <td>
                    <div>{i.summary}</div>
                    {i.contact_id && contactName(i.contact_id) && <div className="small muted">with {contactName(i.contact_id)}</div>}
                    {i.next_step && <div className="small">Next: {i.next_step}</div>}
                    {i.follow_up_date && <div className={'small' + (overdue ? ' due-soon' : ' muted')}>Follow up {fmtDue(i.follow_up_date)}{overdue ? ' (overdue)' : ''}</div>}
                  </td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <label className="check"><input type="checkbox" checked={i.done} onChange={() => toggleIx(i)} /> done</label>
                    <button className="link small" onClick={() => delIx(i)}>delete</button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ follow-ups
function FollowUps({ onOpen }) {
  const [days, setDays] = useState(30)
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  const load = () => api.get('/api/crm/follow-ups?' + qs({ within_days: days })).then(setRows).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [days])
  const done = async (r) => {
    try { await api.put(`/api/crm/interactions/${r.id}`, { done: true }); load() } catch (e) { setErr(e.message) }
  }
  if (err) return <div className="err">{err}</div>
  if (!rows) return <p className="muted">Loading…</p>
  const overdue = rows.filter((r) => r.overdue)
  const upcoming = rows.filter((r) => !r.overdue)
  const Section = ({ title, items, cls }) => (
    <div className="panel">
      <h2>{title} <span className="muted small">({items.length})</span></h2>
      {!items.length ? <p className="small muted">None.</p> : (
        <table>
          <thead><tr><th>Due</th><th>Organization</th><th>What</th><th></th></tr></thead>
          <tbody>
            {items.map((r) => (
              <tr key={r.id}>
                <td className={'small' + (cls ? ` ${cls}` : '')} style={{ whiteSpace: 'nowrap' }}>{fmtDue(r.follow_up_date)}</td>
                <td><button className="link" onClick={() => onOpen(r.organization_id)}>{r.organization}</button></td>
                <td>{r.next_step || r.summary}{r.next_step && r.summary && <div className="small muted">{r.summary}</div>}</td>
                <td><button onClick={() => done(r)}>Mark done</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
  return (
    <>
      <div className="row" style={{ marginBottom: 12 }}>
        <span className="small muted">Show upcoming within</span>
        <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
          {[7, 14, 30, 90, 365].map((d) => <option key={d} value={d}>{d} days</option>)}
        </select>
      </div>
      <Section title="Overdue" items={overdue} cls="due-soon" />
      <Section title="Upcoming" items={upcoming} />
    </>
  )
}

// ------------------------------------------------------------------ teaming finder
function Teaming({ onOpen }) {
  const [f, setF] = useState({ naics: '', state: '', business_type: 'sdvosb', q: '' })
  const [page, setPage] = useState(0)
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [kinds, setKinds] = useState({})

  const search = async (p = 0) => {
    setErr(''); setMsg(''); setBusy(true)
    try { setRes(await api.get('/api/crm/teaming/search?' + qs({ ...f, page: p }))); setPage(p) } catch (e) { setErr(e.message) }
    setBusy(false)
  }
  const save = async (ent) => {
    setErr(''); setMsg('')
    try {
      const r = await api.post('/api/crm/teaming/save', { entity: ent, kind: kinds[ent.uei] || 'teaming_partner' })
      setMsg(`${r.created ? 'Saved' : 'Updated'} ${r.organization.name}.`)
      setRes({ ...res, results: res.results.map((x) => (x.uei === ent.uei ? { ...x, saved_id: r.organization.id, saved_kind: r.organization.kind } : x)) })
    } catch (e) { setErr(e.message) }
  }

  return (
    <>
      <div className="notice small">
        Teaming with other SDVOSBs and small manufacturers lets you bid set-asides you cannot fully perform alone and still meet the limitations on subcontracting (FAR 52.219-14), since work done by similarly situated subcontractors counts toward your share.
        Searches use your SAM.gov public API key, which has a small daily request limit (10 per day without a SAM.gov role), so search with specific filters. Each search is one request and returns 10 entities. POC email and phone need a higher access level and are usually blank.
      </div>
      <div className="panel">
        <div className="grid g4">
          <label className="f">NAICS<input className="mono" placeholder="332710" value={f.naics} onChange={(e) => setF({ ...f, naics: e.target.value.trim() })} /></label>
          <label className="f">State<input placeholder="CT" maxLength={2} value={f.state} onChange={(e) => setF({ ...f, state: e.target.value.toUpperCase() })} /></label>
          <label className="f">Business type<select value={f.business_type} onChange={(e) => setF({ ...f, business_type: e.target.value })}>
            {Object.entries(BT_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select></label>
          <label className="f">Name contains<input value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} onKeyDown={(e) => e.key === 'Enter' && search(0)} /></label>
        </div>
        <div className="row" style={{ marginTop: 12 }}>
          <button className="primary" disabled={busy} onClick={() => search(0)}>{busy ? 'Searching…' : 'Search SAM.gov'}</button>
          <span className="small muted">Active registrations only. NAICS matches any code on the registration.</span>
        </div>
      </div>
      {err && <div className="err">{err}</div>}
      {msg && <div className="okmsg">{msg}</div>}
      {res && (
        <div className="panel" style={{ padding: 0, overflowX: 'auto' }}>
          <div className="row spread" style={{ padding: '12px 16px' }}>
            <span className="small muted">{res.total != null ? `${res.total.toLocaleString()} matches` : `${res.results.length} shown`}, page {res.page + 1}</span>
            <div className="row">
              <button disabled={busy || page === 0} onClick={() => search(page - 1)}>Previous</button>
              <button disabled={busy || !res.has_more} onClick={() => search(page + 1)}>Next</button>
            </div>
          </div>
          {!res.results.length ? <p className="muted" style={{ padding: 16 }}>No matches.</p> : (
            <table>
              <thead><tr><th>Name</th><th>Location</th><th>UEI / CAGE</th><th>Types</th><th>NAICS</th><th>Save</th></tr></thead>
              <tbody>
                {res.results.map((e) => (
                  <tr key={e.uei || e.name}>
                    <td>
                      <div className="t">{e.name}</div>
                      {e.website && <a className="small" href={/^https?:/.test(e.website) ? e.website : `https://${e.website}`} target="_blank" rel="noreferrer">{e.website}</a>}
                      {e.poc?.name && <div className="small muted">{e.poc.name}{e.poc.title ? `, ${e.poc.title}` : ''}</div>}
                    </td>
                    <td className="small">{[e.city, e.state].filter(Boolean).join(', ')}</td>
                    <td className="mono">{e.uei}<div className="muted">{e.cage}</div></td>
                    <td><div className="row" style={{ gap: 4 }}>
                      {btTags(e.business_types).map((t) => <span key={t} className="tag">{t}</span>)}
                      {e.is_manufacturer && <span className="tag">MFR</span>}
                    </div></td>
                    <td className="mono small">{e.primary_naics && <b>{e.primary_naics}</b>}{e.naics_codes.filter((n) => n !== e.primary_naics).length > 0 && <div className="muted">{e.naics_codes.filter((n) => n !== e.primary_naics).slice(0, 6).join(', ')}{e.naics_codes.length > 7 ? ' …' : ''}</div>}</td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <div className="row" style={{ gap: 6 }}>
                        <select value={kinds[e.uei] || e.saved_kind || 'teaming_partner'} onChange={(ev) => setKinds({ ...kinds, [e.uei]: ev.target.value })}>
                          <option value="teaming_partner">Teaming partner</option>
                          <option value="vendor">Vendor</option>
                        </select>
                        <button onClick={() => save(e)}>{e.saved_id ? 'Update' : 'Save to contacts'}</button>
                      </div>
                      {e.saved_id && <button className="link small" onClick={() => onOpen(e.saved_id)}>Open saved record</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </>
  )
}
