import { Link } from 'react-router-dom'
import DogPhoto from './DogPhoto'
import { ENERGY_TONE, formatAge, titleCase } from '../lib/dogs'

/**
 * One dog in a grid. Used by the `/dogs` gallery and by the "Meet our dogs"
 * preview on the homepage, so both stay identical as the card evolves.
 *
 * The whole card is a link; the "View profile" text is a visual affordance
 * inside it rather than a second link to the same place, which would make a
 * screen reader announce every dog twice.
 */
export default function DogCard({ dog, matchScore = null, eager = false }) {
  return (
    <Link
      to={`/dogs/${dog.dog_id}`}
      className="card hover:shadow-lift group flex flex-col overflow-hidden transition-all duration-300 hover:-translate-y-1"
    >
      <div className="relative">
        <DogPhoto
          dog={dog}
          eager={eager}
          className="aspect-[4/3] w-full"
          sizes="(min-width: 1024px) 20rem, (min-width: 640px) 45vw, 90vw"
        />
        {matchScore != null && (
          <span className="bg-olive-500 absolute top-3 left-3 rounded-full px-3 py-1 text-xs font-bold text-white shadow-sm">
            {matchScore}% match
          </span>
        )}
      </div>

      <div className="flex flex-1 flex-col p-5">
        <div className="flex items-start justify-between gap-3">
          <h3 className="text-lg">{dog.name}</h3>
          <span
            className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold ${ENERGY_TONE[dog.energy_level]}`}
          >
            {titleCase(dog.energy_level)} energy
          </span>
        </div>

        <p className="mt-1 text-sm">
          {formatAge(dog.age)} old · {titleCase(dog.size)} ·{' '}
          {titleCase(dog.temperament)}
        </p>

        <div className="mt-3 flex flex-wrap gap-1.5">
          {dog.good_with_kids && <Tag>Good with kids</Tag>}
          {dog.good_with_other_pets && <Tag>Good with pets</Tag>}
          {dog.medical_needs && <Tag warn>Medical needs</Tag>}
        </div>

        <span className="text-olive-600 mt-5 inline-flex items-center gap-1.5 text-sm font-semibold">
          View profile
          <span
            className="transition-transform group-hover:translate-x-1"
            aria-hidden="true"
          >
            →
          </span>
        </span>
      </div>
    </Link>
  )
}

function Tag({ children, warn = false }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
        warn ? 'bg-rust/10 text-rust' : 'bg-bark-50 text-stone-neutral'
      }`}
    >
      {children}
    </span>
  )
}
