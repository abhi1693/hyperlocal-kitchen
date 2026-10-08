/// <reference types="jest" />
import {
  FormError,
  dishCreate,
  dishUpdate,
  indiaDate,
  indiaTime,
  kitchenCreate,
  kitchenUpdate,
  listingCreate,
  listingUpdate,
  paiseToRupees,
  parseQuantity,
  pickupPointCreate,
  pickupPointUpdate,
  rupeesToPaise,
  timeToIso,
  validDate,
  validFssaiNumber,
  validHttpsImage,
  validTime,
  validUpiId,
  type KitchenForm,
  type ListingContext,
  type ListingForm,
} from "../forms";
import type { ListingOut } from "../../api/generated";

const ID = "abcd1234-5678-4567-8123-123456789abc";
const COMMUNITY = "21e09029-840f-4a7b-ae11-393f7fe1d26f";
const KITCHEN: KitchenForm = {
  name: "  Anita’s kitchen  ",
  description: " Home cooking ",
  addressLabel: "",
  deliveryFee: "0",
  upiId: "",
  fssaiNumber: "",
  pickupEnabled: true,
  deliveryEnabled: false,
};
const MENU: ListingForm = {
  dishId: ID,
  serviceDate: "2027-01-02",
  readyFrom: "12:00",
  readyUntil: "14:00",
  cutoff: "11:30",
  price: "99.29",
  quantity: "20",
  pickupEnabled: true,
  deliveryEnabled: false,
  pickupPointIds: [ID],
  status: "draft",
};
const CONTEXT: ListingContext = {
  kitchen: { id: ID, status: "pending", pickup_enabled: true, delivery_enabled: false },
  now: new Date("2027-01-02T05:59:00Z"),
};
const APPROVED: ListingContext = {
  ...CONTEXT,
  kitchen: { ...CONTEXT.kitchen, status: "approved" },
};
const ORIGINAL: ListingOut = {
  id: "0c9bdc88-9b74-4a76-b0c0-ebce76445de5",
  kitchen: {
    ...APPROVED.kitchen,
    community_id: COMMUNITY,
    community_name: "River Park",
    name: "Anita’s kitchen",
    description: null,
    delivery_fee_paise: 0,
    fssai_number: null,
    is_accepting_orders: true,
    pause_reason: null,
  },
  dish: {
    id: ID,
    kitchen_id: ID,
    name: "Dal",
    description: null,
    image_url: null,
    is_active: true,
  },
  pickup_points: [],
  service_date: MENU.serviceDate,
  available_from: "2027-01-02T06:30:30.123456Z",
  available_until: "2027-01-02T06:30:59.987654Z",
  order_cutoff: "2027-01-02T06:00:30.123456Z",
  price_paise: 9929,
  quantity_total: 20,
  quantity_remaining: 2,
  pickup_enabled: true,
  delivery_enabled: false,
  delivery_fee_paise: 0,
  status: "published",
  is_orderable: false,
};

describe("exact rupee and portion parsing", () => {
  it.each([
    ["0", 0],
    ["0.01", 1],
    ["0.29", 29],
    ["1.1", 110],
    ["99.29", 9929],
    [" 001.05 ", 105],
    ["100000.00", 10_000_000],
  ])("converts %s without rounding", (value, paise) => {
    expect(rupeesToPaise(value as string)).toBe(paise);
  });
  it.each([
    "",
    " ",
    "-1",
    "+1",
    "1e2",
    "1,000",
    "1.001",
    ".50",
    "1.",
    "Infinity",
    "NaN",
    "100000.01",
    "9007199254740993",
    "١٢.٣٤",
    "１２.３４",
    "₹12",
    "1\0",
    "1\n2",
    "1;alert(1)",
  ])("rejects invalid money %j", (value) => {
    expect(rupeesToPaise(value)).toBeNull();
  });
  it("applies the kitchen delivery fee bound separately", () => {
    expect(rupeesToPaise("10000", 1_000_000)).toBe(1_000_000);
    expect(rupeesToPaise("10000.01", 1_000_000)).toBeNull();
    expect(rupeesToPaise("1", NaN)).toBeNull();
  });
  it.each([0, 1, 29, 101, 9929, 10_000_000])("round trips whole paise %i", (paise) => {
    expect(rupeesToPaise(paiseToRupees(paise))).toBe(paise);
  });
  it.each([-1, 0.1, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1])(
    "rejects invalid stored paise %j",
    (value) => {
      expect(() => paiseToRupees(value)).toThrow(FormError);
    },
  );
  it.each([
    ["1", 1],
    [" 00020 ", 20],
    ["10000", 10000],
  ])("parses whole portions %s", (value, quantity) => {
    expect(parseQuantity(value as string)).toBe(quantity);
  });
  it.each(["", "0", "-1", "+1", "1.0", "1e2", "10001", "١", "1\0", "1\n2"])(
    "rejects invalid portions %j",
    (value) => {
      expect(parseQuantity(value)).toBeNull();
    },
  );
});

