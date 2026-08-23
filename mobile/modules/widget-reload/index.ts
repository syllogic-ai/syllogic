import { requireNativeModule } from 'expo-modules-core';
import { Platform } from 'react-native';

// requireNativeModule() throws if the native module isn't registered (Expo
// Go, a stale dev client, or autolinking failing silently). Some call sites
// (e.g. login) run very early in app startup, so an unguarded throw here
// would crash sign-in over what is only a best-effort widget refresh —
// failing to refresh widgets must never break the app. Swallow the lookup
// failure and degrade to the same no-op used off iOS.
let nativeModule: { reloadWidgets: () => void } | null = null;
if (Platform.OS === 'ios') {
  try {
    nativeModule = requireNativeModule('WidgetReload');
  } catch {
    nativeModule = null;
  }
}

/// Asks WidgetKit to rebuild every timeline. No-op off iOS.
export function reloadWidgets(): void {
  nativeModule?.reloadWidgets();
}
