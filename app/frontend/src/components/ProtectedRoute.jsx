import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/useAuth'
import Spinner from './Spinner'

export default function ProtectedRoute({ children, requireAdmin = false }) {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <div className="grid min-h-[60vh] place-items-center">
        <Spinner label="Checking your session…" />
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  if (requireAdmin && !user.is_admin) {
    return (
      <div className="shell grid min-h-[60vh] place-items-center py-20 text-center">
        <div>
          <p className="eyebrow">403</p>
          <h1 className="mt-3 text-3xl font-bold">Admin access only</h1>
          <p className="mt-3 max-w-md text-balance">
            You are signed in as {user.email}, which is not an admin account.
          </p>
        </div>
      </div>
    )
  }

  return children
}