describe("India calendar and time input", () => {
  it.each(["0001-01-01", "2000-02-29", "2028-02-29", "9999-12-31"])(
    "accepts actual date %s",
    (date) => {
      expect(validDate(date)).toBe(true);
    },
  );
  it.each([
    "0000-01-01",
    "1900-02-29",
    "2027-02-29",
    "2026-04-31",
    "2026-00-01",
    "2026-13-01",
    "2026-01-00",
    "2026-1-01",
    "2026-01-01T00:00:00Z",
    "２０２６-01-01",
    "2026-01-01\0",
  ])("rejects invalid date %j", (date) => {
    expect(validDate(date)).toBe(false);
    expect(() => timeToIso(date, "12:00")).toThrow(FormError);
  });
  it.each(["00:00", "09:05", "23:59"])("accepts 24-hour time %s", (time) => {
    expect(validTime(time)).toBe(true);
    expect(timeToIso("2027-01-02", time)).toBe(`2027-01-02T${time}:00+05:30`);
  });
  it.each(["24:00", "12:60", "9:05", "12:00:00", "12:00Z", "12:00+05:30", "１２:００", "12:00\0"])(
    "rejects invalid time %j",
    (time) => {
      expect(validTime(time)).toBe(false);
      expect(() => timeToIso("2027-01-02", time)).toThrow(FormError);
    },
  );
  it("formats India midnight independently of the host timezone", () => {
    expect(indiaDate(new Date("2026-10-09T18:29:59Z"))).toBe("2026-10-09");
    expect(indiaTime(new Date("2026-10-09T18:29:59Z"))).toBe("23:59");
    expect(indiaDate(new Date("2026-10-09T18:30:00Z"))).toBe("2026-10-10");
    expect(indiaTime(new Date("2026-10-09T18:30:00Z"))).toBe("00:00");
    expect(() => indiaDate(new Date(NaN))).toThrow(FormError);
  });
});

