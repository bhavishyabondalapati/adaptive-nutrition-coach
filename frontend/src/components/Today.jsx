import { useCallback, useEffect, useState } from 'react'
import { api, todayISO } from '../api'

function Macro({ label, color, eaten, target }) {
  const pct = target ? Math.min(100, (eaten / target) * 100) : 0
  return (
    <div className="macro">
      <div className="label"><span className="dot" style={{ background: color }} />{label}</div>
      <div className="progress"><span style={{ width: `${pct}%`, background: color }} /></div>
      <div className="val">{Math.round(eaten)} / {target} g</div>
    </div>
  )
}

export default function Today({ targets }) {
  const [day, setDay] = useState(todayISO())
  const [entries, setEntries] = useState([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState(null)
  const [error, setError] = useState(null)

  const load = useCallback(() => api.food(day).then(setEntries).catch((e) => setError(e.message)), [day])
  useEffect(() => { load() }, [load])

  async function submit(e) {
    e.preventDefault()
    if (!text.trim()) return
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const r = await api.logFood(text, day)
      setText('')
      const notes = [...r.warnings, ...r.items.filter((i) => i.note).map((i) => `${i.input_name}: ${i.note}`)]
      setNotice(notes.length ? notes : null)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function remove(id) {
    await api.deleteFood(id)
    load()
  }

  const sum = (k) => entries.reduce((s, e) => s + e[k], 0)
  const eaten = sum('kcal')
  const t = targets?.targets
  const remaining = t ? t.calories - Math.round(eaten) : null

  return (
    <>
      {t && (
        <section className="card" aria-label="Daily targets">
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <h2 style={{ margin: 0 }}>{day === todayISO() ? 'Today' : day}</h2>
            <span className="pill accent">{t.goal}</span>
          </div>
          <div className="hero" style={{ marginTop: 8 }}>
            <span className="big">{remaining >= 0 ? remaining : -remaining}</span>
            <span className="muted">kcal {remaining >= 0 ? 'left' : 'over'} · {Math.round(eaten)} of {t.calories}</span>
          </div>
          <div className={`progress ${remaining < 0 ? 'over' : ''}`}>
            <span style={{ width: `${Math.min(100, (eaten / t.calories) * 100)}%` }} />
          </div>
          <div className="macros">
            <Macro label="Protein" color="var(--protein)" eaten={sum('protein_g')} target={t.protein_g} />
            <Macro label="Carbs" color="var(--carbs)" eaten={sum('carbs_g')} target={t.carbs_g} />
            <Macro label="Fat" color="var(--fat)" eaten={sum('fat_g')} target={t.fat_g} />
          </div>
          {t.expected_weekly_change_kg !== 0 && (
            <p className="muted small" style={{ marginBottom: 0 }}>
              Planned change: {t.expected_weekly_change_kg > 0 ? '+' : ''}{t.expected_weekly_change_kg} kg/week
              ({t.weekly_rate_pct}% of body weight)
            </p>
          )}
          {t.warnings.map((w) => <div key={w} className="warning">{w}</div>)}
        </section>
      )}

      <section className="card">
        <h2>Log food</h2>
        <form onSubmit={submit}>
          <label className="sr-only" htmlFor="food-text">What did you eat?</label>
          <div className="row">
            <input
              id="food-text" className="grow" placeholder="e.g. 2 eggs and toast"
              value={text} onChange={(e) => setText(e.target.value)} autoComplete="off"
            />
            <button className="primary" disabled={busy || !text.trim()}>{busy ? '…' : 'Log'}</button>
          </div>
          <div className="row" style={{ marginTop: 8 }}>
            <label className="muted small" htmlFor="food-day">Date</label>
            <input id="food-day" type="date" value={day} max={todayISO()} onChange={(e) => setDay(e.target.value)} style={{ width: 'auto' }} />
          </div>
        </form>
        {notice && notice.map((n) => <div key={n} className="warning">{n}</div>)}
        {error && <div className="error">{error}</div>}
      </section>

      <section className="card">
        <h2>Entries</h2>
        {entries.length === 0 ? (
          <p className="muted">Nothing logged yet. Try “1 cup oatmeal with a banana”.</p>
        ) : (
          <ul className="entries">
            {entries.map((e) => (
              <li key={e.id}>
                <div className="grow">
                  <div className="entry-name">{e.matched_name ?? e.input_name}</div>
                  <div className="entry-meta">
                    {e.quantity} {e.unit ?? '×'} · {e.grams} g · P {e.protein_g} C {e.carbs_g} F {e.fat_g}
                    {e.source === 'usda' && ' · USDA'}
                    {e.source === 'unknown' && ' · not found'}
                  </div>
                </div>
                <span className="num">{Math.round(e.kcal)} kcal</span>
                <button className="link" onClick={() => remove(e.id)} aria-label={`Delete ${e.input_name}`}>✕</button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  )
}
