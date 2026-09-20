import { Link } from 'react-router-dom'
import { logo } from '../assets/images'

/**
 * Social accounts.
 *
 * `href` is null until a real account exists, and an entry with no href is not
 * rendered. Previously these pointed at `https://instagram.com/`,
 * `https://facebook.com/` and `https://wa.me/` — the first two are the sites'
 * own home pages rather than an account, and a bare `wa.me/` with no phone
 * number is an error page. Icons that look like links and go nowhere are worse
 * than no icons.
 *
 * To enable one, put the real URL in `href`:
 *   Instagram  https://instagram.com/<handle>
 *   Facebook   https://facebook.com/<page>
 *   WhatsApp   https://wa.me/<country code><number>   e.g. https://wa.me/917015596198
 */
const socials = [
  {
    label: 'Instagram',
    href: null,
    path: 'M12 2.2c3.2 0 3.58.01 4.85.07 1.17.05 1.8.25 2.23.41.56.22.96.48 1.38.9.42.42.68.82.9 1.38.16.42.36 1.06.41 2.23.06 1.27.07 1.65.07 4.85s-.01 3.58-.07 4.85c-.05 1.17-.25 1.8-.41 2.23-.22.56-.48.96-.9 1.38-.42.42-.82.68-1.38.9-.42.16-1.06.36-2.23.41-1.27.06-1.65.07-4.85.07s-3.58-.01-4.85-.07c-1.17-.05-1.8-.25-2.23-.41a3.8 3.8 0 0 1-1.38-.9 3.8 3.8 0 0 1-.9-1.38c-.16-.42-.36-1.06-.41-2.23C2.21 15.58 2.2 15.2 2.2 12s.01-3.58.07-4.85c.05-1.17.25-1.8.41-2.23.22-.56.48-.96.9-1.38.42-.42.82-.68 1.38-.9.42-.16 1.06-.36 2.23-.41C8.42 2.21 8.8 2.2 12 2.2Zm0 5.3a4.5 4.5 0 1 0 0 9 4.5 4.5 0 0 0 0-9Zm0 7.42a2.92 2.92 0 1 1 0-5.84 2.92 2.92 0 0 1 0 5.84Zm5.73-7.6a1.05 1.05 0 1 1-2.1 0 1.05 1.05 0 0 1 2.1 0Z',
  },
  {
    label: 'Facebook',
    href: null,
    path: 'M13.5 21v-8h2.7l.4-3.1h-3.1V7.9c0-.9.25-1.5 1.55-1.5H16.7V3.63c-.29-.04-1.28-.13-2.43-.13-2.4 0-4.05 1.47-4.05 4.17V9.9H7.5V13h2.72v8h3.28Z',
  },
  {
    label: 'WhatsApp',
    href: null,
    path: 'M12.04 2C6.6 2 2.2 6.4 2.2 11.84c0 1.74.46 3.44 1.32 4.93L2.1 22l5.36-1.4a9.8 9.8 0 0 0 4.58 1.16h.01c5.43 0 9.84-4.4 9.84-9.84 0-2.63-1.02-5.1-2.88-6.96A9.77 9.77 0 0 0 12.04 2Zm0 18.02h-.01a8.2 8.2 0 0 1-4.16-1.14l-.3-.18-3.1.81.83-3.02-.2-.31a8.15 8.15 0 0 1-1.25-4.34c0-4.5 3.68-8.17 8.2-8.17a8.13 8.13 0 0 1 8.18 8.18c0 4.5-3.67 8.17-8.19 8.17Zm4.49-6.12c-.25-.13-1.46-.72-1.68-.8-.23-.08-.39-.13-.56.12-.16.25-.64.8-.78.97-.15.16-.29.18-.53.06-.25-.13-1.04-.39-1.98-1.22-.73-.65-1.23-1.46-1.37-1.7-.14-.25-.02-.38.11-.5.11-.11.25-.29.37-.44.13-.15.17-.25.25-.42.09-.16.04-.31-.02-.44-.06-.12-.56-1.34-.76-1.84-.2-.48-.4-.42-.56-.43h-.48c-.16 0-.43.06-.65.31-.23.25-.86.84-.86 2.05s.88 2.38 1 2.54c.13.16 1.74 2.65 4.2 3.72.59.25 1.05.4 1.4.52.6.19 1.14.16 1.56.1.48-.07 1.46-.6 1.67-1.18.2-.58.2-1.07.15-1.18-.06-.1-.23-.16-.48-.28Z',
  },
]

