import { NavLink } from 'react-router-dom'

/** Navigation between the admin views. One admin area, two sections — the
 *  activity overview that already existed, and health monitoring. */
export default function AdminTabs() {
  const tabs = [
    { to: '/admin', label: 'Overview', end: true },
    { to: '/admin/health', label: 'Health monitoring' },
  ]

  return (
    <nav aria-label="Admin sections" className="border-bark-100 mt-6 border-b">
      <ul className="-mb-px flex gap-1 overflow-x-auto">
        {tabs.map((tab) => (
          <li key={tab.to}>
            <NavLink
              to={tab.to}
              end={tab.end}
              className={({ isActive }) =>
                `inline-block border-b-2 px-4 py-3 text-sm font-semibold whitespace-nowrap transition ${
                  isActive
                    ? 'border-olive-500 text-bark-900'
                    : 'hover:text-bark-900 border-transparent'
                }`
              }
            >
              {tab.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}
