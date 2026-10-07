import { useCallback, useEffect, useState } from 'react'
import { CartesianGrid, ComposedChart, Line, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from 'recharts'
import { api, shortDate, todayISO } from '../api'

function WeightTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div className="tooltip">
      <div className="t">{shortDate(p.day)}</div>
      <div>Scale: <b>{p.weight_kg} kg</b></div>
      <div>Trend: <b>{p.trend_kg} kg</b></div>
    </div>
  )
}

export default function WeightView({ onChange }) {
  const [rows, setRows] = useState([])
  const [weight, setWeight] = useState('')
  const [day, setDay] = useState(todayISO())
  const [error, setError] = useState(null)

  const load = useCallback(() => api.weights(90).then(setRows).catch((e) => setError(e.message)), [])
  useEffect(() => { load() }, [load])

  async function submit(e) {
    e.preventDefault()
    setError(null)
    try {
      await api.addWeight(Number(weight), day)
      setWeight('')
      await load()
      onChange?.()
    } catch (err) {
      setError(err.message)
    }
  }

  async function remove(id) {
    await api.deleteWeight(id)
    await load()
    onChange?.()
  }

  const data = rows.map((r) => ({ ...r, t: new Date(r.day).getTime() }))
  const last = rows.at(-1)
  const weekAgo = rows.filter((r) => new Date(r.day) <= new Date(new Date(last?.day).getTime() - 7 * 864e5)).at(-1)
  const weekly = last && weekAgo ? (last.trend_kg - weekAgo.trend_kg).toFixed(2) : null

  return (
    <>
      <section className="card">
        <h2>Log weight</h2>
        <form onSubmit={submit} className="row">
          <input className="grow" type="number" step="0.1" min="30" max="300" placeholder="kg" value={weight} onChange={(e) => setWeight(e.target.value)} required aria-label="Weight in kg" />
          <input type="date" value={day} max={todayISO()} onChange={(e) => setDay(e.target.value)} style={{ width: 'auto' }} aria-label="Date" />
          <button className="primary">Save</button>
        </form>
        <p className="muted small" style={{ marginBottom: 0 }}>Weigh in each morning; the trend smooths out water-weight noise.</p>
        {error && <div className="error">{error}</div>}
      </section>

      <section className="card">
        <div className="hero">
          <span className="big">{last ? last.trend_kg : '—'}</span>
          <span className="muted">kg trend{weekly !== null && ` · ${weekly > 0 ? '+' : ''}${weekly} kg vs last week`}</span>
        </div>
        {data.length > 1 ? (
          <>
            <div className="legend" aria-hidden="true">
              <span><span className="swatch" />Trend (smoothed)</span>
              <span><span className="swatch dot" />Daily weigh-in</span>
            </div>
            <div className="chart" role="img" aria-label="Weight trend chart for the last 90 days">
              <ResponsiveContainer>
                <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke="var(--grid)" vertical={false} />
                  <XAxis dataKey="t" type="number" scale="time" domain={['dataMin', 'dataMax']} tickFormatter={(t) => shortDate(new Date(t).toISOString().slice(0, 10))} tick={{ fill: 'var(--text-3)', fontSize: 11 }} stroke="var(--grid)" tickLine={false} minTickGap={24} />
                  <YAxis domain={['dataMin - 1', 'dataMax + 1']} tick={{ fill: 'var(--text-3)', fontSize: 11 }} tickFormatter={(v) => v.toFixed(0)} axisLine={false} tickLine={false} width={44} />
                  <Tooltip content={<WeightTooltip />} cursor={{ stroke: 'var(--text-3)', strokeDasharray: '3 3' }} />
                  <Scatter dataKey="weight_kg" fill="var(--series-muted)" shape={(p) => <circle cx={p.cx} cy={p.cy} r={3.5} fill="var(--series-muted)" />} isAnimationActive={false} />
                  <Line dataKey="trend_kg" stroke="var(--series-1)" strokeWidth={2} dot={false} activeDot={{ r: 4, stroke: 'var(--surface)', strokeWidth: 2 }} isAnimationActive={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </>
        ) : (
          <p className="muted">Log a couple of weigh-ins to see your trend.</p>
        )}
      </section>

      {rows.length > 0 && (
        <section className="card">
          <h2>Recent weigh-ins</h2>
          <table className="simple">
            <thead><tr><th>Date</th><th>Scale</th><th>Trend</th><th /></tr></thead>
            <tbody>
              {rows.slice(-14).reverse().map((r) => (
                <tr key={r.id}>
                  <td>{shortDate(r.day)}</td>
                  <td>{r.weight_kg} kg</td>
                  <td>{r.trend_kg} kg</td>
                  <td><button className="link" onClick={() => remove(r.id)} aria-label={`Delete weigh-in ${r.day}`}>✕</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </>
  )
}
