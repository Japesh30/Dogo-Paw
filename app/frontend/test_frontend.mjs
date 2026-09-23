/**
 * Integration checks for the medical dashboard's data layer.
 *
 * The project has no component test runner, so this drives the real
 * `src/lib/api.js` and `src/lib/medical.js` against a real Flask backend on a
 * throwaway SQLite database: every request the dashboard makes, the
 * authorization it relies on, the error mapping it shows, and the timeline it
 * renders from. Component rendering is covered by `npm run build`, which
 * compiles and resolves every page, plus the manual pass in the report.
 *
 *   node test_frontend.mjs
 *
 * It starts and stops the backend itself. Nothing touches the development
 * database, and DATABASE_URL is set explicitly so it cannot reach a hosted one.
 */

import { spawn } from 'node:child_process'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = fileURLToPath(new URL('.', import.meta.url))
const BACKEND = join(HERE, '..', 'backend')
const PYTHON = join(BACKEND, '.venv', 'Scripts', 'python.exe')
const PORT = 5199
const failures = []

const check = (label, ok, detail = '') => {
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${label}${ok || detail === '' ? '' : `  (${detail})`}`)
  if (!ok) failures.push(label)
}
const section = (title) => console.log(`\n${title}`)

/** api.js is written for Vite, which replaces import.meta.env at build time.
 *  Node has no such thing, so the two references are substituted here and the
 *  rest of the module — the part under test — is used exactly as it ships. */
async function loadApiModule(dir) {
  const source = await readFile(join(HERE, 'src', 'lib', 'api.js'), 'utf8')
  const shimmed = source
    .replace('import.meta.env.VITE_API_URL', JSON.stringify(`http://127.0.0.1:${PORT}`))
    .replace('import.meta.env.DEV', 'true')
  const path = join(dir, 'api.mjs')
  await writeFile(path, shimmed)
  return import(`file://${path}`)
}

async function waitForBackend() {
  for (let i = 0; i < 120; i++) {
    try {
      const res = await fetch(`http://127.0.0.1:${PORT}/api/health`)
      if (res.ok) return true
    } catch {
      // not listening yet
    }
    await new Promise((r) => setTimeout(r, 500))
  }
  return false
}

const dir = await mkdtemp(join(tmpdir(), 'dogopaw-fe-'))
const dbPath = join(dir, 'fe.db').replaceAll('\\', '/')

// A stub is enough: api.js only uses localStorage to hold the token.
const store = new Map()
globalThis.localStorage = {
  getItem: (k) => store.get(k) ?? null,
  setItem: (k, v) => store.set(k, v),
  removeItem: (k) => store.delete(k),
}

// Started without the debug reloader: `python app.py` restarts itself, which
// doubles the memory footprint and re-imports scikit-learn for no benefit here.
const server = spawn(PYTHON, ['-c',
  `from app import app; app.run(port=${PORT}, debug=False, use_reloader=False)`], {
  cwd: BACKEND,
  env: {
    ...process.env,
    DATABASE_URL: `sqlite:///${dbPath}`,
    APP_ENV: 'development',
    RATE_LIMIT_ENABLED: 'false',
    PORT: String(PORT),
    PYTHONIOENCODING: 'utf-8',
  },
  stdio: ['ignore', 'ignore', 'pipe'],
})
let serverError = ''
server.stderr.on('data', (chunk) => {
  serverError += chunk.toString()
})

