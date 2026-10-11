import { useEffect, useRef, useState } from 'react'
import { accountHref, call, money, pdfLink, statusPath, useAccount } from './shared'

// Ordering an instant quote: contact, ship-to, card (Stripe's page) or purchase order, terms.
const BLANK = { name: '', company: '', line1: '', line2: '', city: '', state: '', zip: '', phone: '' }

export default function Checkout({ req, token, setReq, info }) {
  const acct = useAccount()
  const me = acct?.customer
  const methods = req.checkout?.methods || ['invoice']
  const [open, setOpen] = useState(false)
  const [f, setF] = useState({ name: '', company: '', email: '', phone: '', method: methods[0], po_number: '', billing_email: '', needed_by: '', notes: '', accept_terms: false, save_address: true })
  const [ship, setShip] = useState(BLANK)
  const [pick, setPick] = useState('new')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [changed, setChanged] = useState(null)
  const total = req.result?.total
  const terms = me?.net_terms_days || 0

  useEffect(() => {
    if (!me) return
    setF((x) => ({ ...x, name: x.name || me.name, company: x.company || me.company, email: x.email || me.email, phone: x.phone || me.phone }))
    if (me.addresses?.length) { setPick('0'); setShip({ ...BLANK, ...me.addresses[0] }) }
    else setShip((s) => ({ ...s, name: s.name || me.name, company: s.company || me.company }))
  }, [me?.id])
  useEffect(() => { if (!methods.includes(f.method)) setF((x) => ({ ...x, method: methods[0] })) }, [methods.join()])

  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const setS = (k) => (e) => { setShip({ ...ship, [k]: e.target.value }); setPick('new') }
  const choose = (v) => { setPick(v); setShip(v === 'new' ? { ...BLANK, name: f.name, company: f.company } : { ...BLANK, ...me.addresses[Number(v)] }) }

  const place = async (e) => {
    e.preventDefault()
    setBusy(true); setErr(''); setChanged(null)
    try {
      const r = await call('POST', `/api/public/quote/${req.ref}/checkout`, {
        token, expected_total: total, method: f.method, po_number: f.po_number, billing_email: f.billing_email, needed_by: f.needed_by,
        notes: f.notes, accept_terms: f.accept_terms, save_address: !!me && pick === 'new' && f.save_address,
        contact: { name: f.name, company: f.company, email: f.email, phone: f.phone }, ship_to: { ...ship, name: ship.name || f.name, company: ship.company || f.company },
      })
      if (r.redirect) { window.location.assign(r.redirect); return }
      setReq({ ...r.view, token })
      if (!window.location.pathname.startsWith('/quote/status/')) window.history.replaceState(null, '', statusPath(req.ref, token))
    } catch (x) {
      if (x.status === 409 && x.data?.view) { setChanged(x.data.total); setReq({ ...x.data.view, token }) } else setErr(x.message)
    }
    setBusy(false)
  }

  if (!open) {
    return (
      <div className="pq-buy">
        <h2>Ready to order?</h2>
        <p className="pq-muted pq-small">This price is firm. Order now{methods.includes('card') ? ' and pay by card, or have us invoice your company' : ' and we invoice your company'}. We confirm the ship date by email.</p>
        <button type="button" className="pq-btn" onClick={() => setOpen(true)}>Order for {money(total)}</button>
      </div>
    )
  }
  return (
    <form className="pq-submit pq-checkout" onSubmit={place}>
      <h2>Place your order</h2>
      {!me && acct !== undefined && (
        <p className="pq-muted pq-small"><a href={accountHref(statusPath(req.ref, token))}>Sign in or create an account</a> to keep your orders and addresses together. You can also order without one.</p>
      )}

      <fieldset>
        <legend>Contact</legend>
        <div className="pq-fields two">
          <label>Name<input required autoComplete="name" value={f.name} onChange={set('name')} /></label>
          <label>Company<input autoComplete="organization" value={f.company} onChange={set('company')} /></label>
          <label>Email<input required type="email" autoComplete="email" value={f.email} onChange={set('email')} /></label>
          <label>Phone<input type="tel" autoComplete="tel" value={f.phone} onChange={set('phone')} /></label>
        </div>
      </fieldset>

      <fieldset>
        <legend>Ship to</legend>
        {me?.addresses?.length > 0 && (
          <label className="pq-wide">Saved addresses
            <select value={pick} onChange={(e) => choose(e.target.value)}>
              {me.addresses.map((a, i) => <option key={i} value={String(i)}>{a.label || a.company || a.name}, {a.line1}, {a.city}</option>)}
              <option value="new">A new address</option>
            </select>
          </label>
        )}
        <div className="pq-fields two">
          <label>Attention<input autoComplete="shipping name" placeholder={f.name} value={ship.name} onChange={setS('name')} /></label>
          <label>Company<input autoComplete="shipping organization" value={ship.company} onChange={setS('company')} /></label>
          <label className="pq-span2">Street<input required autoComplete="shipping address-line1" value={ship.line1} onChange={setS('line1')} /></label>
          <label className="pq-span2">Suite, building, room<input autoComplete="shipping address-line2" value={ship.line2} onChange={setS('line2')} /></label>
          <label>City<input required autoComplete="shipping address-level2" value={ship.city} onChange={setS('city')} /></label>
          <div className="pq-pair">
            <label>State<input required autoComplete="shipping address-level1" value={ship.state} onChange={setS('state')} /></label>
            <label>ZIP<input required autoComplete="shipping postal-code" inputMode="numeric" value={ship.zip} onChange={setS('zip')} /></label>
          </div>
        </div>
        {me && pick === 'new' && <label className="pq-check"><input type="checkbox" checked={f.save_address} onChange={set('save_address')} /><span>Save this address to my account</span></label>}
      </fieldset>

      <fieldset>
        <legend>Payment</legend>
        <div className="pq-methods" role="radiogroup">
          {methods.includes('card') && (
            <label className={`pq-method ${f.method === 'card' ? 'on' : ''}`}>
              <input type="radio" name="method" value="card" checked={f.method === 'card'} onChange={set('method')} />
              <span><b>Card</b><span className="pq-muted">Pay on Stripe's secure page. Your card number never reaches us.</span></span>
            </label>
          )}
          <label className={`pq-method ${f.method === 'invoice' ? 'on' : ''}`}>
            <input type="radio" name="method" value="invoice" checked={f.method === 'invoice'} onChange={set('method')} />
            <span><b>Invoice my company</b><span className="pq-muted">{terms
              ? `Your account has net ${terms} terms. You sign a short order agreement online, then we start and you pay within ${terms} days.`
              : 'You sign a short order agreement online and get the invoice. Pay it by bank transfer or check' + (methods.includes('card') ? ', or online' : '') + ', and we start when it is paid.'}</span></span>
          </label>
        </div>
        {f.method === 'invoice' && (
          <>
            <div className="pq-fields two">
              <label>PO number, if you have one<input value={f.po_number} onChange={set('po_number')} /></label>
              <label>Send the invoice to<input type="email" placeholder={f.email || 'accounts payable email'} value={f.billing_email} onChange={set('billing_email')} /></label>
            </div>
            {!terms && (
              <p className="pq-muted pq-small">{me
                ? (me.terms_requested ? 'You asked for net terms. We will let you know once your account is approved.' : <>Want net 30 terms? <a href="/quote/account#terms">Ask for them in your account</a>.</>)
                : <>Approved accounts can pay on net 30 terms. <a href={accountHref(statusPath(req.ref, token))}>Create an account</a> to ask for them.</>}</p>
            )}
          </>
        )}
      </fieldset>

      <div className="pq-fields two">
        <label>Needed by<input type="date" value={f.needed_by} onChange={set('needed_by')} /></label>
      </div>
      <label className="pq-notes">Order notes<textarea maxLength={2000} value={f.notes} onChange={set('notes')} placeholder="Packaging, certificates of conformance, receiving hours" /></label>
      <label className="pq-check">
        <input type="checkbox" required checked={f.accept_terms} onChange={set('accept_terms')} />
        <span>{info.terms}</span>
      </label>
      <p className="pq-muted pq-small">This total does not include shipping or sales tax. We confirm shipping with you before the parts go out.</p>
      {changed != null && <p className="pq-err" role="alert">The price changed since you last looked. The new total is {money(changed)}. Check it and place the order again.</p>}
      {err && <p className="pq-err" role="alert">{err}</p>}
      <button className="pq-btn" disabled={busy}>{busy ? 'Placing your order…' : f.method === 'card' ? `Continue to payment, ${money(total)}` : `Place order and sign, ${money(total)}`}</button>
      <button type="button" className="pq-link" onClick={() => setOpen(false)}>Not now</button>
      <p className="pq-muted pq-small"><a href={pdfLink(req.ref, token)} target="_blank" rel="noopener">Save the quote as a PDF</a> for your purchasing team first.</p>
    </form>
  )
}

