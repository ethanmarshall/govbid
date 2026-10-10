import { useEffect, useState } from 'react'
import { call, claimSaved, money, range, refreshAccount, setAccount, statusPath, useAccount } from './shared'
import { invoiceLink } from './Checkout'

// /quote/account: sign in, create an account, reset a password, and (signed in) quotes, orders, profile and addresses.
export default function Account({ info }) {
  const acct = useAccount()
  const qs = new URLSearchParams(window.location.search)
  const next = qs.get('next')
  const reset = qs.get('reset')
  useEffect(() => { document.title = `Your account: ${info.name}` }, [info.name])
  if (acct === undefined) return <p className="pq-muted pq-pad">Loading…</p>
  if (reset) return <Reset token={reset} email={qs.get('e') || ''} />
  if (!acct.customer) return <SignIn next={next} canReset={acct.reset_by_email} info={info} />
  return <Dashboard me={acct.customer} />
}

const safeNext = (n) => (n && n.startsWith('/quote') && !n.startsWith('//') ? n : null)

async function afterSignIn(r, next) {
  setAccount({ customer: r.customer, reset_by_email: true })
  await claimSaved()
  refreshAccount()
  const to = safeNext(next)
  window.location.assign(to || '/quote/account')
}

function SignIn({ next, canReset, info }) {
  const [mode, setMode] = useState('in')
  const [f, setF] = useState({ email: '', password: '', name: '', company: '', phone: '' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [note, setNote] = useState('')
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const go = async (e) => {
    e.preventDefault(); setBusy(true); setErr(''); setNote('')
    try {
      if (mode === 'forgot') {
        const r = await call('POST', '/api/public/account/forgot', { email: f.email })
        setNote(r.message)
      } else {
        const r = await call('POST', `/api/public/account/${mode === 'in' ? 'login' : 'register'}`, f)
        await afterSignIn(r, next)
        return
      }
    } catch (x) { setErr(x.message) }
    setBusy(false)
  }
  const tab = (k, label) => <button type="button" role="tab" aria-selected={mode === k} className={`pq-path ${mode === k ? 'on' : ''}`} onClick={() => { setMode(k); setErr(''); setNote('') }}><b>{label}</b></button>
  return (
    <div className="pq-acctbox">
      <h1>{mode === 'up' ? 'Create your account' : mode === 'forgot' ? 'Reset your password' : 'Sign in'}</h1>
      <p className="pq-intro">{mode === 'up'
        ? 'Keep your quotes, orders and shipping addresses in one place, and check out faster.'
        : mode === 'forgot' ? 'Enter your email and we will send a link to choose a new password.'
          : `Your quotes and orders with ${info.name}.`}</p>
      {mode !== 'forgot' && <div className="pq-paths pq-tabs" role="tablist">{tab('in', 'Sign in')}{tab('up', 'Create an account')}</div>}
      <form onSubmit={go} className="pq-acctform">
        {mode === 'up' && (
          <div className="pq-fields two">
            <label>Name<input required autoComplete="name" value={f.name} onChange={set('name')} /></label>
            <label>Company<input autoComplete="organization" value={f.company} onChange={set('company')} /></label>
          </div>
        )}
        <div className="pq-fields two">
          <label>Email<input required type="email" autoComplete="email" value={f.email} onChange={set('email')} /></label>
          {mode !== 'forgot' && (
            <label>Password<input required type="password" minLength={mode === 'up' ? 10 : undefined} autoComplete={mode === 'up' ? 'new-password' : 'current-password'} value={f.password} onChange={set('password')} /></label>
          )}
        </div>
        {mode === 'up' && <p className="pq-muted pq-small">At least 10 characters. Quotes you made in this browser are added to your account.</p>}
        {err && <p className="pq-err" role="alert">{err}</p>}
        {note && <p className="pq-okline" role="status">{note}</p>}
        <div className="pq-actions">
          <button className="pq-btn" disabled={busy}>{busy ? 'One moment…' : mode === 'up' ? 'Create account' : mode === 'forgot' ? 'Send the link' : 'Sign in'}</button>
          {mode === 'in' && (canReset
            ? <button type="button" className="pq-link" onClick={() => setMode('forgot')}>Forgot your password?</button>
            : info.contact_email && <span className="pq-muted pq-small">Forgot your password? Email <a href={`mailto:${info.contact_email}`}>{info.contact_email}</a>.</span>)}
          {mode === 'forgot' && <button type="button" className="pq-link" onClick={() => setMode('in')}>Back to sign in</button>}
        </div>
      </form>
      <p className="pq-muted pq-small" style={{ marginTop: 28 }}>You do not need an account to get a price. <a href="/quote">Get a quote</a></p>
    </div>
  )
}

function Reset({ token, email }) {
  const [pw, setPw] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const go = async (e) => {
    e.preventDefault(); setBusy(true); setErr('')
    try { await afterSignIn(await call('POST', '/api/public/account/reset', { email, token, password: pw }), null); return } catch (x) { setErr(x.message) }
    setBusy(false)
  }
  return (
    <form className="pq-acctbox" onSubmit={go}>
      <h1>Choose a new password</h1>
      <p className="pq-intro">For {email}. The link works once, within 2 hours of the email.</p>
      <div className="pq-fields two"><label>New password<input required type="password" minLength={10} autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} /></label></div>
      {err && <p className="pq-err" role="alert">{err} <a href="/quote/account">Ask for a new link</a></p>}
      <div className="pq-actions"><button className="pq-btn" disabled={busy}>{busy ? 'Saving…' : 'Save and sign in'}</button></div>
    </form>
  )
}

const priceOf = (q) => (q.order?.number ? money(q.order.amount) : q.total != null ? money(q.total) : q.total_low != null ? range(q.total_low, q.total_high) : q.kind === 'concept' ? '' : 'By review')

function Dashboard({ me }) {
  const [list, setList] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { call('GET', '/api/public/account/requests').then(setList).catch((e) => setErr(e.message)) }, [])
  const signOut = async () => { await call('POST', '/api/public/account/logout'); setAccount({ customer: null }); window.location.assign('/quote') }
  const orders = (list || []).filter((q) => q.order?.number && q.order.status !== 'awaiting_payment')
  const rest = (list || []).filter((q) => !orders.includes(q))
  const row = (q) => (
    <li key={q.ref}>
      <a className="pq-saved-ref" href={statusPath(q.ref, q.token)}>{q.ref}</a>
      <span className="pq-saved-what">{q.title || q.files.join(', ') || 'No files'}<span className="pq-muted"> {q.created}{q.lines > 1 ? `, ${q.lines} parts` : ''}</span></span>
      <span className="pq-saved-price">{priceOf(q)}</span>
      <span className="pq-saved-act pq-muted">{q.order?.number ? q.order.status_label : q.status_label}{q.order?.invoice_number && <> <a href={invoiceLink(q.ref, q.token)} target="_blank" rel="noopener">{q.order.method === 'card' && q.order.status === 'paid' ? 'Receipt' : `Invoice ${q.order.invoice_number}`}</a></>}</span>
    </li>
  )
  return (
    <>
      <div className="pq-accthead">
        <div>
          <h1>Hello, {me.name.split(' ')[0] || 'there'}</h1>
          <p className="pq-muted">{me.email}{me.company ? `, ${me.company}` : ''}</p>
        </div>
        <div className="pq-actions" style={{ marginTop: 0 }}>
          <a className="pq-btn" href="/quote">Get a new quote</a>
          <button type="button" className="pq-btn ghost" onClick={signOut}>Sign out</button>
          <button type="button" className="pq-link pq-small" onClick={async () => { if (!confirm('Sign out on every phone and computer signed in to this account?')) return; await call('POST', '/api/public/account/logout?everywhere=1'); setAccount({ customer: null }); window.location.assign('/quote/account') }}>Sign out of all devices</button>
        </div>
      </div>
      {err && <p className="pq-err">{err}</p>}
      {list && (
        <>
          <section className="pq-sec" aria-labelledby="orders-h">
            <h2 id="orders-h">Orders</h2>
            {orders.length ? <ul className="pq-saved">{orders.map(row)}</ul> : <p className="pq-muted">No orders yet. Quotes with a firm price can be ordered straight from the quote.</p>}
          </section>
          <section className="pq-sec" aria-labelledby="quotes-h">
            <h2 id="quotes-h">Quotes and project ideas</h2>
            {rest.length ? <ul className="pq-saved">{rest.map(row)}</ul> : <p className="pq-muted">Nothing here yet. <a href="/quote">Upload your files for a price.</a></p>}
          </section>
        </>
      )}
      {!list && !err && <p className="pq-muted pq-pad">Loading your quotes…</p>}
      <Terms me={me} />
      <Profile me={me} />
      <Addresses me={me} />
      <Password />
    </>
  )
}

