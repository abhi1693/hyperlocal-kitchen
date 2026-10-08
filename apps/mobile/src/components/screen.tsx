import { type PropsWithChildren } from "react";
import { ScrollView, StyleSheet, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Text, useTheme } from "react-native-paper";
export function Screen({
  title,
  subtitle,
  children,
}: PropsWithChildren<{ title: string; subtitle: string }>) {
  const theme = useTheme();
  return (
    <SafeAreaView
      edges={["top", "left", "right"]}
      style={[styles.page, { backgroundColor: theme.colors.background }]}
    >
      <ScrollView contentContainerStyle={styles.scroll}>
        <View style={styles.content}>
          <Text variant="labelLarge" style={{ color: theme.colors.primary }}>
            HYPERLOCAL KITCHEN
          </Text>
          <Text variant="headlineLarge" accessibilityRole="header">
            {title}
          </Text>
          <Text variant="bodyLarge" style={{ color: theme.colors.onSurfaceVariant }}>
            {subtitle}
          </Text>
          {children}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
const styles = StyleSheet.create({
  page: { flex: 1 },
  scroll: { padding: 24, flexGrow: 1 },
  content: { width: "100%", maxWidth: 600, alignSelf: "center", gap: 20 },
});
