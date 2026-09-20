/**
 * Shared banner used at the top of every interior page. Pass `image` for a
 * photographic backdrop, or leave it out for the flat olive treatment.
 */
export default function PageHeader({ eyebrow, title, subtitle, image, imageAlt = '' }) {
  return (
    <section className="relative isolate overflow-hidden">
      {image ? (
        <>
          <img
            src={image}
            alt={imageAlt}
            className="absolute inset-0 h-full w-full object-cover"
          />
          <div
            className="from-bark-900/85 via-bark-900/65 to-bark-900/80 absolute inset-0 bg-gradient-to-r"
            aria-hidden="true"
          />
        </>
      ) : (
        <div className="from-olive-700 to-olive-500 absolute inset-0 bg-gradient-to-br" aria-hidden="true" />
      )}

      <div className="shell relative py-16 sm:py-20 lg:py-24">
        {eyebrow && (
          <p className="text-amber-brand text-xs font-semibold tracking-[0.28em] uppercase">
            {eyebrow}
          </p>
        )}
        <h1 className="mt-3 max-w-3xl text-4xl text-white sm:text-5xl lg:text-6xl">
          {title}
        </h1>
        {subtitle && (
          <p className="mt-5 max-w-2xl text-base leading-relaxed text-white/85 sm:text-lg">
            {subtitle}
          </p>
        )}
      </div>
    </section>
  )
}
