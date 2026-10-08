import { Redirect } from "expo-router";
import { useAuth } from "../auth/provider";
export default function Index() {
  const { user } = useAuth();
  return <Redirect href={user ? "/discover" : "/login"} />;
}
