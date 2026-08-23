import Constants from 'expo-constants';
import * as SecureStore from 'expo-secure-store';

// better-auth's Expo client is handed a storage object and calls it without
// options, so expo-secure-store's `accessGroup` is never applied. Wrapping it
// here puts the session in a Keychain access group the widget extension can
// also read. Must stay byte-identical in behaviour to raw SecureStore
// otherwise — better-auth relies on getItem being synchronous.
//
// The entitlements (mobile/app.json's ios.entitlements and
// mobile/targets/widget/expo-target.config.js) declare
// `$(AppIdentifierPrefix)ai.syllogic.mobile`. Xcode expands
// `$(AppIdentifierPrefix)` to `<TeamID>.` only at signing time -- neither
// expo-secure-store nor this file does that expansion, so a bare
// `'ai.syllogic.mobile'` access group here is NOT the fully-expanded string
// `SecItemAdd` needs at runtime. Passing that unexpanded value fails
// silently: `SecItemAdd` returns `errSecMissingEntitlement`, and
// @better-auth/expo only `console.error`s the failure, so sign-in appears to
// succeed while no session is ever persisted -- the app itself loses auth on
// relaunch on a real device (the Simulator's keychain doesn't enforce access
// groups, which is why this doesn't show up there).
//
// `expo.ios.appleTeamId` is not yet configured in mobile/app.json, so there
// is no team ID to build the real string from — do not invent one. Read it
// from `Constants.expoConfig?.ios?.appleTeamId` once it exists; until then,
// pass NO `accessGroup` at all rather than a wrong one, since an unexpanded
// group is exactly what breaks device sign-in today. The Swift-side
// counterpart (which resolves the same `<TeamID>.` prefix at runtime instead
// of reading app.json) lives in
// `mobile/targets/widget/Core/SessionStore.swift` as
// `SessionStore.accessGroup` -- both sides must agree once a team ID exists.
const appleTeamId = Constants.expoConfig?.ios?.appleTeamId;
const options: SecureStore.SecureStoreOptions = {
  // expo-secure-store defaults to `WHEN_UNLOCKED`, which makes
  // `SecItemCopyMatching` fail with `errSecInteractionNotAllowed` whenever
  // WidgetKit regenerates a timeline while the device is locked (routine
  // for a background refresh). `AFTER_FIRST_UNLOCK` keeps the item readable
  // from the moment the device is first unlocked after a boot until the
  // next reboot, which covers that case while still not being `ALWAYS`
  // (deprecated, no protection at all). Must match on both the write side
  // here and any place that re-adds this item; a mismatched accessibility
  // class does not itself change what `readKeychain` can find (Keychain
  // reads aren't filtered by accessibility class), but the item must have
  // been written with an accessible-enough class in the first place for it
  // to be there to read.
  keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK,
  ...(appleTeamId ? { accessGroup: `${appleTeamId}.ai.syllogic.mobile` } : {}),
};

export const sharedSecureStore = {
  getItem: (key: string) => SecureStore.getItem(key, options),
  setItem: (key: string, value: string) =>
    SecureStore.setItemAsync(key, value, options),
  deleteItemAsync: (key: string) => SecureStore.deleteItemAsync(key, options),
};
