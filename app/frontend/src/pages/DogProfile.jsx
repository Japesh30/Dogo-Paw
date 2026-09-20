import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import DogPhoto from '../components/DogPhoto'
import DemoDataNotice from '../components/DemoDataNotice'
import Spinner from '../components/Spinner'
import { api } from '../lib/api'
import { ENERGY_TONE, SIZE_HINT, formatAge, titleCase } from '../lib/dogs'
import { readMatchSession, scoreForDog } from '../lib/matchSession'

const HOME_TYPE_LABEL = {
  apartment: 'an apartment',
  house_no_yard: 'a house without a yard',
  house_with_yard: 'a house with a yard',
}

export default function DogProfile() {
  const { dogId } = useParams()
  const [dog, setDog] = useState(null)
  const [state, setState] = useState('loading') // loading | ready | error
  const [message, setMessage] = useState('')

  // Whatever /adopt-match already worked out for this dog, if the visitor has
  // been through the questionnaire in this tab. No request, and no MatchRequest
  // row written just because someone opened a profile page.
  const match = scoreForDog(Number(dogId))

  useEffect(() => {
    let cancelled = false
    setState('loading')
    api
      .dog(dogId)
      .then((data) => {
        if (cancelled) return
        setDog(data.dog)
        setState('ready')
      })
      .catch((err) => {
        if (cancelled) return
        setMessage(err.message)
        setState('error')
      })
    return () => {
      cancelled = true
    }
  }, [dogId])

  if (state === 'loading') {
    return (
      <div className="shell grid place-items-center py-32">
        <Spinner label="Fetching this dog's profile…" />
      </div>
    )
  }

  if (state === 'error') {
    return (
      <div className="shell py-24 text-center">
        <h1 className="text-3xl">We could not load that dog</h1>
        <p className="mx-auto mt-4 max-w-md text-sm">{message}</p>
        <Link to="/dogs" className="btn-primary mt-8">
          Back to all dogs
        </Link>
      </div>
    )
  }

  const attributes = [
    { label: 'Age', value: `${formatAge(dog.age)} old` },
    { label: 'Size', value: `${titleCase(dog.size)} — ${SIZE_HINT[dog.size]}` },
    { label: 'Energy level', value: titleCase(dog.energy_level) },
    { label: 'Temperament', value: titleCase(dog.temperament) },
    {
      label: 'Good with children',
      value: dog.good_with_kids ? 'Yes' : 'Not currently placed with children',
      warn: !dog.good_with_kids,
    },
    {
      label: 'Good with other pets',
      value: dog.good_with_other_pets
        ? 'Yes'
        : 'Does better as the only pet',
      warn: !dog.good_with_other_pets,
    },
    {
      label: 'Medical needs',
      value: dog.medical_needs
        ? 'Ongoing — needs regular medication and check-ups'
        : 'None',
      warn: dog.medical_needs,
    },
  ]

  return (
    <>
      {/* ---------------- Breadcrumb ---------------- */}
      <nav aria-label="Breadcrumb" className="shell pt-8">
        <ol className="flex flex-wrap items-center gap-2 text-sm">
          <li>
            <Link
              to="/dogs"
              className="hover:text-olive-600 -mx-2 inline-block rounded-lg px-2 py-1.5 font-medium"
            >
              Our dogs
            </Link>
          </li>
          <li aria-hidden="true">/</li>
          <li className="text-bark-900 font-semibold">{dog.name}</li>
        </ol>
      </nav>

      <section className="pt-6 pb-14 sm:pb-20">
        <div className="shell grid gap-10 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] lg:items-start lg:gap-14">
          {/* ---------------- Photo + actions ----------------
              Sticky from lg, because the details column is much taller than
              the photo: without it the left half of the page is empty for most
              of the scroll, and the "call us" button scrolls away just as
              someone finishes reading and decides they want it. */}
          <div className="lg:sticky lg:top-24 lg:self-start">
            <DogPhoto
              dog={dog}
              eager
              className="rounded-card shadow-soft aspect-[4/3] w-full"
              sizes="(min-width: 1024px) 34rem, 92vw"
            />

            {/* Stacked layouts read top to bottom, so on a phone the actions
                belong after the story, not between the photo and the name.
                Rendered in both columns, only ever visible in one. */}
            <Actions dog={dog} className="mt-5 hidden lg:block" />
          </div>

          {/* ---------------- Details ---------------- */}
          <div>
            {/* Before the name, not after: this is the page most likely to be
                shared or bookmarked as "here is the dog I want", and the
                Actions block below invites a phone call about it. */}
            <DemoDataNotice className="mb-7" />

            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-4xl sm:text-5xl">{dog.name}</h1>
              <span
                className={`rounded-full px-3 py-1 text-xs font-semibold ${ENERGY_TONE[dog.energy_level]}`}
              >
                {titleCase(dog.energy_level)} energy
              </span>
            </div>

            <p className="mt-2 text-base">
              {formatAge(dog.age)} old · {titleCase(dog.size)} ·{' '}
              {titleCase(dog.temperament)}
            </p>

            {dog.bio && (
              <p className="text-bark-700 mt-6 text-base leading-relaxed">
                {dog.bio}
              </p>
            )}

            {/* Match panel, or the invitation to create one */}
            {match ? (
              <MatchPanel dog={dog} match={match} />
            ) : (
              <div className="border-olive-200 bg-olive-50 mt-8 rounded-2xl border-2 p-5 sm:p-6">
                <h2 className="text-lg">Not sure yet?</h2>
                <p className="mt-2 text-sm leading-relaxed">
                  Take the matching quiz — five questions about your home and
                  lifestyle — and we will show you how well {dog.name} fits, and
                  where you would rank {dog.name} against the other 17 dogs.
                </p>
                <Link to="/adopt-match" className="btn-primary mt-5">
                  Check my match score
                </Link>
              </div>
            )}

            {/* ---------------- Attributes ---------------- */}
            <h2 className="mt-10 text-xl">About {dog.name}</h2>
            <dl className="border-bark-100 mt-4 divide-y divide-[color:var(--color-bark-100)] border-t border-b">
              {attributes.map((a) => (
                <div
                  key={a.label}
                  className="flex flex-col gap-1 py-3 sm:flex-row sm:items-baseline sm:justify-between sm:gap-6"
                >
                  <dt className="text-bark-900 text-sm font-semibold">
                    {a.label}
                  </dt>
                  <dd
                    className={`text-sm sm:text-right ${a.warn ? 'text-rust font-medium' : ''}`}
                  >
                    {a.value}
                  </dd>
                </div>
              ))}
            </dl>

            <Actions dog={dog} className="mt-8 lg:hidden" />
          </div>
        </div>
      </section>
    </>
  )
}

