import { createCuratorClient } from "@caf/api-client";

export const curatorClient = createCuratorClient({ baseUrl: "" });

export function requiredData<T>(result: { data?: T; response: Response }): T {
  if (!result.response.ok) throw new Error(`Request failed (${result.response.status})`);
  if (result.data === undefined) throw new Error("The API returned no response data.");
  return result.data;
}
