import { BrowserRouter, Routes, Route, Link, Navigate } from 'react-router-dom'
import { useEffect, useMemo, useState, type ReactElement } from 'react'
import { api, type UserOut, type ImmichSettings, type GroupDetailOut, type InstanceStats, type SyncProgress } from './lib/api'

function RequireAuth({ children }: { children: ReactElement }) {
  const [checked, setChecked] = useState(false)
  const [ok, setOk] = useState(false)
  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) { setChecked(true); setOk(false); return }
    api.me()
      .then(() => { setOk(true) })
      .catch(() => { localStorage.removeItem('token'); setOk(false) })
      .finally(() => setChecked(true))
  }, [])
  if (!checked) return null
  if (!ok) return <Navigate to="/login" replace />
  return children
}

function GuestOnly({ children }: { children: ReactElement }) {
  const [checked, setChecked] = useState(false)
  const [loggedIn, setLoggedIn] = useState(false)
  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) { setChecked(true); setLoggedIn(false); return }
    api.me()
      .then(() => setLoggedIn(true))
      .catch(() => { localStorage.removeItem('token'); setLoggedIn(false) })
      .finally(() => setChecked(true))
  }, [])
  if (!checked) return null
  if (loggedIn) return <Navigate to="/" replace />
  return children
}

function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    try {
      await api.login(username, password)
      location.href = '/'
    } catch (err: any) {
      setError(err.message || 'Login failed')
    }
  }
  return (
    <div className="auth-hero">
      <div className="card auth-card">
        <img className="auth-logo" src="/immich-logo.svg" alt="Immich" />
        <div className="auth-title">Login</div>
        <div className="card-body">
          <form onSubmit={onSubmit} className="input-group">
            <input className="input" placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} />
            <input className="input" placeholder="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
            <div className="auth-actions">
              <button className="btn btn-primary" type="submit" style={{ width: '100%' }}>Login</button>
            </div>
          </form>
          {error && <p style={{ color: 'var(--danger)', marginTop: 10 }}>{error}</p>}
          <p className="muted" style={{ marginTop: 10, textAlign: 'center' }}>No account? <Link to="/register">Register</Link></p>
        </div>
      </div>
    </div>
  )
}

function Register() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    try {
      await api.register(username, password)
      await api.login(username, password)
      location.href = '/'
    } catch (err: any) {
      setError(err.message || 'Register failed')
    }
  }
  return (
    <div className="auth-hero">
      <div className="card auth-card">
        <img className="auth-logo" src="/immich-logo.svg" alt="Immich" />
        <div className="auth-title">Create account</div>
        <div className="card-body">
          <form onSubmit={onSubmit} className="input-group">
            <input className="input" placeholder="Email" value={username} onChange={(e) => setUsername(e.target.value)} />
            <input className="input" placeholder="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
            <div className="auth-actions">
              <button className="btn btn-primary" type="submit" style={{ width: '100%' }}>Register</button>
            </div>
          </form>
          {error && <p style={{ color: 'var(--danger)', marginTop: 10 }}>{error}</p>}
          <p className="muted" style={{ marginTop: 10, textAlign: 'center' }}>Have an account? <Link to="/login">Login</Link></p>
        </div>
      </div>
    </div>
  )
}

function Navbar({ user }: { user: UserOut | null }) {
  const isAuthPage = location.pathname.startsWith('/login') || location.pathname.startsWith('/register')
  if (isAuthPage) return null
  return (
    <div className="nav">
      <div className="nav-inner">
        <div className="nav-logo"><span className="nav-logo-dot" /> Immich Sync</div>
        <div className="nav-links">
          <Link to="/">Groups</Link>
          <Link to="/settings">Settings</Link>
        </div>
        <div className="nav-spacer" />
        {user ? (
          <div className="row" style={{ gap: 8 }}>
            <span className="badge">@{user.username}</span>
            <button className="btn btn-ghost" onClick={() => { localStorage.removeItem('token'); location.href = '/login' }}>Logout</button>
          </div>
        ) : (
          <Link to="/login">Login</Link>
        )}
      </div>
    </div>
  )
}

