import { useQuery } from "@tanstack/react-query";
import { accountKey } from "@caf/api-client";
import { taxonomyApi, type PendingDescriptorReview } from "@caf/api-client/src/taxonomy";
import { isDemoMode } from "./demo";

/** Descriptor changes by other students that need this account's second review. */
export function usePendingReviews() {
  return useQuery({
    queryKey: ["pending-reviews", accountKey()],
    queryFn: taxonomyApi.pendingReviews,
    enabled: !isDemoMode(),
    refetchInterval: 5 * 60_000,
  });
}

export const reviewLink = (item: PendingDescriptorReview) =>
  `/curator/textbooks?version=${encodeURIComponent(item.version_id)}&node=${encodeURIComponent(item.node_id)}`;
