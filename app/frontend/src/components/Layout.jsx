import { useEffect } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import Navbar from './Navbar'
import Footer from './Footer'
import ChatWidget from './ChatWidget'

/** Only the homepage sits under a transparent, video-backed navbar. */
const TRANSPARENT_NAV_ROUTES = new Set(['/'])

const SITE_NAME = 'Dogo-Paw'

/**
 * The browser tab per route.
 *
 * A single-page app never reloads, so without this every route keeps the one
 * <title> from index.html — every tab, bookmark and history entry reads
 * "Dogo-Paw — Rescue, Foster, Adopt", including a specific dog's page.
 *
 * Kept here rather than in each page so there is one owner: two components
 * both writing document.title would race on effect order, and the winner would
 * depend on when a fetch happened to resolve.
 */
const PAGE_TITLES = {
  '/': 'Rescue, Foster, Adopt',
  '/about': 'About us',
  '/dogs': 'Our dogs',
  '/volunteer': 'Volunteer with us',
  '/foster': 'Foster a dog',
  '/login': 'Sign in',
  '/adopt-match': 'Find your match',
  '/admin': 'Admin dashboard',
}

function titleFor(pathname) {
  if (PAGE_TITLES[pathname]) return PAGE_TITLES[pathname]
  // /dogs/3 and friends. The dog's own name would read better, but it is not
  // known until the profile page's fetch resolves.
  if (/^\/dogs\/[^/]+$/.test(pathname)) return 'Dog profile'
  return 'Page not found'
}

export default function Layout() {
  const { pathname } = useLocation()
  const transparent = TRANSPARENT_NAV_ROUTES.has(pathname)

  useEffect(() => {
    window.scrollTo(0, 0)
    document.title = `${titleFor(pathname)} · ${SITE_NAME}`
  }, [pathname])

  return (
    <div className="flex min-h-screen flex-col">
      {/* Keyboard and screen-reader users would otherwise tab through the whole
          navbar on every route before reaching the page. Visually hidden until
          focused, which is the first thing Tab reaches. */}
      <a
        href="#main"
        className="bg-olive-500 focus:ring-olive-700 sr-only rounded-br-xl px-4 py-3 text-sm font-semibold text-white focus:not-sr-only focus:absolute focus:top-0 focus:left-0 focus:z-[100] focus:ring-2"
      >
        Skip to content
      </a>
      <Navbar transparent={transparent} />
      {/* Non-hero pages need to clear the fixed 4.5rem navbar. */}
      <main id="main" className={`flex-1 ${transparent ? '' : 'pt-18'}`}>
        <Outlet />
      </main>
      <Footer />
      {/* Sits above everything, on every route. */}
      <ChatWidget />
    </div>
  )
}
