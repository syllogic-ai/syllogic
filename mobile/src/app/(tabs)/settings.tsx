import { router } from 'expo-router';
import { Pressable, StyleSheet } from 'react-native';

import { authClient } from '@/auth/client';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';

export default function SettingsScreen() {
  const { data: session } = authClient.useSession();

  async function handleLogout() {
    await authClient.signOut();
    router.replace('/login');
  }

  return (
    <ThemedView style={styles.container}>
      <ThemedText type="small">Signed in as</ThemedText>
      <ThemedText type="smallBold" style={styles.email}>
        {session?.user.email}
      </ThemedText>
      <Pressable style={styles.button} onPress={handleLogout}>
        <ThemedText type="smallBold" style={{ color: 'white' }}>
          Sign out
        </ThemedText>
      </Pressable>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 16 },
  email: { marginBottom: 24 },
  button: {
    backgroundColor: '#e5484d',
    borderRadius: 8,
    padding: 14,
    alignItems: 'center',
  },
});
