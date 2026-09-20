import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { logo } from '../assets/images'
import { useAuth } from '../context/useAuth'

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

const EMPTY = { name: '', email: '', password: '' }

export default function Login() {
  const [mode, setMode] = useState('signin') // 'signin' | 'signup'
  const [values, setValues] = useState(EMPTY)
  const [errors, setErrors] = useState({})
  const [formError, setFormError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const { user, login, register } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = location.state?.from ?? '/adopt-match'

  if (user) return <Navigate to={from} replace />

  const isSignup = mode === 'signup'

  const validate = () => {
    const next = {}
    if (isSignup && !values.name.trim()) next.name = 'Please enter your name.'
    if (!values.email.trim()) next.email = 'Email is required.'
    else if (!EMAIL_RE.test(values.email.trim()))
      next.email = 'That does not look like a valid email address.'
    if (!values.password) next.password = 'Password is required.'
    else if (isSignup && values.password.length < 6)
      next.password = 'Use at least 6 characters.'
    return next
  }

  const update = (field) => (e) => {
    setValues((v) => ({ ...v, [field]: e.target.value }))
    setErrors((prev) => {
      if (!prev[field]) return prev
      const { [field]: _removed, ...rest } = prev
      return rest
    })
  }

  const switchMode = (next) => {
    setMode(next)
    setErrors({})
    setFormError('')
  }

  const onSubmit = async (e) => {
    e.preventDefault()
    setFormError('')

    const found = validate()
    setErrors(found)
    if (Object.keys(found).length) return

    setSubmitting(true)
    try {
      if (isSignup) {
        await register({
          name: values.name.trim(),
          email: values.email.trim(),
          password: values.password,
        })
      } else {
        await login({ email: values.email.trim(), password: values.password })
      }
      navigate(from, { replace: true })
    } catch (err) {
      setFormError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="bg-bark-50 grid min-h-[calc(100vh-4.5rem)] place-items-center px-5 py-12 sm:px-8 sm:py-16">
      <div className="w-full max-w-md">
        <div className="text-center">
          <img src={logo} alt="" className="mx-auto h-16 w-16 object-contain" />
          <h1 className="mt-4 text-3xl">
            {isSignup ? 'Join Dogo-Paw' : 'Welcome back'}
          </h1>
          <p className="mt-2 text-sm">
            {isSignup
              ? 'Create an account to save your matches and apply to adopt or foster.'
              : 'Sign in to pick up where you left off.'}
          </p>
        </div>

        <div className="card mt-8 p-6 sm:p-8">
          {/* Tabs */}
          <div
            role="tablist"
            aria-label="Sign in or sign up"
            className="bg-bark-50 grid grid-cols-2 gap-1 rounded-full p-1"
          >
            {[
              ['signin', 'Sign In'],
              ['signup', 'Sign Up'],
            ].map(([value, label]) => (
              <button
                key={value}
                role="tab"
                type="button"
                aria-selected={mode === value}
                onClick={() => switchMode(value)}
                className={`rounded-full py-2.5 text-sm font-semibold transition ${
                  mode === value
                    ? 'text-bark-900 bg-white shadow-sm'
                    : 'text-stone-neutral hover:text-bark-900'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <form onSubmit={onSubmit} noValidate className="mt-7 space-y-5">
            {isSignup && (
              <Field
                id="name"
                label="Full name"
                autoComplete="name"
                placeholder="Priya Sharma"
                value={values.name}
                onChange={update('name')}
                error={errors.name}
              />
            )}

            <Field
              id="email"
              type="email"
              label="Email"
              autoComplete="email"
              placeholder="you@example.com"
              value={values.email}
              onChange={update('email')}
              error={errors.email}
            />

            <Field
              id="password"
              type="password"
              label="Password"
              autoComplete={isSignup ? 'new-password' : 'current-password'}
              placeholder={isSignup ? 'At least 6 characters' : '••••••••'}
              value={values.password}
              onChange={update('password')}
              error={errors.password}
            />

            {formError && (
              <p
                role="alert"
                className="bg-rust/10 text-rust rounded-xl px-4 py-3 text-sm font-medium"
              >
                {formError}
              </p>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="btn-primary w-full disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting
                ? 'Please wait…'
                : isSignup
                  ? 'Create account'
                  : 'Sign in'}
            </button>
          </form>

          <p className="mt-6 text-center text-sm">
            {isSignup ? 'Already have an account? ' : 'New to Dogo-Paw? '}
            <button
              type="button"
              onClick={() => switchMode(isSignup ? 'signin' : 'signup')}
              className="text-olive-600 -my-1 rounded px-1 py-2 font-semibold hover:underline"
            >
              {isSignup ? 'Sign in instead' : 'Create one'}
            </button>
          </p>
        </div>

        {/* Local convenience only.

            This panel used to print the admin credentials too, which meant the
            public login page handed out access to the dashboard — every
            volunteer's name, email, phone number and address. `import.meta.env.DEV`
            is false in any production build, so the block is removed by the
            bundler rather than merely hidden, and the admin account is no longer
            named here at all: in production its password comes from
            ADMIN_PASSWORD and is never committed. */}
        {import.meta.env.DEV && (
          <div className="border-bark-100 mt-6 rounded-2xl border border-dashed p-4 text-center text-xs">
            <p className="text-bark-900 font-semibold">
              Demo account (development only)
            </p>
            <p className="mt-1">demo@dogo-paw.org / demo123</p>
          </div>
        )}

        <p className="mt-4 text-center text-sm">
          <Link
            to="/"
            className="hover:text-olive-600 inline-block rounded px-2 py-2"
          >
            ← Back to home
          </Link>
        </p>
      </div>
    </section>
  )
}

function Field({ id, label, error, ...props }) {
  return (
    <div>
      <label htmlFor={id} className="text-bark-900 block text-sm font-semibold">
        {label}
      </label>
      <input
        id={id}
        name={id}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? `${id}-error` : undefined}
        className={`mt-2 w-full rounded-xl border-2 px-4 py-3 text-base transition outline-none ${
          error
            ? 'border-rust focus:border-rust'
            : 'border-bark-100 focus:border-olive-500'
        }`}
        {...props}
      />
      {error && (
        <p id={`${id}-error`} className="text-rust mt-1.5 text-sm">
          {error}
        </p>
      )}
    </div>
  )
}
