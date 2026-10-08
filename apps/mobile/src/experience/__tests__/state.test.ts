/// <reference types="jest" />
import { experienceState } from "../state";

const KITCHEN = {
  id: "35760335-ea27-41a8-bd51-d7f3b0e13eca",
  community_id: "78d45667-01bc-459e-80dc-5f002543ee55",
  community_name: "River Park",
  name: "Anita’s kitchen",
  description: null,
  pickup_enabled: true,
  delivery_enabled: false,
  delivery_fee_paise: 0,
  status: "pending",
  fssai_number: null,
  is_accepting_orders: true,
  pause_reason: null,
  paused_at: null,
  upi_id: null,
  zone_id: null,
  zone_name: null,
  address_label: null,
};

describe("server-owned app experience", () => {
  it.each([null, "customer", "kitchen_owner"])("accepts mode %j before kitchen setup", (mode) => {
    const value = { mode, owned_kitchen: null };
    expect(experienceState(value)).toBe(value);
  });
  it.each(["customer", "kitchen_owner"])("allows an owner to use %s mode", (mode) => {
    const value = { mode, owned_kitchen: KITCHEN };
    expect(experienceState(value)).toBe(value);
  });
  it("allows missing optional address and zone fields", () => {
    const { address_label: _address, zone_id: _zone, zone_name: _name, ...kitchen } = KITCHEN;
    expect(
      experienceState({ mode: "kitchen_owner", owned_kitchen: kitchen }).owned_kitchen,
    ).toEqual(kitchen);
  });
  it("accepts an aware paused timestamp and selected zone", () => {
    const kitchen = {
      ...KITCHEN,
      is_accepting_orders: false,
      paused_at: "2028-02-29T12:30:01.123456+05:30",
      pause_reason: "On holiday",
      zone_id: KITCHEN.id,
      zone_name: "Tower A",
    };
    expect(
      experienceState({ mode: "kitchen_owner", owned_kitchen: kitchen }).owned_kitchen,
    ).toEqual(kitchen);
  });
  it.each([
    null,
    [],
    {},
    false,
    "owner",
    { mode: "owner", owned_kitchen: KITCHEN },
    { mode: "customer" },
    { owned_kitchen: null },
    { mode: null, owned_kitchen: KITCHEN },
    { mode: "kitchen_owner", owned_kitchen: {} },
  ])("rejects malformed or inconsistent state %j", (value) => {
    expect(() => experienceState(value)).toThrow("Could not load your app experience");
  });
  it("does not accept inherited fields as a server response", () => {
    expect(() =>
      experienceState(Object.create({ mode: "customer", owned_kitchen: null })),
    ).toThrow();
  });
  it.each([
    { id: null },
    { id: [KITCHEN.id] },
    { id: "invalid" },
    { community_id: "invalid" },
    { community_id: undefined },
    { community_name: 1 },
    { community_name: " " },
    { name: "" },
    { name: "food\0" },
    { description: undefined },
    { description: {} },
    { pickup_enabled: "false" },
    { delivery_enabled: 1 },
    { pickup_enabled: false },
    { delivery_fee_paise: -1 },
    { delivery_fee_paise: 1.5 },
    { delivery_fee_paise: NaN },
    { delivery_fee_paise: Number.MAX_SAFE_INTEGER + 1 },
    { status: "rejected" },
    { fssai_number: 123 },
    { upi_id: undefined },
    { pause_reason: {} },
    { is_accepting_orders: "true" },
    { paused_at: undefined },
    { paused_at: "2026-02-30T12:00:00Z" },
    { paused_at: "2026-10-09T12:00:00" },
    { paused_at: "2026-10-09T24:00:00Z" },
    { paused_at: "0000-01-01T12:00:00Z" },
    { paused_at: "2026-10-09T12:00:00+99:99" },
    { address_label: 1 },
    { address_label: "flat\0" },
    { zone_id: [KITCHEN.id] },
    { zone_name: {} },
    { zone_name: "Tower A" },
  ])("rejects malformed owner kitchen data %j", (changes) => {
    expect(() =>
      experienceState({ mode: "kitchen_owner", owned_kitchen: { ...KITCHEN, ...changes } }),
    ).toThrow();
  });
});
