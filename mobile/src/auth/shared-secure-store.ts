import * as SecureStore from 'expo-secure-store';

// better-auth's Expo client is handed a storage object and calls it without
// options, so expo-secure-store's `accessGroup` is never applied. Wrapping it
// here puts the session in a Keychain access group the widget extension can
// also read. Must stay byte-identical in behaviour to raw SecureStore
// otherwise — better-auth relies on getItem being synchronous.
const options: SecureStore.SecureStoreOptions = {
  accessGroup: 'ai.syllogic.mobile',
};

export const sharedSecureStore = {
  getItem: (key: string) => SecureStore.getItem(key, options),
  setItem: (key: string, value: string) =>
    SecureStore.setItemAsync(key, value, options),
  deleteItemAsync: (key: string) => SecureStore.deleteItemAsync(key, options),
};
