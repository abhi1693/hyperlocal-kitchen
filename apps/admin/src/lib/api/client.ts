/** Same-origin Orval transport, adapted from DevFeed's admin client. */
let csrfToken: string | undefined;
export function setCsrfToken(value: string | undefined) {
  csrfToken = value;
}
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public fields: Record<string, string> = {},
  ) {
    super(message);
  }
}
export type ErrorType<T> = ApiError;
export type BodyType<T> = T;
export async function adminFetch<T>(url: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (!["GET", "HEAD", "OPTIONS"].includes((options.method ?? "GET").toUpperCase()) && csrfToken)
    headers.set("X-CSRF-Token", csrfToken);
  const response = await fetch(url, {
    ...options,
    headers,
    credentials: "same-origin",
    cache: "no-store",
    redirect: "error",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const fields: Record<string, string> = {};
    if (Array.isArray(body?.detail))
      for (const issue of body.detail) {
        if (Array.isArray(issue.loc) && typeof issue.msg === "string")
          fields[issue.loc.slice(1).join(".")] = issue.msg;
      }
    const message =
      response.status === 401
        ? "Your session has expired. Sign in again."
        : response.status >= 500
          ? "The admin service is unavailable. Try again."
          : typeof body?.detail?.message === "string"
            ? body.detail.message
            : Object.keys(fields).length
              ? "Please correct the form fields."
              : "This action could not be completed.";
    if (
      response.status === 401 &&
      typeof window !== "undefined" &&
      window.location.pathname !== "/login"
    ) {
      setCsrfToken(undefined);
      window.location.replace("/login");
    }
    throw new ApiError(response.status, message, fields);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
