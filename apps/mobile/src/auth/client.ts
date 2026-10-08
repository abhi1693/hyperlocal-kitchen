export const SESSION_KEY = "kitchen.session.v1";
const TOKEN = /^[A-Za-z0-9_-]{43}$/;
export const PHONE = /^\+[1-9][0-9]{7,14}$/;

export type User = { id: string; name: string | null; phone: string | null };
export type AuthDependencies = {
  fetch: typeof fetch;
  get: (key: string) => Promise<string | null>;
  set: (key: string, value: string) => Promise<void>;
  remove: (key: string) => Promise<void>;
  now: () => number;
};
export class AuthError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
  }
}

export function apiOrigin(value: string | undefined, development: boolean): string {
  if (!value) throw new AuthError("Sign-in is unavailable right now. Please try again later.");
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new AuthError("Sign-in is unavailable right now. Please try again later.");
  }
  if (
    (!development && url.protocol !== "https:") ||
    !["http:", "https:"].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    (url.pathname !== "/" && url.pathname !== "")
  ) {
    throw new AuthError("Sign-in is unavailable right now. Please try again later.");
  }
  return url.origin;
}

function userFrom(value: unknown): User {
  if (
    !value ||
    typeof value !== "object" ||
    !("id" in value) ||
    typeof value.id !== "string" ||
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value.id)
  )
    throw new AuthError("Sign-in could not be completed. Please try again.");
  const data = value as Record<string, unknown>;
  if (
    (data.name !== null && typeof data.name !== "string") ||
    (data.phone !== null && typeof data.phone !== "string")
  )
    throw new AuthError("Sign-in could not be completed. Please try again.");
  return { id: value.id, name: data.name as string | null, phone: data.phone as string | null };
}

export class AuthClient {
  private token: string | null = null;
  private signingIn = false;
  private signingOut = false;
  private storageWork: Promise<void> = Promise.resolve();
  constructor(
    readonly origin: string,
    private readonly deps: AuthDependencies,
  ) {}

  private withStorage<T>(work: () => Promise<T>): Promise<T> {
    const result = this.storageWork.then(work);
    this.storageWork = result.then(
      () => undefined,
      () => undefined,
    );
    return result;
  }

  private async request(path: string, body?: unknown, token?: string): Promise<unknown> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20_000);
    try {
      const response = await this.deps.fetch(this.origin + "/api/v1/auth" + path, {
        method: body === undefined ? "GET" : "POST",
        credentials: "omit",
        redirect: "error",
        headers: {
          Accept: "application/json",
          ...(body === undefined ? {} : { "Content-Type": "application/json" }),
          ...(token ? { Authorization: "Bearer " + token } : {}),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });
      if (!response.ok) {
        throw new AuthError(
          response.status === 401
            ? "Please sign in again."
            : response.status === 503
              ? "Sign-in is temporarily unavailable. Please try again."
              : "Sign-in could not be completed. Please try again.",
          response.status,
        );
      }
      return response.status === 204 ? null : await response.json();
    } catch (error) {
      if (error instanceof AuthError) throw error;
      throw new AuthError("Could not connect. Check your connection and try again.");
    } finally {
      clearTimeout(timer);
    }
  }

  async restore(): Promise<User | null> {
    const raw = await this.deps.get(SESSION_KEY);
    if (!raw) return null;
    let stored;
    try {
      stored = JSON.parse(raw);
    } catch {
      await this.deps.remove(SESSION_KEY);
      return null;
    }
    if (
      stored?.origin !== this.origin ||
      typeof stored?.token !== "string" ||
      !TOKEN.test(stored.token)
    ) {
      await this.deps.remove(SESSION_KEY);
      return null;
    }
    this.token = stored.token;
    return this.refresh();
  }

  async refresh(): Promise<User | null> {
    if (!this.token) return null;
    const token = this.token;
    try {
      const user = userFrom(await this.request("/me", undefined, token));
      return token === this.token ? user : this.refresh();
    } catch (error) {
      if (token !== this.token) return this.refresh();
      if (error instanceof AuthError && error.status === 401) {
        const cleared = await this.withStorage(async () => {
          if (token !== this.token) return false;
          await this.deps.remove(SESSION_KEY);
          this.token = null;
          return true;
        });
        return cleared ? null : this.refresh();
      }
      throw error;
    }
  }

  async signInWithPhone(phone: string): Promise<User> {
    if (!PHONE.test(phone))
      throw new AuthError("Enter a valid phone number including its country code.");
    if (this.signingIn || this.signingOut) throw new AuthError("Sign-in is already in progress.");
    this.signingIn = true;
    try {
      const config = (await this.request("/config")) as { phone_login_enabled?: unknown };
      if (config?.phone_login_enabled !== true)
        throw new AuthError("Phone sign-in is not available right now. Please try again later.");
      const result = await this.request("/mobile/phone", { phone });
      return await this.saveSession(result);
    } finally {
      this.signingIn = false;
    }
  }

  private async saveSession(value: unknown): Promise<User> {
    const result = value as { session_token?: unknown; expires_at?: unknown; user?: unknown };
    if (
      !result ||
      typeof result.session_token !== "string" ||
      !TOKEN.test(result.session_token) ||
      typeof result.expires_at !== "number" ||
      !Number.isFinite(result.expires_at) ||
      result.expires_at * 1000 <= this.deps.now()
    )
      throw new AuthError("Sign-in could not be completed. Please try again.");
    const user = userFrom(result.user);
    const token = result.session_token;
    try {
      await this.withStorage(async () => {
        await this.deps.set(SESSION_KEY, JSON.stringify({ origin: this.origin, token }));
        this.token = token;
      });
    } catch {
      // Revoke the newly issued server session if the device cannot persist it.
      await this.request("/logout", {}, result.session_token).catch(() => undefined);
      throw new AuthError("Could not save your sign-in. Please try again.");
    }
    return user;
  }

  async signOut(): Promise<void> {
    if (this.signingIn || this.signingOut)
      throw new AuthError("Please finish or cancel sign-in first.");
    this.signingOut = true;
    try {
      if (this.token) await this.request("/logout", {}, this.token);
      await this.withStorage(async () => {
        await this.deps.remove(SESSION_KEY);
        this.token = null;
      });
    } finally {
      this.signingOut = false;
    }
  }
}
