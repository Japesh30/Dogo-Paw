import { Link } from 'react-router-dom'
import DogPhoto from './DogPhoto'
import { formatAge, titleCase } from '../lib/dogs'

const scoreTone = (score) => {
  if (score >= 75) return { label: 'Strong match', bar: 'bg-olive-500', text: 'text-olive-700' }
  if (score >= 50) return { label: 'Worth meeting', bar: 'bg-amber-brand', text: 'text-amber-brand-dark' }
  return { label: 'Not recommended', bar: 'bg-rust', text: 'text-rust' }
}

export default function MatchCard({ match, rank }) {
  const { score, breakdown, success_probability: successProbability } = match
  const tone = scoreTone(score)
  const profile = `/dogs/${match.dog_id}`

  return (
    <article className="card hover:shadow-lift flex flex-col overflow-hidden transition-shadow">
      <Link to={profile} className="group relative block" tabIndex={-1} aria-hidden="true">
        <DogPhoto dog={match} className="h-44 w-full" />
        {rank <= 3 && (
          <span className="bg-bark-900 absolute top-3 left-3 rounded-full px-3 py-1 text-xs font-bold text-white">
            #{rank} match
          </span>
        )}
      </Link>

      <div className="flex flex-1 flex-col p-6">
        <div className="flex items-baseline justify-between gap-3">
          <h3 className="text-xl">
            {/* The card's one real link — the photo above repeats it purely as
                an affordance, so it is hidden from assistive tech. */}
            <Link
              to={profile}
              className="hover:text-olive-600 hover:underline underline-offset-4"
            >
              {match.name}
            </Link>
          </h3>
          <span className={`text-2xl font-extrabold ${tone.text}`}>
            {score}%
          </span>
        </div>

        <p className="mt-1 text-sm">
          {formatAge(match.age)} old · {titleCase(match.size)} ·{' '}
          {titleCase(match.temperament)}
        </p>

        {/* Compatibility bar */}
        <div className="mt-4">
          <div className="flex items-center justify-between text-xs font-semibold">
            <span className={tone.text}>{tone.label}</span>
            <span className="text-stone-neutral">Compatibility</span>
          </div>
          <div
            className="bg-bark-100 mt-1.5 h-2.5 overflow-hidden rounded-full"
            role="meter"
            aria-valuenow={score}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Compatibility score for ${match.name}`}
          >
            <div
              className={`h-full rounded-full transition-[width] duration-700 ${tone.bar}`}
              style={{ width: `${score}%` }}
            />
          </div>
        </div>

        {/* Predicted adoption success — a separate model from the score above,
            so it is labelled as a prediction rather than a second score. */}
        {successProbability != null && (
          <div className="mt-3">
            <div className="flex items-center justify-between text-xs font-semibold">
              <span className="text-bark-900">{successProbability}%</span>
              <span className="text-stone-neutral">
                Predicted adoption success
              </span>
            </div>
            <div
              className="bg-bark-100 mt-1.5 h-2 overflow-hidden rounded-full"
              role="meter"
              aria-valuenow={successProbability}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label={`Predicted adoption success for ${match.name}`}
            >
              <div
                className="bg-bark-700 h-full rounded-full transition-[width] duration-700"
                style={{ width: `${successProbability}%` }}
              />
            </div>
          </div>
        )}

        {/* Why this match */}
        <div className="mt-5 flex-1">
          <p className="text-bark-900 text-xs font-bold tracking-wider uppercase">
            Why this match
          </p>
          <ul className="mt-2 space-y-1.5">
            {breakdown.reasons.map((r) => (
              <li key={r} className="flex gap-2 text-sm">
                <span className="text-olive-500 mt-0.5 shrink-0" aria-hidden="true">
                  ✓
                </span>
                {r}
              </li>
            ))}
            {breakdown.concerns.map((c) => (
              <li key={c} className="flex gap-2 text-sm">
                <span className="text-amber-brand-dark mt-0.5 shrink-0" aria-hidden="true">
                  !
                </span>
                {c}
              </li>
            ))}
            {breakdown.reasons.length === 0 && breakdown.concerns.length === 0 && (
              <li className="text-sm">A reasonable fit on every axis.</li>
            )}
          </ul>
        </div>

        {/* Penalties spelled out — these are safety rules, not preferences */}
        {breakdown.penalties.length > 0 && (
          <div className="bg-rust/10 mt-4 rounded-xl p-3">
            {breakdown.penalties.map((p) => (
              <p key={p.rule} className="text-rust text-sm font-medium">
                {p.message}{' '}
                <span className="font-normal opacity-80">
                  (score × {p.multiplier})
                </span>
              </p>
            ))}
          </div>
        )}

        <details className="group mt-4">
          <summary className="text-stone-neutral hover:text-olive-600 cursor-pointer list-none text-xs font-semibold">
            <span className="group-open:hidden">Show score breakdown ▾</span>
            <span className="hidden group-open:inline">Hide score breakdown ▴</span>
          </summary>
          <dl className="border-bark-100 mt-3 space-y-1.5 border-t pt-3 text-xs">
            <Row label="Base score (before rules)" value={`${breakdown.base_score}%`} />
            <Row
              label="Profile distance"
              value={`${breakdown.distance} / ${breakdown.max_distance}`}
            />
            <Row label="Energy gap" value={breakdown.axis_gaps.energy} />
            <Row label="Space gap" value={breakdown.axis_gaps.space} />
            <Row label="Experience gap" value={breakdown.axis_gaps.experience} />
            <Row
              label="Good with kids / pets"
              value={`${match.good_with_kids ? 'yes' : 'no'} / ${match.good_with_other_pets ? 'yes' : 'no'}`}
            />
            {successProbability != null && (
              <Row
                label="Success model (logistic regression)"
                value={`${successProbability}%`}
              />
            )}
          </dl>
        </details>
      </div>
    </article>
  )
}

function Row({ label, value }) {
  return (
    <div className="flex justify-between gap-4">
      <dt>{label}</dt>
      <dd className="text-bark-900 font-mono font-semibold">{value}</dd>
    </div>
  )
}
