import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import DogCard from '../components/DogCard'
import { api } from '../lib/api'
import { heroVideo, tommy, volunteerPhotos } from '../assets/images'

const stats = [
  { value: '30+', label: 'Dogs rehomed every month' },
  { value: '100%', label: 'Volunteer-run, zero salaries' },
  { value: '0', label: 'Kennels — every dog lives in a home' },
]

const paths = [
  {
    to: '/adopt-match',
    eyebrow: 'AI matching',
    title: 'Find your match',
    body: 'Answer five questions about your home and lifestyle. Our matching engine scores every available dog against your profile and explains each result.',
    cta: 'Start matching',
    accent: true,
  },
  {
    to: '/foster',
    eyebrow: 'Foster',
    title: 'Open your home',
    body: 'We have no shelter. A dog can only be rescued if a foster home is ready for it — even a few weeks of care changes everything.',
    cta: 'Learn about fostering',
  },
  {
    to: '/volunteer',
    eyebrow: 'Volunteer',
    title: 'Give a few hours',
    body: 'Home visits, application screening, event help, dog taxi runs. There is a role here for whatever time and skills you have.',
    cta: 'See the roles',
  },
]

export default function Home() {
  // A taste of the gallery. If the backend is down this simply does not render
  // — the homepage is the front door and must not depend on the API to work.
  const [preview, setPreview] = useState([])

  useEffect(() => {
    let cancelled = false
    api
      .dogs()
      .then((data) => {
        if (!cancelled) setPreview(data.dogs.slice(0, 4))
      })
      .catch(() => {
        /* leave the section out */
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <>
      {/* ---------------- Hero ---------------- */}
      <section className="relative flex min-h-[100svh] items-center justify-center overflow-hidden">
        <video
          className="absolute inset-0 h-full w-full object-cover"
          src={heroVideo}
          autoPlay
          loop
          muted
          playsInline
          preload="auto"
          poster={tommy}
          aria-hidden="true"
        />
        <div
          className="absolute inset-0 bg-gradient-to-b from-black/70 via-black/45 to-black/75"
          aria-hidden="true"
        />

        <div className="shell relative z-10 pt-28 pb-20 text-center">
          <p className="text-amber-brand text-xs font-semibold tracking-[0.3em] uppercase sm:text-sm">
            Shelterless · All-breed · Volunteer-run
          </p>
          <h1 className="mt-5 text-5xl font-extrabold text-white drop-shadow-lg sm:text-7xl lg:text-8xl">
            Dogo-Paw
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-base leading-relaxed text-white/85 sm:text-lg">
            We pull abandoned and surrendered dogs from local shelters, get them
            healthy, and place them in foster homes until the right family
            arrives. That family might be yours.
          </p>

          <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
            <Link to="/adopt-match" className="btn-accent w-full sm:w-auto">
              Adopt Now
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path
                  d="M5 12h14m-6-6 6 6-6 6"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </Link>
            <Link to="/about" className="btn-ghost w-full sm:w-auto">
              How we work
            </Link>
          </div>
        </div>

        <div
          className="absolute bottom-8 left-1/2 hidden -translate-x-1/2 animate-bounce text-white/70 sm:block"
          aria-hidden="true"
        >
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
            <path
              d="M12 5v14m0 0-6-6m6 6 6-6"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
      </section>

      {/* ---------------- Stats ---------------- */}
      <section className="bg-white">
        <div className="shell grid gap-8 py-14 sm:grid-cols-3 sm:py-16">
          {stats.map((s) => (
            <div key={s.label} className="text-center">
              <p className="text-olive-600 text-4xl font-extrabold sm:text-5xl">
                {s.value}
              </p>
              <p className="mt-2 text-sm sm:text-base">{s.label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ---------------- Three paths ---------------- */}
      <section className="py-16 sm:py-20">
        <div className="shell">
          <p className="eyebrow text-center">Three ways in</p>
          <h2 className="mt-3 text-center text-3xl sm:text-4xl">
            However much you can give, it helps a dog
          </h2>

          <div className="mt-12 grid gap-6 md:grid-cols-3">
            {paths.map((p) => (
              <Link
                key={p.to}
                to={p.to}
                className={`card hover:shadow-lift group flex flex-col p-7 transition-all duration-300 hover:-translate-y-1 ${
                  p.accent ? 'ring-amber-brand/50 ring-2' : ''
                }`}
              >
                <p className="eyebrow">{p.eyebrow}</p>
                <h3 className="mt-2 text-xl">{p.title}</h3>
                <p className="mt-3 flex-1 text-sm leading-relaxed">{p.body}</p>
                <span className="text-olive-600 mt-6 inline-flex items-center gap-2 text-sm font-semibold">
                  {p.cta}
                  <span className="transition-transform group-hover:translate-x-1">
                    →
                  </span>
                </span>
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* ---------------- Meet our dogs ---------------- */}
      {preview.length > 0 && (
        <section className="bg-white py-16 sm:py-20">
          <div className="shell">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="eyebrow">Meet our dogs</p>
                <h2 className="mt-3 text-3xl sm:text-4xl">
                  Some of the dogs waiting right now
                </h2>
              </div>
              <Link
                to="/dogs"
                className="text-olive-600 hover:text-olive-700 -mx-2 shrink-0 rounded-lg px-2 py-2 text-sm font-semibold"
              >
                See all our dogs →
              </Link>
            </div>

            <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
              {preview.map((dog) => (
                <DogCard key={dog.dog_id} dog={dog} />
              ))}
            </div>
          </div>
        </section>
      )}

      {/* ---------------- Photo strip + closing CTA ---------------- */}
      {/* Tinted rather than white, so it does not merge into the dog grid
          above it — the page alternates ground colour section by section. */}
      <section className="py-16 sm:py-20">
        <div className="shell grid items-center gap-12 lg:grid-cols-2">
          {/* One column on mobile, two from the sm breakpoint up. */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {volunteerPhotos.map((p, i) => (
              <img
                key={p.src}
                src={p.src}
                alt={p.alt}
                loading="lazy"
                className={`rounded-card shadow-soft h-full w-full object-cover ${
                  i === 0
                    ? 'aspect-[16/9] sm:col-span-2'
                    : 'aspect-[16/9] sm:aspect-square'
                }`}
              />
            ))}
          </div>

          <div>
            <p className="eyebrow">Why it works</p>
            <h2 className="mt-3 text-3xl sm:text-4xl">
              No kennels. Just homes, and the people who open them.
            </h2>
            <p className="mt-5 leading-relaxed">
              Every dog in our care is temperament-evaluated, health-checked,
              vaccinated and spayed or neutered before adoption. Because they
              live with foster families rather than in a shelter, we know how
              each dog behaves around children, cats and other dogs — and that
              is exactly what our matching engine uses to find them the right
              family.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Link to="/adopt-match" className="btn-primary">
                Find my match
              </Link>
              <Link
                to="/volunteer"
                className="btn border-olive-500 text-olive-700 hover:bg-olive-50 border-2"
              >
                I want to help
              </Link>
            </div>
          </div>
        </div>
      </section>
    </>
  )
}
