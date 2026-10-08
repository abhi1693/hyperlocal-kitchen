import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type PropsWithChildren,
} from "react";
import { AppState } from "react-native";
import { useQueryClient } from "@tanstack/react-query";
import { AuthError, type ApiOptions, type User } from "./client";
import { createNativeAuthClient } from "./native";

function message(error: unknown): string {
  return error instanceof AuthError
    ? error.message
    : "Sign-in could not be completed. Please try again.";
}
type AuthContextValue = {
  origin: string | null;
  user: User | null;
  loading: boolean;
  busy: boolean;
  error: string | null;
  signInWithPhone: (phone: string) => Promise<void>;
  signOut: () => Promise<void>;
  retry: () => Promise<void>;
  api: <T>(path: string, options?: ApiOptions) => Promise<T>;
};
const AuthContext = createContext<AuthContextValue | null>(null);
export function AuthProvider({ children }: PropsWithChildren) {
  const [client] = useState(() => {
    try {
      return createNativeAuthClient();
    } catch {
      return null;
    }
  });
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const revision = useRef(0);
  const cache = useQueryClient();
  const changeUser = useCallback(
    (next: User | null) => {
      cache.clear();
      setUser(next);
    },
    [cache],
  );
  const api = useCallback(
    async <T,>(path: string, options?: ApiOptions): Promise<T> => {
      if (!client) throw new AuthError("Could not connect. Please try again.");
      const current = revision.current;
      try {
        return await client.api<T>(path, options);
      } catch (reason) {
        if (reason instanceof AuthError && reason.status === 401 && current === revision.current) {
          const next = await client.refresh();
          if (current === revision.current && !next) {
            revision.current += 1;
            changeUser(null);
          }
        }
        throw reason;
      }
    },
    [changeUser, client],
  );
  useEffect(() => {
    let mounted = true;
    const timer = new Promise<void>((resolve) => setTimeout(resolve, 700));
    const restore = async () => {
      try {
        const next = client ? await client.restore() : null;
        if (mounted) setUser(next);
      } catch (reason) {
        if (mounted) setError(message(reason));
      }
    };
    void Promise.all([restore(), timer]).finally(() => {
      if (mounted) setLoading(false);
    });
    return () => {
      mounted = false;
    };
  }, [client]);
  useEffect(() => {
    const subscription = AppState.addEventListener("change", (state) => {
      if (state !== "active" || !user || busy || !client) return;
      const current = revision.current;
      void client
        .refresh()
        .then((next) => {
          if (current === revision.current && !next) changeUser(null);
        })
        .catch(() => {
          /* Keep a verified session on temporary connectivity failure. */
        });
    });
    return () => subscription.remove();
  }, [busy, changeUser, client, user]);
  const run = async (operation: () => Promise<User | null | void>, update = true) => {
    if (!client) {
      setError("Sign-in is unavailable right now. Please try again later.");
      return;
    }
    revision.current += 1;
    setBusy(true);
    setError(null);
    try {
      const next = await operation();
      if (update && next !== undefined) changeUser(next);
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  };
  return (
    <AuthContext.Provider
      value={{
        origin: client?.origin ?? null,
        api,
        user,
        loading,
        busy,
        error,
        retry: () => run(() => client!.restore()),
        signInWithPhone: (phone) => run(() => client!.signInWithPhone(phone)),
        signOut: () =>
          run(async () => {
            await client!.signOut();
            return null;
          }),
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("AuthProvider is required");
  return value;
}
