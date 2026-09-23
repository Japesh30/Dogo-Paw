/**
 * Render checks for the medical dashboard components.
 *
 * There is no component test runner in this project, so the components are
 * bundled with rolldown (already a dependency, via Vite) and rendered to
 * static markup with react-dom/server. That verifies what each one actually
 * produces from API-shaped data — the timeline order, the severity wording,
 * the labels a screen reader reads — rather than only that it compiles.
 *
 *   node test_components.mjs
 */

import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { rolldown } from 'rolldown'

const HERE = fileURLToPath(new URL('.', import.meta.url))
const failures = []

const check = (label, ok, detail = '') => {
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${label}${ok || detail === '' ? '' : `  (${detail})`}`)
  if (!ok) failures.push(label)
}
const section = (title) => console.log(`\n${title}`)

const ENTRY = `
import { renderToStaticMarkup } from 'react-dom/server'
import MedicalTimeline from './src/components/medical/MedicalTimeline'
import ObservationTrends from './src/components/medical/ObservationTrends'
import RecordForm from './src/components/medical/RecordForm'
import MlAnomalies from './src/components/medical/MlAnomalies'
import {
  EmptyState, ErrorNote, RecordStatusPill, SeverityBadge, StatusPill, SuccessNote,
} from './src/components/medical/Pills'
import { buildTimeline } from './src/lib/medical'

export { renderToStaticMarkup, MedicalTimeline, ObservationTrends, RecordForm, MlAnomalies,
  EmptyState, ErrorNote, RecordStatusPill, SeverityBadge, StatusPill, SuccessNote,
  buildTimeline }
`

const dir = await mkdtemp(join(tmpdir(), 'dogopaw-render-'))
try {
  await writeFile(join(HERE, '.render-entry.jsx'), ENTRY)
  const bundle = await rolldown({
    input: join(HERE, '.render-entry.jsx'),
    platform: 'node',
    // React and its renderer stay external so the real installed copies run.
    external: ['react', 'react-dom/server', 'react/jsx-runtime', 'recharts'],
    // RecordForm imports the API client, which reads Vite's compile-time
    // environment. Vite substitutes these during a build; do the same here.
    plugins: [
      {
        name: 'vite-env',
        transform(code) {
          if (!code.includes('import.meta.env')) return null
          return code
            .replaceAll('import.meta.env.VITE_API_URL', '""')
            .replaceAll('import.meta.env.DEV', 'true')
        },
      },
    ],
  })
  // Written inside the project so Node resolves react-dom and recharts from
  // node_modules; a temp directory has no package scope to resolve against.
  await bundle.write({ file: join(HERE, '.render-bundle.mjs'), format: 'esm' })
  await bundle.close()

  const m = await import(`file://${join(HERE, '.render-bundle.mjs').replaceAll('\\', '/')}`)
  const render = (element) => m.renderToStaticMarkup(element)
  const jsx = (type, props) => ({ $$typeof: Symbol.for('react.transitional.element'),
    type, key: null, props, _owner: null, _store: {} })

  // A summary shaped exactly like GET /api/dogs/<id>/medical.
  const summary = {
    dog: { name: 'Rocky' },
    vaccinations: [
      { id: 1, vaccine_name: 'DHPP', administered_date: '2026-01-10',
        next_due_date: '2027-01-10', status: 'completed', notes: null },
      { id: 2, vaccine_name: 'Lepto', administered_date: null,
        next_due_date: '2026-10-01', status: 'scheduled', notes: null },
    ],
    medications: [
      { id: 1, medication_name: 'Phenobarbital', dosage: '1 tablet', frequency: 'twice daily',
        start_date: '2026-03-01', end_date: null, status: 'active', prescribed_by: 'Dr. Menon' },
      { id: 2, medication_name: 'Amoxicillin', dosage: '1 tablet', frequency: 'daily',
        start_date: '2026-02-01', end_date: '2026-02-10', status: 'completed' },
    ],
    recent_observations: [
      { id: 2, observation_date: '2026-09-20', weight_kg: 30.4, temperature_c: 38.9,
        symptoms: ['reduced appetite'], notes: null },
      { id: 1, observation_date: '2026-06-25', weight_kg: 34, temperature_c: 38.5,
        symptoms: [], notes: null },
    ],
    follow_ups: [
      { id: 1, reason: 'Recheck medication levels', due_date: '2026-09-09',
        completed_date: null, status: 'missed', notes: null },
    ],
    recent_medical_records: [
      { id: 1, title: 'Blood panel', visit_date: '2026-06-20', record_type: 'diagnostic',
        veterinarian: 'Dr. Menon', description: 'Routine monitoring bloods.' },
    ],
  }

  section('1. Medical timeline')
  const entries = m.buildTimeline(summary)
  const timeline = render(jsx(m.MedicalTimeline, { entries }))
  check('renders an entry for every record type', entries.length >= 7, entries.length)
  check('shows a medication start', timeline.includes('Phenobarbital started'))
  check('shows an observation with its measurements',
    timeline.includes('30.4 kg') && timeline.includes('38.9 °C'))
  check('shows the missed follow-up', timeline.includes('Recheck medication levels'))
  check('shows the medical record', timeline.includes('Blood panel'))
  check('labels each entry with its type',
    ['Medical record', 'Vaccination', 'Medication', 'Health observation', 'Follow-up']
      .every((label) => timeline.includes(label)))
  check('uses semantic time elements with machine-readable dates',
    timeline.includes('<time') && /datetime="2026-09-20"/i.test(timeline))
  check('marks a future-dated entry as upcoming', timeline.includes('Upcoming'))
  check('is ordered newest first',
    timeline.indexOf('2026-09-20') < timeline.indexOf('2026-06-20'))
  check('empty timeline shows a meaningful message',
    render(jsx(m.MedicalTimeline, { entries: [] })).includes('Nothing recorded yet'))

  section('2. Severity and status labels')
  for (const [severity, label] of Object.entries({
    critical: 'Critical', high: 'High', moderate: 'Moderate', low: 'Low',
  })) {
    check(`severity ${severity} is named in text, not colour alone`,
      render(jsx(m.SeverityBadge, { severity })).includes(label))
  }
  for (const [status, label] of Object.entries({
    open: 'Open', acknowledged: 'Acknowledged', resolved: 'Resolved',
  })) {
    check(`alert status ${status} is labelled`,
      render(jsx(m.StatusPill, { status })).includes(label))
  }
  check('a record status renders', render(jsx(m.RecordStatusPill, { status: 'active' })).includes('active'))
  check('an unknown status still renders rather than breaking',
    render(jsx(m.StatusPill, { status: 'weird' })).includes('weird'))

  section('3. States')
  check('an error is announced to assistive tech',
    render(jsx(m.ErrorNote, { children: 'Something failed.' })).includes('role="alert"'))
  check('a success message is announced politely',
    render(jsx(m.SuccessNote, { children: 'Saved.' })).includes('role="status"'))
  check('an empty state explains what would appear',
    render(jsx(m.EmptyState, { children: 'No alerts.' })).includes('No alerts.'))

  section('4. Observation trends')
  const trends = render(jsx(m.ObservationTrends, {
    observations: summary.recent_observations,
    analysis: {
      data_quality: {
        weight_series: { first_weight_kg: 34, latest_weight_kg: 30.4,
          percent_change: -10.6, period_days: 87, observation_count: 2 },
        temperature_series: { monitoring_range_c: [37.2, 39.4] },
      },
    },
  }))
  check('labels both measurements', trends.includes('Weight (kg)') && trends.includes('Temperature (°C)'))
  check('states the weight change from the backend series',
    trends.includes('34 kg') && trends.includes('30.4 kg') && trends.includes('-10.6%'))
  check('explains the shaded monitoring band is not clinical',
    trends.includes('not a clinical range'))
  const single = render(jsx(m.ObservationTrends, {
    observations: [summary.recent_observations[0]], analysis: null,
  }))
  check('a single reading is not drawn as a trend',
    single.includes('At least two are needed'))
  check('no observations gives a clear empty state',
    render(jsx(m.ObservationTrends, { observations: [], analysis: null }))
      .includes('No weight recorded yet'))

  section('5. Data entry form')
  const form = render(jsx(m.RecordForm, { dogId: 4, kind: 'observations' }))
  check('every field has a label',
    ['Date', 'Weight (kg)', 'Temperature (°C)', 'Symptoms', 'Notes']
      .every((label) => form.includes(label)))
  check('inputs are associated with their labels', (form.match(/for="observations-/g) ?? []).length >= 5)
  check('required fields are marked', form.includes('*'))
  check('the comma hint is described for screen readers',
    form.includes('aria-describedby="observations-symptoms-hint"'))
  const vaccForm = render(jsx(m.RecordForm, { dogId: 4, kind: 'vaccinations' }))
  check('the vaccination form offers only valid statuses',
    ['completed', 'scheduled', 'overdue'].every((s) => vaccForm.includes(`value="${s}"`)))
  const medForm = render(jsx(m.RecordForm, { dogId: 4, kind: 'medications' }))
  check('the medication form offers only valid statuses',
    ['active', 'completed', 'discontinued'].every((s) => medForm.includes(`value="${s}"`)))

  section('6. ML anomaly section')
  const mlResult = {
    available: true,
    model_version: 'health-anomaly-v1',
    algorithm: 'IsolationForest (StandardScaler pipeline)',
    trained_on: 'synthetic development data (ml/health_anomaly_data.py)',
    observations_scored: 3,
    anomaly_count: 1,
    anomalies: [
      {
        observation_id: 42,
        observation_date: '2026-09-03',
        is_anomaly: true,
        anomaly_score: 0.2807,
        severity: 'high',
        measurements_considered: ['temperature', 'weight'],
        reasons: [
          "Weight 17.6 kg is 12.2% below this dog's recent baseline of 20.04 kg (last 5 weigh-ins).",
          "Temperature 39.9 °C is 1.42 °C above this dog's recent baseline of 38.48 °C.",
        ],
        evidence: {},
        model_version: 'health-anomaly-v1',
      },
    ],
    score_scale: { note: 'An anomaly score, not a probability.' },
  }
  const mlMarkup = render(jsx(m.MlAnomalies, { ml: mlResult }))
  check('states plainly that it does not diagnose', mlMarkup.includes('does not'))
  check('and the word diagnose appears only as a denial',
    mlMarkup.includes('diagnose disease') && !/does diagnose/i.test(mlMarkup))
  check('shows the model version', mlMarkup.includes('health-anomaly-v1'))
  check('shows the anomaly score', mlMarkup.includes('0.2807'))
  check('labels the score as not a probability', mlMarkup.includes('not a probability'))
  check('names the severity in words, not colour alone', mlMarkup.includes('High anomaly'))
  // Locale-independent: the runner's locale decides the order of the parts.
  check('shows the affected observation date',
    mlMarkup.includes('Sep') && mlMarkup.includes('2026') && mlMarkup.includes('3'))
  check('lists the human-readable reasons',
    mlMarkup.includes('12.2% below') && mlMarkup.includes('1.42 °C above'))
  check('says which measurements were considered',
    mlMarkup.includes('temperature and weight'))
  check('shows no fabricated confidence percentage', !/\d{1,3}% (chance|confidence|likely)/i.test(mlMarkup))
  check('does not claim a disease',
    !/(disease|illness|infection|condition)/i.test(mlMarkup.replace('does not diagnose disease', '')))

  check('no anomalies gives the documented empty message',
    render(jsx(m.MlAnomalies, { ml: { ...mlResult, anomaly_count: 0, anomalies: [] } }))
      .includes('No unusual health patterns detected'))
  check('insufficient history is explained',
    render(jsx(m.MlAnomalies, {
      ml: { available: false, reason: 'insufficient_history', observations_available: 2, observations_required: 4, anomalies: [] },
    })).includes('Not enough historical observations'))
  check('...and states how many more are needed',
    render(jsx(m.MlAnomalies, {
      ml: { available: false, reason: 'insufficient_history', observations_available: 2, observations_required: 4, anomalies: [] },
    })).includes('2 of 4 observations'))
  check('a missing model is explained without alarming the reader',
    render(jsx(m.MlAnomalies, { ml: { available: false, reason: 'model_unavailable', anomalies: [] } }))
      .includes('Everything else on this page is unaffected'))
  check('a scoring failure is handled',
    render(jsx(m.MlAnomalies, { ml: { available: false, reason: 'scoring_failed', anomalies: [] } }))
      .includes('could not score'))
  check('an unknown reason still renders something sensible',
    render(jsx(m.MlAnomalies, { ml: { available: false, reason: 'mystery', anomalies: [] } }))
      .includes('unavailable'))
  check('a missing ML section does not break the page',
    render(jsx(m.MlAnomalies, { ml: null })).includes('not loaded'))
  check('ML wording is distinct from the deterministic rules',
    mlMarkup.includes("recent observations") && !mlMarkup.includes('declined by'))
} finally {
  await rm(join(HERE, '.render-entry.jsx'), { force: true })
  await rm(join(HERE, '.render-bundle.mjs'), { force: true })
  await rm(dir, { recursive: true, force: true }).catch(() => {})
}

console.log(`\n${failures.length ? `${failures.length} FAILED: ${failures.join(', ')}` : 'all passed'}`)
process.exit(failures.length ? 1 : 0)
