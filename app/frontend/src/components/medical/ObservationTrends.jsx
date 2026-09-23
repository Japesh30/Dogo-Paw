import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { SERIES } from '../charts'
import { EmptyState } from './Pills'

const AXIS = '#696764'
const GRID = '#ebe6df'
const TICK = { fill: AXIS, fontSize: 11 }

const shortDate = (value) =>
  new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
  })

function TrendTooltip({ active, payload, label, unit }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-xl border border-[#ebe6df] bg-white px-3 py-2 shadow-lg">
      <p className="text-bark-900 text-xs font-semibold">{label}</p>
      <p className="mt-0.5 text-sm">
        <span className="text-bark-900 font-bold tabular-nums">{payload[0].value}</span> {unit}
      </p>
    </div>
  )
}

/**
 * One measurement over time.
 *
 * `band` shades the range the backend treats as normal for monitoring, when it
 * reported one. The chart never decides that range itself — it draws what the
 * analysis said it used.
 */
function Trend({ points, unit, band }) {
  const values = points.map((p) => p.value)
  const min = Math.min(...values, ...(band ? [band[0]] : []))
  const max = Math.max(...values, ...(band ? [band[1]] : []))
  const pad = Math.max((max - min) * 0.15, unit === 'kg' ? 0.5 : 0.3)

  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart data={points} margin={{ top: 10, right: 12, bottom: 4, left: -16 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        {band && (
          <ReferenceArea
            y1={band[0]}
            y2={band[1]}
            fill="#96a65c"
            fillOpacity={0.12}
            ifOverflow="extendDomain"
          />
        )}
        <XAxis dataKey="label" tick={TICK} tickLine={false} axisLine={{ stroke: GRID }} />
        <YAxis
          tick={TICK}
          tickLine={false}
          axisLine={false}
          width={46}
          domain={[Number((min - pad).toFixed(1)), Number((max + pad).toFixed(1))]}
        />
        <Tooltip content={<TrendTooltip unit={unit} />} cursor={{ stroke: GRID }} />
        <Line
          type="monotone"
          dataKey="value"
          stroke={SERIES}
          strokeWidth={2.5}
          dot={{ r: 3, fill: SERIES }}
          activeDot={{ r: 5 }}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}

/**
 * Weight and temperature over time.
 *
 * Observations arrive newest first and are reversed here so the line reads
 * left to right. A single reading is shown as a value, not a trend — one point
 * is not a direction, which is also how the backend treats it.
 */
export default function ObservationTrends({ observations, analysis }) {
  const rows = [...(observations ?? [])].reverse()
  const weight = rows
    .filter((o) => o.weight_kg != null)
    .map((o) => ({ label: shortDate(o.observation_date), value: o.weight_kg }))
  const temperature = rows
    .filter((o) => o.temperature_c != null)
    .map((o) => ({ label: shortDate(o.observation_date), value: o.temperature_c }))

  const monitoring = analysis?.data_quality?.temperature_series?.monitoring_range_c
  const weightSeries = analysis?.data_quality?.weight_series

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div>
        <h3 className="text-bark-900 text-sm font-semibold">Weight (kg)</h3>
        {weight.length >= 2 ? (
          <>
            <div className="mt-2">
              <Trend points={weight} unit="kg" />
            </div>
            {weightSeries?.percent_change != null && (
              <p className="text-stone-neutral mt-1 text-xs">
                {weightSeries.first_weight_kg} kg → {weightSeries.latest_weight_kg} kg,{' '}
                {weightSeries.percent_change > 0 ? '+' : ''}
                {weightSeries.percent_change}% over {weightSeries.period_days} days
                {' · '}
                {weightSeries.observation_count} observations
              </p>
            )}
          </>
        ) : (
          <div className="mt-2">
            <EmptyState>
              {weight.length === 1
                ? `One weight recorded (${weight[0].value} kg). At least two are needed to show a trend.`
                : 'No weight recorded yet.'}
            </EmptyState>
          </div>
        )}
      </div>

      <div>
        <h3 className="text-bark-900 text-sm font-semibold">Temperature (°C)</h3>
        {temperature.length >= 2 ? (
          <>
            <div className="mt-2">
              <Trend points={temperature} unit="°C" band={monitoring} />
            </div>
            {monitoring && (
              <p className="text-stone-neutral mt-1 text-xs">
                Shaded band is the monitoring range the analysis used ({monitoring[0]}–
                {monitoring[1]} °C). It is a threshold for review, not a clinical range.
              </p>
            )}
          </>
        ) : (
          <div className="mt-2">
            <EmptyState>
              {temperature.length === 1
                ? `One reading recorded (${temperature[0].value} °C). At least two are needed to compare over time.`
                : 'No temperature recorded yet.'}
            </EmptyState>
          </div>
        )}
      </div>
    </div>
  )
}
