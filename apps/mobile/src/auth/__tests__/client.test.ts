/// <reference types="jest" />

import {
  apiOrigin,
  AuthClient,
  AuthError,
  SESSION_KEY,
  type AuthDependencies,
  type User,
} from "../client";

const ORIGIN = "https://api.kitchen.example";
const NOW = 1_750_000_000_000;
const TOKEN = "t".repeat(43);
const PHONE = "+919876543210";
const USER: User = {
  id: "98db36de-8d46-4a42-851b-25a24a66d590",
  name: "Resident",
  phone: PHONE,
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((finish) => { resolve = finish; });
  return { promise, resolve };
}

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

function setup() {
  const storage = new Map<string, string>();
  const fetchMock = jest.fn<Promise<Response>, [input: RequestInfo | URL, init?: RequestInit]>();
  const deps = {
    fetch: fetchMock,
    get: jest.fn(async (key: string) => storage.get(key) ?? null),
    set: jest.fn(async (key: string, value: string) => {
      storage.set(key, value);
    }),
    remove: jest.fn(async (key: string) => {
      storage.delete(key);
    }),
    now: jest.fn(() => NOW),
  } satisfies AuthDependencies;
  const client = new AuthClient(ORIGIN, deps);
  const session = (changes: Record<string, unknown> = {}) => {
    storage.set(SESSION_KEY, JSON.stringify({ origin: ORIGIN, token: TOKEN, ...changes }));
  };
  const issued = (changes: Record<string, unknown> = {}) =>
    response({ session_token: TOKEN, expires_at: NOW / 1000 + 3600, user: USER, ...changes });
  return { client, deps, fetchMock, storage, session, issued };
}

describe("API origin configuration", () => {
  it("accepts HTTPS in production and loopback HTTP during development", () => {
    expect(apiOrigin(`${ORIGIN}/`, false)).toBe(ORIGIN);
    expect(apiOrigin("http://127.0.0.1:8000", true)).toBe("http://127.0.0.1:8000");
  });

  it.each([
    undefined,
    "",
    "not a URL",
    "http://api.kitchen.example",
    "https://user:password@api.kitchen.example",
    `${ORIGIN}/api`,
    `${ORIGIN}?token=secret`,
    `${ORIGIN}#fragment`,
    "file:///api",
  ])("rejects an unsafe or missing production origin: %s", (value) => {
    expect(() => apiOrigin(value, false)).toThrow(AuthError);
  });
});

