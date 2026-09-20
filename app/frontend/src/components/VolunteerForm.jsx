import { useState } from 'react'
import { api } from '../lib/api'

/**
 * Migrated from the standalone `form/dog-volunteer` Vite app.
 *
 * Same fields and the same validation rules as the original. Two deliberate
 * changes: the localStorage draft is gone (it does not survive every preview
 * environment, and a half-typed address is not worth persisting), and the
 * submit now goes through the shared API client to Flask rather than to the
 * retired Node/Mongo service.
 */

const EMPTY = {
  name: '',
  email: '',
  mobile: '',
  address: '',
  state: '',
  city: '',
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function validate(values) {
  const errors = {}

  if (!values.name.trim()) errors.name = 'Name is required'

  if (!values.email.trim()) errors.email = 'Email is required'
  else if (!EMAIL_RE.test(values.email)) errors.email = 'Invalid email'

  if (!values.mobile.trim()) errors.mobile = 'Mobile is required'
  else if (values.mobile.replace(/\D/g, '').length < 10)
    errors.mobile = 'Enter at least 10 digits'

  if (!values.address.trim()) errors.address = 'Address is required'
  if (!values.state.trim()) errors.state = 'State is required'
  if (!values.city.trim()) errors.city = 'City is required'

  return errors
}

const FIELDS = [
  { name: 'name', label: 'Full name', placeholder: 'Priya Sharma', autoComplete: 'name' },
  {
    name: 'email',
    label: 'Email',
    type: 'email',
    placeholder: 'you@example.com',
    autoComplete: 'email',
  },
  {
    name: 'mobile',
    label: 'Mobile number',
    type: 'tel',
    placeholder: '+91 98765 43210',
    autoComplete: 'tel',
  },
  {
    name: 'address',
    label: 'Address',
    textarea: true,
    placeholder: 'Flat / street / area',
    autoComplete: 'street-address',
    full: true,
  },
  { name: 'state', label: 'State', placeholder: 'Maharashtra', autoComplete: 'address-level1' },
  { name: 'city', label: 'City', placeholder: 'Mumbai', autoComplete: 'address-level2' },
]

export default function VolunteerForm() {
  const [form, setForm] = useState(EMPTY)
  const [errors, setErrors] = useState({})
  const [touched, setTouched] = useState({})
  const [submitting, setSubmitting] = useState(false)
  const [savedMsg, setSavedMsg] = useState('')
  const [warningMsg, setWarningMsg] = useState('')

  // Once nothing is wrong any more, the "please fix things" banner should go.
  const applyValidation = (values) => {
    const found = validate(values)
    setErrors(found)
    if (Object.keys(found).length === 0) setWarningMsg('')
    return found
  }

  const handleChange = (e) => {
    const { name, value } = e.target
    const next = { ...form, [name]: value }
    setForm(next)
    // Re-validate a field the user has already left, so a fix clears its error.
    if (touched[name]) applyValidation(next)
  }

  const handleBlur = (e) => {
    setTouched((prev) => ({ ...prev, [e.target.name]: true }))
    applyValidation(form)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()

    const currentErrors = validate(form)
    setErrors(currentErrors)
    setTouched(Object.fromEntries(Object.keys(EMPTY).map((k) => [k, true])))

    if (Object.keys(currentErrors).length > 0) {
      setSavedMsg('')
      setWarningMsg('Please fill out all fields correctly before submitting.')
      return
    }

    setSubmitting(true)
    setWarningMsg('')

    try {
      const data = await api.volunteer(form)
      setSavedMsg(data.message || 'Thanks — your volunteering request was recorded!')
      setForm(EMPTY)
      setTouched({})
      setErrors({})
    } catch (err) {
      setWarningMsg(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  const handleReset = () => {
    setForm(EMPTY)
    setTouched({})
    setErrors({})
    setWarningMsg('')
    setSavedMsg('')
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="card p-6 sm:p-9">
      <h2 className="text-2xl sm:text-3xl">Sign up to volunteer</h2>
      <p className="mt-2 text-sm">
        Tell us how to reach you and we will be in touch about the roles that
        suit your availability.
      </p>

      <div className="mt-8 grid gap-5 sm:grid-cols-2">
        {FIELDS.map((f) => {
          const error = touched[f.name] && errors[f.name]
          const shared = {
            id: f.name,
            name: f.name,
            value: form[f.name],
            onChange: handleChange,
            onBlur: handleBlur,
            placeholder: f.placeholder,
            autoComplete: f.autoComplete,
            'aria-invalid': Boolean(error),
            'aria-describedby': error ? `${f.name}-error` : undefined,
            className: `mt-2 w-full rounded-xl border-2 px-4 py-3 text-base transition outline-none ${
              error
                ? 'border-rust focus:border-rust'
                : 'border-bark-100 focus:border-olive-500'
            }`,
          }

          return (
            <div key={f.name} className={f.full ? 'sm:col-span-2' : undefined}>
              <label
                htmlFor={f.name}
                className="text-bark-900 block text-sm font-semibold"
              >
                {f.label}
              </label>

              {f.textarea ? (
                <textarea rows={3} {...shared} />
              ) : (
                <input type={f.type ?? 'text'} {...shared} />
              )}

              {error && (
                <p id={`${f.name}-error`} className="text-rust mt-1.5 text-sm">
                  {errors[f.name]}
                </p>
              )}
            </div>
          )
        })}
      </div>

      {warningMsg && (
        <p
          role="alert"
          className="bg-rust/10 text-rust mt-6 rounded-xl px-4 py-3 text-sm font-medium"
        >
          {warningMsg}
        </p>
      )}

      {savedMsg && (
        <p
          role="status"
          className="bg-olive-100 text-olive-700 mt-6 rounded-xl px-4 py-3 text-sm font-medium"
        >
          {savedMsg}
        </p>
      )}

      {/* Shown before the submit button, not after it and not behind a link:
          this form asks for a home address and a phone number, and the moment
          to say what happens to them is before someone hands them over. */}
      <div className="border-bark-100 bg-bark-50 mt-8 rounded-2xl border p-4 text-sm leading-relaxed sm:p-5">
        <p className="text-bark-900 font-semibold">How we use your details</p>
        <p className="mt-1.5">
          Your name, email, phone number and address are stored so a volunteer
          coordinator can contact you about volunteering. They are not sold, not
          shared with anyone outside Dogo-Paw, and not used for marketing.
        </p>
        <p className="mt-2">
          <span className="text-bark-900 font-medium">
            Please note this is a student project.
          </span>{' '}
          Submissions are stored in its database and are visible to the project
          administrator. Please do not submit details you would not want held
          for coursework. To have a submission removed, contact us using the
          details in the footer.
        </p>
      </div>

      <div className="mt-6 flex flex-col gap-3 sm:flex-row">
        <button
          type="submit"
          disabled={submitting}
          className="btn-primary flex-1 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? 'Submitting…' : 'Submit application'}
        </button>
        <button
          type="button"
          onClick={handleReset}
          className="btn border-bark-100 text-stone-neutral hover:border-olive-500 hover:text-olive-600 border-2"
        >
          Reset
        </button>
      </div>
    </form>
  )
}