describe("kitchen, dish and pickup point payloads", () => {
  it("creates a kitchen without requiring an onboarding address", () => {
    const payload = kitchenCreate(KITCHEN, COMMUNITY);
    expect(payload).toEqual({
      community_id: COMMUNITY,
      name: "Anita’s kitchen",
      description: "Home cooking",
      pickup_enabled: true,
      delivery_enabled: false,
      delivery_fee_paise: 0,
      upi_id: null,
      fssai_number: null,
    });
    expect(payload).not.toHaveProperty("address_label");
    expect(payload).not.toHaveProperty("zone_id");
    expect(KITCHEN.name).toBe("  Anita’s kitchen  ");
  });
  it("clears optional text on update and supports a selected or cleared zone on create", () => {
    expect(kitchenUpdate(KITCHEN).address_label).toBeNull();
    expect(
      kitchenCreate({ ...KITCHEN, addressLabel: " Flat 101 " }, COMMUNITY, ID).address_label,
    ).toBe("Flat 101");
    expect(kitchenCreate(KITCHEN, COMMUNITY, ID).zone_id).toBe(ID);
    expect(kitchenCreate(KITCHEN, COMMUNITY, null).zone_id).toBeNull();
    expect(() => kitchenCreate(KITCHEN, "bad")).toThrow(FormError);
    expect(() => kitchenCreate(KITCHEN, COMMUNITY, "bad")).toThrow(FormError);
  });
  it("counts Unicode text as code points and trims before bounds", () => {
    expect(
      kitchenCreate({ ...KITCHEN, name: ` ${"🥘".repeat(150)} ` }, COMMUNITY).name,
    ).toHaveLength(300);
    expect(() => kitchenUpdate({ ...KITCHEN, name: "🥘".repeat(151) })).toThrow(FormError);
    expect(() => kitchenUpdate({ ...KITCHEN, description: "a".repeat(1001) })).toThrow(FormError);
    expect(() => kitchenUpdate({ ...KITCHEN, addressLabel: "a".repeat(251) })).toThrow(FormError);
  });
  it.each([
    { name: " " },
    { name: "food\0" },
    { deliveryFee: "10000.01" },
    { upiId: "a@b" },
    { fssaiNumber: "123" },
    { pickupEnabled: false },
  ])("rejects kitchen fields %j", (changes) => {
    expect(() => kitchenCreate({ ...KITCHEN, ...changes }, COMMUNITY)).toThrow(FormError);
  });
  it("allows optional identifiers, validates supplied identifiers, and represents a free fee", () => {
    expect(validUpiId("")).toBe(true);
    expect(validUpiId("kitchen@bank")).toBe(true);
    expect(validUpiId("kitchen@bank;script")).toBe(false);
    expect(validFssaiNumber("")).toBe(true);
    expect(validFssaiNumber("12345678901234")).toBe(true);
    expect(validFssaiNumber("１２３４５６７８９０１２３４")).toBe(false);
    expect(
      kitchenUpdate({ ...KITCHEN, deliveryEnabled: true, deliveryFee: "" }).delivery_fee_paise,
    ).toBe(0);
  });
  it("creates and edits dishes with canonical HTTPS images and cleared optional fields", () => {
    expect(
      dishCreate({ name: " Dal ", description: " ", imageUrl: "https://example.com" }),
    ).toEqual({ name: "Dal", description: null, image_url: "https://example.com/" });
    expect(dishUpdate({ name: "Dal", description: "", imageUrl: "" }).image_url).toBeNull();
    expect(() => dishCreate({ name: " ", description: "", imageUrl: "" })).toThrow(FormError);
  });
  it.each([
    "http://example.com/meal.jpg",
    "javascript:alert(1)",
    "data:image/png;base64,AAAA",
    "https://user:password@example.com",
    "https://example.com\n/meal.jpg",
    "https://",
    `https://example.com/${"a".repeat(2048)}`,
  ])("rejects unsafe or malformed image URLs %j", (imageUrl) => {
    expect(validHttpsImage(imageUrl)).toBe(false);
    expect(() => dishCreate({ name: "Dal", description: "", imageUrl })).toThrow(FormError);
  });
  it("requires a real pickup address without changing optional kitchen address rules", () => {
    const form = { name: " Gate ", addressLabel: " Lobby, Tower A ", instructions: " " };
    expect(pickupPointCreate(form)).toEqual({
      name: "Gate",
      address_label: "Lobby, Tower A",
      instructions: null,
    });
    expect(pickupPointUpdate(form)).toEqual(pickupPointCreate(form));
    expect(() => pickupPointCreate({ ...form, addressLabel: " " })).toThrow(FormError);
    expect(() => pickupPointCreate({ ...form, instructions: "a".repeat(1001) })).toThrow(FormError);
  });
});

