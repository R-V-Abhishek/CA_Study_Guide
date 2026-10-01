import createClient, { type ClientOptions } from "openapi-fetch";
import type { paths } from "./generated";

export class ApiError extends Error {
  constructor(message: string, public readonly status?: number) {
    super(message);
    this.name = "ApiError";
  }
}

async function checkedResponse(response: Response): Promise<Response> {
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.clone().json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      // Keep the HTTP status when a proxy returns a non-JSON error page.
    }
    throw new ApiError(`Request failed (${response.status}): ${detail}`, response.status);
  }
  return response;
}

/** Shared HTTP boundary: failed responses never become successful query data. */
export async function apiRequest<T>(url: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, {
      ...options,
      headers: { "Content-Type": "application/json", ...options.headers },
    });
  } catch (error) {
    throw new ApiError(error instanceof Error ? error.message : "Network request failed");
  }
  await checkedResponse(response);
  return response.status === 204 ? undefined as T : response.json();
}

const errorMiddleware = {
  onResponse: async ({ response }: { response: Response }) => checkedResponse(response),
};

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
  const client = createClient<paths>({
    baseUrl,
    headers: {
      "Content-Type": "application/json",
      ...config.headers,
    },
    ...config,
  });
  client.use(errorMiddleware);
  return client;
}

/**
 * Creates a typed fetch client for curator-facing routes.
 * Automatically injects the X-Curator-Token header.
 */
export function createCuratorClient(config: ApiClientConfig = {}) {
  const baseUrl = config.baseUrl ?? "";
  const token = config.curatorToken ?? (typeof window !== "undefined" ? localStorage.getItem("caf_curator_token") || "curator-dev-token" : "curator-dev-token");
  
  const client = createClient<paths>({
    baseUrl,
    headers: {
      "Content-Type": "application/json",
      "X-Curator-Token": token,
      ...config.headers,
    },
    ...config,
  });
  client.use(errorMiddleware);
  return client;
}

export type StudentClient = ReturnType<typeof createStudentClient>;
export type CuratorClient = ReturnType<typeof createCuratorClient>;
