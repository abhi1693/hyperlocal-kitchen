import type { ExperienceState, KitchenOwnOut } from "../api/generated";

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const text = (value: unknown): value is string =>
  typeof value === "string" && !value.includes("\0");
const nullableText = (value: unknown) => value === null || text(value);
const optionalText = (value: unknown) => value === undefined || nullableText(value);
const identifier = (value: unknown) => typeof value === "string" && uuid.test(value);

function timestamp(value: unknown): boolean {
  if (value === null) return true;
  if (
    !text(value) ||
    !/^[0-9]{4}-[0-9]{2}-[0-9]{2}T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]+)?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])$/.test(
      value,
    )
  )
    return false;
  const date = value.slice(0, 10);
  const calendar = new Date(`${date}T00:00:00Z`);
  return (
    !date.startsWith("0000-") &&
    Number.isFinite(Date.parse(value)) &&
    Number.isFinite(calendar.getTime()) &&
    calendar.toISOString().slice(0, 10) === date
  );
}

function kitchen(value: unknown): value is KitchenOwnOut {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const data = value as Record<string, unknown>;
  return (
    identifier(data.id) &&
    identifier(data.community_id) &&
    text(data.community_name) &&
    !!data.community_name.trim() &&
    text(data.name) &&
    !!data.name.trim() &&
    nullableText(data.description) &&
    typeof data.pickup_enabled === "boolean" &&
    typeof data.delivery_enabled === "boolean" &&
    (data.pickup_enabled || data.delivery_enabled) &&
    typeof data.delivery_fee_paise === "number" &&
    Number.isSafeInteger(data.delivery_fee_paise) &&
    data.delivery_fee_paise >= 0 &&
    ["pending", "approved", "suspended"].includes(data.status as string) &&
    typeof data.is_accepting_orders === "boolean" &&
    nullableText(data.fssai_number) &&
    nullableText(data.upi_id) &&
    nullableText(data.pause_reason) &&
    timestamp(data.paused_at) &&
    optionalText(data.address_label) &&
    optionalText(data.zone_name) &&
    (data.zone_id === undefined || data.zone_id === null || identifier(data.zone_id)) &&
    !(data.zone_id === null && data.zone_name != null)
  );
}

export function experienceState(value: unknown): ExperienceState {
  const invalid = () => new Error("Could not load your app experience. Please try again.");
  if (!value || typeof value !== "object" || Array.isArray(value)) throw invalid();
  const state = value as Record<string, unknown>;
  if (
    !Object.prototype.hasOwnProperty.call(state, "mode") ||
    !Object.prototype.hasOwnProperty.call(state, "owned_kitchen") ||
    ![null, "customer", "kitchen_owner"].includes(state.mode as string | null) ||
    !(state.owned_kitchen === null || kitchen(state.owned_kitchen)) ||
    (state.mode === null && state.owned_kitchen !== null)
  )
    throw invalid();
  return value as ExperienceState;
}
