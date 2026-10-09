import { useEffect, useState } from 'react'
import { api } from '../api'

const usd = (n) => (n == null ? '' : `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`)
const pct = (n) => (n == null ? 'n/a' : `${n}%`)
const DIMS = [['kind', 'Quote type'], ['process', 'Process'], ['material', 'Material'], ['fsc', 'FSC (from NSN)']]

function WinBar({ won, lost }) {
  const total = won + lost
  if (!total) return <span className="muted small">no decisions</span>
  return (
    <div className="wl-bar" title={`${won} won, ${lost} lost`}>
      <span className="wl-won" style={{ width: `${(won / total) * 100}%` }} />
    </div>
  )
}

function Bands({ bands }) {
  const max = Math.max(1, ...bands.map((b) => b.won + b.lost))
  return (
    <div className="wl-bands">
      {bands.map((b) => (
        <div key={b.label} className="wl-band" title={`${b.label} margin: ${b.won} won, ${b.lost} lost`}>
          <div className="wl-stack" style={{ height: `${((b.won + b.lost) / max) * 100}%` }}>
            <span className="wl-lost" style={{ flex: b.lost }} />
            <span className="wl-won" style={{ flex: b.won }} />
          </div>
          <span className="wl-band-label">{b.label.replace(' to ', '-')}</span>
        </div>
      ))}
    </div>
  )
}

function Ratio({ v, n }) {
  if (v == null) return <span className="muted">n/a</span>
  const over = Math.round((v - 1) * 100)
  return <span title={`${n} lost quote(s) with a known award price`}>{v.toFixed(2)} <span className="muted small">({over >= 0 ? `${over}% above` : `${-over}% below`} award, n={n})</span></span>
}

export default function QuoteInsights() {
  const [d, setD] = useState(null)
  const [dim, setDim] = useState('kind')
  const [err, setErr] = useState('')
  const [showPoints, setShowPoints] = useState(false)
  useEffect(() => { api.get('/api/quote-tools/insights').then(setD).catch((e) => setErr(e.message)) }, [])
  if (err) return <p className="err">{err}</p>
  if (!d) return <p className="muted">Loading…</p>
  const o = d.overall
  const groups = d.groups[dim] || []

  return (
    <>
      <div className="grid g4">
        <div className="stat"><div className="n">{o.quotes}</div><div className="l">Quotes submitted, won or lost</div></div>
        <div className="stat"><div className="n">{pct(o.win_rate)}</div><div className="l">Win rate ({o.won} won, {o.lost} lost, {o.submitted} pending)</div></div>
        <div className="stat"><div className="n">{o.avg_price_ratio == null ? 'n/a' : o.avg_price_ratio.toFixed(2)}</div><div className="l">Our price / award price when lost (n={o.ratio_count})</div></div>
        <div className="stat"><div className="n">{pct(o.avg_margin_won)} / {pct(o.avg_margin_lost)}</div><div className="l">Average margin at win / at loss</div></div>
      </div>

      <div className="panel" style={{ marginTop: 16 }}>
        <div className="row spread">
          <h2 style={{ margin: 0 }}>Suggested target margin</h2>
          <span className={o.suggestion.enough ? 'small' : 'small due-soon'}>{o.suggestion.text}</span>
        </div>
        <div className="tabs" style={{ marginTop: 12 }}>
          {DIMS.map(([k, label]) => <button key={k} className={dim === k ? 'on' : ''} onClick={() => setDim(k)}>{label}</button>)}
        </div>
        {groups.length === 0 ? (
          <p className="muted">No quotes are marked submitted, won or lost yet. Set the status on saved quotes as results come in.</p>
        ) : (
          <table className="small wl-table">
            <thead>
              <tr><th>{DIMS.find((x) => x[0] === dim)[1]}</th><th>Quotes</th><th>Win rate</th><th>Our price / award</th><th>Margin at win</th><th>Margin at loss</th><th>Wins by margin band</th><th>Suggested target</th></tr>
            </thead>
            <tbody>
              {groups.map((g) => (
                <tr key={g.value}>
                  <td className="t">{g.value.replace(/_/g, ' ')}</td>
                  <td>{g.quotes}<div className="muted">{g.won}W {g.lost}L {g.submitted}P</div></td>
                  <td style={{ minWidth: 110 }}>{pct(g.win_rate)}<WinBar won={g.won} lost={g.lost} /></td>
                  <td><Ratio v={g.avg_price_ratio} n={g.ratio_count} /></td>
                  <td>{pct(g.avg_margin_won)}</td>
                  <td>{pct(g.avg_margin_lost)}</td>
                  <td><Bands bands={g.bands} /></td>
                  <td style={{ maxWidth: 260 }} className={g.suggestion.enough ? '' : 'muted'}>{g.suggestion.text}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="row small muted" style={{ marginTop: 8 }}>
          <span className="wl-key wl-won" /> won <span className="wl-key wl-lost" /> lost
        </div>
      </div>

      <div className="panel">
        <h2>How this is worked out</h2>
        <ul className="clean small">
          <li>Only saved quotes with status submitted, won or lost count. Win rate uses won and lost only; submitted quotes are still pending.</li>
          <li>Our price is the quoted unit price at the quoting quantity. Margin is (price minus our estimated unit cost) divided by price, so it includes G&A as well as profit.</li>
          <li>Price against award: for a lost quote with an NSN, the award price is the first award in the NSN price history on or after the quote date (or the latest award if none is newer). A ratio of 1.10 means we were 10% above the winning price. Add award records under NSN history to fill this in.</li>
          <li>FSC is the first four digits of the NSN.</li>
          <li>Suggested target: the highest margin band (0-10%, 10-20%, and so on) that still has at least one win in the group. With fewer than {d.min_points} won or lost quotes the group says there is not enough data. Treat it as a starting point: small samples move a lot with one result.</li>
        </ul>
      </div>

      <div className="panel">
        <div className="row spread">
          <h2 style={{ margin: 0 }}>Quotes counted ({d.points.length})</h2>
          <button className="link small" onClick={() => setShowPoints(!showPoints)}>{showPoints ? 'Hide' : 'Show'}</button>
        </div>
        {showPoints && (
          <table className="small" style={{ marginTop: 10 }}>
            <thead><tr><th>Quote</th><th>Status</th><th>NSN</th><th>Qty</th><th>Our unit price</th><th>Margin</th><th>Award price</th><th>Ratio</th></tr></thead>
            <tbody>
              {d.points.map((p) => (
                <tr key={p.id}>
                  <td>#{p.id} {p.name}<div className="muted">{p.solicitation_number}</div></td>
                  <td><span className="tag">{p.status}</span></td>
                  <td className="mono">{p.nsn}</td>
                  <td>{p.quantity}</td>
                  <td>{usd(p.unit_price)}</td>
                  <td>{pct(p.margin_pct)}</td>
                  <td>{p.award_price != null ? <>{usd(p.award_price)} <span className="muted">{p.award_date}</span></> : <span className="muted">{p.status === 'lost' ? 'not in history' : ''}</span>}</td>
                  <td>{p.price_ratio != null ? p.price_ratio.toFixed(2) : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  )
}