const activeSocials = socials.filter((s) => s.href)

export default function Footer() {
  return (
    <footer className="bg-bark-900 mt-auto text-white/70">
      <div className="shell grid gap-10 py-14 sm:grid-cols-2 lg:grid-cols-4">
        <div className="sm:col-span-2 lg:col-span-1">
          <div className="flex items-center gap-2.5">
            <img
              src={logo}
              alt=""
              className="h-11 w-11 rounded-full bg-white/95 object-contain p-0.5"
            />
            <span className="text-lg font-extrabold tracking-tight text-white">
              Dogo<span className="text-olive-400">-Paw</span>
            </span>
          </div>
          <p className="mt-4 max-w-xs text-sm leading-relaxed">
            A shelterless, all-breed dog rescue run entirely by volunteers.
            Every dog we pull is fostered in a real home until the right family
            comes along.
          </p>
        </div>

        <nav aria-label="Footer">
          <h3 className="text-sm font-semibold tracking-wide text-white uppercase">
            Explore
          </h3>
          {/* py-1.5 + inline-block so each link is a comfortable tap target
              rather than a 20px-tall line of text. */}
          <ul className="mt-3 text-sm">
            {[
              ['/about', 'About Us'],
              ['/volunteer', 'Volunteer'],
              ['/foster', 'Foster'],
              ['/adopt-match', 'Adopt Match'],
            ].map(([to, label]) => (
              <li key={to}>
                <Link
                  to={to}
                  className="inline-block py-1.5 transition hover:text-white"
                >
                  {label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        <div>
          <h3 className="text-sm font-semibold tracking-wide text-white uppercase">
            Get in touch
          </h3>
          <ul className="mt-3 text-sm">
            <li>
              <a
                href="tel:+917015596198"
                className="inline-block py-1.5 transition hover:text-white"
              >
                +91 70155 96198
              </a>
            </li>
            <li>
              <a
                href="mailto:hello@dogo-paw.org"
                className="inline-block py-1.5 transition hover:text-white"
              >
                hello@dogo-paw.org
              </a>
            </li>
          </ul>
        </div>

        {activeSocials.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold tracking-wide text-white uppercase">
              Follow along
            </h3>
            <ul className="mt-4 flex gap-3">
              {activeSocials.map((s) => (
                <li key={s.label}>
                  <a
                    href={s.href}
                    target="_blank"
                    rel="noreferrer"
                    aria-label={s.label}
                    className="hover:bg-olive-500 grid h-11 w-11 place-items-center rounded-full bg-white/10 text-white transition hover:text-white"
                  >
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                      <path d={s.path} />
                    </svg>
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div className="border-t border-white/10">
        <div className="shell py-6 text-xs">
          {/* Said here as well as on the dog pages: the footer is on every
              route, including ones that never show a dog. */}
          <p className="text-center sm:text-left">
            Dogo-Paw is a student project. The dog profiles shown on this site
            are demonstration data, not real animals available for adoption.
          </p>
          <div className="mt-3 flex flex-col items-center justify-between gap-2 sm:flex-row">
            <p>© {new Date().getFullYear()} Dogo-Paw. Student project.</p>
            <p>Built by volunteers, for dogs who are still waiting.</p>
          </div>
        </div>
      </div>
    </footer>
  )
}
