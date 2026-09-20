import { Link } from 'react-router-dom'
import PageHeader from '../components/PageHeader'
import VolunteerForm from '../components/VolunteerForm'
import { volunteerPhotos } from '../assets/images'

const roles = [
  {
    title: 'Fostering',
    commitment: 'Weeks to months',
    body: 'As a shelterless rescue we depend on people willing to open their homes until a dog is adopted. Your job is to love, feed and care for a homeless dog until her own family is found. The approval process for foster homes is the same as for adopters.',
    icon: 'M12 21s-7.5-4.6-9.6-9A5.4 5.4 0 0 1 12 6.2 5.4 5.4 0 0 1 21.6 12c-2.1 4.4-9.6 9-9.6 9Z',
  },
  {
    title: 'Home visits',
    commitment: 'A couple of hours',
    body: 'A home visit is required for every adopter. As a home visitor you are our eyes and ears, confirming that the home would be a safe and loving environment for one of our dogs. We send you a checklist beforehand so you know exactly what to look for and what to ask.',
    icon: 'M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1v-9.5Z',
  },
  {
    title: 'Adoption coordinator',
    commitment: 'Ongoing, flexible',
    body: 'Manage the adoption process end to end: screen applications, run the phone interview, complete the vet check, arrange a home visitor, keep foster carers and adopters updated on progress, and finalise the adoption.',
    icon: 'M9 12h6m-6 4h4M8 4h8a2 2 0 0 1 2 2v14l-3-2-3 2-3-2-3 2V6a2 2 0 0 1 2-2Z',
  },
  {
    title: 'Event volunteer',
    commitment: 'A day at a time',
    body: 'Help us wrangle dogs at meet-and-greets, lend a hand at fundraising events — or come up with, coordinate and run an entirely new fundraiser of your own.',
    icon: 'M8 3v4m8-4v4M4 9h16M5 5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z',
  },
  {
    title: 'Dog taxi',
    commitment: 'Occasional trips',
    body: 'Every so often a dog needs to get from one place to another. A valid driving licence, a car, a crate depending on the dog, and the willingness to help are all it takes.',
    icon: 'M5 17h14M6.5 17a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0Zm14 0a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0ZM4 13l1.5-5A2 2 0 0 1 7.4 6.5h9.2A2 2 0 0 1 18.5 8L20 13v4H4v-4Z',
  },
  {
    title: 'Something else entirely',
    commitment: 'Up to you',
    body: 'Have a skill or a talent you would like to put to use — photography, design, legal, accounting, training, anything? Get in touch. We would love to hear from you.',
    icon: 'M12 4v16m8-8H4',
  },
]

export default function Volunteer() {
  return (
    <>
      <PageHeader
        eyebrow="Volunteer"
        title="There are lots of ways to help."
        subtitle="If you would love to be part of the rescue, we are always looking for dedicated volunteers — home visits, screening applications, help at meet-and-greets, and plenty more."
        image={volunteerPhotos[2].src}
        imageAlt=""
      />

      {/* ---------------- Intro + photos ---------------- */}
      <section className="bg-white py-16 sm:py-20">
        <div className="shell grid items-center gap-12 lg:grid-cols-2">
          <div>
            <p className="eyebrow">Why it matters</p>
            <h2 className="mt-3 text-3xl sm:text-4xl">
              Dozens of dogs, every single month
            </h2>
            <p className="mt-5 leading-relaxed">
              Each month we save dozens of wonderful dogs from local and
              Southern kill shelters and find them placements in safe,
              nurturing homes. None of that happens without volunteers — there
              is no paid staff behind the scenes to pick up the slack.
            </p>
            <p className="mt-4 leading-relaxed">
              Please consider joining us in this incredibly rewarding effort. We
              would love to have you on the team.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <a href="#signup" className="btn-primary">
                Sign up to volunteer
              </a>
              <a
                href="#roles"
                className="btn border-olive-500 text-olive-700 hover:bg-olive-50 border-2"
              >
                See the six roles
              </a>
            </div>
          </div>

          {/* One column on mobile, two from the sm breakpoint up. */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {volunteerPhotos.map((p, i) => (
              <img
                key={p.src}
                src={p.src}
                alt={p.alt}
                loading="lazy"
                className={`rounded-card shadow-soft h-full w-full object-cover ${
                  i === 2
                    ? 'aspect-[16/9] sm:col-span-2'
                    : 'aspect-[16/9] sm:aspect-square'
                }`}
              />
            ))}
          </div>
        </div>
      </section>

      {/* ---------------- Roles ---------------- */}
      <section id="roles" className="scroll-mt-24 py-16 sm:py-20">
        <div className="shell">
          <p className="eyebrow">Ways to help</p>
          <h2 className="mt-3 text-3xl sm:text-4xl">
            Six roles. Pick whichever fits your week.
          </h2>

          <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {roles.map((role) => (
              <article key={role.title} className="card hover:shadow-lift flex flex-col p-7 transition-shadow">
                <span className="bg-olive-100 text-olive-700 grid h-12 w-12 place-items-center rounded-2xl">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path
                      d={role.icon}
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </span>
                <h3 className="mt-5 text-xl">{role.title}</h3>
                <p className="text-amber-brand-dark mt-1 text-xs font-semibold tracking-wide uppercase">
                  {role.commitment}
                </p>
                <p className="mt-3 flex-1 text-sm leading-relaxed">{role.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* ---------------- Sign-up form ---------------- */}
      <section id="signup" className="scroll-mt-24 bg-white py-16 sm:py-20">
        <div className="shell grid gap-10 lg:grid-cols-[0.85fr_1.15fr]">
          <div className="lg:sticky lg:top-28 lg:self-start">
            <p className="eyebrow">Join us</p>
            <h2 className="mt-3 text-3xl sm:text-4xl">
              Tell us how you would like to help
            </h2>
            <p className="mt-5 leading-relaxed">
              Fill this in and someone from the rescue will call you. There is
              no commitment at this stage — we mainly want to know where you are
              and how much time you have.
            </p>
            <ul className="mt-6 space-y-2.5 text-sm">
              {[
                'No account needed to apply',
                // Was "We usually respond within 48 hours". A response time is
                // a promise to a real person, and this site has no staffed
                // inbox behind it to keep one.
                'A volunteer coordinator will get back to you',
                'Every role has someone to show you the ropes',
              ].map((t) => (
                <li key={t} className="flex gap-2">
                  <span className="text-olive-500" aria-hidden="true">
                    ✓
                  </span>
                  {t}
                </li>
              ))}
            </ul>
          </div>

          <VolunteerForm />
        </div>
      </section>

      {/* ---------------- CTA ---------------- */}
      <section className="bg-olive-500 py-16 sm:py-20">
        <div className="shell text-center">
          <h2 className="text-3xl text-white sm:text-4xl">
            Fostering is where we need people most
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-white/90">
            Every foster place that opens up is one more dog we can pull from a
            shelter. It really is that direct.
          </p>
          <div className="mt-9 flex flex-col items-center justify-center gap-4 sm:flex-row">
            <Link
              to="/foster"
              className="btn text-olive-700 bg-white hover:bg-white/90"
            >
              Read about fostering
            </Link>
            <Link to="/adopt-match" className="btn-ghost">
              Or find your match
            </Link>
          </div>
        </div>
      </section>
    </>
  )
}
