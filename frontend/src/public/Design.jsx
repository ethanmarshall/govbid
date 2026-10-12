import { useEffect, useRef, useState } from 'react'
import StepViewer from '../StepViewer.jsx'
import { call, statusPath } from './shared'

// Design a part on the site: describe it to the assistant (when it is on) or fill in the sizes, see it in 3D with a
// dimensioned drawing, then get a price or send it with a project idea. The server checks every size and builds the model.

const NONLEN = new Set(['count', 'angle', 'leaves', 'locking_casters'])
const convert = (v, f, key = '') => {
  if (Array.isArray(v)) return v.map((x) => convert(x, f))
  if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, convert(x, f, k)]))
  if (typeof v === 'number' && !NONLEN.has(key)) return Math.round(v * f * 10000) / 10000
  return v
}
const num = (v) => (v === '' || v == null ? '' : v)
const fmt = (n) => (n == null ? '' : String(Math.round(n * 1000) / 1000))

// Feature lists per part type: [params key, title, columns]
const FEATURES = {
  plate: [['holes', 'Holes', [['x', 'X'], ['y', 'Y'], ['diameter', 'Dia'], ['depth', 'Depth (0 = thru)']]],
    ['slots', 'Slots', [['x', 'X'], ['y', 'Y'], ['length', 'Length'], ['width', 'Width'], ['angle', 'Angle (0/90)']]],
    ['pockets', 'Pockets and cutouts', [['x', 'X'], ['y', 'Y'], ['length', 'Length'], ['width', 'Width'], ['depth', 'Depth (0 = thru)'], ['corner_radius', 'Corner R']]]],
  l_bracket: [['holes_a', 'Holes in the base', [['x', 'From corner'], ['y', 'Across'], ['diameter', 'Dia']]],
    ['holes_b', 'Holes in the upright', [['x', 'From corner'], ['y', 'Across'], ['diameter', 'Dia']]]],
  u_channel: [['holes_base', 'Holes in the base', [['x', 'Along'], ['y', 'Across'], ['diameter', 'Dia']]],
    ['holes_flange', 'Holes through both sides', [['x', 'Along'], ['y', 'Up'], ['diameter', 'Dia']]]],
  box: [['holes', 'Holes in the floor', [['x', 'X'], ['y', 'Y'], ['diameter', 'Dia']]]],
  round: [['sections', 'Diameters, left to right', [['diameter', 'Diameter'], ['length', 'Length']]]],
}
FEATURES.block = FEATURES.plate
const STARTERS = ['A 6 x 4 in aluminum mounting plate with a hole in each corner', 'An L bracket to hold a sensor on a panel', 'A 1/2 in long spacer for a #10 screw']

