import { requireNativeModule } from 'expo-modules-core';
import { Platform } from 'react-native';

const nativeModule = Platform.OS === 'ios'
  ? requireNativeModule('WidgetReload')
  : null;

/// Asks WidgetKit to rebuild every timeline. No-op off iOS.
export function reloadWidgets(): void {
  nativeModule?.reloadWidgets();
}