const STEP = { awaiting_signature: 'Sign the order agreement', awaiting_payment: 'Waiting for payment', paid: 'Paid', po_received: 'PO received', invoiced: 'Invoiced', invoice_due: 'Invoice sent', cancelled: 'Cancelled' }
export const invoiceLink = (ref, token) => `/api/public/quote/${ref}/invoice.pdf?token=${encodeURIComponent(token)}`
export const agreementLink = (ref, token) => `/api/public/quote/${ref}/agreement.pdf?token=${encodeURIComponent(token)}`

// Full width under the order: the agreement text, then the signature. Invoice orders start only once it is signed.
export function SignAgreement({ req, token, onSigned }) {
  const ag = req.order?.agreement
  const me = useAccount()?.customer
  const [f, setF] = useState({ name: '', title: '', company: '', code: '', authority: false, consent: false, agree: false })
  const [read, setRead] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [sent, setSent] = useState('')
  const box = useRef()
  useEffect(() => { const t = box.current; if (t && t.scrollHeight <= t.clientHeight + 40) setRead(true) }, [ag?.sha256])
  const buyer = req.order?.buyer || {}
  useEffect(() => { setF((x) => ({ ...x, name: x.name || buyer.name || me?.name || '', company: x.company || buyer.company || me?.company || '' })) }, [me?.id, ag?.sha256])
  if (!ag || ag.status !== 'pending') return null
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const code = async () => {
    setErr('')
    try { setSent((await call('POST', `/api/public/quote/${req.ref}/agreement/code`, { token })).sent_to) } catch (x) { setErr(x.message) }
  }
  const sign = async (e) => {
    e.preventDefault(); setBusy(true); setErr('')
    try { onSigned({ ...(await call('POST', `/api/public/quote/${req.ref}/agreement/sign`, { token, sha256: ag.sha256, ...f })), token }); window.scrollTo({ top: 0, behavior: 'smooth' }) } catch (x) { setErr(x.message) }
    setBusy(false)
  }
  if (ag.expired) return <section id="sign" className="pq-sec pq-anchor"><h2>Order agreement</h2><p className="pq-err">This agreement was not signed within 30 days and has expired. Contact us and we will send a new one at current prices.</p></section>
  const company = f.company || 'my company'
  return (
    <section id="sign" className="pq-sec pq-anchor pq-sign" aria-labelledby="sign-h">
      <div className="pq-sign-head">
        <h2 id="sign-h">Order agreement</h2>
        <a href={agreementLink(req.ref, token)} target="_blank" rel="noopener">Download as PDF</a>
      </div>
      <p className="pq-muted pq-secnote">Read it, then sign below. Questions or changes before you sign? Contact us; nothing starts until it is signed.</p>
      <div className="pq-agreement" ref={box} tabIndex={0} onScroll={(e) => { const t = e.currentTarget; if (t.scrollTop + t.clientHeight >= t.scrollHeight - 40) setRead(true) }}>
        {ag.text.split('\n\n').map((para, i) => <p key={i}>{para.split('\n').map((ln, j) => <span key={j}>{j > 0 && <br />}{ln}</span>)}</p>)}
      </div>
      {!read && <p className="pq-muted pq-small">Scroll to the end of the agreement to sign.</p>}
      <form onSubmit={sign} className="pq-signform">
        <div className="pq-fields">
          <label>Full name<input required autoComplete="name" value={f.name} onChange={set('name')} /></label>
          <label>Title<input required autoComplete="organization-title" placeholder="Purchasing manager" value={f.title} onChange={set('title')} /></label>
          <label>Company<input autoComplete="organization" value={f.company} onChange={set('company')} /></label>
        </div>
        <label className="pq-check"><input type="checkbox" checked={f.authority} onChange={set('authority')} /><span>I am authorized to sign for {company}.</span></label>
        <label className="pq-check"><input type="checkbox" checked={f.consent} onChange={set('consent')} /><span>I agree to sign electronically and to receive this agreement and related records electronically.</span></label>
        <label className="pq-check"><input type="checkbox" checked={f.agree} onChange={set('agree')} /><span>I have read and agree to this order agreement for order {req.ref}.</span></label>
        {ag.needs_code && (
          <div className="pq-fields two">
            <label>Code from your email<input inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={f.code} onChange={set('code')} /></label>
            <div className="pq-codebtn"><button type="button" className="pq-btn ghost" onClick={code}>{sent ? 'Send another code' : 'Email me a code'}</button>{sent && <span className="pq-muted pq-small">Sent to {sent}</span>}</div>
          </div>
        )}
        {f.name && <p className="pq-sigline" aria-hidden="true">{f.name}</p>}
        {err && <p className="pq-err" role="alert">{err}</p>}
        <button className="pq-btn" disabled={busy || !read}>{busy ? 'Signing…' : 'Sign the agreement'}</button>
      </form>
    </section>
  )
}

