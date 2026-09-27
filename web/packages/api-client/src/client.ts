import createClient, { type ClientOptions } from "openapi-fetch";
import type { paths } from "./generated";

export interface ApiClientConfig extends ClientOptions {
  baseUrl?: string;
  curatorToken?: string;
}

/**
 * Creates a typed fetch client for student-facing routes.
 * Base URL defaults to window.location.origin or relative `/api/v1`.
 */
export function createStudentClient(config: ApiClientConfig = {}) {
  const baseUrl = config.baseUrl ?? "";
  return createClient<paths>({
    baseUrl,
    headers: {
      "Content-Type": "application/json",
      ...config.headers,
    },
    ...config,
  });
}

/**
 * Creates a typed fetch client for curator-facing routes.
 * Automatically injects the X-Curator-Token header.
 */
export function createCuratorClient(config: ApiClientConfig = {}) {
  const baseUrl = config.baseUrl ?? "";
  const token = config.curatorToken ?? (typeof window !== "undefined" ? localStorage.getItem("caf_curator_token") || "curator-dev-token" : "curator-dev-token");
  
  return createClient<paths>({
    baseUrl,
    headers: {
      "Content-Type": "application/json",
      "X-Curator-Token": token,
      ...config.headers,
    },
    ...config,
  });
}

export type StudentClient = ReturnType<typeof createStudentClient>;
export type CuratorClient = ReturnType<typeof createCuratorClient>;
