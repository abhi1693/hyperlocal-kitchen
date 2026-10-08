import type {
  DishCreate,
  DishUpdate,
  KitchenCreate,
  KitchenOwnOut,
  KitchenUpdate,
  ListingCreate,
  ListingOut,
  ListingUpdate,
  PickupPointCreate,
  PickupPointUpdate,
} from "../api/generated";

export class FormError extends Error {
  constructor(
    message: string,
    readonly field: string,
  ) {
    super(message);
    this.name = "FormError";
  }
}

export type KitchenForm = {
  name: string;
  description: string;
  addressLabel: string;
  deliveryFee: string;
  upiId: string;
  fssaiNumber: string;
  pickupEnabled: boolean;
  deliveryEnabled: boolean;
};
export type DishForm = { name: string; description: string; imageUrl: string };
export type PickupPointForm = { name: string; addressLabel: string; instructions: string };
export type ListingForm = {
  dishId: string;
  serviceDate: string;
  readyFrom: string;
  readyUntil: string;
  readyUntilDate?: string;
  cutoff: string;
  cutoffDate?: string;
  price: string;
  quantity: string;
  pickupEnabled: boolean;
  deliveryEnabled: boolean;
  pickupPointIds?: string[];
  status: "draft" | "published";
};
export type ListingContext = {
  kitchen: Pick<KitchenOwnOut, "id" | "status" | "pickup_enabled" | "delivery_enabled">;
  now?: Date;
  existingStatus?: string;
};

function text(source: string, field: string, maximum: number, required = false): string {
  if (typeof source !== "string" || source.includes("\0"))
    throw new FormError("Use text without null characters.", field);
  const value = source.trim();
  if (required && !value) throw new FormError(`Enter ${field}.`, field);
  if ([...value].length > maximum)
    throw new FormError(`Keep ${field} within ${maximum} characters.`, field);
  return value;
}

function identifier(value: string, field: string): string {
  if (
    typeof value !== "string" ||
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)
  )
    throw new FormError(`Choose a valid ${field}.`, field);
  return value.toLowerCase();
}

function fulfillment(pickup: boolean, delivery: boolean) {
  if (typeof pickup !== "boolean" || typeof delivery !== "boolean" || (!pickup && !delivery))
    throw new FormError("Enable pickup or delivery.", "fulfillment");
}

export function rupeesToPaise(value: string, maxPaise = 10_000_000): number | null {
  if (typeof value !== "string" || !Number.isSafeInteger(maxPaise) || maxPaise < 0) return null;
  const normalized = value.trim();
  if (!/^[0-9]+(?:\.[0-9]{1,2})?$/.test(normalized)) return null;
  const [whole, fraction = ""] = normalized.split(".");
  // Parse integer components separately so decimal floating-point rounding never changes cents.
  const paise = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
  return Number.isSafeInteger(paise) && paise <= maxPaise ? paise : null;
}

export function paiseToRupees(value: number): string {
  if (!Number.isSafeInteger(value) || value < 0)
    throw new FormError("Use a whole, nonnegative amount in paise.", "price");
  return `${Math.floor(value / 100)}.${String(value % 100).padStart(2, "0")}`;
}

export function parseQuantity(value: string): number | null {
  if (typeof value !== "string" || !/^[0-9]+$/.test(value.trim())) return null;
  const quantity = Number(value.trim());
  return Number.isSafeInteger(quantity) && quantity >= 1 && quantity <= 10_000 ? quantity : null;
}

