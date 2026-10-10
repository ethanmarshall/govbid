import { useEffect, useState } from 'react'
import { api } from '../api'

const usd = (n, d = 2) => (n == null ? '' : `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: 4 })}`)
const blank = { part_number: '', vendor: 'McMaster-Carr', description: '', match: '', pack_price: '', pack_qty: 1 }

// Bought parts (bearings, fasteners, catalog items): what customer models are matched against, and their prices.
export default function Hardware() {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [f, setF] = useState(blank)
  const [mc, setMc] = useState({ part_number: '', match: '' })
  const [test, setTest] = useState({ name: '', qty: 1 })
  const [testOut, setTestOut] = useState(null)
  const load = () => api.get('/api/hardware').then(setD).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [])

  const save = async () => {
    setErr(''); setMsg('')
    try {
      await api.post('/api/hardware', { ...f, pack_price: f.pack_price === '' ? null : Number(f.pack_price), pack_qty: Number(f.pack_qty) || 1 })
      setF(blank); setMsg('Saved.'); load()
    } catch (e) { setErr(e.message) }
  }
  const addMc = async () => {
    setErr(''); setMsg('')
    try { await api.post('/api/hardware/mcmaster', mc); setMc({ part_number: '', match: '' }); setMsg('Added and priced from McMaster-Carr.') } catch (e) { setErr(e.message) }
    load()
  }
  const refresh = async (id) => { setErr(''); try { await api.post(`/api/hardware/${id}/refresh`); load() } catch (e) { setErr(e.message) } }
  const del = async (id) => { if (!confirm('Remove this part from the library?')) return; await api.del(`/api/hardware/${id}`); load() }
  const runTest = async () => { setErr(''); try { setTestOut(await api.post('/api/hardware/test', { name: test.name, qty: Number(test.qty) || 1 })) } catch (e) { setErr(e.message) } }

  if (!d) return <p className="muted">{err || 'Loading…'}</p>
  const st = d.mcmaster
  return (
    <>
      <h1>Hardware</h1>
      <p className="sub">Bought parts in customer models (bearings, screws, anything named "reference") are priced from this list. A part matches by a McMaster-Carr part number in its name, by its part number here, or by your match words.</p>

      <div className="panel">
        <h2 style={{ marginTop: 0 }}>McMaster-Carr</h2>
        {st.configured ? <p className="small okline">Connected. Parts with a McMaster part number are priced from their API and refreshed every 30 days.</p> : (
          <div className="small">
            <p style={{ marginTop: 0 }}>Not connected. McMaster's Product Information API is free for approved customers:</p>
            <ol style={{ marginTop: 0 }}>
              <li>Email <a href="mailto:eCommerce@mcmaster.com">eCommerce@mcmaster.com</a> and ask for API access for your account. They send a client certificate (.pfx) and its password.</li>
              <li>In Render, add the certificate as a secret file named <span className="mono">mcmaster.pfx</span>, and set <span className="mono">MCMASTER_USERNAME</span>, <span className="mono">MCMASTER_PASSWORD</span> (your mcmaster.com login) and <span className="mono">MCMASTER_CERT_PASSWORD</span>.</li>
            </ol>
            <p className="muted">Until then, enter prices by hand below (copy them from mcmaster.com). Missing: {st.missing.join(', ')}.</p>
          </div>
        )}
        <div className="row" style={{ alignItems: 'flex-end' }}>
          <label className="f">McMaster part number<input value={mc.part_number} onChange={(e) => setMc({ ...mc, part_number: e.target.value })} placeholder="91290A115" /></label>
          <label className="f" style={{ flex: 1 }}>Match words (optional)<input value={mc.match} onChange={(e) => setMc({ ...mc, match: e.target.value })} placeholder="m5 x 10 socket head" /></label>
          <button disabled={!st.configured || !mc.part_number} onClick={addMc}>Add from McMaster</button>
        </div>
      </div>

      <div className="panel">
        <h2 style={{ marginTop: 0 }}>Add a part by hand</h2>
        <div className="grid g3">
          <label className="f">Part number<input value={f.part_number} onChange={(e) => setF({ ...f, part_number: e.target.value })} placeholder="5972K91" /></label>
          <label className="f">Vendor<input value={f.vendor} onChange={(e) => setF({ ...f, vendor: e.target.value })} /></label>
          <label className="f">Description<input value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} placeholder="608 ball bearing, sealed" /></label>
          <label className="f">Match words, comma between phrases<input value={f.match} onChange={(e) => setF({ ...f, match: e.target.value })} placeholder="608 bearing, 608zz" /></label>
          <label className="f">Price as listed<input type="number" min="0" step="0.01" value={f.pack_price} onChange={(e) => setF({ ...f, pack_price: e.target.value })} /></label>
          <label className="f">Pieces in that price (pack size)<input type="number" min="1" value={f.pack_qty} onChange={(e) => setF({ ...f, pack_qty: e.target.value })} /></label>
        </div>
        <div className="row" style={{ marginTop: 8 }}><button className="primary" onClick={save}>Save part</button>{msg && <span className="small okline">{msg}</span>}</div>
        {err && <div className="err">{err}</div>}
      </div>

      <div className="panel">
        <h2 style={{ marginTop: 0 }}>Library ({d.items.length})</h2>
        {!d.items.length ? <p className="small muted">No parts yet.</p> : (
          <div style={{ overflowX: 'auto' }}>
            <table className="small">
              <thead><tr><th>Part</th><th>Matches</th><th>Price</th><th>Each</th><th>Source</th><th></th></tr></thead>
              <tbody>{d.items.map((it) => (
                <tr key={it.id}>
                  <td><b className="mono">{it.url ? <a href={it.url} target="_blank" rel="noreferrer">{it.part_number || '—'}</a> : it.part_number || '—'}</b> <span className="muted">{it.vendor}</span><div>{it.description}</div>{it.error && <div className="err small">{it.error}</div>}</td>
                  <td>{it.match || <span className="muted">part number only</span>}</td>
                  <td className="mono">{usd(it.pack_price)}{it.pack_qty > 1 ? ` / ${it.pack_qty}` : ''}{it.price_breaks?.length > 1 && <div className="muted">{it.price_breaks.map((b) => `${b.min_qty}+: ${usd(b.amount)}`).join(', ')}</div>}</td>
                  <td className="mono">{usd(it.unit_price, 2)}</td>
                  <td>{it.source}{it.priced_at && <div className={it.stale ? 'due-soon' : 'muted'}>{it.priced_at.slice(0, 10)}{it.stale ? ', old' : ''}</div>}</td>
                  <td className="row" style={{ gap: 6 }}>
                    <button className="small-btn" onClick={() => setF({ ...blank, ...it, pack_price: it.pack_price ?? '' })}>Edit</button>
                    {st.configured && it.source === 'mcmaster' && <button className="small-btn" onClick={() => refresh(it.id)}>Price again</button>}
                    <button className="link" onClick={() => del(it.id)}>Remove</button>
                  </td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </div>

      <div className="panel">
        <h2 style={{ marginTop: 0 }}>Try a part name</h2>
        <p className="small muted" style={{ marginTop: 0 }}>Type a name as it appears in a model (for example 08_bearing_608_reference) to see what it matches and costs.</p>
        <div className="row" style={{ alignItems: 'flex-end' }}>
          <label className="f" style={{ flex: 1 }}>Part name<input value={test.name} onChange={(e) => setTest({ ...test, name: e.target.value })} /></label>
          <label className="f">Quantity<input type="number" min="1" value={test.qty} onChange={(e) => setTest({ ...test, qty: e.target.value })} style={{ width: 90 }} /></label>
          <button onClick={runTest} disabled={!test.name}>Check</button>
        </div>
        {testOut && <p className="small">{testOut.found
          ? <>Matches <b>{testOut.item?.vendor} {testOut.part_number}</b> {testOut.item?.description}. {testOut.total != null ? <>{usd(testOut.each)} each, {usd(testOut.total)} for {test.qty}{testOut.packs ? ` (${testOut.packs} pack${testOut.packs > 1 ? 's' : ''})` : ''}.</> : 'No price yet.'}</>
          : testOut.part_number ? <>Has McMaster part number <b>{testOut.part_number}</b>, not in the library yet.</> : 'No match.'}</p>}
      </div>
    </>
  )
}
