import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ASSIST, CATEGORIES, CHECKLISTS } from '../resources'

const STORE_KEY = 'govbid.checklists'

function loadChecks() {
  try { return JSON.parse(localStorage.getItem(STORE_KEY) || '{}') } catch { return {} }
}
function saveChecks(v) {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(v)) } catch {}
}

export default function Resources() {
  const [q, setQ] = useState('')
  const [cat, setCat] = useState('')
  const [freeOnly, setFreeOnly] = useState(false)
  const [copied, setCopied] = useState('')

  const cats = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return CATEGORIES.filter((c) => !cat || c.id === cat)
      .map((c) => ({
        ...c,
        items: c.items.filter(
          (i) => (!freeOnly || i.free) && (!needle || `${i.name} ${i.desc} ${(i.clauses || []).join(' ')}`.toLowerCase().includes(needle))
        ),
      }))
      .filter((c) => c.items.length)
  }, [q, cat, freeOnly])

  const copy = async (id) => {
    try { await navigator.clipboard.writeText(id); setCopied(id); setTimeout(() => setCopied(''), 1500) } catch {}
  }

  return (
    <>
      <h1>Resources</h1>
      <p className="sub">Standards, regulations and guides for writing technical proposals and delivering technical data packages for completed work.</p>

      <div className="tabs">
        <button className={cat === '' ? 'on' : ''} onClick={() => setCat('')}>All</button>
        {CATEGORIES.map((c) => (
          <button key={c.id} className={cat === c.id ? 'on' : ''} onClick={() => setCat(c.id)}>{c.title}</button>
        ))}
        <button className={cat === 'checklists' ? 'on' : ''} onClick={() => setCat('checklists')}>Checklists</button>
      </div>

      {cat !== 'checklists' && (
        <>
          <div className="row" style={{ marginBottom: 16 }}>
            <input style={{ minWidth: 320 }} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search: GD&T, IUID, 252.204-7012, test report…" />
            <label className="check"><input type="checkbox" checked={freeOnly} onChange={(e) => setFreeOnly(e.target.checked)} /> Free documents only</label>
          </div>

          {!cat && (
            <div className="panel std-lookup">
              <div className="row spread">
                <div>
                  <h2 style={{ margin: 0 }}>Military and industry standards</h2>
                  <p className="small muted" style={{ margin: '4px 0 0' }}>
                    Hundreds of MIL-STDs, MIL-DTL and MIL-PRF specs, DIDs and industry standards, with lookup of any document ID, revision tracking, your own PDF copies and the standards each solicitation cites.
                  </p>
                </div>
                <Link className="btn primary" to="/standards">Open the Standards library</Link>
              </div>
            </div>
          )}

          {cats.map((c) => (
            <div className="panel" key={c.id}>
              <h2>{c.title}</h2>
              <p className="small muted" style={{ marginTop: -6 }}>{c.blurb}</p>
              <table>
                <tbody>
                  {c.items.map((i) => (
                    <tr key={i.name}>
                      <td style={{ width: '38%' }}>
                        <a href={i.url} target="_blank" rel="noreferrer" className="t">{i.name}</a>
                        <div className="row small" style={{ gap: 6, marginTop: 4 }}>
                          <span className={`badge ${i.free ? 'b-eligible_now' : 'b-not_eligible'}`}>{i.free ? 'Free' : 'Paid'}</span>
                          {(i.clauses || []).map((cl) => <span key={cl} className="tag">{cl}</span>)}
                        </div>
                      </td>
                      <td>
                        {i.desc}
                        {i.id && (
                          <div className="small" style={{ marginTop: 4 }}>
                            <span className="muted">On ASSIST, search document ID </span>
                            <button className="link mono" onClick={() => copy(i.id)} title="Copy document ID">{i.id}</button>
                            {copied === i.id && <span className="muted"> copied</span>}
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
          {cats.length === 0 && <p className="muted">Nothing matches that search.</p>}

          <p className="small muted">
            MIL-STDs and DIDs are free on <a href={ASSIST} target="_blank" rel="noreferrer">ASSIST QuickSearch</a>. Contracts cite a specific revision; use that one, not necessarily the newest. Paid industry standards are often available through a university or public library.
          </p>
        </>
      )}

      {cat === 'checklists' && <Checklists />}
    </>
  )
}

function Checklists() {
  const [checks, setChecks] = useState(loadChecks)
  const toggle = (list, idx) => {
    const next = { ...checks, [list]: { ...(checks[list] || {}), [idx]: !checks[list]?.[idx] } }
    setChecks(next); saveChecks(next)
  }
  const reset = (list) => {
    const next = { ...checks, [list]: {} }
    setChecks(next); saveChecks(next)
  }
  return (
    <div className="grid g2">
      {CHECKLISTS.map((cl) => {
        const done = cl.items.filter((_, i) => checks[cl.id]?.[i]).length
        return (
          <div className="panel" key={cl.id}>
            <div className="row spread">
              <h2 style={{ margin: 0 }}>{cl.title}</h2>
              <span className="small muted">{done}/{cl.items.length}</span>
            </div>
            <div style={{ marginTop: 12 }}>
              {cl.items.map((item, i) => (
                <label key={i} className="check" style={{ alignItems: 'flex-start', marginBottom: 8 }}>
                  <input type="checkbox" checked={!!checks[cl.id]?.[i]} onChange={() => toggle(cl.id, i)} style={{ marginTop: 3 }} />
                  <span style={{ textDecoration: checks[cl.id]?.[i] ? 'line-through' : 'none', color: checks[cl.id]?.[i] ? 'var(--ink-3)' : 'inherit' }}>{item}</span>
                </label>
              ))}
            </div>
            <div className="row" style={{ marginTop: 8 }}>
              <button onClick={() => reset(cl.id)}>Reset</button>
              <button onClick={() => window.print()}>Print</button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
