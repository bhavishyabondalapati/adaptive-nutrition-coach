import { useCallback, useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, shortDate } from '../api'

function IntakeTooltip({ active, payload, target }) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div className="tooltip">
      <div className="t">{shortDate(p.day)}</div>
      {p.kcal == null ? <div>Not logged</div> : (
        <>
          <div><b>{p.kcal} kcal</b>{target ? ` (${p.kcal - target >= 0 ? '+' : ''}${p.kcal - target} vs target)` : ''}</div>
          <div>P {p.protein_g} g · C {p.carbs_g} g · F {p.fat_g} g</div>
        </>
      )}
    </div>
  )
}

export default function Trends({ targets, onCheckin }) {
  const [intake, setIntake] = useState([])
  const [checkins, setCheckins] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    try {
      const [i, c] = await Promise.all([api.intake(30), api.checkins()])
      setIntake(i)
      setCheckins(c)
    } catch (e) {
      setError(e.message)
    }
  }, [])
  useEffect(() => { load() }, [load])

  async function runNow() {
    setBusy(true)
    try {
      await api.runCheckin(true)
      await load()
      onCheckin?.()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const target = targets?.targets.calories
  const logged = intake.filter((d) => d.kcal != null)
  const avg = logged.length ? Math.round(logged.reduce((s, d) => s + d.kcal, 0) / logged.length) : null

  return (
    <>
      <section className="card">
        <h2>Calories, last 30 days</h2>
        <div className="hero" style={{ marginBottom: 8 }}>
          <span className="big">{avg ?? '—'}</span>
          <span className="muted">kcal/day average · {logged.length} days logged</span>
        </div>
        <div className="legend" aria-hidden="true">
          <span><span className="swatch bar" />Daily intake</span>
          {target && <span><span className="swatch dash" />Target ({target})</span>}
        </div>
        <div className="chart" role="img" aria-label="Daily calorie intake bar chart with target line">
          <ResponsiveContainer>
            <BarChart data={intake} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barCategoryGap={2}>
              <CartesianGrid stroke="var(--grid)" vertical={false} />
              <XAxis dataKey="day" tickFormatter={shortDate} tick={{ fill: 'var(--text-3)', fontSize: 11 }} stroke="var(--grid)" tickLine={false} minTickGap={24} />
              <YAxis tick={{ fill: 'var(--text-3)', fontSize: 11 }} axisLine={false} tickLine={false} width={44} />
              <Tooltip content={<IntakeTooltip target={target} />} cursor={{ fill: 'var(--surface-2)' }} />
              <Bar dataKey="kcal" fill="var(--series-1)" radius={[4, 4, 0, 0]} maxBarSize={18} isAnimationActive={false} />
              {target && <ReferenceLine y={target} stroke="var(--text-3)" strokeDasharray="4 3" />}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="card">
        <div className="row" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
          <h2 style={{ margin: 0 }}>Weekly check-ins</h2>
          <button onClick={runNow} disabled={busy}>{busy ? 'Running…' : 'Run now'}</button>
        </div>
        <p className="muted small">
          Each week the app compares what you ate with how your weight trend moved to estimate what you really burn,
          then nudges your targets (max ±200 kcal per week).
        </p>
        {checkins.length === 0 ? <p className="muted">No check-ins yet.</p> : (
          <div className="table-scroll">
            <table className="simple">
              <thead>
                <tr><th>Date</th><th>Formula</th><th>Estimate</th><th>Using</th><th>Target</th><th>Trend/wk</th></tr>
              </thead>
              <tbody>
                {checkins.map((c) => (
                  <tr key={c.id}>
                    <td>{shortDate(c.day)}</td>
                    <td>{c.formula_tdee}</td>
                    <td>{c.raw_estimate ?? "—"}{c.status === "ok" && c.confidence < 1 && <span className="muted"> ({Math.round(c.confidence * 100)}%)</span>}</td>
                    <td><b>{c.used_tdee}</b></td>
                    <td>{c.calories}</td>
                    <td>{c.trend_kg_per_week != null ? `${c.trend_kg_per_week > 0 ? '+' : ''}${c.trend_kg_per_week.toFixed(2)}` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {checkins[0]?.warnings.map((w) => <div key={w} className="warning">{w}</div>)}
        {error && <div className="error">{error}</div>}
      </section>
    </>
  )
}
