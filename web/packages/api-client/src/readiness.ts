import { apiRequest } from './client';
import type { components } from './generated';

export type SourceEvidence = components['schemas']['TextbookEvidence'] | components['schemas']['DocumentEvidence'];
export type BindingRecord = components['schemas']['BindingRecord'];
export type InventoryRecord = components['schemas']['InventoryRecord'];
export type PriorRecord = components['schemas']['PriorRecord'];
export type ReadinessTask = components['schemas']['ReadinessTask'];
export type ReadinessSummary = components['schemas']['ReadinessSummary'];
export type AuditDecision = components['schemas']['AuditDecision'];
export type BindingWrite = components['schemas']['BindingWrite'];
export type InventoryWrite = components['schemas']['InventoryWrite'];
export type PriorWrite = components['schemas']['PriorWrite'];
export type ReadinessWriteResult = components['schemas']['ReadinessWriteResult'];
export interface ReadinessFilters {
  target_attempt_id?: string;
  taxonomy_version_id?: number;
  paper_id?: string;
  source_family?: string;
  blocker_type?: string;
}
const base = '/api/v1/admin/readiness';
export const readinessApi = {
  summary(filters: ReadinessFilters = {}, signal?: AbortSignal): Promise<ReadinessSummary> {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value !== undefined && value !== '') query.set(key, String(value));
    }
    return apiRequest(`${base}?${query}`, { signal });
  },
  binding(body: BindingWrite): Promise<ReadinessWriteResult> {
    return apiRequest(`${base}/bindings`, { method: 'PUT', body: JSON.stringify(body) });
  },
  inventory(body: InventoryWrite): Promise<ReadinessWriteResult> {
    return apiRequest(`${base}/inventory`, { method: 'PUT', body: JSON.stringify(body) });
  },
  prior(body: PriorWrite): Promise<ReadinessWriteResult> {
    return apiRequest(`${base}/priors`, { method: 'PUT', body: JSON.stringify(body) });
  },
};
