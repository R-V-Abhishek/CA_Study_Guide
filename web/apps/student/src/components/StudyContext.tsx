import type { components } from '@caf/api-client';
export interface StudyContextFields { context?: components['schemas']['StudyContextIdentity'] | null; freshness?: components['schemas']['ScoreFreshness'] | null }
export function StudyContext({ data }: { data: StudyContextFields }) {
  return <div className="study-meta">{data.freshness && <p>Scores: {data.freshness.status.replace(/_/g, ' ')}{data.freshness.computed_at && ` · Computed ${data.freshness.computed_at}`}</p>}{data.freshness?.error && <p role="alert">Score refresh failed: {data.freshness.error}</p>}<details><summary>Technical details</summary>{data.context && <p>Target {data.context.target_attempt_id ?? 'Unavailable'} · Taxonomy {data.context.taxonomy_version_id ?? 'Unavailable'} · Readiness: {data.context.readiness.replace(/_/g, ' ')}</p>}{data.freshness && <p>Published generation {data.freshness.publication_generation} · Scored generation {data.freshness.scored_generation ?? 'Unavailable'}</p>}</details></div>;
}
