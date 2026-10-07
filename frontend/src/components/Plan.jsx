import { useEffect, useState } from 'react'
import { api } from '../api'

const EQUIPMENT = { full_gym: 'Full gym', dumbbells: 'Dumbbells', bodyweight: 'Bodyweight' }

export default function Plan() {
  const [plan, setPlan] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => { api.workoutPlan().then(setPlan).catch((e) => setError(e.message)) }, [])

  if (error) return <div className="card error">{error}</div>
  if (!plan) return <p className="muted">Loading…</p>

  return (
    <>
      <section className="card">
        <h2>{plan.split}</h2>
        <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
          <span className="pill accent">{plan.goal}</span>
          <span className="pill">{plan.days_per_week} days/week</span>
          <span className="pill">{EQUIPMENT[plan.equipment]}</span>
        </div>
        <p className="muted small" style={{ marginBottom: 0 }}>Change days or equipment on the Profile tab.</p>
      </section>

      <section className="card">
        {plan.week.map((d) => (
          <div key={d.day} className={`day-card ${d.session === 'Rest' ? 'rest' : ''}`}>
            <div className="head"><span>{d.day}</span><span>{d.session}</span></div>
            {d.exercises.map((ex) => (
              <div key={ex.name} className="exercise">
                <span>{ex.name}</span>
                <span className="sets">{ex.sets} × {ex.reps} · {ex.rest_seconds}s</span>
              </div>
            ))}
            {d.note && <div className="muted small">{d.note}</div>}
          </div>
        ))}
      </section>

      <section className="card">
        <h2>Notes</h2>
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          {plan.notes.map((n) => <li key={n} className="small" style={{ marginBottom: 4 }}>{n}</li>)}
          <li className="small">Cardio: {plan.cardio}</li>
        </ul>
      </section>
    </>
  )
}
