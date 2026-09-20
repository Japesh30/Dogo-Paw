import { createContext } from 'react'

// Kept in its own module so AuthContext.jsx only exports a component and
// React Fast Refresh keeps working.
export const AuthContext = createContext(null)
