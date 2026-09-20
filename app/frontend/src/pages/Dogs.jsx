import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import PageHeader from '../components/PageHeader'
import DogCard from '../components/DogCard'
import DemoDataNotice from '../components/DemoDataNotice'
import Spinner from '../components/Spinner'
import { api } from '../lib/api'
import { fosterPhotos } from '../assets/images'
import { ENERGY_LEVELS, SIZES, titleCase } from '../lib/dogs'
import { readMatchSession, scoresByDog } from '../lib/matchSession'

const NO_FILTERS = {
  sizes: [],
  energy: [],
  kidsOnly: false,
  petsOnly: false,
  query: '',
}

export default function Dogs() {
  const [dogs, setDogs] = useState([])
  const [state, setState] = useState('loading') // loading | ready | error
  const [message, setMessage] = useState('')
  const [filters, setFilters] = useState(NO_FILTERS)

  // If they have already been through the questionnaire this session, every
  // card can carry its score. Read once — the results do not change while the
  // gallery is open.
  const [session] = useState(() => readMatchSession())
  const matchScores = useMemo(() => scoresByDog(session), [session])

  useEffect(() => {
    let cancelled = false
    api
      .dogs()
      .then((data) => {
        if (cancelled) return
        setDogs(data.dogs)
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
  }, [])

  // All filtering happens here, against the list we already hold — no request
  // per keystroke, and the result is instant.
  const visible = useMemo(() => {
    const query = filters.query.trim().toLowerCase()
    return dogs.filter((dog) => {
      if (filters.sizes.length && !filters.sizes.includes(dog.size)) return false
      if (filters.energy.length && !filters.energy.includes(dog.energy_level))
        return false
      if (filters.kidsOnly && !dog.good_with_kids) return false
      if (filters.petsOnly && !dog.good_with_other_pets) return false
      if (query && !dog.name.toLowerCase().includes(query)) return false
      return true
    })
  }, [dogs, filters])

  const toggle = (key, value) =>
    setFilters((f) => ({
      ...f,
      [key]: f[key].includes(value)
        ? f[key].filter((v) => v !== value)
        : [...f[key], value],
    }))

  const filtersActive =
    filters.sizes.length > 0 ||
    filters.energy.length > 0 ||
    filters.kidsOnly ||
    filters.petsOnly ||
    filters.query.trim() !== ''

  return (
    <>
      <PageHeader
        eyebrow="Our dogs"
        title="Every dog currently looking for a home"
        subtitle="All of them live with foster families, which is how we know how each one behaves around children, cats and other dogs. Filter the list, or let the matcher rank them for you."
        image={fosterPhotos[2].src}
      />

      <section className="py-10 sm:py-14">
        <div className="shell">
          <DemoDataNotice className="mb-8" />

          {/* ---------------- Filters ---------------- */}
          <div className="card p-5 sm:p-6">
            {/* Four equal columns from lg, stacked below it. A flex-wrap row
                left the household checkboxes stranded on their own line with a
                gap beside the energy chips. */}
            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4 lg:gap-8">
              <div>
                <label
                  htmlFor="dog-search"
                  className="text-bark-900 text-sm font-semibold"
                >
                  Search by name
                </label>
                <input
                  id="dog-search"
                  type="search"
                  value={filters.query}
                  onChange={(e) =>
                    setFilters((f) => ({ ...f, query: e.target.value }))
                  }
                  placeholder="e.g. Luna"
                  className="border-bark-100 focus:border-olive-500 mt-2 w-full rounded-xl border-2 px-4 py-2.5 text-sm outline-none"
                />
              </div>

              <FilterGroup label="Size">
                {SIZES.map((size) => (
                  <Chip
                    key={size}
                    active={filters.sizes.includes(size)}
                    onClick={() => toggle('sizes', size)}
                  >
                    {titleCase(size)}
                  </Chip>
                ))}
              </FilterGroup>

              <FilterGroup label="Energy level">
                {ENERGY_LEVELS.map((level) => (
                  <Chip
                    key={level}
                    active={filters.energy.includes(level)}
                    onClick={() => toggle('energy', level)}
                  >
                    {titleCase(level)}
                  </Chip>
                ))}
              </FilterGroup>

              <FilterGroup label="Household" stack>
                <Check
                  checked={filters.kidsOnly}
                  onChange={(v) => setFilters((f) => ({ ...f, kidsOnly: v }))}
                >
                  Good with kids
                </Check>
                <Check
                  checked={filters.petsOnly}
                  onChange={(v) => setFilters((f) => ({ ...f, petsOnly: v }))}
                >
                  Good with other pets
                </Check>
              </FilterGroup>
            </div>

            {filtersActive && (
              <div className="border-bark-100 mt-5 flex items-center justify-between gap-4 border-t pt-4">
                <p className="text-sm" aria-live="polite">
                  Showing <strong className="text-bark-900">{visible.length}</strong>{' '}
                  of {dogs.length} dogs
                </p>
                <button
                  type="button"
                  onClick={() => setFilters(NO_FILTERS)}
                  className="text-olive-600 hover:text-olive-700 text-sm font-semibold underline underline-offset-2"
                >
                  Clear filters
                </button>
              </div>
            )}
          </div>

          {/* ---------------- Results ---------------- */}
          {state === 'loading' && (
            <div className="grid place-items-center py-24">
              <Spinner label="Fetching the dogs…" />
            </div>
          )}

          {state === 'error' && (
            <p
              role="alert"
              className="bg-rust/10 text-rust mt-10 rounded-xl px-4 py-3 text-sm font-medium"
            >
              {message}
            </p>
          )}

          {state === 'ready' && visible.length === 0 && (
            <div className="card mt-10 p-10 text-center sm:p-14">
              <p className="text-5xl" aria-hidden="true">
                🐾
              </p>
              <h2 className="mt-4 text-2xl">No dogs match these filters</h2>
              <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed">
                Try widening the search — our list is small because every dog
                has to have a foster home before we can take them in.
              </p>
              <button
                type="button"
                onClick={() => setFilters(NO_FILTERS)}
                className="btn-primary mt-7"
              >
                Show all {dogs.length} dogs
              </button>
            </div>
          )}

          {state === 'ready' && visible.length > 0 && (
            <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {visible.map((dog, i) => (
                <DogCard
                  key={dog.dog_id}
                  dog={dog}
                  eager={i < 3}
                  matchScore={matchScores[dog.dog_id]?.score ?? null}
                />
              ))}
            </div>
          )}

          {/* ---------------- Closing CTA ---------------- */}
          {state === 'ready' && (
            <div className="bg-bark-50 rounded-card mt-14 p-6 text-center sm:p-9">
              <h2 className="text-2xl">
                {session
                  ? 'Want to see the reasoning behind those scores?'
                  : 'Not sure which of them suits you?'}
              </h2>
              <p className="mx-auto mt-3 max-w-xl text-sm leading-relaxed">
                {session
                  ? 'Your results page ranks all 18 and explains every score, axis by axis.'
                  : 'Answer five questions about your home and lifestyle, and we will rank every dog on this page against your profile — and show you why each one ranked where it did.'}
              </p>
              <Link to="/adopt-match" className="btn-primary mt-6">
                {session ? 'Back to my matches' : 'Take the matching quiz'}
              </Link>
            </div>
          )}
        </div>
      </section>
    </>
  )
}

/** `stack` puts the controls in a column — the household checkboxes are too
 *  wide to sit side by side in a quarter-width column. */
function FilterGroup({ label, children, stack = false }) {
  return (
    <fieldset>
      <legend className="text-bark-900 text-sm font-semibold">{label}</legend>
      <div
        className={`mt-2 flex gap-2 ${stack ? 'flex-col' : 'flex-wrap'}`}
      >
        {children}
      </div>
    </fieldset>
  )
}

function Chip({ active, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-full border-2 px-4 py-1.5 text-sm font-medium transition ${
        active
          ? 'border-olive-500 bg-olive-50 text-olive-700'
          : 'border-bark-100 text-stone-neutral hover:border-olive-300'
      }`}
    >
      {children}
    </button>
  )
}

function Check({ checked, onChange, children }) {
  return (
    <label className="flex cursor-pointer items-center gap-2 py-1 text-sm font-medium">
      {/* 20px rather than the browser default 13px: a checkbox is the smallest
          thing on this page and the one most often missed with a thumb. */}
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="accent-olive-500 h-5 w-5 shrink-0"
      />
      {children}
    </label>
  )
}
