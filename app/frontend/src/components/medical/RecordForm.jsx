import { useState } from 'react'
import { api } from '../../lib/api'
import { RECORD_TYPES, errorMessage } from '../../lib/medical'
import { FORM_FIELDS } from '../../lib/medicalForms'
import { ErrorNote, SuccessNote } from './Pills'

/** Turn the form's strings into the JSON the API expects. */
function toPayload(kind, values) {
  const body = {}
  for (const field of FORM_FIELDS[kind]) {
    const raw = values[field.name]
    if (raw === undefined || raw === '') continue
    if (field.numeric) {
      const n = Number(raw)
      // Let a non-number through as typed; the backend rejects it with a
      // clearer message than a silent NaN would give.
      body[field.name] = Number.isNaN(n) ? raw : n
    } else if (field.list) {
      const items = raw
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
      if (items.length) body[field.name] = items
    } else {
      body[field.name] = raw
    }
  }
  return body
}

export default function RecordForm({ dogId, kind, onSaved, onCancel }) {
  const fields = FORM_FIELDS[kind]
  const [values, setValues] = useState({})
  const [missing, setMissing] = useState([])
  const [error, setError] = useState('')
  const [saved, setSaved] = useState('')
  const [saving, setSaving] = useState(false)

  const set = (name, value) => setValues((v) => ({ ...v, [name]: value }))

  const submit = async (event) => {
    event.preventDefault()
    setError('')
    setSaved('')

    // A quick check so the obvious gaps do not need a round trip. The backend
    // checks everything again regardless.
    const blanks = fields.filter((f) => f.required && !values[f.name]?.toString().trim())
    setMissing(blanks.map((f) => f.name))
    if (blanks.length) {
      setError(`Please fill in: ${blanks.map((f) => f.label).join(', ')}.`)
      return
    }

    setSaving(true)
    try {
      await api.medicalCreate(dogId, kind, toPayload(kind, values))
      setSaved(`${RECORD_TYPES[kind].singular} saved.`)
      setValues({})
      onSaved?.()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} noValidate className="border-bark-100 mt-4 rounded-xl border p-4">
      <div className="grid gap-4 sm:grid-cols-2">
        {fields.map((field) => {
          const invalid = missing.includes(field.name)
          const id = `${kind}-${field.name}`
          const shared = {
            id,
            value: values[field.name] ?? '',
            onChange: (e) => set(field.name, e.target.value),
            'aria-invalid': invalid || undefined,
            'aria-describedby': field.hint ? `${id}-hint` : undefined,
            className: `mt-1.5 w-full rounded-xl border-2 px-3 py-2 text-sm outline-none transition ${
              invalid ? 'border-rust' : 'border-bark-100 focus:border-olive-500'
            }`,
          }

          return (
            <div key={field.name} className={field.full ? 'sm:col-span-2' : undefined}>
              <label htmlFor={id} className="text-bark-900 block text-sm font-semibold">
                {field.label}
                {field.required && <span className="text-rust"> *</span>}
              </label>

              {field.options ? (
                <select {...shared}>
                  <option value="">Select…</option>
                  {field.options.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              ) : field.textarea ? (
                <textarea rows={2} placeholder={field.placeholder} {...shared} />
              ) : (
                <input
                  type={field.type ?? 'text'}
                  step={field.step}
                  placeholder={field.placeholder}
                  {...shared}
                />
              )}

              {field.hint && (
                <p id={`${id}-hint`} className="text-stone-neutral mt-1 text-xs">
                  {field.hint}
                </p>
              )}
            </div>
          )
        })}
      </div>

      {error && (
        <div className="mt-4">
          <ErrorNote>{error}</ErrorNote>
        </div>
      )}
      {saved && (
        <div className="mt-4">
          <SuccessNote>{saved}</SuccessNote>
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="submit"
          disabled={saving}
          className="bg-olive-500 hover:bg-olive-600 rounded-full px-5 py-2 text-sm font-semibold text-white disabled:opacity-50"
        >
          {saving ? 'Saving…' : `Save ${RECORD_TYPES[kind].singular}`}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="bg-bark-50 hover:bg-bark-100 text-bark-900 rounded-full px-5 py-2 text-sm font-semibold"
        >
          Close
        </button>
      </div>
    </form>
  )
}