function useSave() {
  const [state, setState] = useState({ busy: false, err: '', ok: '' })
  const save = async (body, ok = 'Saved.') => {
    setState({ busy: true, err: '', ok: '' })
    try { const r = await call('PUT', '/api/public/account', body); setAccount({ customer: r.customer, reset_by_email: true }); refreshAccount(); setState({ busy: false, err: '', ok }); return true } catch (x) { setState({ busy: false, err: x.message, ok: '' }); return false }
  }
  return [state, save]
}

function Profile({ me }) {
  const [f, setF] = useState({ name: me.name, company: me.company, phone: me.phone })
  const [st, save] = useSave()
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  return (
    <section className="pq-sec" aria-labelledby="prof-h">
      <h2 id="prof-h">Your details</h2>
      <form onSubmit={(e) => { e.preventDefault(); save(f) }}>
        <div className="pq-fields">
          <label>Name<input required autoComplete="name" value={f.name} onChange={set('name')} /></label>
          <label>Company<input autoComplete="organization" value={f.company} onChange={set('company')} /></label>
          <label>Phone<input type="tel" autoComplete="tel" value={f.phone} onChange={set('phone')} /></label>
        </div>
        <div className="pq-actions"><button className="pq-btn ghost" disabled={st.busy}>Save details</button>{st.ok && <span className="pq-okline">{st.ok}</span>}</div>
        {st.err && <p className="pq-err">{st.err}</p>}
      </form>
    </section>
  )
}

