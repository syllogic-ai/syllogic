import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { FlatList, Modal, Pressable, StyleSheet } from 'react-native';

import { api } from '@/api/client';
import type { AccountBalance } from '@/api/types';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { FilterSheet } from '@/components/filter-sheet';
import { SavedViewsBar } from '@/components/saved-views-bar';
import { applyFilters, useFilterStore } from '@/state/filter-store';

export default function AccountsScreen() {
  const [filterSheetOpen, setFilterSheetOpen] = useState(false);
  const filters = useFilterStore((s) => s.filters);

  const { data, isLoading, isError, refetch, isRefetching } = useQuery({
    queryKey: ['account-balances'],
    queryFn: api.getAccountBalances,
  });

  const accounts = useMemo(() => applyFilters(data ?? [], filters), [data, filters]);
  const total = accounts.reduce((sum, a) => sum + a.balance, 0);

  return (
    <ThemedView style={styles.container}>
      <SavedViewsBar accounts={data ?? []} />

      <Pressable style={styles.filterButton} onPress={() => setFilterSheetOpen(true)}>
        <ThemedText type="link">Filter accounts</ThemedText>
      </Pressable>

      {isLoading && <ThemedText style={styles.padded}>Loading accounts…</ThemedText>}
      {isError && (
        <ThemedText style={styles.padded}>Couldn't load accounts. Pull down to retry.</ThemedText>
      )}

      {!isLoading && !isError && (
        <>
          <ThemedText type="subtitle" style={styles.padded}>
            {total.toFixed(2)} {accounts[0]?.currency ?? ''}
          </ThemedText>
          <FlatList
            data={accounts}
            keyExtractor={(item) => item.account_id}
            onRefresh={refetch}
            refreshing={isRefetching}
            contentContainerStyle={styles.list}
            ListEmptyComponent={<ThemedText style={styles.padded}>No accounts match this filter.</ThemedText>}
            renderItem={({ item }) => <AccountRow account={item} />}
          />
        </>
      )}

      <Modal visible={filterSheetOpen} animationType="slide" onRequestClose={() => setFilterSheetOpen(false)}>
        <FilterSheet accounts={data ?? []} onClose={() => setFilterSheetOpen(false)} />
      </Modal>
    </ThemedView>
  );
}

function AccountRow({ account }: { account: AccountBalance }) {
  return (
    <ThemedView type="backgroundElement" style={styles.row}>
      <ThemedView style={{ flex: 1 }}>
        <ThemedText type="smallBold">{account.name}</ThemedText>
        <ThemedText type="small">{account.account_type}</ThemedText>
      </ThemedView>
      <ThemedText type="smallBold">
        {account.balance.toFixed(2)} {account.currency}
      </ThemedText>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  padded: { padding: 16 },
  filterButton: { paddingHorizontal: 16, paddingBottom: 8 },
  list: { paddingHorizontal: 16, gap: 8, paddingBottom: 32 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 12,
    borderRadius: 10,
  },
});
