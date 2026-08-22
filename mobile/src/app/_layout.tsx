import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEffect } from 'react';
import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useColorScheme } from 'react-native';

import { AppLockProvider } from '@/auth/app-lock';

SplashScreen.preventAutoHideAsync();

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1 } },
});

export default function RootLayout() {
  const colorScheme = useColorScheme();
  // preventAutoHideAsync() above keeps the native splash up past the first
  // frame; without a matching hide it never comes down and the app is stuck
  // on the logo forever. Nothing here needs to block on async setup, so hide
  // as soon as the tree mounts — the session gate and app lock render their
  // own loading/locked states underneath.
  useEffect(() => {
    SplashScreen.hideAsync().catch(() => {});
  }, []);
  return (
    <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
      <QueryClientProvider client={queryClient}>
        <AppLockProvider>
          <Stack screenOptions={{ headerShown: false }} />
        </AppLockProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