const EMPTY = { label: '', name: '', company: '', line1: '', line2: '', city: '', state: '', zip: '', phone: '' }

function Addresses({ me }) {
  const list = me.addresses || []
  const [edit, setEdit] = useState(null) // index, or 'new'
  const [a, setA] = useState(EMPTY)
  const [st, save] = useSave()
  const set = (k) => (e) => setA({ ...a, [k]: e.target.value })
  const begin = (i) => { setEdit(i); setA(i === 'new' ? { ...EMPTY, name: me.name, company: me.company } : { ...EMPTY, ...list[i] }) }
  const store = async (next) => { if (await save({ addresses: next })) setEdit(null) }
  const submit = (e) => { e.preventDefault(); store(edit === 'new' ? [...list, a] : list.map((x, i) => (i === edit ? a : x))) }
  return (
    <section className="pq-sec" aria-labelledby="addr-h">
      <h2 id="addr-h">Shipping addresses</h2>
      {list.length > 0 && (
        <ul className="pq-addrs">
          {list.map((x, i) => (
            <li key={i}>
              <address>{x.label && <b>{x.label}{i === 0 ? ', default' : ''}<br /></b>}{!x.label && i === 0 && <b>Default<br /></b>}{x.name}{x.company && <><br />{x.company}</>}<br />{x.line1}{x.line2 && <><br />{x.line2}</>}<br />{x.city}, {x.state} {x.zip}</address>
              <span className="pq-saved-act">
                <button type="button" className="pq-link" onClick={() => begin(i)}>Edit</button>
                {i > 0 && <button type="button" className="pq-link" onClick={() => store([x, ...list.filter((_, j) => j !== i)])}>Make default</button>}
                <button type="button" className="pq-link" onClick={() => { if (confirm('Remove this address?')) store(list.filter((_, j) => j !== i)) }}>Remove</button>
              </span>
            </li>
          ))}
        </ul>
      )}
      {edit === null ? (
        <button type="button" className="pq-btn ghost" onClick={() => begin('new')}>Add an address</button>
      ) : (
        <form onSubmit={submit} className="pq-addrform">
          <div className="pq-fields">
            <label>Label<input placeholder="Main plant, receiving dock" value={a.label} onChange={set('label')} /></label>
            <label>Attention<input required value={a.name} onChange={set('name')} /></label>
            <label>Company<input value={a.company} onChange={set('company')} /></label>
            <label>Street<input required autoComplete="address-line1" value={a.line1} onChange={set('line1')} /></label>
            <label>Suite, building, room<input autoComplete="address-line2" value={a.line2} onChange={set('line2')} /></label>
            <label>City<input required autoComplete="address-level2" value={a.city} onChange={set('city')} /></label>
            <label>State<input required autoComplete="address-level1" value={a.state} onChange={set('state')} /></label>
            <label>ZIP<input required autoComplete="postal-code" value={a.zip} onChange={set('zip')} /></label>
            <label>Phone<input type="tel" value={a.phone} onChange={set('phone')} /></label>
          </div>
          <div className="pq-actions"><button className="pq-btn" disabled={st.busy}>Save address</button><button type="button" className="pq-link" onClick={() => setEdit(null)}>Cancel</button></div>
        </form>
      )}
      {st.err && <p className="pq-err">{st.err}</p>}
    </section>
  )
}

