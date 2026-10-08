import { Card, Icon, Text } from "react-native-paper";
import { Screen } from "../../components/screen";
export default function OrdersScreen() {
  return (
    <Screen title="Your orders" subtitle="Follow your meals from the kitchen to your table.">
      <Card mode="outlined">
        <Card.Content style={{ gap: 16 }}>
          <Icon source="receipt-text-outline" size={48} />
          <Text variant="titleMedium">Orders will appear here</Text>
          <Text variant="bodyMedium">
            Once ordering is available, you can check preparation updates and pickup or delivery
            details here.
          </Text>
        </Card.Content>
      </Card>
    </Screen>
  );
}
