import { useRef, useState } from 'react'
import PageHeader from '../components/PageHeader'
import MatchCard from '../components/MatchCard'
import DemoDataNotice from '../components/DemoDataNotice'
import Spinner from '../components/Spinner'
import { api } from '../lib/api'
import { fosterPhotos } from '../assets/images'
import {
  clearMatchSession,
  readMatchSession,
  saveMatchSession,
} from '../lib/matchSession'

const QUESTIONS = [
  {
    name: 'activity_level',
    label: 'How active is your household?',
    help: 'Think about walks, runs and play on an average day — not your best week.',
    options: [
      { value: 'low', label: 'Low', hint: 'Short walks, a quiet routine' },
      { value: 'medium', label: 'Medium', hint: 'A daily walk and some play' },
      { value: 'high', label: 'High', hint: 'Long walks, running, hiking' },
    ],
  },
  {
    name: 'home_type',
    label: 'What kind of home do you have?',
    help: 'This sets how much space we assume a dog would have.',
    options: [
      { value: 'apartment', label: 'Apartment', hint: 'No private outdoor space' },
      { value: 'house_no_yard', label: 'House, no yard', hint: 'More room indoors' },
      { value: 'house_with_yard', label: 'House with yard', hint: 'Secure outdoor space' },
    ],
  },
  {
    name: 'experience_level',
    label: 'How much experience do you have with dogs?',
    help: 'Nervous, stubborn and protective dogs need a more practised handler.',
    options: [
      { value: 'none', label: 'None', hint: 'This would be my first dog' },
      { value: 'some', label: 'Some', hint: 'I have lived with a dog before' },
      { value: 'experienced', label: 'Experienced', hint: 'I have trained or handled several' },
    ],
  },
]

const YES_NO = [
  {
    name: 'has_kids',
    label: 'Are there children in the home?',
    help: 'Dogs not cleared for children are heavily down-ranked, never hidden.',
  },
  {
    name: 'has_other_pets',
    label: 'Do you already have other pets?',
    help: 'Same rule — we down-rank dogs who do better as an only pet.',
  },
]

const INITIAL = {
  activity_level: '',
  home_type: '',
  experience_level: '',
  has_kids: null,
  has_other_pets: null,
}

/**
 * Anything already stored for this tab, so someone who walked off to a dog's
 * profile page and came back finds their results still here rather than an
 * empty form. Restored from storage, never re-requested — asking the server
 * again would log a second MatchRequest for one questionnaire.
 */
const restore = () => {
  const session = readMatchSession()
  if (!session) return null
  const { id: _id, ...answers } = session.adopter
  return { answers, result: { ...session, matches: session.matches } }
}

