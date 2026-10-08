import { useEffect, useRef, useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useInfiniteQuery } from "@tanstack/react-query";
import {
  ActivityIndicator,
  Button,
  Card,
  HelperText,
  RadioButton,
  Searchbar,
  Text,
  TextInput,
  useTheme,
} from "react-native-paper";
import type { CommunityOut, CommunityPage } from "../api/generated";
import { communityTypeLabels } from "../api/community-type-choices";
import { AuthError } from "../auth/client";
import { useAuth } from "../auth/provider";
import { useOnboarding } from "../onboarding/provider";
import { validAddress } from "../onboarding/state";

export default function OnboardingScreen() {
  const theme = useTheme();
  const scroll = useRef<ScrollView>(null);
  const { api, origin, user, signOut, busy, error: authError } = useAuth();
  const { complete, saving } = useOnboarding();
  const [step, setStep] = useState<"community" | "address">("community");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<CommunityOut | null>(null);
  const [zoneId, setZoneId] = useState<string | null>(null);
  const [address, setAddress] = useState("");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), 350);
    return () => clearTimeout(timer);
  }, [search]);
  useEffect(() => {
    scroll.current?.scrollTo({ y: 0, animated: false });
  }, [step]);
  const communities = useInfiniteQuery({
    queryKey: ["communities", origin, user?.id, query],
    enabled: !!user && step === "community",
    networkMode: "always",
    retry: false,
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      api<CommunityPage>(
        `/api/v1/communities?limit=20&offset=${pageParam}&query=${encodeURIComponent(query)}`,
      ),
    getNextPageParam: (page) => {
      const next = page.offset + page.items.length;
      return page.items.length && next < page.total ? next : undefined;
    },
  });
  const choices = communities.data?.pages.flatMap((page) => page.items) ?? [];
  const zones = selected?.zones.filter((zone) => zone.active) ?? [];
  const join = async () => {
    if (!selected || saving) return;
    if (!validAddress(address)) {
      setError("Keep your address within 250 characters.");
      return;
    }
    setError(null);
    try {
      await complete({
        community_id: selected.id,
        zone_id: zoneId,
        address_label: address.trim() || null,
      });
    } catch (reason) {
      setError(
        reason instanceof AuthError
          ? reason.message
          : "Could not join your community. Please try again.",
      );
    }
  };
  return (
    <SafeAreaView style={[styles.page, { backgroundColor: theme.colors.background }]}>
      <KeyboardAvoidingView
        style={styles.page}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView
          ref={scroll}
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={styles.scroll}
        >
          <View style={styles.content}>
            <Text variant="labelLarge" style={{ color: theme.colors.primary }}>
              HYPERLOCAL KITCHEN
            </Text>
            <Text variant="labelMedium" style={{ color: theme.colors.onSurfaceVariant }}>
              Step {step === "community" ? "1" : "2"} of 2
            </Text>
            <Text variant="headlineLarge" accessibilityRole="header">
              {step === "community" ? "Find your community" : "Set up your address"}
            </Text>
            <Text variant="bodyLarge" style={{ color: theme.colors.onSurfaceVariant }}>
              {step === "community"
                ? "Join your community to find kitchens and meals near home."
                : "Add the details that help your kitchen find your home. You can also do this later."}
            </Text>
            {step === "community" ? (
              <>
                <Searchbar
                  placeholder="Search communities"
                  accessibilityLabel="Search communities"
                  value={search}
                  maxLength={200}
                  onChangeText={(value) => {
                    setSearch(value);
                    setSelected(null);
                    setZoneId(null);
                  }}
                />
                {communities.isPending && (
                  <ActivityIndicator accessibilityLabel="Loading communities" />
                )}
                {communities.isError && (
                  <View accessibilityLiveRegion="polite">
                    <HelperText type="error" visible>
                      {communities.error instanceof AuthError
                        ? communities.error.message
                        : "Could not load communities. Please try again."}
                    </HelperText>
                    <Button
                      loading={communities.isFetching}
                      disabled={communities.isFetching}
                      onPress={() => void communities.refetch()}
                    >
                      Try again
                    </Button>
                  </View>
                )}
                {!communities.isPending && !communities.isError && !choices.length && (
                  <Card mode="contained">
                    <Card.Content style={styles.group}>
                      <Text variant="titleMedium">
                        {query ? "No communities found" : "Communities are coming soon"}
                      </Text>
                      <Text variant="bodyMedium">
                        {query
                          ? "Try another name. If your community isn’t listed, ask its organiser to have it added."
                          : "Your organiser needs to add and activate your community before you can join."}
                      </Text>
                      <Button onPress={() => void communities.refetch()}>
                        Refresh communities
                      </Button>
                    </Card.Content>
                  </Card>
                )}
                <RadioButton.Group
                  value={selected?.id ?? ""}
                  onValueChange={(id) => {
                    setSelected(choices.find((community) => community.id === id) ?? null);
                    setZoneId(null);
                    setError(null);
                  }}
                >
                  <View style={styles.group}>
                    {choices.map((community) => (
                      <Card
                        key={community.id}
                        mode={selected?.id === community.id ? "contained" : "outlined"}
                      >
                        <RadioButton.Item
                          label={community.name}
                          value={community.id}
                          disabled={community.status !== "active"}
                          accessibilityLabel={`${community.name}, ${community.city}`}
                        />
                        <Card.Content style={{ gap: 6, paddingBottom: 16 }}>
                          <Text variant="labelMedium" style={{ color: theme.colors.primary }}>
                            {communityTypeLabels[community.type]}
                          </Text>
                          <Text variant="bodyMedium">
                            {[community.address, community.city, community.postal_code]
                              .filter(Boolean)
                              .join(", ")}
                          </Text>
                        </Card.Content>
                      </Card>
                    ))}
                  </View>
                </RadioButton.Group>
                {communities.hasNextPage && (
                  <Button
                    disabled={communities.isFetchingNextPage}
                    loading={communities.isFetchingNextPage}
                    onPress={() => void communities.fetchNextPage()}
                  >
                    Load more communities
                  </Button>
                )}
                <Button
                  mode="contained"
                  contentStyle={styles.button}
                  disabled={!selected || busy || saving || search.trim() !== query}
                  onPress={() => {
                    setError(null);
                    setStep("address");
                  }}
                >
                  Continue
                </Button>
              </>
            ) : (
              <>
                <Card mode="contained">
                  <Card.Content style={styles.group}>
                    <Text variant="titleMedium">{selected?.name}</Text>
                    <Text variant="bodyMedium">
                      {[selected?.address, selected?.city, selected?.postal_code]
                        .filter(Boolean)
                        .join(", ")}
                    </Text>
                    <Button disabled={saving} onPress={() => setStep("community")}>
                      Change community
                    </Button>
                  </Card.Content>
                </Card>
                {!!zones.length && (
                  <View>
                    <Text variant="titleMedium">Tower, block or area (optional)</Text>
                    <RadioButton.Group
                      value={zoneId ?? ""}
                      onValueChange={(id) => setZoneId(id || null)}
                    >
                      <RadioButton.Item
                        label="No tower, block or area"
                        value=""
                        disabled={saving}
                      />
                      {zones.map((zone) => (
                        <RadioButton.Item
                          key={zone.id}
                          value={zone.id}
                          disabled={saving}
                          label={
                            zone.parent_zone_id
                              ? `${selected?.zones.find((parent) => parent.id === zone.parent_zone_id)?.name ?? ""} / ${zone.name}`
                              : zone.name
                          }
                        />
                      ))}
                    </RadioButton.Group>
                  </View>
                )}
                <TextInput
                  label="Home address (optional)"
                  mode="outlined"
                  multiline
                  numberOfLines={3}
                  value={address}
                  disabled={saving}
                  onChangeText={(value) => {
                    setAddress(value);
                    setError(null);
                  }}
                  error={!validAddress(address)}
                  accessibilityLabel="Home address, optional"
                />
                {!validAddress(address) && (
                  <HelperText type="error" visible accessibilityLiveRegion="polite">
                    Keep your address within 250 characters.
                  </HelperText>
                )}
                <Text variant="bodySmall" style={{ color: theme.colors.onSurfaceVariant }}>
                  Include your flat, house or room number, street and any useful landmark. Up to 250
                  characters.
                </Text>
                <Text variant="bodySmall" style={{ color: theme.colors.onSurfaceVariant }}>
                  Joining your community completes setup. You can add or update your address from
                  Account.
                </Text>
                <Button
                  mode="contained"
                  contentStyle={styles.button}
                  loading={saving}
                  disabled={saving || busy || !validAddress(address)}
                  onPress={() => void join()}
                >
                  Join community
                </Button>
              </>
            )}
            {(error || authError) && (
              <HelperText type="error" visible accessibilityLiveRegion="polite">
                {error ?? authError}
              </HelperText>
            )}
            <Button disabled={busy || saving} loading={busy} onPress={() => void signOut()}>
              Sign out
            </Button>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
const styles = StyleSheet.create({
  page: { flex: 1 },
  scroll: { padding: 24, flexGrow: 1 },
  content: { width: "100%", maxWidth: 600, alignSelf: "center", gap: 20 },
  group: { gap: 12 },
  button: { minHeight: 52 },
});