export default function DesignStudio({ info, onSendIdea }) {
  const tpls = info.design?.templates || []
  const ai = !!info.design?.ai
  const [spec, setSpec] = useState(() => ({ type: 'plate', units: 'in', name: '', material: '', notes: '', params: structuredClone(tpls.find((t) => t.type === 'plate')?.default_params || {}) }))
  const [view, setView] = useState(null)
  const [err, setErr] = useState('')
  const [building, setBuilding] = useState(false)
  const [tab, setTab] = useState('3d')
  const seq = useRef(0)
  const skip = useRef(false)

  // rebuild the model when sizes change (the assistant hands over a model already built)
  useEffect(() => {
    if (skip.current) { skip.current = false; return }
    const n = ++seq.current
    setBuilding(true)
    const t = setTimeout(async () => {
      try {
        const r = await call('POST', '/api/public/design/preview', { spec })
        if (n === seq.current) { setView(r); setErr('') }
      } catch (e) { if (n === seq.current) setErr(e.message) }
      if (n === seq.current) setBuilding(false)
    }, 450)
    return () => clearTimeout(t)
  }, [spec])

  const fromAssistant = (r) => { skip.current = true; seq.current++; setSpec(r.spec); setView(r.render); setErr(''); setBuilding(false) }
  const tpl = tpls.find((t) => t.type === spec.type)
  const k = spec.units === 'mm' ? 25.4 : 1
  const setType = (type) => {
    const t = tpls.find((x) => x.type === type)
    setSpec({ ...spec, type, params: convert(structuredClone(t.default_params), k) })
  }
  const setUnits = (u) => { if (u !== spec.units) setSpec({ ...spec, units: u, params: convert(spec.params, u === 'mm' ? 25.4 : 1 / 25.4) }) }
  const setP = (key, v) => setSpec({ ...spec, params: { ...spec.params, [key]: v } })
  const numIn = (key, label, obj = spec.params, onSet = (v) => setP(key, v)) => (
    <label key={key}>{label}
      <input type="number" step="any" min="0" inputMode="decimal" value={num(obj?.[key])} onChange={(e) => onSet(e.target.value === '' ? '' : Number(e.target.value))} />
    </label>
  )

  return (
    <div className="pq-design">
      <h1>Design a part</h1>
      <p className="pq-intro">{ai ? 'Describe what you need and the assistant draws it, or fill in the sizes yourself.' : 'Pick the kind of part and fill in its sizes.'} You see it in 3D with dimensions, and you can get a price right away.</p>
      <div className="pq-design-grid">
        {ai && <div className="pq-d-assist"><Assistant spec={spec} onModel={fromAssistant} /></div>}
        <section className="pq-design-form" aria-labelledby="sizes-h">
            <h2 id="sizes-h">{ai ? 'Or set the sizes' : 'Sizes'}</h2>
            <div className="pq-fields two">
              <label>Kind of part
                <select value={spec.type} onChange={(e) => setType(e.target.value)}>{tpls.map((t) => <option key={t.type} value={t.type}>{t.label}</option>)}</select>
              </label>
              <label>Units
                <select value={spec.units} onChange={(e) => setUnits(e.target.value)}><option value="in">Inches</option><option value="mm">Millimeters</option></select>
              </label>
              <label className="pq-span2">Name<input value={spec.name} maxLength={60} placeholder={tpl?.label} onChange={(e) => setSpec({ ...spec, name: e.target.value })} /></label>
            </div>
            {tpl?.fields?.length > 0 && <div className="pq-fields">{tpl.fields.map((f) => numIn(f.key, f.label))}</div>}
            {spec.type === 'frame' && <FrameForm p={spec.params} tpl={tpl} setP={setP} numIn={numIn} />}
            {spec.type === 'round' && (
              <div className="pq-fields">
                {numIn('diameter', 'Bore diameter (0 = none)', spec.params.bore || {}, (v) => setP('bore', { ...(spec.params.bore || { depth: 0 }), diameter: v }))}
                {numIn('depth', 'Bore depth (0 = through)', spec.params.bore || {}, (v) => setP('bore', { ...(spec.params.bore || { diameter: 0 }), depth: v }))}
              </div>
            )}
            {spec.type === 'flange' && (
              <div className="pq-fields">
                {numIn('count', 'Bolt holes', spec.params.bolt_circle || {}, (v) => setP('bolt_circle', { ...(spec.params.bolt_circle || {}), count: v }))}
                {numIn('diameter', 'Bolt circle diameter', spec.params.bolt_circle || {}, (v) => setP('bolt_circle', { ...(spec.params.bolt_circle || {}), diameter: v }))}
                {numIn('hole_diameter', 'Bolt hole diameter', spec.params.bolt_circle || {}, (v) => setP('bolt_circle', { ...(spec.params.bolt_circle || {}), hole_diameter: v }))}
                {numIn('diameter', 'Hub diameter (0 = none)', spec.params.hub || {}, (v) => setP('hub', { ...(spec.params.hub || { height: 0.25 * k }), diameter: v }))}
                {numIn('height', 'Hub height', spec.params.hub || {}, (v) => setP('hub', { ...(spec.params.hub || { diameter: 0 }), height: v }))}
              </div>
            )}
            {(FEATURES[spec.type] || []).map(([key, title, cols]) => (
              <Rows key={key} title={title} cols={cols} rows={spec.params[key] || []} onChange={(rows) => setP(key, rows)}
                blank={Object.fromEntries(cols.map(([c]) => [c, c === 'angle' || c === 'depth' ? 0 : '']))} />
            ))}
            <label className="pq-notes">Notes for the shop<input value={spec.notes} maxLength={500} placeholder="Threads, tolerances, finish, what it mounts to" onChange={(e) => setSpec({ ...spec, notes: e.target.value })} /></label>
        </section>

        <div className="pq-design-right">
          <div className="pq-design-view">
            <div className="pq-viewtabs" role="tablist">
              <button type="button" role="tab" aria-selected={tab === '3d'} className={tab === '3d' ? 'on' : ''} onClick={() => setTab('3d')}>3D model</button>
              <button type="button" role="tab" aria-selected={tab === 'drawing'} className={tab === 'drawing' ? 'on' : ''} onClick={() => setTab('drawing')}>Drawing</button>
              <span className="pq-muted pq-small" aria-live="polite">{building ? 'Updating…' : view ? `${fmt(view.size[0])} x ${fmt(view.size[1])} x ${fmt(view.size[2])} ${view.units}` : ''}</span>
            </div>
            {view && tab === '3d' && <StepViewer mesh={view.mesh} height={360} />}
            {view && tab === 'drawing' && <img className="pq-design-drawing" alt="Front, top, right and isometric views with dimensions" src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(view.drawing)}`} />}
            {!view && <div className="pq-design-empty pq-muted">{err ? 'Fix the sizes to see the part.' : 'Building the model…'}</div>}
          </div>
          {err && <p className="pq-err" role="alert">{err}</p>}
          {view && (
            <dl className="pq-design-sum">
              {view.summary.map((r, i) => <div key={i}><dt>{r.label}</dt><dd>{r.text}</dd></div>)}
            </dl>
          )}
          <PriceIt info={info} spec={spec} ready={!!view && !err && !building} onSendIdea={() => onSendIdea({ spec, view })} />
        </div>
      </div>
    </div>
  )
}

function Rows({ title, cols, rows, onChange, blank }) {
  const set = (i, c, v) => onChange(rows.map((r, j) => (j === i ? { ...r, [c]: v === '' ? '' : Number(v) } : r)))
  return (
    <div className="pq-rows">
      <div className="pq-rows-head"><h3>{title}</h3><button type="button" className="pq-link" onClick={() => onChange([...rows, { ...blank }])}>Add</button></div>
      {rows.length > 0 && (
        <table>
          <thead><tr>{cols.map(([c, l]) => <th key={c}>{l}</th>)}<th aria-label="Remove" /></tr></thead>
          <tbody>{rows.map((r, i) => (
            <tr key={i}>
              {cols.map(([c, l]) => <td key={c}><input type="number" step="any" inputMode="decimal" aria-label={`${l} ${i + 1}`} value={num(r[c])} onChange={(e) => set(i, c, e.target.value)} /></td>)}
              <td><button type="button" className="pq-link" aria-label={`Remove ${title} ${i + 1}`} onClick={() => onChange(rows.filter((_, j) => j !== i))}>Remove</button></td>
            </tr>
          ))}</tbody>
        </table>
      )}
    </div>
  )
}

function Assistant({ spec, onModel }) {
  const [msgs, setMsgs] = useState([{ role: 'assistant', content: 'Hi. What are you looking to make? Tell me what it is for and any sizes you know. Rough is fine.' }])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const end = useRef()
  useEffect(() => { end.current?.scrollIntoView({ block: 'nearest' }) }, [msgs.length, busy])
  const send = async (t = text) => {
    const msg = t.trim()
    if (!msg || busy) return
    const next = [...msgs, { role: 'user', content: msg }]
    setMsgs(next); setText(''); setBusy(true); setErr('')
    try {
      const r = await call('POST', '/api/public/design/assistant', { messages: next.slice(1), spec })
      setMsgs([...next, { role: 'assistant', content: r.reply }])
      if (r.spec && r.render) onModel({ spec: r.spec, render: r.render })
    } catch (e) { setErr(e.message); setMsgs(next) }
    setBusy(false)
  }
  return (
    <section className="pq-assist" aria-labelledby="assist-h">
      <h2 id="assist-h">Describe it</h2>
      <div className="pq-chat" role="log" aria-live="polite">
        {msgs.map((m, i) => <p key={i} className={`pq-msg-${m.role}`}>{m.content}</p>)}
        {busy && <p className="pq-msg-assistant pq-muted">Drawing it…</p>}
        <span ref={end} />
      </div>
      {msgs.length === 1 && <div className="pq-starters">{STARTERS.map((s) => <button key={s} type="button" className="pq-chip" onClick={() => send(s)}>{s}</button>)}</div>}
      <form className="pq-chatform" onSubmit={(e) => { e.preventDefault(); send() }}>
        <textarea rows={2} maxLength={2000} value={text} placeholder="A bracket to hold a 2 in pump on a panel, with four 1/4 in holes" aria-label="Message"
          onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }} />
        <button className="pq-btn" disabled={busy || !text.trim()}>Send</button>
      </form>
      {err && <p className="pq-err" role="alert">{err}</p>}
      <p className="pq-muted pq-small">The assistant uses Anthropic's Claude AI: what you type here is sent to Anthropic to build the model. Do not include export-controlled (ITAR or EAR) or confidential details. Check every size before you order.</p>
    </section>
  )
}

function PriceIt({ info, spec, ready, onSendIdea }) {
  const [qty, setQty] = useState('1')
  const [material, setMaterial] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const sheet = spec.type === 'plate' || spec.type === 'l_bracket' || spec.type === 'u_channel'
  const frame = spec.type === 'frame'
  const price = async () => {
    setBusy(true); setErr('')
    try {
      const r = await call('POST', '/api/public/design/quote', { spec, quantity: Math.max(1, parseInt(qty, 10) || 1), material, preview: !info.enabled && !!info.owner })
      window.location.assign(statusPath(r.ref, r.token))
      return
    } catch (e) { setErr(e.message) }
    setBusy(false)
  }
  return (
    <div className="pq-design-price">
      <div className="pq-fields two">
        <label>Quantity<input type="number" min="1" max={info.max_quantity} step="1" inputMode="numeric" value={qty} onChange={(e) => setQty(e.target.value)} /></label>
        {frame ? <p className="pq-muted pq-small" style={{ alignSelf: 'end', margin: 0 }}>Aluminum T-slot extrusion, hardware and panels as listed.</p> : (
        <label>Material
          <select value={material} onChange={(e) => setMaterial(e.target.value)}>
            <option value="">{sheet ? 'Aluminum (we suggest)' : 'Not sure'}</option>
            <optgroup label="Metals and plastics">{(info.materials || []).map((m) => <option key={m}>{m}</option>)}</optgroup>
            <optgroup label="3D printing">{(info.print_materials || []).map((m) => <option key={m}>{m}</option>)}</optgroup>
          </select>
        </label>)}
      </div>
      {err && <p className="pq-err" role="alert">{err}</p>}
      <div className="pq-actions">
        <button type="button" className="pq-btn" disabled={!ready || busy || !(info.enabled || info.owner)} onClick={price}>{busy ? 'Pricing…' : frame ? 'Get an estimate' : 'Get a price'}</button>
        <button type="button" className="pq-link" disabled={!ready} onClick={onSendIdea}>Send it with a project idea instead</button>
      </div>
      {frame && <p className="pq-muted pq-small">Frames get an estimate from our parts list; an engineer checks the panel sizes and door hardware, then confirms the price.</p>}
      <p className="pq-muted pq-small">Getting a price saves the design as a quote you can order or send for review. Not sure it is right? Send it as a project idea and an engineer will check it with you.</p>
    </div>
  )
}

const FACES = ['front', 'back', 'left', 'right']

// A T-slot frame: profiles, base, doors, shelf levels and panels. Every member and cut length is worked out on the server.
function FrameForm({ p, tpl, setP, numIn }) {
  const profiles = tpl?.profiles || []
  const panels = tpl?.panels || []
  const sel = (key, label, options, value = p[key] ?? '') => (
    <label key={key}>{label}
      <select value={value} onChange={(e) => setP(key, e.target.value)}>{options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
    </label>
  )
  const profOpts = profiles.map((x) => [x.id, x.label])
  const panelOpts = [['', 'None'], ...panels.map((x) => [x.id, x.label])]
  const doors = p.doors || []
  const levels = p.levels || []
  const pan = p.panels || {}
  const setDoor = (i, k, v) => setP('doors', doors.map((d, j) => (j === i ? { ...d, [k]: v } : d)))
  const setLevel = (i, k, v) => setP('levels', levels.map((d, j) => (j === i ? { ...d, [k]: v } : d)))
  return (
    <>
      <div className="pq-fields">
        {sel('post_profile', 'Corner posts', profOpts)}
        {sel('rail_profile', 'Rails', profOpts)}
        {sel('door_profile', 'Door frames', [['', 'Same as rails'], ...profOpts])}
        {sel('post_wide_along', 'Wide face of the posts', [['depth', 'Along the depth (sides)'], ['width', 'Along the width (front)']])}
        {sel('joints', 'Joints', [['anchor', 'Butt joints, anchor fasteners'], ['bracket', 'Butt joints, corner brackets']])}
        {sel('base', 'Base', [['casters', 'Casters'], ['feet', 'Leveling feet'], ['none', 'None']])}
        {p.base === 'casters' && numIn('caster_height', 'Caster height')}
        {p.base === 'casters' && sel('locking_casters', 'Casters with brakes', [0, 1, 2, 3, 4].map((n) => [n, String(n)]), p.locking_casters ?? 2)}
      </div>
      <div className="pq-rows">
        <div className="pq-rows-head"><h3>Doors (inset)</h3>{doors.length < 4 && <button type="button" className="pq-link" onClick={() => setP('doors', [...doors, { face: FACES.find((f) => !doors.some((d) => d.face === f)), leaves: 1, panel: 'PANEL-PC-250' }])}>Add</button>}</div>
        {doors.length > 0 && <table><thead><tr><th>Side</th><th>Doors</th><th>Panel</th><th /></tr></thead><tbody>{doors.map((d, i) => (
          <tr key={i}>
            <td><select aria-label={`Door ${i + 1} side`} value={d.face} onChange={(e) => setDoor(i, 'face', e.target.value)}>{FACES.map((f) => <option key={f}>{f}</option>)}</select></td>
            <td><select aria-label={`Door ${i + 1} count`} value={d.leaves || 1} onChange={(e) => setDoor(i, 'leaves', Number(e.target.value))}><option value={1}>Single</option><option value={2}>Double</option></select></td>
            <td><select aria-label={`Door ${i + 1} panel`} value={d.panel ?? ''} onChange={(e) => setDoor(i, 'panel', e.target.value)}>{panelOpts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></td>
            <td><button type="button" className="pq-link" onClick={() => setP('doors', doors.filter((_, j) => j !== i))}>Remove</button></td>
          </tr>))}</tbody></table>}
      </div>
      <div className="pq-rows">
        <div className="pq-rows-head"><h3>Shelf levels</h3><button type="button" className="pq-link" onClick={() => setP('levels', [...levels, { z: Math.round((Number(p.height) || 30) / 2), shelf: '' }])}>Add</button></div>
        {levels.length > 0 && <table><thead><tr><th>Height of shelf top</th><th>Shelf panel</th><th /></tr></thead><tbody>{levels.map((lv, i) => (
          <tr key={i}>
            <td><input type="number" step="any" aria-label={`Level ${i + 1} height`} value={lv.z ?? ''} onChange={(e) => setLevel(i, 'z', e.target.value === '' ? '' : Number(e.target.value))} /></td>
            <td><select aria-label={`Level ${i + 1} shelf`} value={lv.shelf ?? ''} onChange={(e) => setLevel(i, 'shelf', e.target.value)}>{panelOpts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></td>
            <td><button type="button" className="pq-link" onClick={() => setP('levels', levels.filter((_, j) => j !== i))}>Remove</button></td>
          </tr>))}</tbody></table>}
      </div>
      <div className="pq-fields">
        {FACES.filter((f) => !doors.some((d) => d.face === f)).map((f) => (
          <label key={f}>{f[0].toUpperCase() + f.slice(1)} side panel
            <select value={pan[f] || ''} onChange={(e) => setP('panels', { ...pan, [f]: e.target.value })}>{panelOpts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
          </label>
        ))}
        {sel('top_panel', 'Top panel', panelOpts)}
        {sel('bottom_panel', 'Bottom panel', panelOpts)}
      </div>
    </>
  )
}