export default function AdoptMatch() {
  const [restored] = useState(restore)
  const [answers, setAnswers] = useState(restored?.answers ?? INITIAL)
  const [errors, setErrors] = useState({})
  const [state, setState] = useState(restored ? 'done' : 'idle') // idle | loading | done | error
  const [result, setResult] = useState(restored?.result ?? null)
  const [message, setMessage] = useState('')
  const resultsRef = useRef(null)

  const set = (name, value) => {
    setAnswers((a) => ({ ...a, [name]: value }))
    setErrors((prev) => {
      if (!prev[name]) return prev
      const { [name]: _removed, ...rest } = prev
      return rest
    })
  }

  const onSubmit = async (e) => {
    e.preventDefault()

    const missing = {}
    for (const q of QUESTIONS) if (!answers[q.name]) missing[q.name] = 'Pick one.'
    for (const q of YES_NO) if (answers[q.name] === null) missing[q.name] = 'Pick one.'
    setErrors(missing)
    if (Object.keys(missing).length) return

    setState('loading')
    setMessage('')
    try {
      const data = await api.recommend(answers)
      setResult(data)
      setState('done')
      // Kept for the gallery badges and each dog's profile page, so neither has
      // to ask the server again — see lib/matchSession.js.
      saveMatchSession(data)
      requestAnimationFrame(() =>
        resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }),
      )
    } catch (err) {
      setMessage(err.message)
      setState('error')
    }
  }

  const reset = () => {
    setAnswers(INITIAL)
    setErrors({})
    setResult(null)
    setState('idle')
    clearMatchSession()
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const strong = result?.matches.filter((m) => m.score >= 75).length ?? 0

  return (
    <>
      <PageHeader
        eyebrow="AI adoption matching"
        title="Answer five questions. Meet your shortlist."
        subtitle="Our matching engine scores every dog currently in foster care against your lifestyle, your home and your experience — and shows you exactly why each one ranked where it did."
        image={fosterPhotos[3].src}
      />

      {/* ---------------- How it works ---------------- */}
      <section className="bg-white py-12 sm:py-16">
        <div className="shell grid gap-8 sm:grid-cols-3">
          {[
            {
              n: '1',
              t: 'You describe your home',
              d: 'Activity level, living space, experience, children and existing pets.',
            },
            {
              n: '2',
              t: 'We compare profiles',
              d: 'Both you and each dog become a point in the same energy / space / experience space. Closer means a better fit.',
            },
            {
              n: '3',
              t: 'Safety rules apply',
              d: 'Dogs not cleared for children or other pets are penalised, and we tell you when that happened.',
            },
          ].map((s) => (
            <div key={s.n} className="flex gap-4">
              <span className="bg-olive-500 grid h-10 w-10 shrink-0 place-items-center rounded-full font-bold text-white">
                {s.n}
              </span>
              <div>
                <h3 className="text-lg">{s.t}</h3>
                <p className="mt-1 text-sm leading-relaxed">{s.d}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ---------------- Questionnaire ---------------- */}
      <section className="py-14 sm:py-16">
        <div className="shell max-w-3xl">
          <form onSubmit={onSubmit} noValidate className="card p-6 sm:p-9">
            <h2 className="text-2xl sm:text-3xl">Your adopter profile</h2>
            <p className="mt-2 text-sm">
              Nothing here is binding — it just tells the engine what to look
              for.
            </p>

            <div className="mt-8 space-y-9">
              {QUESTIONS.map((q) => (
                <fieldset key={q.name}>
                  <legend className="text-bark-900 text-base font-semibold">
                    {q.label}
                  </legend>
                  <p className="mt-1 text-sm">{q.help}</p>
                  <div className="mt-4 grid gap-3 sm:grid-cols-3">
                    {q.options.map((o) => (
                      <Choice
                        key={o.value}
                        name={q.name}
                        value={o.value}
                        checked={answers[q.name] === o.value}
                        onChange={() => set(q.name, o.value)}
                        label={o.label}
                        hint={o.hint}
                      />
                    ))}
                  </div>
                  <FieldError error={errors[q.name]} />
                </fieldset>
              ))}

              {YES_NO.map((q) => (
                <fieldset key={q.name}>
                  <legend className="text-bark-900 text-base font-semibold">
                    {q.label}
                  </legend>
                  <p className="mt-1 text-sm">{q.help}</p>
                  <div className="mt-4 grid max-w-sm grid-cols-2 gap-3">
                    {[
                      [true, 'Yes'],
                      [false, 'No'],
                    ].map(([value, label]) => (
                      <Choice
                        key={label}
                        name={q.name}
                        value={String(value)}
                        checked={answers[q.name] === value}
                        onChange={() => set(q.name, value)}
                        label={label}
                      />
                    ))}
                  </div>
                  <FieldError error={errors[q.name]} />
                </fieldset>
              ))}
            </div>

            {state === 'error' && (
              <p
                role="alert"
                className="bg-rust/10 text-rust mt-8 rounded-xl px-4 py-3 text-sm font-medium"
              >
                {message}
              </p>
            )}

            <div className="mt-9 flex flex-col gap-3 sm:flex-row">
              <button
                type="submit"
                disabled={state === 'loading'}
                className="btn-primary flex-1 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {state === 'loading' ? 'Scoring 18 dogs…' : 'Find my matches'}
              </button>
              {result && (
                <button
                  type="button"
                  onClick={reset}
                  className="btn border-bark-100 text-stone-neutral hover:border-olive-500 hover:text-olive-600 border-2"
                >
                  Start over
                </button>
              )}
            </div>
          </form>
        </div>
      </section>

      {/* ---------------- Results ---------------- */}
      <section ref={resultsRef} className="scroll-mt-24">
        {state === 'loading' && (
          <div className="shell grid place-items-center py-20">
            <Spinner label="Comparing you against every dog in foster care…" />
          </div>
        )}

        {state === 'done' && result && (
          <div className="bg-white py-14 sm:py-20">
            <div className="shell">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
                <div>
                  <p className="eyebrow">Your results</p>
                  <h2 className="mt-3 text-3xl sm:text-4xl">
                    {strong > 0
                      ? `${strong} strong ${strong === 1 ? 'match' : 'matches'} for you`
                      : 'Here is how every dog scored'}
                  </h2>
                </div>
                <p className="max-w-sm text-sm">
                  All {result.count} dogs are shown, ranked best first. Nothing
                  is hidden — a low score is information too.
                </p>
              </div>

              <DemoDataNotice className="mt-8" />

              <div className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
                {result.matches.map((m, i) => (
                  <MatchCard key={m.dog_id} match={m} rank={i + 1} />
                ))}
              </div>

              <div className="bg-bark-50 rounded-card mt-12 p-6 text-center sm:p-8">
                <h3 className="text-xl">Found one you would like to meet?</h3>
                <p className="mx-auto mt-2 max-w-lg text-sm">
                  Call us and we will arrange an introduction with the dog's
                  foster family. A home visit follows before any adoption is
                  finalised.
                </p>
                <a href="tel:+917015596198" className="btn-primary mt-6">
                  Call +91 70155 96198
                </a>
              </div>
            </div>
          </div>
        )}
      </section>
    </>
  )
}

function Choice({ name, value, checked, onChange, label, hint }) {
  return (
    <label
      className={`block cursor-pointer rounded-2xl border-2 p-4 transition ${
        checked
          ? 'border-olive-500 bg-olive-50'
          : 'border-bark-100 hover:border-olive-300'
      }`}
    >
      <input
        type="radio"
        name={name}
        value={value}
        checked={checked}
        onChange={onChange}
        className="sr-only"
      />
      <span className="text-bark-900 flex items-center gap-2 text-sm font-semibold">
        <span
          className={`grid h-4 w-4 shrink-0 place-items-center rounded-full border-2 ${
            checked ? 'border-olive-500' : 'border-bark-100'
          }`}
          aria-hidden="true"
        >
          {checked && <span className="bg-olive-500 h-2 w-2 rounded-full" />}
        </span>
        {label}
      </span>
      {hint && <span className="mt-1 block pl-6 text-xs">{hint}</span>}
    </label>
  )
}

function FieldError({ error }) {
  if (!error) return null
  return (
    <p role="alert" className="text-rust mt-2 text-sm font-medium">
      {error}
    </p>
  )
}