describe("session restoration and refresh", () => {
  it("does not make authenticated requests without a saved session", async () => {
    const { client, fetchMock } = setup();
    await expect(client.restore()).resolves.toBeNull();
    await expect(client.refresh()).resolves.toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("restores the matching-origin token and fetches the current profile", async () => {
    const { client, session, fetchMock } = setup();
    session();
    fetchMock.mockResolvedValueOnce(response(USER));
    await expect(client.restore()).resolves.toEqual(USER);
    expect(fetchMock).toHaveBeenCalledWith(
      `${ORIGIN}/api/v1/auth/me`,
      expect.objectContaining({
        method: "GET",
        credentials: "omit",
        redirect: "error",
        headers: { Accept: "application/json", Authorization: `Bearer ${TOKEN}` },
      }),
    );
  });

  it.each([
    "{invalid json",
    "null",
    JSON.stringify({ origin: "https://different.example", token: TOKEN }),
    JSON.stringify({ origin: ORIGIN, token: "invalid" }),
    JSON.stringify({ origin: ORIGIN, token: 123 }),
  ])("removes invalid or foreign-origin stored tokens without sending them: %s", async (raw) => {
    const { client, storage, fetchMock } = setup();
    storage.set(SESSION_KEY, raw);
    await expect(client.restore()).resolves.toBeNull();
    expect(storage.has(SESSION_KEY)).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("removes a revoked session on 401 and stops subsequent authenticated requests", async () => {
    const { client, session, fetchMock, storage } = setup();
    session();
    fetchMock.mockResolvedValueOnce(response({}, 401));
    await expect(client.restore()).resolves.toBeNull();
    expect(storage.has(SESSION_KEY)).toBe(false);
    await expect(client.refresh()).resolves.toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("keeps a saved session during a network outage and can retry refresh", async () => {
    const { client, session, fetchMock, storage } = setup();
    session();
    fetchMock.mockRejectedValueOnce(new Error("network failed"));
    await expect(client.restore()).rejects.toThrow("Could not connect");
    expect(JSON.parse(storage.get(SESSION_KEY)!)).toEqual({ origin: ORIGIN, token: TOKEN });
    fetchMock.mockResolvedValueOnce(response(USER));
    await expect(client.refresh()).resolves.toEqual(USER);
  });

  it("keeps a saved session if the server is temporarily unavailable", async () => {
    const { client, session, fetchMock, storage } = setup();
    session();
    fetchMock.mockResolvedValueOnce(response({}, 503));
    await expect(client.restore()).rejects.toMatchObject({ status: 503 });
    expect(storage.has(SESSION_KEY)).toBe(true);
  });

  it("does not clear a newer login when an earlier profile request returns 401", async () => {
    const { client, session, fetchMock, storage, issued } = setup();
    session();
    fetchMock.mockResolvedValueOnce(response(USER));
    await client.restore();
    const oldResponse = deferred<Response>();
    fetchMock.mockImplementationOnce(() => oldResponse.promise);
    const refreshing = client.refresh();

    const newToken = "n".repeat(43);
    const newUser = { ...USER, name: "New account" };
    fetchMock.mockResolvedValueOnce(response({ phone_login_enabled: true }));
    fetchMock.mockResolvedValueOnce(issued({ session_token: newToken, user: newUser }));
    await expect(client.signInWithPhone(PHONE)).resolves.toEqual(newUser);
    fetchMock.mockResolvedValueOnce(response(newUser));
    oldResponse.resolve(response({}, 401));

    await expect(refreshing).resolves.toEqual(newUser);
    expect(JSON.parse(storage.get(SESSION_KEY)!)).toEqual({ origin: ORIGIN, token: newToken });
    expect(fetchMock).toHaveBeenLastCalledWith(
      `${ORIGIN}/api/v1/auth/me`,
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: `Bearer ${newToken}` }),
      }),
    );
  });

  it.each([null, {}, { ...USER, id: "malformed" }, { ...USER, name: false }])(
    "rejects invalid profile data: %j",
    async (profile) => {
      const { client, session, fetchMock, storage } = setup();
      session();
      fetchMock.mockResolvedValueOnce(response(profile));
      await expect(client.restore()).rejects.toBeInstanceOf(AuthError);
      expect(storage.has(SESSION_KEY)).toBe(true);
    },
  );

  it("allows account profiles without a name or phone", async () => {
    const { client, session, fetchMock } = setup();
    const user = { id: USER.id, name: null, phone: null };
    session();
    fetchMock.mockResolvedValueOnce(response(user));
    await expect(client.restore()).resolves.toEqual(user);
  });
});

describe("session storage concurrency", () => {
  it("persists a new phone session after an older 401 deletion finishes", async () => {
    const { client, deps, session, fetchMock, storage, issued } = setup();
    session();
    fetchMock.mockResolvedValueOnce(response(USER));
    await client.restore();

    const deletion = deferred<void>();
    deps.remove.mockImplementationOnce(async (key) => {
      await deletion.promise;
      storage.delete(key);
    });
    fetchMock.mockResolvedValueOnce(response({}, 401));
    const oldRefresh = client.refresh();
    while (deps.remove.mock.calls.length === 0) await Promise.resolve();

    const newToken = "n".repeat(43);
    fetchMock.mockResolvedValueOnce(response({ phone_login_enabled: true }));
    fetchMock.mockResolvedValueOnce(issued({ session_token: newToken }));
    const signingIn = client.signInWithPhone(PHONE);
    while (fetchMock.mock.calls.length < 4) await Promise.resolve();
    expect(deps.set).not.toHaveBeenCalled();
    deletion.resolve(undefined);

    await expect(oldRefresh).resolves.toBeNull();
    await expect(signingIn).resolves.toEqual(USER);
    expect(JSON.parse(storage.get(SESSION_KEY)!)).toEqual({ origin: ORIGIN, token: newToken });
    fetchMock.mockResolvedValueOnce(response(USER));
    await expect(client.refresh()).resolves.toEqual(USER);
  });

  it("does not delete a newer phone session while its secure-store write is in flight", async () => {
    const { client, deps, session, fetchMock, storage, issued } = setup();
    session();
    fetchMock.mockResolvedValueOnce(response(USER));
    await client.restore();
    const oldResponse = deferred<Response>();
    fetchMock.mockImplementationOnce(() => oldResponse.promise);
    const oldRefresh = client.refresh();

    const write = deferred<void>();
    deps.set.mockImplementationOnce(async (key, value) => {
      await write.promise;
      storage.set(key, value);
    });
    const newToken = "n".repeat(43);
    fetchMock.mockResolvedValueOnce(response({ phone_login_enabled: true }));
    fetchMock.mockResolvedValueOnce(issued({ session_token: newToken }));
    const signingIn = client.signInWithPhone(PHONE);
    while (deps.set.mock.calls.length === 0) await Promise.resolve();
    fetchMock.mockResolvedValueOnce(response(USER));
    oldResponse.resolve(response({}, 401));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(deps.remove).not.toHaveBeenCalled();
    write.resolve(undefined);

    await expect(signingIn).resolves.toEqual(USER);
    await expect(oldRefresh).resolves.toEqual(USER);
    expect(deps.remove).not.toHaveBeenCalled();
    expect(JSON.parse(storage.get(SESSION_KEY)!)).toEqual({ origin: ORIGIN, token: newToken });
  });
});

describe("sign-out", () => {
  it("revokes the server session before clearing local credentials", async () => {
    const { client, session, fetchMock, storage } = setup();
    session();
    fetchMock.mockResolvedValueOnce(response(USER));
    await client.restore();
    fetchMock.mockResolvedValueOnce(response(null, 204));

    await expect(client.signOut()).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenLastCalledWith(
      `${ORIGIN}/api/v1/auth/logout`,
      expect.objectContaining({
        method: "POST",
        body: "{}",
        headers: expect.objectContaining({ Authorization: `Bearer ${TOKEN}` }),
      }),
    );
    expect(storage.has(SESSION_KEY)).toBe(false);
    await expect(client.refresh()).resolves.toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("preserves credentials when server sign-out fails, allowing a retry", async () => {
    const { client, session, fetchMock, storage } = setup();
    session();
    fetchMock.mockResolvedValueOnce(response(USER));
    await client.restore();
    fetchMock.mockRejectedValueOnce(new Error("offline"));
    await expect(client.signOut()).rejects.toThrow("Could not connect");
    expect(storage.has(SESSION_KEY)).toBe(true);
    fetchMock.mockResolvedValueOnce(response(null, 204));
    await expect(client.signOut()).resolves.toBeUndefined();
    expect(storage.has(SESSION_KEY)).toBe(false);
  });

  it("can clear local state without sending an unauthenticated logout request", async () => {
    const { client, fetchMock, storage } = setup();
    await expect(client.signOut()).resolves.toBeUndefined();
    expect(storage.size).toBe(0);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("prevents a new sign-in or second sign-out while logout is pending", async () => {
    const { client, session, fetchMock } = setup();
    session();
    fetchMock.mockResolvedValueOnce(response(USER));
    await client.restore();
    const logout = deferred<Response>();
    fetchMock.mockImplementationOnce(() => logout.promise);
    const signingOut = client.signOut();
    await expect(client.signInWithPhone(PHONE)).rejects.toThrow("already in progress");
    await expect(client.signOut()).rejects.toBeInstanceOf(AuthError);
    logout.resolve(response(null, 204));
    await expect(signingOut).resolves.toBeUndefined();
    await expect(client.refresh()).resolves.toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("allows retry when local credential deletion fails", async () => {
    const { client, deps, session, fetchMock, storage } = setup();
    session();
    fetchMock.mockResolvedValueOnce(response(USER));
    await client.restore();
    fetchMock.mockResolvedValueOnce(response(null, 204));
    deps.remove.mockRejectedValueOnce(new Error("device storage is busy"));
    await expect(client.signOut()).rejects.toThrow("device storage is busy");
    expect(storage.has(SESSION_KEY)).toBe(true);
    fetchMock.mockResolvedValueOnce(response(null, 204));
    await expect(client.signOut()).resolves.toBeUndefined();
    expect(storage.has(SESSION_KEY)).toBe(false);
  });
});

describe("native phone sign-in", () => {
  const phone = PHONE;

  it.each([
    "",
    "9876543210",
    "+91987654321a",
    "+91 9876543210",
    "+019876543210",
    "+1234567890123456",
  ])("rejects a malformed E.164 phone without sending any request: %s", async (value) => {
    const { client, fetchMock } = setup();
    await expect(client.signInWithPhone(value)).rejects.toBeInstanceOf(AuthError);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([
    null,
    {},
    { enabled: true },
    { phone_login_enabled: false },
    { phone_login_enabled: "true" },
    { phone_login_enabled: 1 },
  ])("does not send the phone number when phone sign-in is unavailable: %j", async (config) => {
    const { client, fetchMock, storage } = setup();
    fetchMock.mockResolvedValueOnce(response(config));
    await expect(client.signInWithPhone(phone)).rejects.toBeInstanceOf(AuthError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe(`${ORIGIN}/api/v1/auth/config`);
    expect(fetchMock.mock.calls[0][1]?.body).toBeUndefined();
    expect(storage.has(SESSION_KEY)).toBe(false);
  });

  it("sends only the phone number and persists the returned session", async () => {
    const { client, fetchMock, storage, issued } = setup();
    fetchMock.mockResolvedValueOnce(response({ phone_login_enabled: true }));
    fetchMock.mockResolvedValueOnce(issued());

    await expect(client.signInWithPhone(phone)).resolves.toEqual(USER);

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock).toHaveBeenLastCalledWith(
      `${ORIGIN}/api/v1/auth/mobile/phone`,
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ phone }),
        credentials: "omit",
        redirect: "error",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
      }),
    );
    expect(JSON.parse(storage.get(SESSION_KEY)!)).toEqual({ origin: ORIGIN, token: TOKEN });
    fetchMock.mockResolvedValueOnce(response(USER));
    await expect(client.refresh()).resolves.toEqual(USER);
    expect(fetchMock.mock.calls[2][1]?.headers).toHaveProperty("Authorization", `Bearer ${TOKEN}`);
  });

  it.each([
    null,
    {},
    { session_token: "invalid", expires_at: NOW / 1000 + 60, user: USER },
    { session_token: TOKEN, expires_at: NOW / 1000, user: USER },
    { session_token: TOKEN, expires_at: Infinity, user: USER },
    { session_token: TOKEN, expires_at: NOW / 1000 + 60, user: null },
    { session_token: TOKEN, expires_at: NOW / 1000 + 60, user: { ...USER, id: "invalid" } },
  ])("rejects malformed issued sessions without retaining credentials: %j", async (result) => {
    const { client, fetchMock, storage } = setup();
    fetchMock.mockResolvedValueOnce(response({ phone_login_enabled: true }));
    fetchMock.mockResolvedValueOnce(response(result));
    await expect(client.signInWithPhone(phone)).rejects.toBeInstanceOf(AuthError);
    expect(storage.has(SESSION_KEY)).toBe(false);
    await expect(client.refresh()).resolves.toBeNull();
  });

  it.each([false, true])(
    "attempts server revocation if phone-session persistence fails (revocation fails=%s)",
    async (revokeFails) => {
      const { client, deps, fetchMock, storage, issued } = setup();
      fetchMock.mockResolvedValueOnce(response({ phone_login_enabled: true }));
      fetchMock.mockResolvedValueOnce(issued());
      if (revokeFails) fetchMock.mockRejectedValueOnce(new Error("network unavailable"));
      else fetchMock.mockResolvedValueOnce(response(null, 204));
      deps.set.mockRejectedValueOnce(new Error("secure storage unavailable"));

      await expect(client.signInWithPhone(phone)).rejects.toThrow("Could not save your sign-in");
      expect(fetchMock).toHaveBeenLastCalledWith(
        `${ORIGIN}/api/v1/auth/logout`,
        expect.objectContaining({
          headers: expect.objectContaining({ Authorization: `Bearer ${TOKEN}` }),
        }),
      );
      expect(storage.has(SESSION_KEY)).toBe(false);
      await expect(client.refresh()).resolves.toBeNull();
    },
  );

  it("prevents concurrent sign-ins and releases the guard after failure", async () => {
    const { client, fetchMock, issued } = setup();
    const config = deferred<Response>();
    fetchMock.mockImplementationOnce(() => config.promise);
    const first = client.signInWithPhone(phone);
    await expect(client.signInWithPhone(phone)).rejects.toThrow("already in progress");
    await expect(client.signOut()).rejects.toThrow("finish or cancel sign-in first");
    config.resolve(response({ phone_login_enabled: false }));
    await expect(first).rejects.toBeInstanceOf(AuthError);

    fetchMock.mockResolvedValueOnce(response({ phone_login_enabled: true }));
    fetchMock.mockResolvedValueOnce(issued());
    await expect(client.signInWithPhone(phone)).resolves.toEqual(USER);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("does not retain credentials when the phone endpoint rejects the request", async () => {
    const { client, fetchMock, storage } = setup();
    fetchMock.mockResolvedValueOnce(response({ phone_login_enabled: true }));
    fetchMock.mockResolvedValueOnce(response({}, 503));
    await expect(client.signInWithPhone(phone)).rejects.toMatchObject({ status: 503 });
    expect(storage.has(SESSION_KEY)).toBe(false);
  });

  it("aborts sign-in requests that exceed the network deadline", async () => {
    jest.useFakeTimers();
    try {
      const { client, fetchMock } = setup();
      fetchMock.mockImplementationOnce((_url, init) => new Promise((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => reject(new Error("request aborted")));
      }));
      const assertion = expect(client.signInWithPhone(phone)).rejects.toThrow("Could not connect");
      jest.advanceTimersByTime(20_000);
      await assertion;
      expect(fetchMock).toHaveBeenCalledTimes(1);
    } finally {
      jest.useRealTimers();
    }
  });
});
