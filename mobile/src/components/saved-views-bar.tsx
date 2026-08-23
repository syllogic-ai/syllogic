import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, TextInput } from 'react-native';

import { ApiError, api } from '@/api/client';
import type { AccountBalance } from '@/api/types';
import { useFilterStore } from '@/state/filter-store';
import { ThemedText } from './themed-text';
import { ThemedView } from './themed-view';

// Backend error bodies are JSON (FastAPI's `{"detail": "..."}`), but
// ApiError.message is the raw response text. Pull the human-readable detail
// out when present, falling back to the raw text for anything else.
function backendDetail(error: unknown): string | undefined {
  if (!(error instanceof ApiError)) return undefined;
  try {
    const parsed = JSON.parse(error.message);
    if (parsed && typeof parsed.detail === 'string') return parsed.detail;
  } catch {
    // Not JSON — fall through to the raw message.
  }
  return error.message || undefined;
}

// 401 gets the sign-in prompt; other 4xx surface the backend's own message
// (e.g. the 409 "reached the maximum of 50 saved views" or 422 validation
// errors) since it's already specific and computed; network failures and
// 5xx fall back to the generic connection-oriented wording.
function errorMessageFor(error: unknown, signInMessage: string, connectionMessage: string): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return signInMessage;
    if (error.status >= 400 && error.status < 500) {
      return backendDetail(error) ?? connectionMessage;
    }
  }
  return connectionMessage;
}

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
    onError: (error) => {
      Alert.alert(
        'Could not save view',
        errorMessageFor(
          error,
          'Your session has expired. Sign in again and try saving.',
          'The view was not saved. Check your connection and try again.'
        )
      );
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteSavedView(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['saved-views'] }),
    onError: (error) => {
      Alert.alert(
        'Could not delete view',
        errorMessageFor(
          error,
          'Your session has expired. Sign in again and try again.',
          'The view was not deleted. Check your connection and try again.'
        )
      );
    },
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
