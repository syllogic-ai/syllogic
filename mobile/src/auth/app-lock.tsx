import * as LocalAuthentication from 'expo-local-authentication';
import { useEffect, useRef, useState, type PropsWithChildren } from 'react';
import { AppState, Pressable, StyleSheet, type AppStateStatus } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';

type AppLockState = 'locked' | 'unlocked';

/**
 * Gates the app behind Face ID / Touch ID whenever it returns to the
 * foreground with an active session. Session persistence itself lives in
 * SecureStore via the better-auth Expo client; this only gates *viewing*.
 */
export function AppLockProvider({ children }: PropsWithChildren) {
  const [state, setState] = useState<AppLockState>('locked');
  const appState = useRef<AppStateStatus>(AppState.currentState);

  async function tryUnlock() {
    const hasHardware = await LocalAuthentication.hasHardwareAsync();
    const isEnrolled = await LocalAuthentication.isEnrolledAsync();
    if (!hasHardware || !isEnrolled) {
      // No biometrics configured on this device — don't block access.
      setState('unlocked');
      return;
    }
    const result = await LocalAuthentication.authenticateAsync({
      promptMessage: 'Unlock Syllogic',
    });
    setState(result.success ? 'unlocked' : 'locked');
  }

  useEffect(() => {
    tryUnlock();
    const sub = AppState.addEventListener('change', (next) => {
      if (appState.current.match(/inactive|background/) && next === 'active') {
        setState('locked');
        tryUnlock();
      }
      appState.current = next;
    });
    return () => sub.remove();
  }, []);

  if (state === 'locked') {
    return (
      <ThemedView style={styles.container}>
        <ThemedText type="subtitle">Syllogic is locked</ThemedText>
        <Pressable onPress={tryUnlock}>
          <ThemedText type="linkPrimary">Unlock with Face ID / Touch ID</ThemedText>
        </Pressable>
      </ThemedView>
    );
  }

  return <>{children}</>;
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 16,
  },
});