describe("draft and published menu payloads", () => {
  it("saves a pending kitchen draft with exact paise and aware India times", () => {
    expect(listingCreate(MENU, CONTEXT)).toEqual({
      dish_id: ID,
      service_date: "2027-01-02",
      available_from: "2027-01-02T12:00:00+05:30",
      available_until: "2027-01-02T14:00:00+05:30",
      order_cutoff: "2027-01-02T11:30:00+05:30",
      price_paise: 9929,
      quantity_total: 20,
      pickup_enabled: true,
      delivery_enabled: false,
      pickup_point_ids: [ID],
      status: "draft",
    });
    expect(listingCreate(MENU, { ...CONTEXT, now: new Date("2030-01-01") }).status).toBe("draft");
  });
  it("publishes only after approval and with a future cutoff", () => {
    const menu = { ...MENU, status: "published" as const };
    expect(() => listingCreate(menu, CONTEXT)).toThrow("approved");
    expect(listingCreate(menu, APPROVED).status).toBe("published");
    expect(() =>
      listingCreate(menu, { ...APPROVED, now: new Date("2027-01-02T06:00:00Z") }),
    ).toThrow("future");
    expect(() => listingCreate(menu, { ...APPROVED, now: new Date(NaN) })).toThrow("future");
  });
  it("accepts a cutoff at ready-until and a 24-hour overnight window", () => {
    expect(listingCreate({ ...MENU, cutoff: "14:00" }, CONTEXT).order_cutoff).toContain("14:00");
    expect(
      listingCreate({ ...MENU, readyUntilDate: "2027-01-03", readyUntil: "12:00" }, CONTEXT)
        .available_until,
    ).toBe("2027-01-03T12:00:00+05:30");
  });
  it.each([
    { readyUntil: "12:00" },
    { readyUntilDate: "2027-01-03", readyUntil: "12:01" },
    { readyUntilDate: "2027-01-01" },
    { cutoff: "14:01" },
    { cutoffDate: "2027-01-03" },
    { serviceDate: "2027-02-29" },
    { readyFrom: "24:00" },
    { price: "0" },
    { price: "0.001" },
    { quantity: "10001" },
    { dishId: "bad" },
    { pickupEnabled: false },
    { deliveryEnabled: true },
  ])("rejects invalid menu details %j", (changes) => {
    expect(() => listingCreate({ ...MENU, ...changes }, CONTEXT)).toThrow(FormError);
  });
  it.each(["published", "sold_out"])(
    "allows stock corrections after cutoff for %s meals without changing the dish",
    (existingStatus) => {
      const payload = listingUpdate(
        { ...MENU, status: "published", quantity: "25" },
        { ...APPROVED, existingStatus, now: new Date("2030-01-01") },
      );
      expect(payload.quantity_total).toBe(25);
      expect(payload).not.toHaveProperty("dish_id");
    },
  );
  it("rechecks approval and cutoff when publishing a draft, and rejects cancelled edits", () => {
    expect(() =>
      listingUpdate({ ...MENU, status: "published" }, { ...CONTEXT, existingStatus: "draft" }),
    ).toThrow("approved");
    expect(() => listingUpdate(MENU, { ...CONTEXT, existingStatus: "cancelled" })).toThrow(
      "cancelled",
    );
  });
  it("checks pickup ids and does not mutate selection arrays", () => {
    const payload = listingCreate(MENU, CONTEXT);
    expect(payload.pickup_point_ids).not.toBe(MENU.pickupPointIds);
    expect(() =>
      listingCreate({ ...MENU, pickupPointIds: [ID, ID.toUpperCase()] }, CONTEXT),
    ).toThrow("once");
    expect(() => listingCreate({ ...MENU, pickupPointIds: ["bad"] }, CONTEXT)).toThrow(FormError);
    expect(() => listingCreate({ ...MENU, pickupPointIds: Array(31).fill(ID) }, CONTEXT)).toThrow(
      "30",
    );
    expect(() => listingUpdate({ ...MENU, pickupPointIds: [] }, CONTEXT)).toThrow(FormError);
    expect(listingCreate({ ...MENU, pickupPointIds: [] }, CONTEXT).pickup_point_ids).toEqual([]);
  });
  it("allows delivery-only menus and rejects pickup points when pickup is disabled", () => {
    const context = { ...CONTEXT, kitchen: { ...CONTEXT.kitchen, delivery_enabled: true } };
    const menu = { ...MENU, pickupEnabled: false, deliveryEnabled: true, pickupPointIds: [] };
    expect(listingCreate(menu, context).delivery_enabled).toBe(true);
    expect(() => listingCreate({ ...menu, pickupPointIds: [ID] }, context)).toThrow(FormError);
  });
  it("preserves sub-minute reserved schedules and hidden inactive pickup links during stock edits", () => {
    const form = {
      ...MENU,
      readyUntil: "12:00",
      quantity: "25",
      pickupPointIds: [],
      status: "published" as const,
    };
    const result = listingUpdate(form, { ...APPROVED, now: new Date("2030-01-01") }, ORIGINAL);
    // Both ready times display 12:00, but the exact original window is still positive.
    expect(result).toEqual({ quantity_total: 25 });
    expect(ORIGINAL.available_from).toBe("2027-01-02T06:30:30.123456Z");
    expect(result).not.toHaveProperty("pickup_point_ids");
  });
  it("sends only changed fields and retains exact timestamps with nonzero seconds", () => {
    const form = {
      ...MENU,
      readyUntil: "12:00",
      price: "100.01",
      pickupPointIds: [],
      status: "published" as const,
    };
    expect(listingUpdate(form, APPROVED, ORIGINAL)).toEqual({ price_paise: 10001 });
    expect(listingUpdate({ ...form, price: MENU.price }, APPROVED, ORIGINAL)).toEqual({});
    expect(listingUpdate({ ...form, readyUntil: "12:01" }, APPROVED, ORIGINAL)).toEqual({
      price_paise: 10001,
      available_until: "2027-01-02T12:01:00+05:30",
    });
  });
  it("does not clear pickup links when visible selections are unchanged or reordered", () => {
    const other = "2d1e913d-ab84-4a20-95a0-cecc08d56b3d";
    const point = {
      id: ID,
      community_id: COMMUNITY,
      kitchen_id: ID,
      zone_id: null,
      name: "Gate",
      address_label: "Tower A",
      instructions: null,
      active: true,
    };
    const original = { ...ORIGINAL, pickup_points: [point, { ...point, id: other }] };
    const form = {
      ...MENU,
      readyUntil: "12:00",
      pickupPointIds: [other, ID],
      status: "published" as const,
    };
    expect(listingUpdate(form, APPROVED, original)).toEqual({});
    expect(() => listingUpdate({ ...form, pickupPointIds: [] }, APPROVED, original)).toThrow(
      FormError,
    );
    expect(listingUpdate({ ...form, pickupPointIds: [ID] }, APPROVED, original)).toEqual({
      pickup_point_ids: [ID],
    });
  });
  it("still requires a pickup selection when newly enabling pickup", () => {
    const original = { ...ORIGINAL, pickup_enabled: false, delivery_enabled: true };
    const form = { ...MENU, readyUntil: "12:00", pickupPointIds: [], status: "published" as const };
    expect(() =>
      listingUpdate(
        form,
        { ...APPROVED, kitchen: { ...APPROVED.kitchen, delivery_enabled: true } },
        original,
      ),
    ).toThrow(FormError);
  });
  it("uses the original draft status for publication checks and rejects another kitchen or dish", () => {
    const form = { ...MENU, readyUntil: "12:00", pickupPointIds: [], status: "published" as const };
    expect(() =>
      listingUpdate(
        form,
        { ...APPROVED, existingStatus: "published", now: new Date("2030-01-01") },
        { ...ORIGINAL, status: "draft" },
      ),
    ).toThrow("future");
    expect(() =>
      listingUpdate(form, APPROVED, {
        ...ORIGINAL,
        kitchen: { ...ORIGINAL.kitchen, id: COMMUNITY },
      }),
    ).toThrow("Reload");
    expect(() => listingUpdate({ ...form, dishId: COMMUNITY }, APPROVED, ORIGINAL)).toThrow(
      "Reload",
    );
  });
});
