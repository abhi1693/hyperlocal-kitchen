import type { OnboardingState } from "../api/generated";

export function onboardingState(value: unknown, userId: string): OnboardingState {
  if (
    !value ||
    typeof value !== "object" ||
    !("completed" in value) ||
    typeof value.completed !== "boolean"
  ) {
    throw new Error("Could not load your home details. Please try again.");
  }
  const state = value as OnboardingState;
  const membership = state.membership;
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  if (
    state.completed !== (membership !== null) ||
    (membership !== null &&
      (!membership ||
        typeof membership !== "object" ||
        membership.user_id !== userId ||
        typeof membership.id !== "string" ||
        !uuid.test(membership.id) ||
        typeof membership.community_id !== "string" ||
        !uuid.test(membership.community_id) ||
        typeof membership.community_name !== "string" ||
        typeof membership.status !== "string" ||
        (membership.address_label !== undefined &&
          membership.address_label !== null &&
          typeof membership.address_label !== "string") ||
        (membership.zone_name !== undefined &&
          membership.zone_name !== null &&
          typeof membership.zone_name !== "string") ||
        (membership.zone_id !== undefined &&
          membership.zone_id !== null &&
          (typeof membership.zone_id !== "string" || !uuid.test(membership.zone_id)))))
  ) {
    throw new Error("Could not load your home details. Please try again.");
  }
  return state;
}

export function validAddress(value: string): boolean {
  const trimmed = value.trim();
  return [...trimmed].length <= 250 && !trimmed.includes("\0");
}