function Password() {
  const [f, setF] = useState({ password: '', new_password: '' })
  const [st, save] = useSave()
  return (
    <section className="pq-sec" aria-labelledby="pw-h">
      <h2 id="pw-h">Password</h2>
      <form onSubmit={async (e) => { e.preventDefault(); if (await save(f, 'Password changed. Other devices are signed out.')) setF({ password: '', new_password: '' }) }}>
        <div className="pq-fields">
          <label>Current password<input required type="password" autoComplete="current-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></label>
          <label>New password<input required type="password" minLength={10} autoComplete="new-password" value={f.new_password} onChange={(e) => setF({ ...f, new_password: e.target.value })} /></label>
        </div>
        <div className="pq-actions"><button className="pq-btn ghost" disabled={st.busy}>Change password</button>{st.ok && <span className="pq-okline">{st.ok}</span>}</div>
        {st.err && <p className="pq-err">{st.err}</p>}
      </form>
    </section>
  )
}

function Terms({ me }) {
  const [note, setNote] = useState('')
  const [st, setSt] = useState({ busy: false, err: '' })
  useEffect(() => { if (window.location.hash === '#terms') setTimeout(() => document.getElementById('terms')?.scrollIntoView({ block: 'start' }), 300) }, [])
  const ask = async (e) => {
    e.preventDefault(); setSt({ busy: true, err: '' })
    try { const r = await call('POST', '/api/public/account/terms-request', { note }); setAccount({ customer: r.customer, reset_by_email: true }); setSt({ busy: false, err: '' }) } catch (x) { setSt({ busy: false, err: x.message }) }
  }
  return (
    <section id="terms" className="pq-sec pq-anchor" aria-labelledby="terms-h">
      <h2 id="terms-h">Payment terms</h2>
      {me.net_terms_days ? (
        <p>Your account has <b>net {me.net_terms_days}</b> terms. When you choose Invoice my company at checkout, we start right away and you pay within {me.net_terms_days} days.</p>
      ) : me.terms_requested ? (
        <p>You asked for net terms. We review requests within a few business days and will email you. Until then, invoices are due on receipt, and you can always pay by card.</p>
      ) : (
        <form onSubmit={ask}>
          <p className="pq-muted" style={{ marginTop: 0 }}>Right now your invoices are due on receipt, and we start when they are paid. Businesses and agencies can ask for net 30 terms.</p>
          <label className="pq-notes">About your company
            <textarea required minLength={10} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)}
              placeholder="Legal company name, years in business, who pays invoices (accounts payable email), and one or two suppliers who give you terms" />
          </label>
          <div className="pq-actions"><button className="pq-btn ghost" disabled={st.busy}>Ask for net 30 terms</button></div>
          {st.err && <p className="pq-err">{st.err}</p>}
        </form>
      )}
    </section>
  )
}