function Settings() {
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [msg, setMsg] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    api.getImmichSettings().then((s: ImmichSettings) => { setBaseUrl(s.base_url); setApiKey(s.api_key) }).catch(() => {})
  }, [])
  const save = async () => {
    setMsg(''); setError('')
    try {
      await api.setImmichSettings({ base_url: baseUrl, api_key: apiKey })
      setMsg('Saved and validated')
    } catch (e: any) { setError(e.message) }
  }
  return (
    <div className="page">
      <div className="page-title"><h2 style={{ margin: 0 }}>Immich Settings</h2><span className="muted">Per-user</span></div>
      <div className="card">
        <div className="card-body">
          <div className="input-group">
            <input className="input" placeholder="Base URL (e.g. https://immich.example.com)" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
            <input className="input" placeholder="API Key" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
            <button className="btn btn-primary" onClick={save}>Save</button>
          </div>
          {msg && <p style={{ color: 'var(--success)', marginTop: 10 }}>{msg}</p>}
          {error && <p style={{ color: 'var(--danger)', marginTop: 10 }}>{error}</p>}
        </div>
      </div>
    </div>
  )
}

function Groups() {
  const [groups, setGroups] = useState<Array<{ id: number; label: string; expires_at: string | null }>>([])
  const [label, setLabel] = useState('')
  const [expires, setExpires] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    api.listGroups().then(setGroups).catch((e) => setError(e.message))
  }, [])
  const create = async () => {
    try {
      const g = await api.createGroup(label, expires)
      setGroups([g, ...groups])
      setLabel('')
      setExpires('')
    } catch (e: any) {
      setError(e.message)
    }
  }
  return (
    <div className="page">
      <div className="page-title"><h2 style={{ margin: 0 }}>Your Groups</h2>
        <div className="input-group">
          <input className="input" placeholder="New group label" value={label} onChange={(e) => setLabel(e.target.value)} />
          <input className="input" placeholder="Expiry (ISO, ≤ 6 months)" value={expires} onChange={(e) => setExpires(e.target.value)} />
          <button className="btn btn-primary" onClick={create}>Create</button>
        </div>
      </div>
      {error && <p style={{ color: 'var(--danger)' }}>{error}</p>}
      <div className="card">
        <div className="card-body">
          <ul className="list">
            {groups.map(g => (
              <li key={g.id} className="row-spread">
                <div className="row" style={{ gap: 8 }}>
                  <Link to={`/groups/${g.id}`}>{g.label}</Link>
                  {g.expires_at && <span className="badge">expires {new Date(g.expires_at).toLocaleString()}</span>}
                </div>
                <Link to={`/groups/${g.id}`}>Open →</Link>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}

function GroupDetail() {
  const id = Number(location.pathname.split('/').pop())
  const [group, setGroup] = useState<GroupDetailOut | null>(null)
  const [albumId, setAlbumId] = useState('')
  const [maxSizeMb, setMaxSizeMb] = useState<number>(100)
  const [error, setError] = useState('')
  const [progress, setProgress] = useState<SyncProgress | null>(null)
  const [stats, setStats] = useState<InstanceStats[] | null>(null)
  const [editLabel, setEditLabel] = useState('')
  const [editExpiry, setEditExpiry] = useState('')
  const [memberUsername, setMemberUsername] = useState('')

  const load = async () => {
    try {
      const g = await api.getGroup(id)
      setGroup(g)
      setEditLabel(g.label)
      setEditExpiry(g.expires_at || '')
    } catch (e: any) {
      setError(e.message)
    }
  }

  useEffect(() => { load() }, [id])

  // Poll progress and instance stats regularly
  useEffect(() => {
    let cancelled = false
    let timer: number | undefined
    const poll = async () => {
      try {
        const [p, s] = await Promise.all([
          api.getProgress(id),
          api.getInstanceStats(id),
        ])
        if (!cancelled) {
          setProgress(p)
          setStats(s)
        }
      } catch (e: any) {
        if (!cancelled) setError(e.message)
      } finally {
        if (!cancelled) timer = window.setTimeout(poll, 2000)
      }
    }
    poll()
    return () => { cancelled = true; if (timer) window.clearTimeout(timer) }
  }, [id])

  const upsertInstance = async () => {
    try {
      const sizeBytes = Math.max(1, Math.floor((Number(maxSizeMb) || 100) * 1024 * 1024))
      await api.addInstance({ sync_id: id, album_id: albumId, size_limit_bytes: sizeBytes })
      setAlbumId('')
      setMaxSizeMb(100)
      await load()
    } catch (e: any) {
      setError(e.message)
    }
  }

  const trigger = async () => {
    try {
      await api.triggerSync(id)
      const p = await api.getProgress(id)
      setProgress(p)
    } catch (e: any) { setError(e.message) }
  }

  const saveGroup = async () => {
    try {
      await api.updateGroup(id, { label: editLabel, expires_at: editExpiry || undefined })
      await load()
    } catch (e: any) { setError(e.message) }
  }

  const addMember = async () => {
    try { await api.addMemberByUsername(id, memberUsername); setMemberUsername(''); await load() } catch (e: any) { setError(e.message) }
  }
  const removeMember = async (uid: number) => {
    try { await api.removeMember(id, uid); await load() } catch (e: any) { setError(e.message) }
  }

  const overallPct = useMemo(() => {
    if (!progress || progress.total === 0) return 0
    return Math.min(100, Math.round((progress.done / Math.max(progress.total, 1)) * 100))
  }, [progress])

  if (!group) return <div className="page">Loading...</div>

  return (
    <div className="page">
      <div className="page-title">
        <h2 style={{ margin: 0 }}>{group.label}</h2>
        <div className="row" style={{ gap: 10 }}>
          <button className="btn btn-primary" onClick={trigger}>Trigger Sync</button>
          <span className="badge">{group.expires_at ? `expires ${new Date(group.expires_at).toLocaleString()}` : 'no expiry'}</span>
        </div>
      </div>

      {progress && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-header">Overall Progress</div>
          <div className="card-body">
            <div className="row-spread" style={{ marginBottom: 8 }}>
              <div className="muted">{progress.status}</div>
              <div className="muted">{progress.done}/{progress.total}{typeof progress.already === 'number' ? ` — already: ${progress.already}` : ''}{typeof progress.remaining === 'number' ? ` — remaining: ${progress.remaining}` : ''}{typeof progress.eta_seconds === 'number' && isFinite(progress.eta_seconds) ? ` — ETA: ${formatEta(progress.eta_seconds)}` : ''}</div>
            </div>
            <div className="progress"><div className="progress-bar" style={{ width: `${overallPct}%` }} /></div>
          </div>
        </div>
      )}

      <div className="grid">
        {group.owner_id && (
          <div className="col-6">
            <div className="card">
              <div className="card-header">Owner Settings</div>
              <div className="card-body">
                <div className="input-group" style={{ marginBottom: 10 }}>
                  <input className="input" placeholder="Label" value={editLabel} onChange={(e) => setEditLabel(e.target.value)} />
                  <input className="input" placeholder="Expiry (ISO)" value={editExpiry} onChange={(e) => setEditExpiry(e.target.value)} />
                  <button className="btn btn-primary" onClick={saveGroup}>Save</button>
                </div>
                <div className="input-group" style={{ marginBottom: 10 }}>
                  <input className="input" placeholder="Add member by username" value={memberUsername} onChange={(e) => setMemberUsername(e.target.value)} />
                  <button className="btn" onClick={addMember}>Add</button>
                </div>
                <ul className="list">
                  {group.members.map(m => (
                    <li key={m.id} className="row-spread">
                      <span>{m.username}</span>
                      {m.id !== group.owner_id && (
                        <button className="btn" onClick={() => removeMember(m.id)}>Remove</button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        )}

        <div className="col-6">
          <div className="card">
            <div className="card-header">Join or Update Your Instance</div>
            <div className="card-body">
              <p className="muted" style={{ marginTop: 0 }}>Provide the album id to sync. Your label is your username, and URL comes from Settings.</p>
              <div className="input-group">
                <input className="input" placeholder="album_id" value={albumId} onChange={(e) => setAlbumId(e.target.value)} />
                <input className="input" style={{ width: 160 }} type="number" min={1} step={1} placeholder="max size (MB)" value={maxSizeMb}
                       onChange={(e) => setMaxSizeMb(Number(e.target.value))} />
                <button className="btn btn-primary" onClick={upsertInstance}>Save</button>
              </div>
              <div className="muted" style={{ marginTop: 8 }}>Default 100 MB</div>
            </div>
          </div>
        </div>

        <div className="col-12">
          <div className="card">
            <div className="card-header">Instances</div>
            <div className="card-body">
              <ul className="list">
                {group.instances?.map((i: any) => {
                  const st = stats?.find(s => s.instance_id === i.id)
                  const p = (progress?.per_instance && (progress.per_instance as any)[i.id]) || null
                  const pct = p ? Math.round((p.done / Math.max(p.missing || 0, p.done + p.missing)) * 100) : null
                  return (
                    <li key={i.id}>
                      <div className="row-spread" style={{ alignItems: 'flex-start' }}>
                        <div>
                          <div className="row" style={{ gap: 8 }}>
                            <strong>{i.username}</strong>
                            {i.base_url && <span className="badge">{i.base_url}</span>}
                            <span className="badge">album {i.album_id}</span>
                            <span className="badge">limit {Math.floor(i.size_limit_bytes / (1024 * 1024))} MB</span>
                          </div>
                          {st && (
                            <div className="muted" style={{ marginTop: 6 }}>{st.album_title ? `${st.album_title}: ` : ''}{st.asset_count} assets</div>
                          )}
                        </div>
                        {p && (
                          <div style={{ minWidth: 240 }}>
                            <div className="muted" style={{ textAlign: 'right', marginBottom: 6 }}>done {p.done} / missing {p.missing} — already {p.already}</div>
                            <div className="progress"><div className="progress-bar" style={{ width: `${pct ?? 0}%` }} /></div>
                          </div>
                        )}
                      </div>
                    </li>
                  )
                })}
              </ul>
            </div>
          </div>
        </div>
      </div>

      {progress?.oversized && Object.keys(progress.oversized).length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="card-header">Oversized assets skipped</div>
          <div className="card-body"><pre style={{ margin: 0 }}>{JSON.stringify(progress.oversized, null, 2)}</pre></div>
        </div>
      )}

      {error && <p style={{ color: 'var(--danger)', marginTop: 16 }}>{error}</p>}
    </div>
  )
}

function Shell() {
  const [user, setUser] = useState<UserOut | null>(null)
  useEffect(() => {
    api.me().then(setUser).catch(() => setUser(null))
  }, [])
  return (
    <BrowserRouter>
      <Navbar user={user} />
      <Routes>
        <Route path="/login" element={<GuestOnly><Login /></GuestOnly>} />
        <Route path="/register" element={<GuestOnly><Register /></GuestOnly>} />
        <Route path="/settings" element={<RequireAuth><Settings /></RequireAuth>} />
        <Route path="/" element={<RequireAuth><Groups /></RequireAuth>} />
        <Route path="/groups/:id" element={<RequireAuth><GroupDetail /></RequireAuth>} />
      </Routes>
    </BrowserRouter>
  )
}

export default function App() {
  return <Shell />
}

function formatEta(seconds: number): string {
  if (!isFinite(seconds) || seconds < 0) return 'n/a'
  const s = Math.ceil(seconds)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const ss = s % 60
  if (h > 0) return `${h}h ${m}m ${ss}s`
  if (m > 0) return `${m}m ${ss}s`
  return `${ss}s`
}
