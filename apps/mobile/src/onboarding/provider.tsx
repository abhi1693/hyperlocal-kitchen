import { createContext, useContext, useLayoutEffect, useRef, type PropsWithChildren } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AuthError } from "../auth/client";
import { useAuth } from "../auth/provider";
import type { MembershipOut, OnboardingComplete, OnboardingState } from "../api/generated";
import { onboardingState } from "./state";

type OnboardingContextValue = {
  state: OnboardingState | undefined;
  loading: boolean;
  error: string | null;
  saving: boolean;
  refresh: () => Promise<void>;
  complete: (details: OnboardingComplete) => Promise<void>;
  updateAddress: (address: string | null) => Promise<void>;
};
const OnboardingContext = createContext<OnboardingContextValue | null>(null);
export function OnboardingProvider({ children }: PropsWithChildren) {
  const { user, origin, api } = useAuth();
  const cache = useQueryClient();
  const identity = `${origin}:${user?.id ?? "anonymous"}`;
  const currentIdentity = useRef(identity);
  useLayoutEffect(() => {
    currentIdentity.current = identity;
  }, [identity]);
  const key = ["onboarding", origin, user?.id] as const;
  const query = useQuery({
    queryKey: key,
    enabled: !!user,
    networkMode: "always",
    retry: false,
    queryFn: async () => onboardingState(await api("/api/v1/me/onboarding"), user!.id),
  });
  const save = useMutation({
    mutationKey: key,
    networkMode: "always",
    retry: false,
    mutationFn: async (details: OnboardingComplete) => {
      let result: OnboardingState;
      try {
        result = onboardingState(
          await api("/api/v1/me/onboarding", { method: "POST", body: details }),
          user!.id,
        );
        if (!result.completed)
          throw new Error("Your community could not be joined. Please try again.");
      } catch (reason) {
        // A response can be lost after the server commits. Check before repeating setup.
        if (
          currentIdentity.current !== identity ||
          (reason instanceof AuthError && reason.status === 401)
        )
          throw reason;
        try {
          const restored = onboardingState(await api("/api/v1/me/onboarding"), user!.id);
          if (!restored.completed) throw reason;
          result = restored;
        } catch {
          throw reason;
        }
      }
      if (currentIdentity.current !== identity)
        throw new AuthError("Your session changed. Please try again.");
      return { state: result, identity, key };
    },
    onSuccess: (result) => {
      if (currentIdentity.current === result.identity) cache.setQueryData(result.key, result.state);
    },
  });
  const address = useMutation({
    mutationKey: [...key, "address"],
    networkMode: "always",
    retry: false,
    mutationFn: async (addressLabel: string | null) => {
      const membership = query.data?.membership;
      if (!membership) throw new Error("Join a community before adding an address.");
      const updated = await api<MembershipOut>(`/api/v1/me/memberships/${membership.id}`, {
        method: "PATCH",
        body: { address_label: addressLabel },
      });
      return {
        state: onboardingState({ completed: true, membership: updated }, user!.id),
        identity,
        key,
      };
    },
    onSuccess: (result) => {
      if (currentIdentity.current === result.identity) cache.setQueryData(result.key, result.state);
    },
  });
  return (
    <OnboardingContext.Provider
      value={{
        state: query.data,
        loading: !!user && !query.data && (query.isPending || query.isFetching),
        error: query.error
          ? query.error instanceof AuthError
            ? query.error.message
            : "Could not load your community. Please try again."
          : null,
        saving: save.isPending || address.isPending,
        refresh: async () => {
          await query.refetch();
        },
        complete: async (details) => {
          await save.mutateAsync(details);
        },
        updateAddress: async (details) => {
          await address.mutateAsync(details);
        },
      }}
    >
      {children}
    </OnboardingContext.Provider>
  );
}
export function useOnboarding() {
  const value = useContext(OnboardingContext);
  if (!value) throw new Error("OnboardingProvider is required");
  return value;
}
