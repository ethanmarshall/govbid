import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, money } from '../api'
import { DaysLeft, EligBadge, useMeta } from '../App.jsx'

export default function Pipeline() {
  const meta = useMeta()
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  const load = () => api.get('/api/pipeline').then(setRows).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [])

  const move = async (r, stage) => {
    await api.put(`/api/opportunities/${r.id}/pipeline`, { ...r.pipeline, stage })
    load()
  }

  if (err) return <div className="err">{err}</div>
  if (!rows || !meta) return <p className="muted">Loading…</p>
  const stages = meta.pipeline_stages
  const won = rows.filter((r) => r.pipeline.stage === 'won')
  const lost = rows.filter((r) => r.pipeline.stage === 'lost')

  return (
    <>
      <h1>Pipeline</h1>
      <p className="sub">
        {rows.length} tracked · {won.length} won ({money(won.reduce((a, r) => a + (r.pipeline.bid_amount || 0), 0)) || '$0'}) · {lost.length} lost
        {won.length + lost.length > 0 && ` · win rate ${Math.round((100 * won.length) / (won.length + lost.length))}%`}
      </p>
      <div className="kanban">
        {stages.map((s) => (
          <div className="col" key={s}>
            <h3>{s.replace('_', ' ')} ({rows.filter((r) => r.pipeline.stage === s).length})</h3>
            {rows.filter((r) => r.pipeline.stage === s).map((r) => (
              <div className="card" key={r.id}>
                <Link to={`/opportunities/${r.id}`}>{r.title}</Link>
                <div className="small muted" style={{ margin: '4px 0' }}>{r.agency?.split(' / ').slice(-1)[0]}</div>
                <div className="row small" style={{ gap: 6 }}>
                  <EligBadge status={r.eligibility.status} />
                  <span>due <DaysLeft days={r.days_left} /></span>
                  {r.pipeline.priority === 'high' && <span className="tag">high</span>}
                  {r.score && <span className="tag" title={`Bid score: ${r.score.recommendation}`}>score {r.score.score}</span>}
                  {r.export_controlled && <span className="tag" title="Export-controlled drawings">JCP</span>}
                </div>
                {r.pipeline.notes && <div className="small" style={{ marginTop: 6 }}>{r.pipeline.notes}</div>}
                <select style={{ marginTop: 8, width: '100%' }} value={s} onChange={(e) => move(r, e.target.value)}>
                  {stages.map((x) => <option key={x} value={x}>Move to: {x.replace('_', ' ')}</option>)}
                </select>
              </div>
            ))}
          </div>
        ))}
      </div>
    </>
  )
}
