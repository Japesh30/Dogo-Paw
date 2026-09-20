import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Scroll-snap carousel. One slide on mobile, two on tablet, three on desktop —
 * the arrows and dots drive `scrollTo` rather than a transform, so it stays
 * swipeable on touch and keyboard-scrollable everywhere.
 */
export default function Carousel({ slides, label = 'Image gallery' }) {
  const trackRef = useRef(null)
  const [index, setIndex] = useState(0)

  const scrollToIndex = useCallback((i) => {
    const track = trackRef.current
    if (!track) return
    const slide = track.children[i]
    if (slide) track.scrollTo({ left: slide.offsetLeft, behavior: 'smooth' })
  }, [])

  // Keep the dots in sync with wherever the user has swiped to.
  useEffect(() => {
    const track = trackRef.current
    if (!track) return
    let frame = 0
    const onScroll = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        const { scrollLeft } = track
        let nearest = 0
        let best = Infinity
        for (let i = 0; i < track.children.length; i += 1) {
          const distance = Math.abs(track.children[i].offsetLeft - scrollLeft)
          if (distance < best) {
            best = distance
            nearest = i
          }
        }
        setIndex(nearest)
      })
    }
    track.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      cancelAnimationFrame(frame)
      track.removeEventListener('scroll', onScroll)
    }
  }, [])

  const step = (delta) => {
    const next = Math.min(Math.max(index + delta, 0), slides.length - 1)
    scrollToIndex(next)
  }

  return (
    <div className="relative" role="region" aria-roledescription="carousel" aria-label={label}>
      <ul
        ref={trackRef}
        className="flex snap-x snap-mandatory gap-4 overflow-x-auto scroll-smooth pb-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {slides.map((s, i) => (
          <li
            key={s.src}
            aria-label={`${i + 1} of ${slides.length}`}
            className="w-[85%] shrink-0 snap-start sm:w-[48%] lg:w-[32%]"
          >
            <img
              src={s.src}
              alt={s.alt}
              loading={i < 2 ? 'eager' : 'lazy'}
              className="rounded-card shadow-soft aspect-[4/3] w-full object-cover"
            />
          </li>
        ))}
      </ul>

      <div className="mt-2 flex items-center justify-center gap-4">
        <button
          type="button"
          onClick={() => step(-1)}
          disabled={index === 0}
          aria-label="Previous images"
          className="border-bark-100 text-bark-900 hover:border-olive-500 hover:text-olive-600 grid h-11 w-11 place-items-center rounded-full border-2 bg-white transition disabled:opacity-35 disabled:hover:border-current"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M15 6l-6 6 6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>

        <ul className="flex items-center">
          {slides.map((s, i) => (
            <li key={s.src}>
              {/* The dot stays 10px visually; the button around it is padded out
                  to a thumb-sized hit area. */}
              <button
                type="button"
                onClick={() => scrollToIndex(i)}
                aria-label={`Go to image ${i + 1}`}
                aria-current={i === index}
                className="grid h-11 w-6 place-items-center"
              >
                <span
                  className={`block h-2.5 rounded-full transition-all ${
                    i === index
                      ? 'bg-olive-500 w-7'
                      : 'bg-bark-100 hover:bg-olive-300 w-2.5'
                  }`}
                />
              </button>
            </li>
          ))}
        </ul>

        <button
          type="button"
          onClick={() => step(1)}
          disabled={index === slides.length - 1}
          aria-label="Next images"
          className="border-bark-100 text-bark-900 hover:border-olive-500 hover:text-olive-600 grid h-11 w-11 place-items-center rounded-full border-2 bg-white transition disabled:opacity-35 disabled:hover:border-current"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  )
}
