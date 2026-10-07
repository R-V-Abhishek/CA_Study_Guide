import type { WhyData } from '../lib/contracts';
import { importance } from '../lib/data';

const signal = (value: number | null | undefined) => value == null ? 'Unavailable' : value.toFixed(2);
export function ScoreExplanation({ data }: { data: WhyData }) {
  const evidence = data as WhyData & { historical_evidence_status?: string | null };
  const breakdown = data.importance_breakdown;
  const weights = breakdown.weights;
  const rows = [
    { label: 'Exam E', normalized: breakdown.exam?.normalized_E_pct, weight: weights?.exam, contribution: breakdown.exam?.weighted_contribution_pct, reason: breakdown.exam?.unavailable_reason },
    { label: 'Practice P', normalized: breakdown.practice?.normalized_P_pct, weight: weights?.practice, contribution: breakdown.practice?.weighted_contribution_pct, reason: breakdown.practice?.unavailable_reason },
    { label: 'Official prior W', normalized: breakdown.weightage_prior?.normalized_W_pct, weight: weights?.prior, contribution: breakdown.weightage_prior?.weighted_contribution_pct, reason: breakdown.weightage_prior?.unavailable_reason },
  ];
  const hasComponents = !!(breakdown.exam || breakdown.practice || breakdown.weightage_prior);
  return <div className="space-y-3"><p>Run {data.score_run?.id ?? 'Unavailable'} · {data.score_run?.version ?? 'Unavailable'} · Target {data.score_run?.target_attempt_id ?? 'Unavailable'} · {data.score_run?.computed_at ?? 'Timestamp unavailable'}</p>
    <p>Importance: {importance(breakdown.importance)}</p>
    {evidence.historical_evidence_status === 'occurrence_inputs_unavailable' && <p>Historical occurrence inputs were not retained. Recorded snapshot components are shown.</p>}
    {data.explanation_status === 'historical_configuration_unavailable' && <p>Historical configuration unavailable. Recorded importance is preserved; derived contributions are unavailable.</p>}
    {breakdown.formula && <p>Snapshot formula: {breakdown.formula}</p>}
    {hasComponents ? <><table className="w-full text-left text-sm"><caption>Normalized signals (0–100); unavailable components retain their configured weights</caption><thead><tr><th>Signal</th><th>Normalized</th><th>Weight</th><th>Weighted contribution</th></tr></thead><tbody>{rows.map(row => <tr key={row.label}><td>{row.label}</td><td>{signal(row.normalized)}</td><td>{signal(row.weight)}</td><td>{signal(row.contribution)}</td></tr>)}</tbody></table>{rows.filter(row => row.reason).map(row => <p key={row.label}>{row.label}: {row.reason}</p>)}<p>Raw exam signal: {signal(breakdown.exam?.score_E)} (decayed marks); raw practice signal: {signal(breakdown.practice?.score_P)} (decayed marks); raw official prior: {signal(breakdown.weightage_prior?.weight_prior_W)}.</p></> : data.explanation_status !== 'historical_configuration_unavailable' && <p>{data.error ?? 'Score explanation unavailable.'}</p>}
    {breakdown.importance == null && breakdown.known_weighted_subtotal != null && <p>Known weighted subtotal: {importance(breakdown.known_weighted_subtotal)} · Partial evidence; full importance requires all components.</p>}
    {data.frequency && <p>{data.frequency.available ? `Frequency: ${data.frequency.freq_hits_F} hits in ${data.frequency.freq_window} usable reviewed paper-attempts. Included attempts: ${data.frequency.window_attempts.join(', ')}.` : 'Frequency unavailable: no usable reviewed denominator.'}</p>}
    {data.appearances.length > 0 && <details><summary>Recorded scoring contributions</summary>{data.appearances.map((item, index) => <p key={index}>{'occurrence_id' in item ? `Occurrence ${item.occurrence_id} · Snapshot ${item.snapshot_id} · Part ${item.part_id}` : `Appearance ${item.appearance_id} · ${item.display_label}`} · {item.attempt_id} · {item.signal_class} · Attributed {signal(item.attributed_marks_m)} marks · Decay {signal(item.decay)} · Raw contribution {signal(item.contribution)}</p>)}</details>}
    {data.coverage_exclusions?.length ? <details><summary>Coverage exclusions</summary>{data.coverage_exclusions.map(item => <p key={`${item.paper_id}:${item.attempt_id}`}>{item.paper_id} · {item.attempt_id}: {item.reasons.join('; ')}</p>)}</details> : null}
  </div>;
}
