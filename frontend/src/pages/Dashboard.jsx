import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { DaysLeft, EligBadge } from '../App.jsx'

export default function Dashboard() {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const [watch, setWatch] = useState('')
  const [copied, setCopied] = useState(false)
  const nav = useNavigate()
  const load = () => api.get('/api/dashboard').then(setD).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [])
  const checkNow = async () => {
    setWatch('Checking SAM.gov…')
    try {
      const r = await api.post('/api/watch/check')
      setWatch(`Checked ${r.checked} tracked opportunit${r.checked === 1 ? 'y' : 'ies'} (${r.requests_used} SAM.gov requests). ${r.changes.length} change(s).${r.errors.length ? ' ' + r.errors[0] : ''}`)
      load()
    } catch (e) { setWatch(e.message) }
  }
  const icsUrl = `${window.location.origin}/api/calendar.ics`
  const copyIcs = async () => { try { await navigator.clipboard.writeText(icsUrl); setCopied(true); setTimeout(() => setCopied(false), 1500) } catch {} }
  if (err) return <div className="err">{err}</div>
  if (!d) return <p className="muted">Loading…</p>

  const be = d.by_eligibility || {}
  return (
    <>
      <h1>Dashboard</h1>
      <p className="sub">Open opportunities you have pulled in, sorted by whether you can bid on them.</p>

      {!d.profile_complete && (
        <div className="notice">
          Your company profile is missing a name or NAICS codes. <Link to="/profile">Fill it in</Link> so syncing and eligibility checks match your business.
        </div>
      )}
      {d.sdvosb_status === 'pending' && (
        <div className="notice">
          VetCert is pending. SDVOSB and VA veteran set-asides show as <b>After certification</b> so you can track them, but you cannot be awarded them until SBA approves you.
        </div>
      )}

      {(d.alerts || []).map((a, i) => <div key={i} className="err">{a} <Link to="/profile">Profile</Link></div>)}

      <div className="grid g4" style={{ marginBottom: 16 }}>
        <Stat n={d.open_total} l="Open opportunities" />
        <Stat n={be.eligible_now || 0} l="You can bid now" />
        <Stat n={be.eligible_once_certified || 0} l="Waiting on a certification" />
        <Stat n={d.veteran_set_asides} l="SDVOSB / VA veteran set-asides" />
      </div>

      <div className="grid g2">
        <div className="panel">
          <h2>Due in the next 10 days</h2>
          {d.due_soon.length === 0 ? (
            <p className="muted">Nothing due soon that you are eligible for.</p>
          ) : (
            <table>
              <tbody>
                {d.due_soon.map((o) => (
                  <tr key={o.id} className="click" onClick={() => nav(`/opportunities/${o.id}`)}>
                    <td>
                      <div className="t">{o.title}</div>
                      <div className="small muted">{o.agency}</div>
                    </td>
                    <td><EligBadge status={o.eligibility.status} /></td>
                    <td><DaysLeft days={o.days_left} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div className="panel">
          <h2>Pipeline</h2>
          {Object.keys(d.pipeline).length === 0 ? (
            <p className="muted">No bids tracked yet. Open an opportunity and add it to your pipeline.</p>
          ) : (
            <table>
              <tbody>
                {Object.entries(d.pipeline).map(([k, v]) => (
                  <tr key={k}><td style={{ textTransform: 'capitalize' }}>{k.replace('_', ' ')}</td><td className="mono">{v}</td></tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="small" style={{ marginTop: 10 }}>Open packages: <b>{d.packages_open || 0}</b> · <Link to="/packages">Go to packages</Link></p>
          <h3>Sources</h3>
          <div className="row">
            {Object.entries(d.by_source).map(([k, v]) => (
              <span key={k} className="tag">{k}: {v}</span>
            ))}
            {Object.keys(d.by_source).length === 0 && <span className="muted">No data yet. Run a SAM.gov sync from Opportunities.</span>}
          </div>
          <p className="small muted" style={{ marginTop: 12 }}>
            Last sync: {d.last_sync ? new Date(d.last_sync + 'Z').toLocaleString() : 'never'}
          </p>
        </div>
      </div>

      <div className="grid g2">
        <div className="panel">
          <div className="row spread">
            <h2 style={{ margin: 0 }}>Amendments and changes</h2>
            <button onClick={checkNow}>Check tracked now</button>
          </div>
          {watch && <p className="small">{watch}</p>}
          {d.recent_changes?.length ? (
            <table className="small" style={{ marginTop: 8 }}><tbody>
              {d.recent_changes.map((c) => (
                <tr key={c.id} className="click" onClick={() => nav(`/opportunities/${c.opportunity_id}`)}>
                  <td><div className="t">{c.title}</div><div className="muted">{c.field}: {c.new}</div></td>
                  <td className="muted" style={{ whiteSpace: 'nowrap' }}>{c.detected_at?.slice(0, 10)}</td>
                </tr>
              ))}
            </tbody></table>
          ) : <p className="muted small">No unseen changes. Opportunities in the pipeline (tracking, evaluating, bidding) are re-checked when you click the button or run <span className="mono">python -m app.cli watch</span>. Each one uses one SAM.gov request.</p>}
        </div>
        <div className="panel">
          <div className="row spread"><h2 style={{ margin: 0 }}>Follow-ups</h2><Link className="small" to="/contacts">Contacts</Link></div>
          {d.follow_ups?.length ? (
            <table className="small" style={{ marginTop: 8 }}><tbody>
              {d.follow_ups.map((f) => (
                <tr key={f.id}><td><div className="t">{f.organization}</div><div className="muted">{f.next_step || f.summary}</div></td>
                  <td className={f.overdue ? 'due-soon' : 'muted'} style={{ whiteSpace: 'nowrap' }}>{f.overdue ? 'Overdue ' : ''}{f.follow_up_date}</td></tr>
              ))}
            </tbody></table>
          ) : <p className="muted small">Nothing due in the next two weeks.</p>}
          {d.cmmc && (
            <>
              <h3>Cyber compliance</h3>
              <p className="small" style={{ margin: 0 }}>Level 1: <b>{d.cmmc.level1_done} of {d.cmmc.level1_total}</b> · {d.cmmc.level2_done ? <>SPRS score: <b>{d.cmmc.sprs_score}</b> of {d.cmmc.sprs_max}</> : 'Level 2 (CUI) not started'}{d.cmmc.open_poam ? ` · ${d.cmmc.open_poam} open POA&M item(s)` : ''} · <Link to="/compliance">Open</Link></p>
            </>
          )}
          <h3>Calendar</h3>
          <p className="small" style={{ margin: 0 }}>Due dates, follow-ups and renewals as a calendar. In Apple Calendar choose File &gt; New Calendar Subscription and paste this address; it refreshes while GovBid Pro is running on this Mac. For Google Calendar, download the .ics and import it.</p>
          <div className="row" style={{ marginTop: 6 }}><span className="mono small">{icsUrl}</span><button className="link" onClick={copyIcs}>{copied ? 'Copied' : 'Copy'}</button><a className="small" href="/api/calendar.ics">Download .ics</a></div>
        </div>
      </div>
    </>
  )
}

function Stat({ n, l }) {
  return (
    <div className="stat">
      <div className="n">{n}</div>
      <div className="l">{l}</div>
    </div>
  )
}