export function OrderPanel({ order, info, token, fresh = false }) {
  const o = order
  const a = o.ship_to || {}
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const pay = async () => {
    setBusy(true); setErr('')
    try { window.location.assign((await call('POST', `/api/public/quote/${o.number}/pay`, { token })).redirect); return } catch (x) { setErr(x.message) }
    setBusy(false)
  }
  const open = o.status === 'invoiced' || o.status === 'invoice_due'
  const payment = o.method === 'card' ? 'Card' : `Invoice ${o.invoice_number || ''}${o.terms_days ? `, net ${o.terms_days}` : ', due on receipt'}${o.po_number ? `, PO ${o.po_number}` : ''}`
  return (
    <div className="pq-done pq-order">
      <h2>{fresh ? 'Order placed' : 'Your order'}</h2>
      <p>Order <b>{o.number}</b>, {money(o.amount)}. <span className={`pq-ostat s-${o.status}`}>{o.status_label || STEP[o.status] || o.status}</span></p>
      {o.status === 'awaiting_signature' && (
        <div className="pq-signnote">
          <p><b>One more step: sign the order agreement.</b> It sets out payment, changes and cancellations. We send the invoice and start once it is signed.</p>
          <a className="pq-btn" href="#sign" onClick={(e) => { e.preventDefault(); document.getElementById('sign')?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }}>Read and sign</a>
        </div>
      )}
      {fresh && o.status === 'invoice_due' && <p>Thank you. Your invoice is ready below. We start your order when it is paid{o.lead_days ? `, and parts ship about ${o.lead_days} days after that` : ''}.</p>}
      {fresh && o.status === 'invoiced' && <p>Thank you. We are starting your order{o.lead_days ? `; parts ship in about ${o.lead_days} days` : ''}. Your invoice is due {o.due_date}.</p>}
      {fresh && o.method === 'card' && <p>Thank you. We confirm the ship date by email{o.lead_days ? `; parts ship in about ${o.lead_days} days` : ''}.</p>}
      <dl className="pq-odl">
        <div><dt>Payment</dt><dd>{payment}</dd></div>
        {open && <div><dt>Due</dt><dd>{o.terms_days ? o.due_date : 'On receipt'}</dd></div>}
        <div><dt>Ship to</dt><dd>{[a.name, a.company, a.line1, a.line2, `${a.city}, ${a.state} ${a.zip}`].filter(Boolean).join('\n')}</dd></div>
        <div><dt>Placed</dt><dd>{(o.placed_at || '').slice(0, 10)}</dd></div>
      </dl>
      {o.agreement && o.agreement.status !== 'pending' && token && (
        <p className="pq-small">Order agreement {o.agreement.status === 'signed' ? `signed by ${o.agreement.signed?.name}, ${(o.agreement.signed?.at || '').slice(0, 10)}` : 'on file'}. <a href={agreementLink(o.number, token)} target="_blank" rel="noopener">Download it</a></p>
      )}
      {o.invoice_number && token && (
        <div className="pq-save-row">
          <a className="pq-btn ghost" href={invoiceLink(o.number, token)} target="_blank" rel="noopener">{o.status === 'paid' && o.method === 'card' ? 'Download receipt' : 'Download invoice'}</a>
          {o.pay_online && <button type="button" className="pq-btn" disabled={busy} onClick={pay}>{busy ? 'Opening…' : `Pay ${money(o.amount)} online`}</button>}
        </div>
      )}
      {open && <p className="pq-muted pq-small">{o.pay_online ? 'Pay online by bank transfer or card, or use the' : 'Pay using the'} bank transfer or check details on the invoice. Put {o.invoice_number} on your payment.</p>}
      {err && <p className="pq-err" role="alert">{err}</p>}
      {info?.contact_email && <p className="pq-muted pq-small">Questions about this order? Email <a href={`mailto:${info.contact_email}?subject=Order ${o.number}`}>{info.contact_email}</a> and mention {o.number}.</p>}
    </div>
  )
}
