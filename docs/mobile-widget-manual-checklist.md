# Balances Widget — Manual Verification

Run on a **real device** after any change to entitlements, the auth storage
adapter, or the widget target. None of this is automatable: widget extensions
cannot be driven by simulator automation, and iOS system sheets (the widget
gallery, the Face ID prompt, the configuration editor) do not accept synthetic
input.

## Blocking prerequisite

- [ ] **Set `expo.ios.appleTeamId` in `mobile/app.json`** and replace
      `REPLACE_WITH_YOUR_APPLE_TEAM_ID` in `eas.json`.
      Everything below is untrustworthy without it. The Keychain access group
      is `$(AppIdentifierPrefix)ai.syllogic.mobile`, and `AppIdentifierPrefix`
      resolves from the team ID. Simulator builds paper over this because the
      simulator keychain is permissive; on device the group will not resolve,
      `SessionStore.cookie()` returns nil, and the widget shows "Tap to sign in"
      forever with nothing on screen explaining why.

## Setup

- [ ] `cd mobile && LANG=en_US.UTF-8 npx expo prebuild --clean`
      (`LANG` is required — without it `pod install` fails while `expo prebuild`
      still exits 0.)
- [ ] Confirm the log contains `Installed CocoaPods` and no `Something went wrong`
- [ ] `LANG=en_US.UTF-8 npx expo run:ios --device <device-udid>`
- [ ] Sign in as a user with at least 3 accounts

## Previews (Xcode, not a device)

Open `mobile/targets/widget/SyllogicWidgetBundle.swift` and resume the canvas.

- [ ] "Medium — 3 accounts": three rows, logo/name/right-aligned balance
- [ ] "Small — 1 account": exactly one row, larger number
- [ ] "Medium — long name": `Interactive Brokers Ireland Limited` truncates
      without pushing the balance off-screen; EUR and USD symbols differ per row
- [ ] "Medium — signed out": shows "Tap to sign in"

## Configuration

- [ ] Long-press Home Screen → Edit → Add Widget → "Balances" appears
- [ ] Add the medium widget; it shows the placeholder, not an error
- [ ] Long-press the widget → Edit Widget → the picker lists real accounts
- [ ] Select 3 accounts; all three render with correct names and balances
- [ ] Select 5 accounts; exactly the first 3 render (AppIntents cannot cap the
      array, so `RowBuilder` enforces `.prefix(3)`)
- [ ] Add the small widget; exactly one account renders

## Data

- [ ] Balances match the Accounts tab in the app
- [ ] An account with a logo shows the image; one without shows a monogram
- [ ] Accounts in different currencies show their own currency symbols
- [ ] A monogram's colour is the same after the widget process restarts
      (colours derive from a hand-rolled DJB2 hash precisely so they survive
      relaunch — Swift's `Hasher` is seeded per launch)

## Auth

- [ ] Sign out in the app → widget shows "Tap to sign in" **without waiting**
      for the 30-minute refresh (this is what `reloadWidgets()` is for)
- [ ] Tap the widget → the app opens at sign-in (`syllogic://login`)
- [ ] Sign back in → widget shows balances again, again without waiting
- [ ] **Chunked session.** Sign in with a session cookie over 1800 characters,
      so better-auth splits it across `syllogic_cookie` plus
      `syllogic_cookie.0/.1/...`, and confirm the widget still loads balances.
      Automated tests cannot cover this: the macOS login Keychain refuses to
      hold the multiple coexisting items a real device holds, so multi-item
      account matching is verified only here. Note `@better-auth/expo@1.6.23`'s
      own reader is broken for this case (it slices at 11 against a 10-character
      marker); our Swift reader deliberately does not copy that bug.

## Resilience

- [ ] Airplane Mode → widget keeps showing the last balances, silently
      (deliberate: no timestamp, no error state)
- [ ] Delete a selected account in the app → its row disappears; others remain
- [ ] Delete ALL selected accounts → widget shows "Open Syllogic to pick
      accounts". Known wording tradeoff: it blames your selection when the real
      cause is missing data. Deliberate — see the design spec's accepted risks.
- [ ] Reboot the device → widget still renders (the Keychain item survived)

## Regeneration

- [ ] `LANG=en_US.UTF-8 npx expo prebuild --clean` reproduces the target
- [ ] `/usr/libexec/PlistBuddy -c "Print" ios/Syllogic/Syllogic.entitlements`
      lists both the App Group and the Keychain access group
- [ ] `/usr/libexec/PlistBuddy -c "Print" ios/.targets/SyllogicWidget/generated.entitlements`
      lists the same two identifiers — they must match on both sides or the
      Keychain item is not shared
- [ ] Only one `expo-modules-core` in the store:
      `ls -d node_modules/.pnpm/expo-modules-core@* | sed 's|.*expo-modules-core@||' | cut -d_ -f1 | sort -u`
      Re-pin it in `mobile/package.json` whenever `expo` is upgraded — see
      `mobile/modules/widget-reload/README.md`.
