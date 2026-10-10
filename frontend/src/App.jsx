import { createContext, useContext, useEffect, useState } from 'react'
import { NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { api } from './api'
import Dashboard from './pages/Dashboard.jsx'
import Opportunities from './pages/Opportunities.jsx'
import OpportunityDetail from './pages/OpportunityDetail.jsx'
import Pipeline from './pages/Pipeline.jsx'
import Imports from './pages/Imports.jsx'
import Competitors from './pages/Competitors.jsx'
import Profile from './pages/Profile.jsx'
import Resources from './pages/Resources.jsx'
import Packages from './pages/Packages.jsx'
import PackageBuilder from './pages/PackageBuilder.jsx'
import PartQuotes from './pages/PartQuotes.jsx'
import Standards from './pages/Standards.jsx'
import Contacts from './pages/Contacts.jsx'
import Compliance from './pages/Compliance.jsx'
import PastPerformance from './pages/PastPerformance.jsx'
import Jobs from './pages/Jobs.jsx'
import Quality from './pages/Quality.jsx'
import Finance from './pages/Finance.jsx'
import PricingWorkbook from './pages/PricingWorkbook.jsx'
import Flowdown from './pages/Flowdown.jsx'
import SourceApprovals from './pages/SourceApprovals.jsx'
import Search from './pages/Search.jsx'
import Market from './pages/Market.jsx'
import CapabilityStatement from './pages/CapabilityStatement.jsx'
import CustomerRequests from './pages/CustomerRequests.jsx'
import Hardware from './pages/Hardware.jsx'
import Calibration from './pages/Calibration.jsx'

const MetaContext = createContext(null)
export const useMeta = () => useContext(MetaContext)

export default function App() {
  const [auth, setAuth] = useState(null) // {login_required, signed_in, username, calendar_token}
  const checkAuth = () => api.get('/api/auth/status').then(setAuth).catch(() => setAuth({ login_required: false, signed_in: true }))
  useEffect(() => {
    checkAuth()
    const out = () => setAuth((a) => (a ? { ...a, signed_in: false } : a))
    window.addEventListener('govbid:signed-out', out)
    return () => window.removeEventListener('govbid:signed-out', out)
  }, [])
  if (!auth) return null
  if (!auth.signed_in) return <Login onDone={checkAuth} />
  return <Shell auth={auth} />
}

function Login({ onDone }) {
  const [u, setU] = useState('')
  const [p, setP] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (e) => {
    e.preventDefault(); setErr(''); setBusy(true)
    try { await api.post('/api/auth/login', { username: u, password: p }); await onDone() } catch (x) { setErr(x.message) }
    setBusy(false)
  }
  return (
    <div className="login-wrap">
      <form className="panel login-box" onSubmit={submit}>
        <div className="brand-dark">GovBid<span>Pro</span></div>
        <label className="f">Username<input autoFocus autoComplete="username" value={u} onChange={(e) => setU(e.target.value)} /></label>
        <label className="f">Password<input type="password" autoComplete="current-password" value={p} onChange={(e) => setP(e.target.value)} /></label>
        {err && <div className="err">{err}</div>}
        <button className="primary" disabled={busy || !u || !p}>{busy ? 'Signing in…' : 'Sign in'}</button>
      </form>
    </div>
  )
}

export const AuthContext = createContext(null)
export const useAuth = () => useContext(AuthContext)

const NAV = [
  [null, [['/', 'Dashboard'], ['/search', 'Search everything']]],
  ['Find work', [['/opportunities', 'Opportunities'], ['/pipeline', 'Pipeline'], ['/competitors', 'Competitor intel'], ['/market', 'Recompetes and buyers'], ['/import', 'Import (DIBBS, forecasts)']]],
  ['Bid', [['/packages', 'Packages'], ['/part-quotes', 'Part quotes'], ['/customer-requests', 'Customer requests'], ['/hardware', 'Hardware'], ['/calibration', 'Calibration'], ['/pricing-workbook', 'Pricing workbook'], ['/source-approvals', 'Source approvals'], ['/standards', 'Standards library'], ['/resources', 'Resources']]],
  ['Deliver', [['/jobs', 'Jobs'], ['/quality', 'Quality and suppliers'], ['/flowdown', 'Clause flowdown'], ['/finance', 'Invoices and finance']]],
  ['Business', [['/contacts', 'Contacts and teaming'], ['/past-performance', 'Past performance'], ['/capability', 'Capability statement'], ['/compliance', 'CMMC compliance'], ['/profile', 'Company profile']]],
]

function pageTitle(path) {
  let best = ['', 'GovBid Pro']
  for (const [, links] of NAV) for (const [to, label] of links) {
    if ((to === '/' ? path === '/' : path === to || path.startsWith(to + '/')) && to.length >= best[0].length) best = [to, label]
  }
  return best[1]
}

function Shell({ auth }) {
  const [meta, setMeta] = useState(null)
  const [menu, setMenu] = useState(false)
  const loc = useLocation()
  useEffect(() => {
    api.get('/api/meta').then(setMeta).catch(() => setMeta({ set_asides: {}, certifications: {}, pipeline_stages: [] }))
  }, [])
  useEffect(() => { setMenu(false); window.scrollTo(0, 0) }, [loc.pathname])
  useEffect(() => { // narrow screens: bring the selected tab into view in a scrolling tab strip
    let tries = 0, t
    const go = () => { // pages draw their tabs after their data loads, so look for a little while
      const on = document.querySelector('.tabs .on')
      const strip = on?.parentElement
      if (strip) { if (strip.scrollWidth > strip.clientWidth) strip.scrollLeft = on.offsetLeft - strip.offsetLeft - (strip.clientWidth - on.clientWidth) / 2 }
      else if (tries++ < 20) t = setTimeout(go, 100)
    }
    t = setTimeout(go, 50)
    return () => clearTimeout(t)
  }, [loc.pathname, loc.search])
  useEffect(() => { // phones and tablets: lock the page behind the open menu, close it with Escape
    document.body.classList.toggle('menu-open', menu)
    const key = (e) => { if (e.key === 'Escape') setMenu(false) }
    if (menu) window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [menu])
  const logout = async () => { try { await api.post('/api/auth/logout', {}) } finally { window.location.href = '/' } }

  return (
    <AuthContext.Provider value={auth}>
    <MetaContext.Provider value={meta}>
      <header className="topbar">
        <button className="menu-btn" aria-label="Open menu" aria-expanded={menu} onClick={() => setMenu(true)}><span /><span /><span /></button>
        <div className="topbar-title">{pageTitle(loc.pathname)}</div>
        <div className="brand topbar-brand">GovBid<span>Pro</span></div>
      </header>
      {menu && <div className="nav-backdrop" onClick={() => setMenu(false)} />}
      <div className="layout">
        <nav className={`nav ${menu ? 'open' : ''}`} aria-label="Main">
          <div className="row spread nav-head">
            <div className="brand">GovBid<span>Pro</span></div>
            <button className="nav-close" aria-label="Close menu" onClick={() => setMenu(false)}>×</button>
          </div>
          <div className="nav-acct">
            <a href="/quote" target="_blank" rel="noreferrer">Customer site</a>
            {auth.login_required && <button type="button" onClick={logout} title={`Signed in as ${auth.username}`}>Sign out</button>}
          </div>
          {NAV.map(([group, links]) => (
            <div key={group || 'top'}>
              {group && <div className="navgroup">{group}</div>}
              {links.map(([to, label]) => <NavLink key={to} to={to} end={to === '/'}>{label}</NavLink>)}
            </div>
          ))}
          <div className="foot">
            SAM.gov key: {meta?.sam_key_configured ? 'set' : 'missing'}
            <br />
            AI analysis: {meta?.ai_configured ? 'on' : 'rule-based'}
            {auth.login_required && <><br />Signed in as {auth.username}</>}
          </div>
        </nav>
        <main className="main">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/opportunities" element={<Opportunities />} />
            <Route path="/opportunities/:id" element={<OpportunityDetail />} />
            <Route path="/pipeline" element={<Pipeline />} />
            <Route path="/packages" element={<Packages />} />
            <Route path="/packages/:id" element={<PackageBuilder />} />
            <Route path="/part-quotes" element={<PartQuotes />} />
            <Route path="/competitors" element={<Competitors />} />
            <Route path="/import" element={<Imports />} />
            <Route path="/resources" element={<Resources />} />
            <Route path="/profile" element={<Profile />} />
            <Route path="/standards" element={<Standards />} />
            <Route path="/contacts" element={<Contacts />} />
            <Route path="/past-performance" element={<PastPerformance />} />
            <Route path="/compliance" element={<Compliance />} />
            <Route path="/jobs" element={<Jobs />} />
            <Route path="/quality" element={<Quality />} />
            <Route path="/finance" element={<Finance />} />
            <Route path="/pricing-workbook" element={<PricingWorkbook />} />
            <Route path="/flowdown" element={<Flowdown />} />
            <Route path="/source-approvals" element={<SourceApprovals />} />
            <Route path="/search" element={<Search />} />
            <Route path="/market" element={<Market />} />
            <Route path="/capability" element={<CapabilityStatement />} />
            <Route path="/customer-requests" element={<CustomerRequests />} />
            <Route path="/hardware" element={<Hardware />} />
            <Route path="/calibration" element={<Calibration />} />
          </Routes>
        </main>
      </div>
    </MetaContext.Provider>
    </AuthContext.Provider>
  )
}

export const ELIG_LABEL = {
  eligible_now: 'Can bid now',
  eligible_once_certified: 'After certification',
  not_eligible: 'Not eligible',
}

export function EligBadge({ status }) {
  return <span className={`badge b-${status}`}>{ELIG_LABEL[status] || status}</span>
}

export function DaysLeft({ days }) {
  if (days == null) return <span className="muted">n/a</span>
  if (days === 0) return <span className="due-soon">today</span>
  return <span className={days <= 7 ? 'due-soon' : ''}>{days}d</span>
}
