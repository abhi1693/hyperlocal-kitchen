/// <reference types="jest" />
import Index from "../../app/index";

const mockSession = { user: null as object | null };
const mockOnboarding = { state: { completed: true } };
const mockExperience = { state: { mode: null as string | null } };

jest.mock("expo-router", () => ({ Redirect: () => null }));
jest.mock("../../auth/provider", () => ({ useAuth: () => mockSession }));
jest.mock("../../onboarding/provider", () => ({ useOnboarding: () => mockOnboarding }));
jest.mock("../../experience/provider", () => ({ useExperience: () => mockExperience }));

describe("URL-based initial navigation", () => {
  it.each([
    [false, false, null, "/login"],
    [true, false, null, "/onboarding"],
    [true, true, null, "/choose-experience"],
    [true, true, "customer", "/discover"],
    [true, true, "kitchen_owner", "/kitchen"],
  ])("routes signedIn=%s completed=%s mode=%s to %s", (signedIn, completed, mode, href) => {
    mockSession.user = signedIn ? {} : null;
    mockOnboarding.state.completed = completed;
    mockExperience.state.mode = mode;
    expect(Index().props.href).toBe(href);
  });
});
