import { apiRequest } from "./client";
import type { components } from "./generated";

export type ClassificationQueueItem = components["schemas"]["ClassificationQueueItem"];
export type PartMapping = components["schemas"]["PartMapping"];
export type ClassificationReview = components["schemas"]["ClassificationReviewRequest"];
export type ClassificationExpectation = components["schemas"]["ClassificationVerificationRequest"];
export type ClassificationDispute = components["schemas"]["ClassificationDisputeRequest"];
export type ClassificationResolution = components["schemas"]["ClassificationResolveRequest"];
export type ClassificationResult = components["schemas"]["ClassificationRevisionResult"];
export type ClassificationHistory = components["schemas"]["ClassificationHistoryItem"];
const base = "/api/v1/curate/classifications";
const post = <T>(path: string, body: unknown) => apiRequest<T>(`${base}${path}`, { method: "POST", body: JSON.stringify(body) });
export const classificationApi = {
  queue: (filters: Record<string, string>) => apiRequest<ClassificationQueueItem[]>(`${base}?${new URLSearchParams(filters)}`),
  review: (suggestion: number, body: ClassificationReview) => post<ClassificationResult>(`/${suggestion}/review`, body),
  history: (question: string) => apiRequest<ClassificationHistory[]>(`${base}/questions/${encodeURIComponent(question)}/history`),
  verify: (question: string, body: ClassificationExpectation) => post<ClassificationResult>(`/questions/${encodeURIComponent(question)}/verify`, body),
  withdraw: (question: string, body: ClassificationExpectation) => post<ClassificationResult>(`/questions/${encodeURIComponent(question)}/withdraw`, body),
  dispute: (question: string, body: ClassificationDispute) => post<ClassificationResult>(`/questions/${encodeURIComponent(question)}/disputes`, body),
  disputes: (question: string) => apiRequest<components["schemas"]["ClassificationDisputeResult"][]>(`${base}/questions/${encodeURIComponent(question)}/disputes`),
  resolve: (dispute: number, body: ClassificationResolution) => post<ClassificationResult>(`/disputes/${dispute}/resolve`, body),
  bulk: (reviews: ClassificationReview[]) => post<components["schemas"]["ClassificationBulkResult"]>("/bulk", { reviews }),
};
