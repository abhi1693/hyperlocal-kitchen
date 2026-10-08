import { Redirect } from "expo-router";
import { useAuth } from "../auth/provider";
import { useOnboarding } from "../onboarding/provider";
export default function Index() {
  const { user } = useAuth();
  const { state } = useOnboarding();
  return <Redirect href={!user ? "/login" : state?.completed ? "/discover" : "/onboarding"} />;
}
