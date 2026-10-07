import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import Today from './components/Today'
import WeightView from './components/WeightView'
import Trends from './components/Trends'
import Plan from './components/Plan'
import ProfileForm from './components/ProfileForm'

const TABS = [
  { id: 'today', label: 'Today', icon: 'M4 12h16M12 4v16' },
  { id: 'weight', label: 'Weight', icon: 'M4 18l5-6 4 3 7-9' },
  { id: 'trends', label: 'Trends', icon: 'M5 20V10M12 20V4M19 20v-7' },
  { id: 'plan', label: 'Workouts', icon: 'M3 10v4M7 7v10M17 7v10M21 10v4M7 12h10' },
  { id: 'profile', label: 'Profile', icon: 'M12 12a4 4 0 100-8 4 4 0 000 8zM4 21a8 8 0 0116 0' },
]

export default function App() {
  const [tab, setTab] = useState('today')
  const [profile, setProfile] = useState(undefined) // undefined = loading, null = none yet
  const [targets, setTargets] = useState(null)
  const [banner, setBanner] = useState(null)
  const [error, setError] = useState(null)

  const refreshTargets = useCallback(async () => {
    setTargets(await api.targets())
  }, [])

  // Weekly adaptive check-in: run automatically when one is due.
  const autoCheckin = useCallback(async () => {
    const t = await api.targets()
    if (t.checkin_due) {
      const result = await api.runCheckin()
      if (result.checkin.status === 'ok') {
        setBanner(
          `Weekly check-in: estimated expenditure ${result.checkin.used_tdee} kcal/day. ` +
            `New target ${result.targets.calories} kcal.`,
        )
      }
      setTargets(await api.targets())
    } else {
      setTargets(t)
    }
  }, [])

  useEffect(() => {
    api
      .getProfile()
      .then((p) => {
        setProfile(p)
        return autoCheckin()
      })
      .catch((e) => (e.status === 404 ? setProfile(null) : setError(e.message)))
  }, [autoCheckin])

  async function onProfileSaved(p) {
    setProfile(p)
    await refreshTargets()
    setTab('today')
  }

  if (error) return <div className="app"><div className="card error">Could not reach the server: {error}</div></div>
  if (profile === undefined) return <div className="app"><p className="muted">Loading…</p></div>

  if (profile === null) {
    return (
      <div className="app">
        <header className="top"><h1>Welcome</h1></header>
        <p className="muted">Tell me a bit about you to calculate your starting targets.</p>
        <ProfileForm onSaved={onProfileSaved} />
      </div>
    )
  }

  return (
    <div className="app">
      <header className="top">
        <h1>{TABS.find((t) => t.id === tab).label}</h1>
        {targets && (
          <span className="sub">
            {targets.tdee_source === 'adaptive' ? 'Adaptive' : 'Formula'} TDEE {targets.targets.tdee} kcal
          </span>
        )}
      </header>
      {banner && (
        <div className="banner" role="status">
          {banner} <button className="link" onClick={() => setBanner(null)} aria-label="Dismiss">✕</button>
        </div>
      )}

      {tab === 'today' && <Today targets={targets} />}
      {tab === 'weight' && <WeightView onChange={refreshTargets} />}
      {tab === 'trends' && <Trends targets={targets} onCheckin={refreshTargets} />}
      {tab === 'plan' && <Plan />}
      {tab === 'profile' && <ProfileForm initial={profile} onSaved={onProfileSaved} />}

      <nav className="tabs" aria-label="Sections">
        <div className="inner">
          {TABS.map((t) => (
            <button key={t.id} className={tab === t.id ? 'active' : ''} onClick={() => setTab(t.id)} aria-current={tab === t.id ? 'page' : undefined}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d={t.icon} />
              </svg>
              {t.label}
            </button>
          ))}
        </div>
      </nav>
    </div>
  )
}
