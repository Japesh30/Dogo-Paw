import { Link } from 'react-router-dom'
import PageHeader from '../components/PageHeader'
import { banner1, tommy } from '../assets/images'

const whatWeDo = [
  {
    tag: 'Donate',
    tone: 'olive',
    body: 'We fund spay and neuter clinics so that fewer unwanted litters are born in the first place — the only real long-term fix for pet overpopulation.',
  },
  {
    tag: 'Community outreach',
    tone: 'amber',
    body: 'We run sessions in local schools teaching children and young adults what animal rescue involves, and what responsible, day-to-day pet ownership actually looks like.',
  },
  {
    tag: 'Service dog support',
    tone: 'rust',
    body: 'We support agencies that train assistance dogs for people who are physically disabled or hearing impaired. Many dogs who were once abandoned now help someone live independently.',
  },
]

const toneStyles = {
  olive: 'bg-olive-100 text-olive-700',
  amber: 'bg-amber-brand/20 text-amber-brand-dark',
  rust: 'bg-rust/15 text-rust',
}

const process = [
  {
    step: '01',
    title: 'Temperament evaluation',
    body: 'Every dog is assessed for how it lives alongside other dogs, cats and children, so we never guess about compatibility.',
  },
  {
    step: '02',
    title: 'Health check & vaccination',
    body: 'A vet examines each dog and brings all shots up to date before it goes anywhere.',
  },
  {
    step: '03',
    title: 'Spay or neuter',
    body: 'No dog leaves our care unaltered. It is non-negotiable, and it is part of the same problem we fund clinics to solve.',
  },
  {
    step: '04',
    title: 'Foster placement',
    body: 'The dog moves into a foster home and stays there — in a real household, not a kennel — until its own family turns up.',
  },
]

export default function About() {
  return (
    <>
      {/* Flat treatment here on purpose: banner1.png is a finished banner with
          its own headline and logo, so it is shown below rather than written
          over. */}
      <PageHeader
        eyebrow="About Dogo-Paw"
        title="Dogs end up homeless through no fault of their own."
        subtitle="We are a non-profit, shelterless, all-breed rescue group run entirely by volunteers who love dogs and refuse to look away."
      />

      <div className="bg-white">
        <img
          src={banner1}
          alt="Dogo-Paw: give new life, help helpless dogs, save a life"
          className="mx-auto block w-full max-w-6xl"
        />
      </div>

      {/* ---------------- Who we are ---------------- */}
      <section className="bg-white py-16 sm:py-20">
        <div className="shell max-w-3xl">
          <p className="eyebrow">Who we are</p>
          <h2 className="mt-3 text-3xl sm:text-4xl">
            No building. No kennels. A network of homes.
          </h2>
          <div className="mt-6 space-y-5 text-base leading-relaxed sm:text-lg">
            <p>
              <strong className="text-olive-600">Dogo-Paw</strong> is a
              non-profit, shelterless, all-breed dog rescue group. We are made
              up of volunteers who want to help dogs that end up homeless
              through no fault of their own — loyal, loving animals who are
              surrendered to shelters by their owners or found roaming the
              streets after being abandoned.
            </p>
            <p>
              Because we have no shelter of our own, every dog we take in is
              cared for inside a real household. It costs us more effort and it
              limits how many dogs we can hold at once, but it means we know
              each dog as an individual rather than as a kennel number — and
              that knowledge is what lets us place them properly.
            </p>
          </div>
        </div>
      </section>

      {/* ---------------- Process ---------------- */}
      <section className="py-16 sm:py-20">
        <div className="shell">
          <p className="eyebrow">Our process</p>
          <h2 className="mt-3 text-3xl sm:text-4xl">
            What happens between rescue and adoption
          </h2>
          <p className="mt-4 max-w-2xl leading-relaxed">
            Our goal is to meet the needs of each dog as an individual and to
            make sure the placement is right — for the dog and for the family.
          </p>

          <ol className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {process.map((p) => (
              <li key={p.step} className="card flex flex-col p-6">
                <span className="text-olive-300 text-4xl font-extrabold">
                  {p.step}
                </span>
                <h3 className="mt-3 text-lg">{p.title}</h3>
                <p className="mt-2 text-sm leading-relaxed">{p.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* ---------------- What we do ---------------- */}
      <section className="bg-white py-16 sm:py-20">
        <div className="shell grid items-start gap-12 lg:grid-cols-2">
          <div className="lg:sticky lg:top-28">
            <img
              src={tommy}
              alt="Tommy, one of the dogs rehomed through Dogo-Paw"
              loading="lazy"
              className="rounded-card shadow-lift aspect-[4/3] w-full object-cover"
            />
            <p className="mt-4 text-sm italic">
              Tommy — surrendered at eight months, adopted eleven weeks later.
            </p>
          </div>

          <div>
            <p className="eyebrow">What we do</p>
            <h2 className="mt-3 text-3xl sm:text-4xl">
              Rehoming is the goal. It is not the whole job.
            </h2>
            <p className="mt-5 leading-relaxed">
              Finding forever homes for abandoned dogs is our primary work, but
              a rescue that only rehomes is treating the symptom. Alongside it
              we:
            </p>

            <ul className="mt-8 space-y-5">
              {whatWeDo.map((item) => (
                <li key={item.tag} className="card p-6">
                  <span
                    className={`inline-block rounded-full px-3 py-1 text-xs font-bold tracking-wider uppercase ${toneStyles[item.tone]}`}
                  >
                    {item.tag}
                  </span>
                  <p className="mt-3 leading-relaxed">{item.body}</p>
                </li>
              ))}
            </ul>

            <p className="mt-8 leading-relaxed">
              We are proud of the work we do with the dogs, and of the work we
              do in the communities around them.
            </p>
          </div>
        </div>
      </section>

      {/* ---------------- CTA ---------------- */}
      <section className="bg-bark-900 py-16 sm:py-20">
        <div className="shell text-center">
          <h2 className="text-3xl text-white sm:text-4xl">
            Ready to meet the dog that fits your life?
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-white/75">
            Our matching engine compares your home, schedule and experience
            against every dog currently in foster care — and tells you why each
            one scored the way it did.
          </p>
          <div className="mt-9 flex flex-col items-center justify-center gap-4 sm:flex-row">
            <Link to="/adopt-match" className="btn-accent w-full sm:w-auto">
              Find my match
            </Link>
            <Link to="/foster" className="btn-ghost w-full sm:w-auto">
              Foster instead
            </Link>
          </div>
        </div>
      </section>
    </>
  )
}
