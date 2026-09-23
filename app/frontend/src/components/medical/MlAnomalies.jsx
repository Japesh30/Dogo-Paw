import { fmtDate, severityStyle } from '../../lib/medical'
import { EmptyState } from './Pills'

/** Why the model could not say anything, in words an admin can act on. */
const UNAVAILABLE = {
  insufficient_history:
    'Not enough historical observations for anomaly detection. Record more weights and temperatures over time and it will start working.',
  model_unavailable:
    'The anomaly model is not available on this server, so no scoring was done. Everything else on this page is unaffected.',
  scoring_failed:
    'The anomaly model could not score these observations. Everything else on this page is unaffected.',
}

/**
 * The machine-learning layer, kept visually and verbally distinct from the
 * deterministic findings above it.
 *
 * Rules state a fact ("weight declined by >= 10%"). This states a comparison
 * ("this reading is unlike the dog's recent ones"). The heading, the wording
 * and the disclaimer all say so, and no score here is ever presented as a
 * probability or a likelihood of illness.
 */
export default function MlAnomalies({ ml }) {
  if (!ml) {
    return <EmptyState>Anomaly detection results were not loaded.</EmptyState>
  }

  if (!ml.available) {
    return (
      <div>
        <EmptyState>
          {UNAVAILABLE[ml.reason] ??
            'Anomaly detection is unavailable for this dog right now.'}
        </EmptyState>
        {ml.reason === 'insufficient_history' && ml.observations_required && (
          <p className="text-stone-neutral mt-2 text-xs">
            {ml.observations_available ?? 0} of {ml.observations_required} observations
            needed.
          </p>
        )}
      </div>
    )
  }

  return (
    <div>
      <p className="border-bark-100 bg-bark-50/60 text-stone-neutral rounded-xl border px-4 py-3 text-sm">
        This model identifies unusual patterns in this dog&rsquo;s historical health
        observations. <span className="text-bark-900 font-semibold">It does not
        diagnose disease</span>, and an anomaly score is not a probability of illness.
        Findings above come from fixed rules; the results here come from the model.
      </p>

      <dl className="text-stone-neutral mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
        <div>
          <dt className="font-semibold">Model</dt>
          <dd>{ml.model_version}</dd>
        </div>
        <div>
          <dt className="font-semibold">Observations scored</dt>
          <dd className="tabular-nums">{ml.observations_scored}</dd>
        </div>
        <div>
          <dt className="font-semibold">Unusual patterns</dt>
          <dd className="tabular-nums">{ml.anomaly_count}</dd>
        </div>
        <div>
          <dt className="font-semibold">Trained on</dt>
          <dd>{ml.trained_on}</dd>
        </div>
      </dl>

      {!ml.anomalies.length ? (
        <div className="mt-4">
          <EmptyState>
            No unusual health patterns detected in the available observation history.
          </EmptyState>
        </div>
      ) : (
        <ul className="mt-4 space-y-3">
          {ml.anomalies.map((anomaly) => {
            const style = severityStyle(anomaly.severity)
            return (
              <li key={anomaly.observation_id} className="border-bark-100 rounded-xl border p-4">
                <div className="flex flex-wrap items-center gap-2">
                  {/* The level is spelled out, never colour alone. */}
                  <span
                    className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-bold tracking-wide uppercase ${style.badge}`}
                  >
                    {style.label} anomaly
                  </span>
                  <span className="bg-bark-50 rounded-full px-2.5 py-1 text-[11px] font-semibold">
                    Observation {fmtDate(anomaly.observation_date)}
                  </span>
                  <span className="text-stone-neutral ml-auto text-xs">
                    Anomaly score{' '}
                    <span className="text-bark-900 font-semibold tabular-nums">
                      {anomaly.anomaly_score}
                    </span>{' '}
                    <span className="whitespace-nowrap">(not a probability)</span>
                  </span>
                </div>

                <p className="text-bark-900 mt-2 text-sm font-semibold">
                  Unusual compared with this dog&rsquo;s recent observations
                </p>

                <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm">
                  {anomaly.reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>

                <p className="text-stone-neutral mt-2 text-xs">
                  Based on {anomaly.measurements_considered.join(' and ')} · model{' '}
                  {anomaly.model_version}
                </p>
              </li>
            )
          })}
        </ul>
      )}

      {ml.score_scale && (
        <p className="text-stone-neutral mt-3 text-xs">
          Higher scores mean further from this dog&rsquo;s usual pattern. {ml.score_scale.note}
        </p>
      )}
    </div>
  )
}
