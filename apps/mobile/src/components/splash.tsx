import { StyleSheet, View } from "react-native";
import { Text } from "react-native-paper";
export function Splash({ onLayout }: { onLayout?: () => void }) {
  return (
    <View style={styles.page} onLayout={onLayout}>
      <Text accessibilityRole="header" style={styles.name}>
        Hyperlocal{"\n"}Kitchen
      </Text>
    </View>
  );
}
const styles = StyleSheet.create({
  page: { flex: 1, justifyContent: "center", alignItems: "center", backgroundColor: "#FFF8F3" },
  name: {
    color: "#9B3E20",
    fontSize: 40,
    lineHeight: 48,
    fontWeight: "700",
    textAlign: "center",
    padding: 24,
  },
});
