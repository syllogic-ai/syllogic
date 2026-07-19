import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet } from 'react-native';

import type { AccountBalance, SavedViewFilters } from '@/api/types';
import { EMPTY_FILTERS, useFilterStore } from '@/state/filter-store';
import { ThemedText } from './themed-text';
import { ThemedView } from './themed-view';

function toggle(list: string[], value: string) {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

export function FilterSheet({ accounts, onClose }: { accounts: AccountBalance[]; onClose: () => void }) {
  const filters = useFilterStore((s) => s.filters);
  const setFilters = useFilterStore((s) => s.setFilters);
  const reset = useFilterStore((s) => s.reset);
  const [draft, setDraft] = useState<SavedViewFilters>(filters);

  const accountTypes = [...new Set(accounts.map((a) => a.account_type))];
  const currencies = [...new Set(accounts.map((a) => a.currency))];

  return (
    <ThemedView style={styles.container}>
      <ThemedText type="subtitle" style={styles.heading}>
        Filter accounts
      </ThemedText>

      <ScrollView contentContainerStyle={styles.scroll}>
        <ThemedText type="smallBold">Accounts</ThemedText>
        <ThemedView style={styles.chipRow}>
          {accounts.map((a) => (
            <Chip
              key={a.account_id}
              label={a.name}
              selected={draft.account_ids.includes(a.account_id)}
              onPress={() => setDraft((d) => ({ ...d, account_ids: toggle(d.account_ids, a.account_id) }))}
            />
          ))}
        </ThemedView>

        <ThemedText type="smallBold" style={styles.sectionGap}>
          Account type
        </ThemedText>
        <ThemedView style={styles.chipRow}>
          {accountTypes.map((t) => (
            <Chip
              key={t}
              label={t}
              selected={draft.account_types.includes(t)}
              onPress={() => setDraft((d) => ({ ...d, account_types: toggle(d.account_types, t) }))}
            />
          ))}
        </ThemedView>

        <ThemedText type="smallBold" style={styles.sectionGap}>
          Currency
        </ThemedText>
        <ThemedView style={styles.chipRow}>
          {currencies.map((c) => (
            <Chip
              key={c}
              label={c}
              selected={draft.currencies.includes(c)}
              onPress={() => setDraft((d) => ({ ...d, currencies: toggle(d.currencies, c) }))}
            />
          ))}
        </ThemedView>
      </ScrollView>

      <ThemedView style={styles.footer}>
        <Pressable
          onPress={() => {
            setDraft(EMPTY_FILTERS);
            reset();
          }}
        >
          <ThemedText type="link">Clear all</ThemedText>
        </Pressable>
        <Pressable
          style={styles.applyButton}
          onPress={() => {
            setFilters(draft);
            onClose();
          }}
        >
          <ThemedText type="smallBold" style={{ color: 'white' }}>
            Apply
          </ThemedText>
        </Pressable>
      </ThemedView>
    </ThemedView>
  );
}

function Chip({ label, selected, onPress }: { label: string; selected: boolean; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={[styles.chip, selected && styles.chipSelected]}>
      <ThemedText type="small" style={selected ? { color: 'white' } : undefined}>
        {label}
      </ThemedText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 16, paddingTop: 48 },
  heading: { marginBottom: 16 },
  scroll: { gap: 8, paddingBottom: 32 },
  sectionGap: { marginTop: 16 },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#8888',
    borderRadius: 16,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  chipSelected: { backgroundColor: '#208AEF', borderColor: '#208AEF' },
  footer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 16,
  },
  applyButton: {
    backgroundColor: '#208AEF',
    borderRadius: 8,
    paddingHorizontal: 20,
    paddingVertical: 10,
  },
});
