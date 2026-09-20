/**
 * Placeholder artwork for dogs in the synthetic dataset, which have no
 * photographs. A drawn silhouette is honest about that; the old site's
 * `dog2/3/5.png` are finished campaign posters, not cutouts, so they are not
 * usable here.
 *
 * `seed` picks one of three tinted plates so a grid of cards has some variety
 * while each dog keeps the same look every time it is rendered.
 */

const PLATES = [
  { bg: 'bg-olive-100', ink: 'text-olive-700' },
  { bg: 'bg-amber-brand/25', ink: 'text-amber-brand-dark' },
  { bg: 'bg-bark-100', ink: 'text-bark-700' },
]

export default function DogAvatar({ seed = 0, className = '' }) {
  const plate = PLATES[seed % PLATES.length]

  return (
    <div
      className={`relative grid place-items-center overflow-hidden ${plate.bg} ${className}`}
    >
      {/* Paw-print wallpaper */}
      <svg
        className={`absolute inset-0 h-full w-full opacity-[0.12] ${plate.ink}`}
        aria-hidden="true"
      >
        <defs>
          <pattern
            id={`paws-${seed}`}
            width="46"
            height="46"
            patternUnits="userSpaceOnUse"
            patternTransform="rotate(12)"
          >
            <g fill="currentColor">
              <ellipse cx="23" cy="26" rx="6" ry="5" />
              <circle cx="15.5" cy="17.5" r="2.6" />
              <circle cx="21" cy="14.5" r="2.6" />
              <circle cx="27" cy="15.5" r="2.6" />
              <circle cx="31.5" cy="20" r="2.6" />
            </g>
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill={`url(#paws-${seed})`} />
      </svg>

      {/* Dog face — built from simple primitives so it reads cleanly at any size */}
      <svg
        viewBox="0 0 100 100"
        className={`relative h-24 w-24 ${plate.ink}`}
        fill="currentColor"
        aria-hidden="true"
      >
        {/* floppy ears, tucked behind the head */}
        <ellipse cx="24" cy="44" rx="11" ry="21" transform="rotate(-18 24 44)" />
        <ellipse cx="76" cy="44" rx="11" ry="21" transform="rotate(18 76 44)" />
        {/* head */}
        <ellipse cx="50" cy="50" rx="27" ry="25" />
        {/* muzzle */}
        <ellipse cx="50" cy="68" rx="16" ry="13" />
        {/* eyes and nose, cut out in the page cream so they read on every plate */}
        <g fill="#f7f5f2">
          <circle cx="40" cy="46" r="3.4" />
          <circle cx="60" cy="46" r="3.4" />
          <ellipse cx="50" cy="62" rx="5.4" ry="4.2" />
          <path
            d="M50 66v5m0 0c0 2.6-2.4 4.4-5 4.4m5-4.4c0 2.6 2.4 4.4 5 4.4"
            stroke="#f7f5f2"
            strokeWidth="2"
            strokeLinecap="round"
            fill="none"
          />
        </g>
      </svg>
    </div>
  )
}