try {
  if (!(await waitForBackend())) {
    console.error('backend did not start\n', serverError.slice(-800))
    process.exit(1)
  }

  const { api, ApiError, setToken, clearToken } = await loadApiModule(dir)
  const { buildTimeline, errorMessage, isAuthError, severityStyle } = await import(
    `file://${join(HERE, 'src', 'lib', 'medical.js').replaceAll('\\', '/')}`
  )

  const asAdmin = async () => setToken((await api.login({
    email: 'admin@dogo-paw.org',
    password: 'admin123',
  })).token)
  const asUser = async () => setToken((await api.login({
    email: 'demo@dogo-paw.org',
    password: 'demo123',
  })).token)
  const status = async (fn) => {
    try {
      await fn()
      return 200
    } catch (err) {
      return err.status
    }
  }

  const today = new Date()
  const iso = (offsetDays) => {
    const d = new Date(today)
    d.setDate(d.getDate() + offsetDays)
    return d.toISOString().slice(0, 10)
  }

  // ---------------------------------------------------------------- access
  section('1. Access control')
  clearToken()
  check('anonymous cannot read the admin alert queue', (await status(() => api.adminAlerts())) === 401)
  check('anonymous cannot read a dog medical summary',
    (await status(() => api.medicalSummary(4))) === 401)
  check('anonymous cannot read the health analysis',
    (await status(() => api.healthAnalysis(4))) === 401)
  check('anonymous cannot sync alerts', (await status(() => api.syncAlerts(4))) === 401)

  await asUser()
  check('a normal user cannot open the admin queue',
    (await status(() => api.adminAlerts())) === 403)
  check('a normal user cannot sync alerts', (await status(() => api.syncAlerts(4))) === 403)
  check('a normal user cannot create a medical record',
    (await status(() => api.medicalCreate(4, 'follow-ups', {
      reason: 'x', due_date: iso(7), status: 'pending',
    }))) === 403)
  check('a normal user cannot acknowledge an alert',
    (await status(() => api.acknowledgeAlert(1))) === 403)

  // Public pages must stay public and unchanged.
  clearToken()
  const dogs = await api.dogs()
  check('the public dog list still loads without a token', dogs.count === 18)
  check('public dog rows carry no medical or alert data',
    dogs.dogs.every((d) => !('alerts' in d) && !('risk_score' in d) && !('health_alerts' in d)))
  check('a public dog profile is unchanged',
    !('risk_score' in (await api.dog(4)).dog))

  // ------------------------------------------------------------ dashboard
  section('2. Admin dashboard data')
  await asAdmin()
  const queue = await api.adminAlerts()
  check('the alert queue loads', Array.isArray(queue.alerts))
  check('the queue carries totals for the header tiles',
    typeof queue.totals?.open === 'number'
    && typeof queue.totals?.active_by_severity?.critical === 'number', JSON.stringify(queue.totals))

  // --------------------------------------------------------- medical data
  section('3. Medical data entry')
  const dogId = 4
  const created = []
  const newRecords = {
    'follow-ups': { reason: 'Dashboard test recheck', due_date: iso(-20), status: 'missed' },
    observations: { observation_date: iso(-30), weight_kg: 22.4, temperature_c: 38.5 },
    vaccinations: {
      vaccine_name: 'Rabies', status: 'completed',
      administered_date: iso(-400), next_due_date: iso(-30),
    },
    medications: {
      medication_name: 'Test drug', dosage: '1 tablet', frequency: 'daily',
      start_date: iso(-200), status: 'active',
    },
    records: { title: 'Dashboard test visit', record_type: 'checkup', visit_date: iso(-5) },
  }
  for (const [kind, body] of Object.entries(newRecords)) {
    try {
      const result = await api.medicalCreate(dogId, kind, body)
      created.push(kind)
      check(`admin can create a ${kind} record`, Boolean(result.item?.id))
    } catch (err) {
      check(`admin can create a ${kind} record`, false, err.message)
    }
  }
  // A second observation so a trend exists to draw.
  await api.medicalCreate(dogId, 'observations', {
    observation_date: iso(-2), weight_kg: 20.1, temperature_c: 39.9,
  })

  section('4. Validation errors reach the form')
  const invalid = [
    ['observations', { observation_date: iso(-1), weight_kg: -5 }, 'negative weight'],
    ['observations', { observation_date: iso(-1), temperature_c: 101.5 }, 'Fahrenheit temperature'],
    ['follow-ups', { reason: '', due_date: iso(5), status: 'pending' }, 'missing reason'],
    ['follow-ups', { reason: 'x', due_date: 'not-a-date', status: 'pending' }, 'invalid date'],
    ['vaccinations', { vaccine_name: 'X', status: 'given' }, 'unknown status'],
  ]
  for (const [kind, body, label] of invalid) {
    try {
      await api.medicalCreate(dogId, kind, body)
      check(`${label} is rejected`, false, 'the API accepted it')
    } catch (err) {
      check(`${label} is rejected with a readable message`,
        err.status === 400 && typeof err.message === 'string' && err.message.length > 5
        && !err.message.includes('Traceback'), err.message)
    }
  }

  // ------------------------------------------------------------- analysis
  section('5. Medical detail view')
  const summary = await api.medicalSummary(dogId)
  check('the medical summary loads every section',
    ['dog', 'vaccinations', 'medications', 'recent_observations', 'follow_ups',
      'recent_medical_records', 'counts'].every((k) => k in summary))
  for (const kind of ['records', 'vaccinations', 'medications', 'observations', 'follow-ups']) {
    const list = await api.medicalList(dogId, kind)
    check(`the ${kind} list loads`, Array.isArray(list.items) && list.items.length > 0)
  }

  const analysis = await api.healthAnalysis(dogId)
  check('the health analysis loads', typeof analysis.risk_score === 'number')
  check('it separates findings from data quality',
    Array.isArray(analysis.findings) && Array.isArray(analysis.data_quality.findings))
  check('the score breakdown explains the score',
    analysis.score_breakdown.points_by_finding.length === analysis.findings.length)
  check('every finding has what the card renders',
    analysis.findings.every((f) =>
      f.severity && f.category && f.title && f.reason && f.recommendation && f.evidence))
  check('every severity maps to a known style',
    analysis.findings.every((f) => severityStyle(f.severity).label))
  check('the weight series is present for the chart',
    analysis.data_quality.weight_series.observation_count >= 2)
  check('the temperature monitoring band is reported',
    Array.isArray(analysis.data_quality.temperature_series.monitoring_range_c))

  const timeline = buildTimeline(summary)
  check('the timeline is built from the API data', timeline.length >= 5, timeline.length)
  check('the timeline is newest first',
    timeline.every((e, i) => i === 0 || timeline[i - 1].date >= e.date))
  check('every timeline entry has a date, type and title',
    timeline.every((e) => e.date && e.kind && e.title))

  // --------------------------------------------------------------- alerts
  section('6. Alert workflow')
  const first = await api.syncAlerts(dogId)
  check('running the analysis creates alerts', first.created > 0, JSON.stringify(first).slice(0, 200))
  check('the sync result reports what the button shows',
    ['created', 'updated', 'reopened', 'resolved', 'risk_score', 'risk_level']
      .every((k) => k in first))
  const second = await api.syncAlerts(dogId)
  check('running it again creates nothing new', second.created === 0 && second.updated > 0)

  const dogAlerts = await api.dogAlerts(dogId)
  check('dog alerts are grouped by status',
    ['open', 'acknowledged', 'resolved'].every((k) => Array.isArray(dogAlerts[k])))
  check('the status filter narrows dog alerts',
    (await api.dogAlerts(dogId, 'open')).open.length === dogAlerts.open.length)

  const queued = await api.adminAlerts({ status: 'open', limit: 200 })
  check('the queue shows the new alerts', queued.alerts.length > 0)
  check('the status filter is applied by the API',
    queued.alerts.every((a) => a.status === 'open'))
  const highOnly = await api.adminAlerts({ severity: 'high,critical' })
  check('the severity filter is applied by the API',
    highOnly.alerts.every((a) => ['high', 'critical'].includes(a.severity)))
  const byDog = await api.adminAlerts({ dogId })
  check('the dog filter is applied by the API',
    byDog.alerts.every((a) => a.dog_id === dogId))
  check('an alert carries every column the queue renders',
    queued.alerts.every((a) =>
      a.dog_name && a.severity && a.title && a.category && a.reason
      && a.first_detected_at && a.last_detected_at && a.status
      && typeof a.risk_score_at_detection === 'number'
      && typeof a.detection_count === 'number'))

  const target = queued.alerts[0]
  const acknowledged = await api.acknowledgeAlert(target.id)
  check('acknowledge works', acknowledged.alert.status === 'acknowledged')
  check('acknowledging twice is refused with a conflict',
    (await status(() => api.acknowledgeAlert(target.id))) === 409)

  const resolved = await api.resolveAlert(target.id, 'Booked a vet visit for Friday.')
  check('resolve works', resolved.alert.status === 'resolved')
  check('the resolution note is saved',
    resolved.alert.resolution_note === 'Booked a vet visit for Friday.')
  check('resolving without a note is allowed', Boolean(
    (await api.resolveAlert(queued.alerts[1].id)).alert.resolved_at))


  section('8. ML anomaly section reaches the dashboard')
  // A clean run of weights and temperatures, then one sharp change.
  const mlDogHistory = [
    [-120, 20.0, 38.4], [-100, 20.2, 38.5], [-80, 19.9, 38.6],
    [-60, 20.1, 38.4], [-40, 20.0, 38.5], [-3, 17.2, 40.1],
  ]
  for (const [offset, weight, temperature] of mlDogHistory) {
    await api.medicalCreate(3, 'observations', {
      observation_date: iso(offset), weight_kg: weight, temperature_c: temperature,
    })
  }
  const mlAnalysis = await api.healthAnalysis(3)
  const ml = mlAnalysis.ml_anomalies
  check('the analysis carries an ml_anomalies section', Boolean(ml))
  check('it is available once there is enough history', ml.available === true, ml.reason)
  check('it reports the model version', ml.model_version === 'health-anomaly-v1', ml.model_version)
  check('it flags the unusual observation', ml.anomaly_count >= 1, ml.anomaly_count)
  check('each anomaly carries what the UI renders',
    ml.anomalies.every((a) =>
      a.observation_date && typeof a.anomaly_score === 'number' && a.severity
      && Array.isArray(a.reasons) && a.reasons.length > 0 && a.model_version))
  check('the score is labelled as not a probability',
    ml.score_scale.note.includes('not a probability'))
  check('the section disclaims diagnosis', ml.disclaimer.includes('does not diagnose'))
  check('no reason uses diagnostic language',
    !ml.anomalies.some((a) => /diagnos|disease|illness|infection/i.test(a.reasons.join(' '))))
  check('deterministic findings remain separate from ML output',
    Array.isArray(mlAnalysis.findings)
    && !mlAnalysis.findings.some((f) => f.code.startsWith('ml.')))
  check('the ML layer does not contribute to the risk score',
    !mlAnalysis.score_breakdown.points_by_finding.some((p) => p.code.startsWith('ml.')))

  const shortHistory = await api.healthAnalysis(2)
  check('a dog with too little history reports insufficient_history',
    shortHistory.ml_anomalies.available === false
    && shortHistory.ml_anomalies.reason === 'insufficient_history')
  check('...and the rest of that analysis still works',
    typeof shortHistory.risk_score === 'number')
  check('the summary endpoint reports the ML state',
    (await api.healthAnalysisSummary(3)).ml_anomalies.available === true)

  const mlSync = await api.syncAlerts(3)
  check('a strong anomaly becomes an alert with its own code',
    mlSync.alerts.some((a) => a.finding_code === 'ml.health_anomaly'), mlSync.created)
  check('the ML alert keeps the model version in its evidence',
    mlSync.alerts.filter((a) => a.finding_code === 'ml.health_anomaly')
      .every((a) => a.evidence.model_version === 'health-anomaly-v1'))
  check('re-syncing creates no duplicate ML alert',
    (await api.syncAlerts(3)).created === 0)

  // --------------------------------------------------------- error paths
  section('9. Error handling')
  check('an unknown dog gives 404', (await status(() => api.medicalSummary(9999))) === 404)
  check('an unknown alert gives 404', (await status(() => api.acknowledgeAlert(999999))) === 404)
  const messages = {
    401: 'Your session has expired. Please sign in again.',
    500: 'Something went wrong on the server. Please try again in a moment.',
  }
  for (const [code, expected] of Object.entries(messages)) {
    check(`a ${code} is explained to the user`,
      errorMessage(new ApiError('raw backend text', Number(code))) === expected)
  }
  for (const code of [403, 404, 409, 422]) {
    const message = errorMessage(new ApiError('The backend said this.', code))
    check(`a ${code} keeps the backend's own message`, message === 'The backend said this.')
  }
  check('a session failure is detectable', isAuthError(new ApiError('x', 401))
    && !isAuthError(new ApiError('x', 403)))
  check('no message leaks a stack trace',
    !errorMessage(new ApiError('Traceback (most recent call last): ...', 500)).includes('Traceback'))

  // A revoked token must read as a lost session, not a silent failure.
  await asAdmin()
  await api.logout()
  check('a revoked token gives 401', (await status(() => api.adminAlerts())) === 401)
} finally {
  server.kill()
  // Wait for it to let go of the SQLite file before deleting the directory;
  // Windows refuses to unlink a file another process still has open.
  await new Promise((resolve) => {
    server.once('exit', resolve)
    setTimeout(resolve, 5000)
  })
  await rm(dir, { recursive: true, force: true }).catch(() => {
    // A leftover temp directory is not worth failing the run over.
  })
}

console.log(`\n${failures.length ? `${failures.length} FAILED: ${failures.join(', ')}` : 'all passed'}`)
process.exit(failures.length ? 1 : 0)
