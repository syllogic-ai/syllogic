import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, TextInput } from 'react-native';

import { api } from '@/api/client';
import type { AccountBalance } from '@/api/types';
import { useFilterStore } from '@/state/filter-store';
import { ThemedText } from './themed-text';
import { ThemedView } from './themed-view';

export function SavedViewsBar({ accounts }: { accounts: AccountBalance[] }) {
  const queryClient = useQueryClient();
  const filters = useFilterStore((s) => s.filters);
  const setFilters = useFilterStore((s) => s.setFilters);
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState('');

  const { data: savedViews } = useQuery({ queryKey: ['saved-views'], queryFn: api.listSavedViews });

  const createMutation = useMutation({
    mutationFn: () => api.createSavedView(name, filters),
    onSuccess: () => {
      setNaming(false);
      setName('');
      queryClient.invalidateQueries({ queryKey: ['saved-views'] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteSavedView(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['saved-views'] }),
  });

  const hasActiveFilters =
    filters.account_ids.length > 0 || filters.account_types.length > 0 || filters.currencies.length > 0;

  if (accounts.length === 0 && !savedViews?.length) return null;

  return (
    <ThemedView style={styles.container}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.row}>
        {savedViews?.map((view) => (
          <Pressable
            key={view.id}
            style={styles.pill}
            onPress={() => setFilters(view.filters)}
            onLongPress={() =>
              Alert.alert('Delete saved view?', view.name, [
                { text: 'Cancel', style: 'cancel' },
                { text: 'Delete', style: 'destructive', onPress: () => deleteMutation.mutate(view.id) },
              ])
            }
          >
            <ThemedText type="small">{view.name}</ThemedText>
          </Pressable>
        ))}

        {hasActiveFilters && !naming && (
          <Pressable style={[styles.pill, styles.pillOutline]} onPress={() => setNaming(true)}>
            <ThemedText type="small">+ Save current view</ThemedText>
          </Pressable>
        )}
      </ScrollView>

      {naming && (
        <ThemedView style={styles.nameRow}>
          <TextInput
            style={styles.input}
            placeholder="View name"
            value={name}
            onChangeText={setName}
            autoFocus
          />
          <Pressable onPress={() => createMutation.mutate()} disabled={!name || createMutation.isPending}>
            <ThemedText type="linkPrimary">Save</ThemedText>
          </Pressable>
          <Pressable onPress={() => setNaming(false)}>
            <ThemedText type="link">Cancel</ThemedText>
          </Pressable>
        </ThemedView>
      )}
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: { paddingHorizontal: 16, paddingTop: 8 },
  row: { gap: 8, paddingBottom: 8 },
  pill: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#8888',
    borderRadius: 16,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  pillOutline: { borderStyle: 'dashed' },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingBottom: 8 },
  input: {
    flex: 1,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#8888',
    borderRadius: 8,
    padding: 8,
  },
});
