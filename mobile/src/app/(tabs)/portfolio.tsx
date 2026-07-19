import { useQuery } from '@tanstack/react-query';
import { FlatList, StyleSheet } from 'react-native';

import { api } from '@/api/client';
import type { Holding } from '@/api/types';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';

export default function PortfolioScreen() {
  const summary = useQuery({ queryKey: ['portfolio-summary'], queryFn: api.getPortfolioSummary });
  const holdings = useQuery({ queryKey: ['holdings'], queryFn: api.getHoldings });

  const isLoading = summary.isLoading || holdings.isLoading;
  const isError = summary.isError || holdings.isError;

  return (
    <ThemedView style={styles.container}>
      {isLoading && <ThemedText style={styles.padded}>Loading portfolio…</ThemedText>}
      {isError && <ThemedText style={styles.padded}>Couldn't load portfolio. Pull down to retry.</ThemedText>}

      {!isLoading && !isError && (
        <>
          <ThemedView style={styles.totalCard}>
            <ThemedText type="small">Total portfolio value</ThemedText>
            <ThemedText type="title" style={styles.totalValue}>
              {summary.data?.total_value.toFixed(2)} {summary.data?.currency}
            </ThemedText>
          </ThemedView>

          <FlatList
            data={holdings.data ?? []}
            keyExtractor={(item) => item.id}
            onRefresh={() => {
              summary.refetch();
              holdings.refetch();
            }}
            refreshing={holdings.isRefetching || summary.isRefetching}
            contentContainerStyle={styles.list}
            ListEmptyComponent={<ThemedText style={styles.padded}>No holdings yet.</ThemedText>}
            renderItem={({ item }) => <HoldingRow holding={item} />}
          />
        </>
      )}
    </ThemedView>
  );
}

function HoldingRow({ holding }: { holding: Holding }) {
  return (
    <ThemedView type="backgroundElement" style={styles.row}>
      <ThemedView style={{ flex: 1 }}>
        <ThemedText type="smallBold">{holding.name ?? holding.symbol}</ThemedText>
        <ThemedText type="small">
          {holding.quantity} {holding.symbol}
          {holding.is_stale ? ' · stale price' : ''}
        </ThemedText>
      </ThemedView>
      <ThemedText type="smallBold">
        {holding.current_value_user_currency?.toFixed(2) ?? '—'} {holding.currency}
      </ThemedText>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  padded: { padding: 16 },
  totalCard: { margin: 16, padding: 16, borderRadius: 12, backgroundColor: '#208AEF22' },
  totalValue: { fontSize: 32, lineHeight: 38, marginTop: 4 },
  list: { paddingHorizontal: 16, gap: 8, paddingBottom: 32 },
  row: { flexDirection: 'row', alignItems: 'center', padding: 12, borderRadius: 10 },
});
