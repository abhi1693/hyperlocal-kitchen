import { Tabs } from "expo-router";
import { Icon, useTheme } from "react-native-paper";
export default function TabLayout() {
  const theme = useTheme();
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: theme.colors.primary,
        tabBarStyle: { backgroundColor: theme.colors.surface },
      }}
    >
      <Tabs.Screen
        name="discover"
        options={{
          title: "Discover",
          tabBarIcon: ({ focused, size }) => (
            <Icon
              source="silverware-fork-knife"
              color={focused ? theme.colors.primary : theme.colors.onSurfaceVariant}
              size={size}
            />
          ),
        }}
      />
      <Tabs.Screen
        name="orders"
        options={{
          title: "Orders",
          tabBarIcon: ({ focused, size }) => (
            <Icon
              source="receipt-text-outline"
              color={focused ? theme.colors.primary : theme.colors.onSurfaceVariant}
              size={size}
            />
          ),
        }}
      />
      <Tabs.Screen
        name="account"
        options={{
          title: "Account",
          tabBarIcon: ({ focused, size }) => (
            <Icon
              source="account-circle-outline"
              color={focused ? theme.colors.primary : theme.colors.onSurfaceVariant}
              size={size}
            />
          ),
        }}
      />
    </Tabs>
  );
}
