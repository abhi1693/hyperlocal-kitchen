import { Redirect } from "expo-router";
import { useAuth } from "../auth/provider";
import { useOnboarding } from "../onboarding/provider";
import { useExperience } from "../experience/provider";
export default function Index() {
  const { user } = useAuth();
  const { state } = useOnboarding();
  const { state: experience } = useExperience();
  return (
    <Redirect
      href={
        !user
          ? "/login"
          : !state?.completed
            ? "/onboarding"
            : !experience?.mode
              ? "/choose-experience"
              : experience.mode === "kitchen_owner"
                ? "/kitchen"
                : "/discover"
      }
    />
  );
}