export function validDate(value: string): boolean {
  if (typeof value !== "string" || !/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return year >= 1 && month >= 1 && month <= 12 && day >= 1 && day <= days[month - 1];
}

export function validTime(value: string): boolean {
  return typeof value === "string" && /^(?:[01][0-9]|2[0-3]):[0-5][0-9]$/.test(value);
}

export function timeToIso(date: string, time: string): string {
  if (!validDate(date)) throw new FormError("Enter a real date as YYYY-MM-DD.", "date");
  if (!validTime(time)) throw new FormError("Enter a 24-hour time as HH:mm.", "time");
  return `${date}T${time}:00+05:30`;
}

function indiaClock(value: Date): string {
  if (!(value instanceof Date) || !Number.isFinite(value.getTime()))
    throw new FormError("Choose a valid date and time.", "date");
  const shifted = new Date(value.getTime() + 330 * 60_000);
  if (shifted.getUTCFullYear() < 1 || shifted.getUTCFullYear() > 9999)
    throw new FormError("Choose a date between years 0001 and 9999.", "date");
  return shifted.toISOString();
}

export const indiaDate = (value = new Date()): string => indiaClock(value).slice(0, 10);
export const indiaTime = (value = new Date()): string => indiaClock(value).slice(11, 16);

export function validUpiId(value: string): boolean {
  if (typeof value !== "string") return false;
  const normalized = value.trim();
  return (
    !normalized ||
    (normalized.length <= 150 && /^[A-Za-z0-9._-]{2,}@[A-Za-z0-9.-]{2,}$/.test(normalized))
  );
}

export function validFssaiNumber(value: string): boolean {
  return typeof value === "string" && (!value.trim() || /^[0-9]{14}$/.test(value.trim()));
}

export function validHttpsImage(value: string): boolean {
  if (typeof value !== "string") return false;
  const normalized = value.trim();
  if (!normalized) return true;
  if ([...normalized].length > 2048 || /[\u0000-\u001f\u007f]/.test(normalized)) return false;
  try {
    const url = new URL(normalized);
    return url.protocol === "https:" && !url.username && !url.password;
  } catch {
    return false;
  }
}

function kitchenPayload(form: KitchenForm) {
  fulfillment(form.pickupEnabled, form.deliveryEnabled);
  const fee = rupeesToPaise(text(form.deliveryFee, "delivery fee", 100) || "0", 1_000_000);
  if (fee === null)
    throw new FormError(
      "Use a delivery fee from ₹0 to ₹10,000, with at most two decimals.",
      "delivery fee",
    );
  const upi = text(form.upiId, "UPI ID", 150);
  const fssai = text(form.fssaiNumber, "FSSAI number", 14);
  if (!validUpiId(upi)) throw new FormError("Enter a UPI ID such as kitchen@bank.", "UPI ID");
  if (!validFssaiNumber(fssai))
    throw new FormError("Enter a 14-digit FSSAI number.", "FSSAI number");
  return {
    name: text(form.name, "kitchen name", 150, true),
    description: text(form.description, "description", 1000) || null,
    address_label: text(form.addressLabel, "address", 250) || null,
    delivery_fee_paise: fee,
    pickup_enabled: form.pickupEnabled,
    delivery_enabled: form.deliveryEnabled,
    upi_id: upi || null,
    fssai_number: fssai || null,
  };
}

export function kitchenCreate(
  form: KitchenForm,
  communityId: string,
  zoneId?: string | null,
): KitchenCreate {
  const payload = kitchenPayload(form);
  const result: KitchenCreate = { ...payload, community_id: identifier(communityId, "community") };
  // Omitting an empty address preserves any existing onboarding address on the server.
  if (payload.address_label === null) delete result.address_label;
  if (zoneId !== undefined) result.zone_id = zoneId === null ? null : identifier(zoneId, "zone");
  return result;
}

export const kitchenUpdate = (form: KitchenForm): KitchenUpdate => kitchenPayload(form);

export function dishCreate(form: DishForm): DishCreate {
  const image = text(form.imageUrl, "image URL", 2048);
  if (!validHttpsImage(image))
    throw new FormError("Use an HTTPS image URL without embedded credentials.", "image URL");
  return {
    name: text(form.name, "dish name", 150, true),
    description: text(form.description, "description", 1000) || null,
    image_url: image ? new URL(image).toString() : null,
  };
}

export const dishUpdate = (form: DishForm): DishUpdate => dishCreate(form);

export function pickupPointCreate(form: PickupPointForm): PickupPointCreate {
  return {
    name: text(form.name, "pickup point name", 150, true),
    address_label: text(form.addressLabel, "pickup address", 250, true),
    instructions: text(form.instructions, "pickup instructions", 1000) || null,
  };
}
export const pickupPointUpdate = (form: PickupPointForm): PickupPointUpdate =>
  pickupPointCreate(form);

function samePoints(first: readonly string[], second: readonly string[]): boolean {
  const canonical = (ids: readonly string[]) => ids.map((id) => id.toLowerCase()).sort();
  const left = canonical(first);
  const right = canonical(second);
  return left.length === right.length && left.every((id, index) => id === right[index]);
}

function listingTime(date: string, time: string, original?: string): string {
  const proposed = timeToIso(date, time);
  if (original) {
    const instant = new Date(original);
    if (date === indiaDate(instant) && time === indiaTime(instant)) return original;
  }
  return proposed;
}

function listingPayload(
  form: ListingForm,
  context: ListingContext,
  updating: boolean,
  original?: ListingOut,
): Omit<ListingCreate, "dish_id"> {
  identifier(context.kitchen.id, "kitchen");
  identifier(form.dishId, "dish");
  if (form.status !== "draft" && form.status !== "published")
    throw new FormError("Choose draft or published.", "status");
  const existingStatus = original?.status ?? context.existingStatus;
  if (updating && existingStatus === "cancelled")
    throw new FormError("Create a new menu instead of republishing a cancelled one.", "status");
  fulfillment(form.pickupEnabled, form.deliveryEnabled);
  if (
    (form.pickupEnabled && !context.kitchen.pickup_enabled) ||
    (form.deliveryEnabled && !context.kitchen.delivery_enabled)
  )
    throw new FormError("Enable this fulfillment option on your kitchen first.", "fulfillment");
  const price = rupeesToPaise(form.price);
  if (price === null || price === 0)
    throw new FormError("Use a price from ₹0.01 to ₹100,000, with at most two decimals.", "price");
  const quantity = parseQuantity(form.quantity);
  if (quantity === null) throw new FormError("Enter 1 to 10,000 whole portions.", "quantity");
  // Existing schedules may contain seconds or microseconds that the minute-based form hides.
  const from = listingTime(form.serviceDate, form.readyFrom, original?.available_from);
  const until = listingTime(
    form.readyUntilDate ?? form.serviceDate,
    form.readyUntil,
    original?.available_until,
  );
  const cutoff = listingTime(
    form.cutoffDate ?? form.serviceDate,
    form.cutoff,
    original?.order_cutoff,
  );
  const window = Date.parse(until) - Date.parse(from);
  if (window <= 0 || window > 86_400_000)
    throw new FormError("Ready until must be after ready from, within 24 hours.", "ready window");
  if (Date.parse(cutoff) > Date.parse(until))
    throw new FormError("Orders must close by the end of the ready window.", "cutoff");
  const publishing =
    form.status === "published" &&
    (!updating || !["published", "sold_out"].includes(existingStatus ?? ""));
  if (publishing) {
    if (context.kitchen.status !== "approved")
      throw new FormError("Your kitchen must be approved before publishing food.", "status");
    const now = context.now ?? new Date();
    if (
      !(now instanceof Date) ||
      !Number.isFinite(now.getTime()) ||
      Date.parse(cutoff) <= now.getTime()
    )
      throw new FormError("Choose an order cutoff in the future.", "cutoff");
  }
  let points: string[] | undefined;
  if (form.pickupPointIds !== undefined) {
    if (!Array.isArray(form.pickupPointIds) || form.pickupPointIds.length > 30)
      throw new FormError("Choose up to 30 pickup points.", "pickup points");
    points = form.pickupPointIds.map((id) => identifier(id, "pickup point"));
    if (new Set(points).size !== points.length)
      throw new FormError("Choose each pickup point once.", "pickup points");
    const preserving =
      original &&
      original.pickup_enabled === form.pickupEnabled &&
      samePoints(
        points,
        original.pickup_points.map((point) => point.id),
      );
    if (
      !preserving &&
      ((!form.pickupEnabled && points.length) || (updating && form.pickupEnabled && !points.length))
    )
      throw new FormError(
        "Choose pickup points only when pickup is enabled, and select at least one.",
        "pickup points",
      );
    // Public output hides inactive linked points. Omission preserves those server-side links.
    if (preserving) points = undefined;
  }
  return {
    service_date: form.serviceDate,
    available_from: from,
    available_until: until,
    order_cutoff: cutoff,
    price_paise: price,
    quantity_total: quantity,
    pickup_enabled: form.pickupEnabled,
    delivery_enabled: form.deliveryEnabled,
    status: form.status,
    ...(points !== undefined ? { pickup_point_ids: points } : {}),
  };
}

export function listingCreate(form: ListingForm, context: ListingContext): ListingCreate {
  return { dish_id: identifier(form.dishId, "dish"), ...listingPayload(form, context, false) };
}
export function listingUpdate(
  form: ListingForm,
  context: ListingContext,
  original?: ListingOut,
): ListingUpdate {
  if (
    original &&
    (original.kitchen.id !== context.kitchen.id ||
      original.dish.kitchen_id !== context.kitchen.id ||
      original.dish.id !== form.dishId)
  )
    throw new FormError("Reload this menu from your kitchen before editing it.", "dish");
  const payload = listingPayload(form, context, true, original);
  if (!original) return payload;
  const result: ListingUpdate = {};
  for (const field of [
    "service_date",
    "available_from",
    "available_until",
    "order_cutoff",
    "price_paise",
    "quantity_total",
    "pickup_enabled",
    "delivery_enabled",
  ] as const) {
    if (payload[field] !== original[field]) Object.assign(result, { [field]: payload[field] });
  }
  const status = original.status === "sold_out" ? "published" : original.status;
  if (payload.status !== status) result.status = payload.status;
  if (payload.pickup_point_ids !== undefined) result.pickup_point_ids = payload.pickup_point_ids;
  return result;
}
