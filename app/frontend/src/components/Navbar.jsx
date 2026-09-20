import { useEffect, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { logo } from "../assets/images";
import { useAuth } from "../context/useAuth";

const links = [
  { to: "/", label: "Home", end: true },
  { to: "/about", label: "About Us" },
  { to: "/dogs", label: "Our Dogs" },
  { to: "/volunteer", label: "Volunteer" },
  { to: "/foster", label: "Foster" },
  { to: "/adopt-match", label: "Adopt Match", highlight: true },
];

/**
 * `transparent` renders the bar over the homepage hero video until the user
 * scrolls; every other page gets the solid white bar from the start.
 */
export default function Navbar({ transparent = false }) {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const { pathname } = useLocation();
  const { user, logout } = useAuth();

  useEffect(() => setOpen(false), [pathname]);

  useEffect(() => {
    if (!transparent) return;
    const onScroll = () => setScrolled(window.scrollY > 40);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [transparent]);

  // Lock body scroll while the mobile sheet is open.
  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  const solid = !transparent || scrolled || open;

  return (
    <>
      {/* Scrim — a sibling of the header, so it paints over page content
          rather than inside the header's own stacking context.

          Hidden from assistive tech: it is a tap-anywhere convenience that
          duplicates the X button below. Exposing it as a second control named
          "Close menu" gave screen readers two identical buttons for one
          action, and made "the close button" ambiguous to anything querying by
          name. The X keeps the keyboard and screen-reader path. */}
      {open && (
        <button
          type="button"
          tabIndex={-1}
          aria-hidden="true"
          onClick={() => setOpen(false)}
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
        />
      )}

      <header
        className={`fixed inset-x-0 top-0 z-50 transition-colors duration-300 ${
          solid
            ? "bg-white/95 shadow-soft backdrop-blur-md"
            : "bg-gradient-to-b from-black/55 to-transparent"
        }`}
      >
        <nav
          aria-label="Main"
          className="shell flex h-18 items-center justify-between gap-4 py-3"
        >
          <Link to="/" className="flex shrink-0 items-center gap-2.5">
            <img
              src={logo}
              alt=""
              className={`h-11 w-11 rounded-full object-contain transition ${
                solid ? "" : "bg-white/90 p-0.5"
              }`}
            />
            <span
              className={`text-lg font-extrabold tracking-tight ${
                solid ? "text-bark-900" : "text-white drop-shadow"
              }`}
            >
              Dogo<span className="text-olive-500">-Paw</span>
            </span>
          </Link>

          {/* Desktop links */}
          <ul className="hidden items-center gap-1 lg:flex">
            {links.map((l) => (
              <li key={l.to}>
                <NavLink
                  to={l.to}
                  end={l.end}
                  className={({ isActive }) =>
                    [
                      "rounded-full px-4 py-2 text-sm font-medium transition-colors",
                      l.highlight && !isActive
                        ? "text-amber-brand-dark hover:bg-amber-brand/15"
                        : "",
                      isActive
                        ? solid
                          ? "bg-olive-100 text-olive-700"
                          : "bg-white/20 text-white"
                        : solid
                          ? l.highlight
                            ? ""
                            : "text-stone-neutral hover:text-olive-600 hover:bg-olive-50"
                          : "text-white/90 hover:bg-white/15 hover:text-white",
                    ]
                      .filter(Boolean)
                      .join(" ")
                  }
                >
                  {l.label}
                </NavLink>
              </li>
            ))}
          </ul>

          <div className="hidden shrink-0 items-center gap-3 lg:flex">
            {user ? (
              <>
                {/* Same padded pill as the other nav links, so it lines up
                    with them instead of sitting as bare text. */}
                {user.is_admin && (
                  <Link
                    to="/admin"
                    className={`rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                      solid
                        ? "text-stone-neutral hover:bg-olive-50 hover:text-olive-600"
                        : "text-white/90 hover:bg-white/15 hover:text-white"
                    }`}
                  >
                    Dashboard
                  </Link>
                )}
                <span
                  className={`text-sm font-semibold ${solid ? "text-bark-900" : "text-white"}`}
                >
                  {user.name.split(" ")[0]}
                </span>
                <button
                  onClick={logout}
                  className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                    solid
                      ? "border-bark-100 text-stone-neutral hover:border-rust hover:text-rust border"
                      : "border border-white/60 text-white hover:bg-white/15"
                  }`}
                >
                  Log out
                </button>
              </>
            ) : (
              <Link
                to="/login"
                className={
                  solid
                    ? "bg-olive-500 hover:bg-olive-600 rounded-full px-5 py-2 text-sm font-semibold text-white transition"
                    : "rounded-full border border-white/70 px-5 py-2 text-sm font-semibold text-white transition hover:bg-white/15"
                }
              >
                Login
              </Link>
            )}
          </div>

          {/* Hamburger */}
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            aria-controls="mobile-menu"
            aria-label={open ? "Close menu" : "Open menu"}
            className={`relative z-50 grid h-11 w-11 place-items-center rounded-full transition lg:hidden ${
              solid
                ? "text-bark-900 hover:bg-bark-50"
                : "text-white hover:bg-white/15"
            }`}
          >
            <span className="sr-only">Menu</span>
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              aria-hidden="true"
            >
              {open ? (
                <path
                  d="M6 6l12 12M18 6L6 18"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
              ) : (
                <path
                  d="M4 7h16M4 12h16M4 17h16"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
              )}
            </svg>
          </button>
        </nav>

        {/* Mobile sheet */}
        <div
          id="mobile-menu"
          hidden={!open}
          className="border-bark-100 relative border-t bg-white lg:hidden"
        >
          <ul className="shell flex flex-col gap-1 py-4">
            {links.map((l) => (
              <li key={l.to}>
                <NavLink
                  to={l.to}
                  end={l.end}
                  className={({ isActive }) =>
                    `block rounded-xl px-4 py-3 text-base font-medium transition ${
                      isActive
                        ? "bg-olive-100 text-olive-700"
                        : "text-bark-900 hover:bg-bark-50"
                    }`
                  }
                >
                  {l.label}
                </NavLink>
              </li>
            ))}
            <li className="mt-2">
              {user ? (
                <div className="flex flex-col gap-2">
                  {user.is_admin && (
                    <Link
                      to="/admin"
                      className="text-bark-900 hover:bg-bark-50 block rounded-xl px-4 py-3 text-base font-medium"
                    >
                      Admin Dashboard
                    </Link>
                  )}
                  <button onClick={logout} className="btn-primary w-full">
                    Log out ({user.name.split(" ")[0]})
                  </button>
                </div>
              ) : (
                <Link to="/login" className="btn-primary w-full">
                  Login / Sign up
                </Link>
              )}
            </li>
          </ul>
        </div>
      </header>
    </>
  );
}
