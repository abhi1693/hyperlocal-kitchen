/// <reference types="jest" />

import { onboardingState, validAddress } from "../state";

const USER_ID = "98db36de-8d46-4a42-851b-25a24a66d590";
const OTHER_USER_ID = "f5d82a1f-27d9-4ea9-92ec-726005a17487";
const MEMBERSHIP = {
  id: "f855fbeb-6ca2-46ca-87ac-99132bff2725",
  community_id: "8b2b2fae-c47b-473a-aacc-f5c23d85e21f",
  user_id: USER_ID,
  community_name: "River Park",
  zone_id: null,
  zone_name: null,
  address_label: null,
  status: "active",
};

describe("one-time community onboarding state", () => {
  it("keeps a user without a community membership incomplete", () => {
    const state = { completed: false, membership: null };
    expect(onboardingState(state, USER_ID)).toBe(state);
  });

  it.each([null, "", "   ", "Flat 101"])("completes setup once membership exists regardless of address: %j", (address_label) => {
    const state = { completed: true, membership: { ...MEMBERSHIP, address_label } };
    expect(onboardingState(state, USER_ID)).toBe(state);
    expect(onboardingState(state, USER_ID).completed).toBe(true);
  });

  it("keeps a suspended membership completed instead of repeating community setup", () => {
    const state = { completed: true, membership: { ...MEMBERSHIP, status: "suspended" } };
    expect(onboardingState(state, USER_ID)).toEqual(state);
  });

  it("accepts memberships whose optional address field is omitted", () => {
    const { address_label: _address, ...membership } = MEMBERSHIP;
    const state = { completed: true, membership };
    expect(onboardingState(state, USER_ID)).toEqual(state);
  });

  it("accepts a valid optional zone and zone name", () => {
    const state = {
      completed: true,
      membership: {
        ...MEMBERSHIP,
        zone_id: "27d6cd1a-fb9a-4e5f-b340-d6dcae50ca85",
        zone_name: "Tower A",
      },
    };
    expect(onboardingState(state, USER_ID)).toEqual(state);
  });

  it("accepts omitted optional zone details", () => {
    const state = { completed: true, membership: { ...MEMBERSHIP, zone_id: undefined, zone_name: undefined } };
    expect(onboardingState(state, USER_ID)).toEqual(state);
  });

  it.each([
    null,
    undefined,
    false,
    "completed",
    [],
    {},
    { completed: "true", membership: MEMBERSHIP },
    { completed: 1, membership: MEMBERSHIP },
    { completed: true, membership: null },
    { completed: false, membership: MEMBERSHIP },
    { completed: false },
    { completed: true },
    { completed: true, membership: "membership" },
    { completed: true, membership: [] },
    { completed: true, membership: {} },
  ])("blocks malformed or inconsistent completion responses: %j", (value) => {
    expect(() => onboardingState(value, USER_ID)).toThrow("Could not load your home details");
  });

  it("blocks another user's membership instead of exposing their onboarding state", () => {
    const state = { completed: true, membership: { ...MEMBERSHIP, user_id: OTHER_USER_ID } };
    expect(() => onboardingState(state, USER_ID)).toThrow("Could not load your home details");
  });

  it.each([
    { id: "invalid" },
    { id: null },
    { id: undefined },
    { id: [MEMBERSHIP.id] },
    { community_id: "invalid" },
    { community_id: null },
    { community_id: undefined },
    { community_id: [MEMBERSHIP.community_id] },
    { user_id: "invalid" },
    { user_id: null },
    { user_id: undefined },
    { community_name: null },
    { community_name: 123 },
    { status: null },
    { status: 123 },
    { address_label: 123 },
    { address_label: {} },
    { zone_id: "invalid" },
    { zone_id: 123 },
    { zone_id: [] },
    { zone_name: 123 },
    { zone_name: {} },
  ])("blocks malformed membership fields: %j", (changes) => {
    expect(() => onboardingState({ completed: true, membership: { ...MEMBERSHIP, ...changes } }, USER_ID)).toThrow("Could not load your home details");
  });
});

describe("optional address validation", () => {
  it.each(["", " ", "\t\n ", "Flat 101", "  Flat 101  "])("accepts optional or trimmed addresses: %j", (address) => {
    expect(validAddress(address)).toBe(true);
  });

  it("accepts exactly 250 ASCII code points and rejects 251", () => {
    expect(validAddress("a".repeat(250))).toBe(true);
    expect(validAddress("a".repeat(251))).toBe(false);
  });

  it("counts astral Unicode characters as code points instead of UTF-16 units", () => {
    expect(validAddress("🥘".repeat(250))).toBe(true);
    expect(validAddress("🥘".repeat(251))).toBe(false);
  });

  it("counts combining marks as separate code points", () => {
    expect(validAddress("e\u0301".repeat(125))).toBe(true);
    expect(validAddress("e\u0301".repeat(125) + "a")).toBe(false);
  });

  it("applies the boundary after trimming surrounding whitespace", () => {
    expect(validAddress(` \n${"🥘".repeat(250)}\t `)).toBe(true);
    expect(validAddress(` \n${"🥘".repeat(251)}\t `)).toBe(false);
  });

  it.each(["\0", "Flat\0 101", "\0Flat 101", "Flat 101\0", " \0 "])("rejects null characters anywhere in the address: %j", (address) => {
    expect(validAddress(address)).toBe(false);
  });
});
