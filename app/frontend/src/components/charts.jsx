import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

/**
 * Both dashboard charts are single-series, so there is no categorical palette
 * and no legend — the card title says what is plotted. SERIES is a darker step
 * of the brand olive: the raw #96A65C only reaches 2.6:1 against the card
 * surface, which is below the 3:1 a chart mark needs.
 */
export const SERIES = '#6f8a2e'
export const SERIES_MUTED = '#c7d3a8'

const AXIS = '#696764'
const GRID = '#ebe6df'
const TICK = { fill: AXIS, fontSize: 12 }

function ChartTooltip({ active, payload, label, unit }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-xl border border-[#ebe6df] bg-white px-3 py-2 shadow-lg">
      <p className="text-bark-900 text-xs font-semibold">{label}</p>
      <p className="mt-0.5 text-sm">
        <span
          className="mr-1.5 inline-block h-2.5 w-2.5 rounded-full align-middle"
          style={{ background: SERIES }}
        />
        <span className="text-bark-900 font-bold tabular-nums">
          {payload[0].value}
        </span>{' '}
        {unit}
      </p>
    </div>
  )
}

/** Match requests per day over the last 7 days. */
export function ActivityChart({ data }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 16, right: 8, bottom: 4, left: -20 }}>
        <CartesianGrid stroke={GRID} strokeWidth={1} vertical={false} />
        <XAxis
          dataKey="label"
          tick={TICK}
          tickLine={false}
          axisLine={{ stroke: GRID }}
        />
        <YAxis
          tick={TICK}
          tickLine={false}
          axisLine={false}
          allowDecimals={false}
          width={40}
        />
        <Tooltip
          cursor={{ fill: 'rgba(111,138,46,0.07)' }}
          content={<ChartTooltip unit="match requests" />}
        />
        <Bar
          dataKey="requests"
          fill={SERIES}
          radius={[4, 4, 0, 0]}
          maxBarSize={24}
          isAnimationActive={false}
        />
      </BarChart>
    </ResponsiveContainer>
  )
}

/**
 * How often each dog came out top. Horizontal bars because the categories are
 * names; the value rides the bar tip so the numbers are readable without the
 * tooltip.
 */
export function TopDogsChart({ data }) {
  return (
    <ResponsiveContainer width="100%" height={Math.max(180, data.length * 46)}>
      <BarChart
        data={data}
        layout="vertical"
        margin={{ top: 4, right: 32, bottom: 4, left: 4 }}
      >
        <CartesianGrid stroke={GRID} strokeWidth={1} horizontal={false} />
        <XAxis
          type="number"
          tick={TICK}
          tickLine={false}
          axisLine={{ stroke: GRID }}
          allowDecimals={false}
          // Without this Recharts pads the domain and the bars use half the card.
          domain={[0, 'dataMax']}
        />
        <YAxis
          type="category"
          dataKey="name"
          tick={TICK}
          tickLine={false}
          axisLine={false}
          width={72}
        />
        <Tooltip
          cursor={{ fill: 'rgba(111,138,46,0.07)' }}
          content={<ChartTooltip unit="times ranked #1" />}
        />
        <Bar
          dataKey="wins"
          radius={[0, 4, 4, 0]}
          maxBarSize={24}
          isAnimationActive={false}
        >
          {/* One series, one colour — the bar length already encodes magnitude. */}
          {data.map((d) => (
            <Cell key={d.name} fill={SERIES} />
          ))}
          <LabelList
            dataKey="wins"
            position="right"
            offset={8}
            style={{ fill: AXIS, fontSize: 12, fontWeight: 600 }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

/**
 * Adopter segments. Still one series — "how many adopters" — measured across
 * nominal categories, so every bar keeps the same colour. Colouring each
 * segment differently would double-encode the bar length as hue and spend the
 * only free channel on information the length already shows.
 */
export function SegmentChart({ data }) {
  return (
    <ResponsiveContainer width="100%" height={Math.max(160, data.length * 56)}>
      <BarChart
        data={data}
        layout="vertical"
        margin={{ top: 4, right: 40, bottom: 4, left: 4 }}
      >
        <CartesianGrid stroke={GRID} strokeWidth={1} horizontal={false} />
        <XAxis
          type="number"
          tick={TICK}
          tickLine={false}
          axisLine={{ stroke: GRID }}
          allowDecimals={false}
          domain={[0, 'dataMax']}
        />
        <YAxis
          type="category"
          dataKey="short"
          tick={TICK}
          tickLine={false}
          axisLine={false}
          width={132}
        />
        <Tooltip
          cursor={{ fill: 'rgba(111,138,46,0.07)' }}
          content={<ChartTooltip unit="adopters" />}
        />
        <Bar
          dataKey="count"
          fill={SERIES}
          radius={[0, 4, 4, 0]}
          maxBarSize={24}
          isAnimationActive={false}
        >
          <LabelList
            dataKey="share"
            position="right"
            offset={8}
            formatter={(v) => `${v}%`}
            style={{ fill: AXIS, fontSize: 12, fontWeight: 600 }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

/** 12-point sparkline for the stat tiles. */
export function Sparkline({ data, dataKey = 'requests' }) {
  return (
    <ResponsiveContainer width="100%" height={36}>
      <BarChart data={data} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
        <Bar
          dataKey={dataKey}
          radius={[2, 2, 0, 0]}
          maxBarSize={8}
          isAnimationActive={false}
        >
          {data.map((d, i) => (
            <Cell
              key={d.date}
              fill={i === data.length - 1 ? SERIES : SERIES_MUTED}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