function Actions({ dog, className = '' }) {
  return (
    <div className={className}>
      <div className="flex flex-col gap-3 sm:flex-row">
        <a href="tel:+917015596198" className="btn-accent flex-1">
          Call about {dog.name}
        </a>
        <Link
          to="/dogs"
          className="btn border-bark-100 text-stone-neutral hover:border-olive-500 hover:text-olive-600 border-2"
        >
          ← All dogs
        </Link>
      </div>
      <p className="text-stone-neutral mt-3 text-xs leading-relaxed">
        Every adoption starts with a meeting at the dog's foster home, followed
        by a home visit.
      </p>
    </div>
  )
}

/**
 * The scores this visitor already received for this dog. Both numbers come from
 * the /adopt-match response they have already seen, so they cannot disagree
 * with the results page.
 */
function MatchPanel({ dog, match }) {
  const summary = adopterSummary()
  const strong = match.score >= 75
  // The stored object is the API's match verbatim, so the explanation lives
  // under `breakdown` — the same shape MatchCard renders on the results page.
  const { penalties = [], reasons = [], concerns = [] } = match.breakdown ?? {}

  return (
    <div className="border-olive-200 mt-8 rounded-2xl border-2 bg-white p-5 sm:p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="eyebrow">Your match</p>
          <h2 className="mt-1 text-lg">
            {strong
              ? `${dog.name} is a strong match for you`
              : `How ${dog.name} scored against your profile`}
          </h2>
        </div>
        <span
          className={`text-3xl font-extrabold ${strong ? 'text-olive-700' : 'text-amber-brand-dark'}`}
        >
          {match.score}%
        </span>
      </div>

      <div
        className="bg-bark-100 mt-4 h-2.5 overflow-hidden rounded-full"
        role="meter"
        aria-valuenow={match.score}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Compatibility score for ${dog.name}`}
      >
        <div
          className={`h-full rounded-full ${strong ? 'bg-olive-500' : 'bg-amber-brand'}`}
          style={{ width: `${match.score}%` }}
        />
      </div>

      {match.success_probability != null && (
        <p className="mt-3 text-sm">
          Predicted adoption success:{' '}
          <strong className="text-bark-900">
            {match.success_probability}%
          </strong>{' '}
          <span className="text-xs">
            (a separate model from the compatibility score)
          </span>
        </p>
      )}

      {penalties.length > 0 && (
        <div className="bg-rust/10 mt-4 rounded-xl p-3">
          {penalties.map((p) => (
            <p key={p.rule} className="text-rust text-sm font-medium">
              {p.message}{' '}
              <span className="font-normal opacity-80">
                (score × {p.multiplier})
              </span>
            </p>
          ))}
        </div>
      )}

      {(reasons.length > 0 || concerns.length > 0) && (
        <ul className="mt-4 space-y-1.5">
          {reasons.map((r) => (
            <li key={r} className="flex gap-2 text-sm">
              <span className="text-olive-500 shrink-0" aria-hidden="true">
                ✓
              </span>
              {r}
            </li>
          ))}
          {concerns.map((c) => (
            <li key={c} className="flex gap-2 text-sm">
              <span
                className="text-amber-brand-dark shrink-0"
                aria-hidden="true"
              >
                !
              </span>
              {c}
            </li>
          ))}
        </ul>
      )}

      {summary && (
        <p className="text-stone-neutral mt-4 text-xs">
          Based on the profile you gave us: {summary}.
        </p>
      )}

      <Link
        to="/adopt-match"
        className="text-olive-600 hover:text-olive-700 mt-5 inline-block text-sm font-semibold underline underline-offset-2"
      >
        See all 18 dogs ranked →
      </Link>
    </div>
  )
}

/** One sentence describing the stored questionnaire answers. */
function adopterSummary() {
  const adopter = readMatchSession()?.adopter
  if (!adopter) return null

  const parts = [
    `${adopter.activity_level} activity`,
    HOME_TYPE_LABEL[adopter.home_type] ?? adopter.home_type,
    `${adopter.experience_level === 'none' ? 'no' : adopter.experience_level} experience with dogs`,
  ]
  if (adopter.has_kids) parts.push('children at home')
  if (adopter.has_other_pets) parts.push('other pets')
  return parts.join(', ')
}
