import { useState } from 'react'
import { api } from '../api'

const DEFAULTS = {
  sex: 'male',
  age: 30,
  height_cm: 175,
  weight_kg: 75,
  activity_level: 'moderate',
  goal: 'maintain',
  rate_pct: '',
  training_days: 3,
  equipment: 'full_gym',
}

const ACTIVITY = {
  sedentary: 'Sedentary (desk job, little exercise)',
  light: 'Light (exercise 1–3 days/week)',
  moderate: 'Moderate (exercise 3–5 days/week)',
  active: 'Active (hard exercise 6–7 days/week)',
  very_active: 'Very active (physical job + training)',
}

export default function ProfileForm({ initial, onSaved }) {
  const [form, setForm] = useState({ ...DEFAULTS, ...initial, rate_pct: initial?.rate_pct ?? '' })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [saved, setSaved] = useState(false)

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  async function submit(e) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const body = {
        ...form,
        age: Number(form.age),
        height_cm: Number(form.height_cm),
        weight_kg: Number(form.weight_kg),
        training_days: Number(form.training_days),
        rate_pct: form.goal === 'maintain' || form.rate_pct === '' ? null : Number(form.rate_pct),
      }
      const p = await api.saveProfile(body)
      setSaved(true)
      onSaved(p)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="card" onSubmit={submit}>
      <h2>Body</h2>
      <div className="grid2">
        <label className="field">Sex
          <select value={form.sex} onChange={set('sex')}>
            <option value="male">Male</option>
            <option value="female">Female</option>
          </select>
        </label>
        <label className="field">Age
          <input type="number" min="16" max="100" value={form.age} onChange={set('age')} required />
        </label>
        <label className="field">Height (cm)
          <input type="number" step="0.1" min="120" max="230" value={form.height_cm} onChange={set('height_cm')} required />
        </label>
        <label className="field">Starting weight (kg)
          <input type="number" step="0.1" min="35" max="300" value={form.weight_kg} onChange={set('weight_kg')} required />
        </label>
      </div>
      <label className="field" style={{ marginTop: 12 }}>Activity level
        <select value={form.activity_level} onChange={set('activity_level')}>
          {Object.entries(ACTIVITY).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </label>

      <h2 style={{ marginTop: 20 }}>Goal</h2>
      <div className="grid2">
        <label className="field">Goal
          <select value={form.goal} onChange={set('goal')}>
            <option value="cut">Cut (lose fat)</option>
            <option value="maintain">Maintain</option>
            <option value="bulk">Bulk (gain muscle)</option>
          </select>
        </label>
        <label className="field">Rate (% body weight / week)
          <input
            type="number" step="0.05" min="0" max="2"
            placeholder={form.goal === 'cut' ? '0.5 (default)' : form.goal === 'bulk' ? '0.25 (default)' : '—'}
            disabled={form.goal === 'maintain'}
            value={form.goal === 'maintain' ? '' : form.rate_pct}
            onChange={set('rate_pct')}
          />
        </label>
      </div>
      <p className="muted small">Safe limits: max 1%/week loss, 0.5%/week gain. Faster requests are capped.</p>

      <h2 style={{ marginTop: 20 }}>Training</h2>
      <div className="grid2">
        <label className="field">Days per week
          <select value={form.training_days} onChange={set('training_days')}>
            {[2, 3, 4, 5, 6].map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </label>
        <label className="field">Equipment
          <select value={form.equipment} onChange={set('equipment')}>
            <option value="full_gym">Full gym</option>
            <option value="dumbbells">Dumbbells only</option>
            <option value="bodyweight">Bodyweight</option>
          </select>
        </label>
      </div>

      <div className="row" style={{ marginTop: 16 }}>
        <button className="primary" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save profile'}</button>
        {saved && !saving && <span className="muted">Saved</span>}
      </div>
      {error && <div className="error">{error}</div>}
    </form>
  )
}
