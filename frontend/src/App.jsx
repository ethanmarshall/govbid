import { createContext, useContext, useEffect, useState } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
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

function Shell({ auth }) {
  const [meta, setMeta] = useState(null)
  useEffect(() => {
    api.get('/api/meta').then(setMeta).catch(() => setMeta({ set_asides: {}, certifications: {}, pipeline_stages: [] }))
  }, [])
  const logout = async () => { await api.post('/api/auth/logout', {}); window.location.reload() }

  return (
    <AuthContext.Provider value={auth}>
    <MetaContext.Provider value={meta}>
      <div className="layout">
        <nav className="nav">
          <div className="brand">GovBid<span>Pro</span></div>
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/search">Search everything</NavLink>
          <div className="navgroup">Find work</div>
          <NavLink to="/opportunities">Opportunities</NavLink>
          <NavLink to="/pipeline">Pipeline</NavLink>
          <NavLink to="/competitors">Competitor intel</NavLink>
          <NavLink to="/market">Recompetes and buyers</NavLink>
          <NavLink to="/import">Import (DIBBS, forecasts)</NavLink>
          <div className="navgroup">Bid</div>
          <NavLink to="/packages">Packages</NavLink>
          <NavLink to="/part-quotes">Part quotes</NavLink>
          <NavLink to="/pricing-workbook">Pricing workbook</NavLink>
          <NavLink to="/source-approvals">Source approvals</NavLink>
          <NavLink to="/standards">Standards library</NavLink>
          <NavLink to="/resources">Resources</NavLink>
          <div className="navgroup">Deliver</div>
          <NavLink to="/jobs">Jobs</NavLink>
          <NavLink to="/quality">Quality and suppliers</NavLink>
          <NavLink to="/flowdown">Clause flowdown</NavLink>
          <NavLink to="/finance">Invoices and finance</NavLink>
          <div className="navgroup">Business</div>
          <NavLink to="/contacts">Contacts and teaming</NavLink>
          <NavLink to="/past-performance">Past performance</NavLink>
          <NavLink to="/capability">Capability statement</NavLink>
          <NavLink to="/compliance">CMMC compliance</NavLink>
          <NavLink to="/profile">Company profile</NavLink>
          <div className="foot">
            SAM.gov key: {meta?.sam_key_configured ? 'set' : 'missing'}
            <br />
            AI analysis: {meta?.ai_configured ? 'on' : 'rule-based'}
            {auth.login_required && <><br /><button className="link navlink" onClick={logout}>Sign out ({auth.username})</button></>}
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
