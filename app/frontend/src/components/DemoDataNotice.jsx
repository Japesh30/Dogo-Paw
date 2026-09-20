/**
 * Tells a visitor, plainly, that the dog profiles are demonstration data.
 *
 * The 18 dogs are a synthetic dataset built for this project, and their photos
 * are crops of the rescue's own photographs reused across several profiles.
 * Without saying so, the site reads as a live adoption listing — someone could
 * reasonably believe a specific animal is waiting for them and get in touch
 * about a dog that does not exist.
 *
 * Deliberately written as a factual note rather than a warning banner: it is
 * shown once per page, in the site's own voice, and does not cover the content
 * or interrupt the flow. The matching engine, the scoring and the explanations
 * are all real — it is the dogs that are not, and the wording says exactly
 * that.
 */
export default function DemoDataNotice({ className = '' }) {
  return (
    <aside
      className={`border-bark-100 bg-bark-50 rounded-2xl border p-4 sm:p-5 ${className}`}
    >
      <div className="flex gap-3">
        <span
          aria-hidden="true"
          className="bg-amber-brand/25 text-amber-brand-dark grid h-8 w-8 shrink-0 place-items-center rounded-full text-sm font-bold"
        >
          i
        </span>
        <div className="text-sm leading-relaxed">
          <p className="text-bark-900 font-semibold">
            These dog profiles are demonstration data
          </p>
          <p className="mt-1">
            Dogo-Paw is a student project. The 18 dogs shown here are a
            synthetic dataset created to demonstrate the adoption matcher — they
            are not real animals currently available for adoption, and the
            photographs are representative images reused across profiles rather
            than portraits of individual dogs.{' '}
            <span className="text-bark-900 font-medium">
              The matching, scoring and explanations are genuine
            </span>{' '}
            — only the dogs are not.
          </p>
        </div>
      </div>
    </aside>
  )
}
