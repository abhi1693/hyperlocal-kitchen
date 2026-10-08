import { createContext, useContext, useLayoutEffect, useRef, type PropsWithChildren } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ExperienceState, ExperienceUpdateMode } from "../api/generated";
import { AuthError } from "../auth/client";
import { useAuth } from "../auth/provider";
import { useOnboarding } from "../onboarding/provider";
import { experienceState } from "./state";

type ExperienceContextValue = {
  state: ExperienceState | undefined;
  loading: boolean;
  error: string | null;
  saving: boolean;
  refresh: () => Promise<void>;
  chooseMode: (mode: ExperienceUpdateMode) => Promise<void>;
};
const ExperienceContext = createContext<ExperienceContextValue | null>(null);

export function ExperienceProvider({ children }: PropsWithChildren) {
  const { user, origin, api } = useAuth();
  const { state: onboarding } = useOnboarding();
  const cache = useQueryClient();
  const identity = [origin, user?.id].join(":");
  const currentIdentity = useRef(identity);
  useLayoutEffect(() => {
    currentIdentity.current = identity;
  }, [identity]);
  const key = ["experience", origin, user?.id] as const;
  const enabled = !!user && onboarding?.completed === true;
  const query = useQuery({
    queryKey: key,
    enabled,
    networkMode: "always",
    retry: false,
    queryFn: async () => experienceState(await api("/api/v1/me/experience")),
  });
  const save = useMutation({
    mutationKey: key,
    networkMode: "always",
    retry: false,
    mutationFn: async (mode: ExperienceUpdateMode) => {
      let state: ExperienceState;
      try {
        state = experienceState(
          await api("/api/v1/me/experience", { method: "PATCH", body: { mode } }),
        );
        if (state.mode !== mode) throw new Error("Your choice could not be saved.");
      } catch (reason) {
        if (
          currentIdentity.current !== identity ||
          (reason instanceof AuthError && reason.status === 401)
        )
          throw reason;
        // A lost response does not require a second write if the preference was saved.
        try {
          const restored = experienceState(await api("/api/v1/me/experience"));
          if (restored.mode !== mode) throw reason;
          state = restored;
        } catch {
          throw reason;
        }
      }
      if (currentIdentity.current !== identity)
        throw new AuthError("Your session changed. Please try again.");
      return { state, identity, key };
    },
    onSuccess: async (result) => {
      if (currentIdentity.current !== result.identity) return;
      // A background read started before the save must not restore the older choice.
      await cache.cancelQueries({ queryKey: result.key, exact: true });
      if (currentIdentity.current === result.identity) cache.setQueryData(result.key, result.state);
    },
  });
  return (
    <ExperienceContext.Provider
      value={{
        state: query.data,
        loading: enabled && !query.data && (query.isPending || query.isFetching),
        error: query.error
          ? query.error instanceof AuthError
            ? query.error.message
            : "Could not load your kitchen settings. Please try again."
          : null,
        saving: save.isPending,
        refresh: async () => {
          const result = await query.refetch();
          if (result.error) throw result.error;
        },
        chooseMode: async (mode) => {
          await save.mutateAsync(mode);
        },
      }}
    >
      {children}
    </ExperienceContext.Provider>
  );
}

export function useExperience() {
  const value = useContext(ExperienceContext);
  if (!value) throw new Error("ExperienceProvider is required");
  return value;
}
