import { Link } from 'react-router-dom'
import PageHeader from '../components/PageHeader'
import Carousel from '../components/Carousel'
import { dog2, dog3, dog5, fosterPhotos } from '../assets/images'

// The old site's dog2/3/5 are finished campaign posters, so they are shown as
// posters rather than used as decorative cutouts.
const posters = [
  { src: dog5, alt: 'Poster: Adopt a pet — get a new friend' },
  { src: dog2, alt: "Poster: Adopt, don't shop — get a new friend" },
  { src: dog3, alt: 'Poster: Paws! Will you consider adoption first?' },
]

const faqs = [
  {
    q: 'Who pays for food and vet care?',
    a: 'We do. Fostering costs you time and space, not money — medical care, vaccinations and supplies are covered by the rescue.',
  },
  {
    q: 'How long does a foster placement last?',
    a: 'It varies with the dog. Some are adopted within a fortnight; older dogs and those with medical needs can take a few months. We never move a dog on before it is ready.',
  },
  {
    q: 'What if it does not work out?',
    a: 'Tell us. We will arrange another placement. A foster home that is honest about a bad fit is far more useful to us than one that struggles in silence.',
  },
  {
    q: 'Do I need previous experience?',
    a: 'No. We match first-time foster carers with settled, easy-going dogs, and there is always someone from the rescue on the end of a phone.',
  },
]

export default function Foster() {
  return (
    <>
      <PageHeader
        eyebrow="Foster"
        title="We have no shelter. Foster homes are the shelter."
        subtitle="Dogo-Paw's mission is to save lives, and that is made possible by a network of foster families who open their hearts and homes to our rescues."
        image={fosterPhotos[0].src}
      />

      {/* ---------------- Mission ---------------- */}
      <section className="bg-white py-16 sm:py-20">
        <div className="shell max-w-3xl text-center">
          <p className="eyebrow">Our mission</p>
          <h2 className="mt-3 text-3xl sm:text-4xl">
            There are always animals in need
          </h2>
          <p className="mt-6 text-base leading-relaxed sm:text-lg">
            <strong className="text-olive-600">Dogo-Paw</strong> is a
            shelterless rescue group, and our mission is to save lives. That is
            only possible because of the incredible foster families who take
            our rescues into their own homes and care for them. Together we are
            able to give loving dogs the chance to find their forever homes.
          </p>
          <p className="mt-4 leading-relaxed">
            Every foster place that opens up is one more dog we can pull from a
            shelter. It really is that direct.
          </p>
        </div>
      </section>

      {/* ---------------- Gallery ---------------- */}
      <section className="py-16 sm:py-20">
        <div className="shell">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="eyebrow">Life in foster care</p>
              <h2 className="mt-3 text-3xl sm:text-4xl">
                Sofas, gardens, and second chances
              </h2>
            </div>
            <p className="max-w-sm text-sm">
              Photographs sent in by the families currently fostering for us.
            </p>
          </div>

          <div className="mt-10">
            <Carousel slides={fosterPhotos} label="Photos from Dogo-Paw foster homes" />
          </div>
        </div>
      </section>

      {/* ---------------- What it involves ---------------- */}
      <section className="bg-white py-16 sm:py-20">
        <div className="shell grid gap-12 lg:grid-cols-[1fr_1.1fr]">
          <div>
            <p className="eyebrow">Common questions</p>
            <h2 className="mt-3 text-3xl sm:text-4xl">
              What fostering actually involves
            </h2>
            <p className="mt-5 leading-relaxed">
              Your job is simple to describe and hard to overstate: love, care
              for and feed a homeless dog until she finds her own family. The
              approval process is the same as for adopters, because the standard
              of home is the same.
            </p>
          </div>

          <dl className="space-y-4">
            {faqs.map((f) => (
              <div key={f.q} className="card p-6">
                <dt className="text-bark-900 text-lg font-semibold">{f.q}</dt>
                <dd className="mt-2 leading-relaxed">{f.a}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      {/* ---------------- Campaign posters ---------------- */}
      <section className="py-16 sm:py-20">
        <div className="shell">
          <div className="text-center">
            <p className="eyebrow">Spread the word</p>
            <h2 className="mt-3 text-3xl sm:text-4xl">Share our campaigns</h2>
            <p className="mx-auto mt-4 max-w-xl leading-relaxed">
              Not able to foster right now? Sharing one of these does real work
              too — most of our foster carers first heard about us from a friend.
            </p>
          </div>

          {/* The three posters are different shapes (two portrait, one square),
              so each sits in a matching 4:5 plate and is contained rather than
              cropped — the artwork carries text that must not be cut. */}
          <ul className="mx-auto mt-10 grid max-w-4xl gap-6 sm:grid-cols-3">
            {posters.map((p) => (
              <li
                key={p.src}
                className="rounded-card shadow-soft border-bark-100 flex aspect-4/5 items-center justify-center overflow-hidden border bg-white p-3"
              >
                <img
                  src={p.src}
                  alt={p.alt}
                  loading="lazy"
                  className="max-h-full w-auto max-w-full rounded-lg object-contain"
                />
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* ---------------- CTA ---------------- */}
      <section className="bg-bark-900 py-16 sm:py-20">
        <div className="shell text-center">
          <h2 className="text-3xl text-white sm:text-4xl">
            Thinking about it? Ask us anything.
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-white/75">
            Please feel free to contact us with any questions you may have about
            fostering. There is no commitment in asking.
          </p>
          <div className="mt-9 flex flex-col items-center justify-center gap-4 sm:flex-row">
            <a href="tel:+917015596198" className="btn-accent w-full sm:w-auto">
              Call +91 70155 96198
            </a>
            <Link to="/login" className="btn-ghost w-full sm:w-auto">
              Create an account
            </Link>
          </div>
        </div>
      </section>
    </>
  )
}
