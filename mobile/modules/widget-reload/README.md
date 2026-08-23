# widget-reload

Local Expo module that asks WidgetKit to reload all timelines
(`WidgetCenter.shared.reloadAllTimelines()`) after sign-in and settings
changes.

## Why `expo-modules-core` is a direct dependency

`index.ts` imports `expo-modules-core` directly (for `requireNativeModule`).
Because this workspace uses pnpm's strict linking, a package can only import
what it directly declares in its own `package.json` — so `expo-modules-core`
must be listed as a direct dependency of `mobile/package.json`, not just
pulled in transitively through `expo`.

## Why the version is pinned exactly

`mobile/package.json` pins `expo-modules-core` to an **exact** version
(`57.0.6`, no `~` range) to match whatever version `expo` itself resolves to.
Without this, pnpm can end up hoisting two copies of `expo-modules-core`
(one satisfying `expo`'s pin, one satisfying a floating `~57.x.x` range),
which duplicates the native module registry and breaks native module lookups
at runtime.

**This pin must be re-checked every time `expo` is upgraded.** After bumping
`expo`, run:

```sh
ls -d node_modules/.pnpm/expo-modules-core@* | sed 's|.*expo-modules-core@||' | cut -d_ -f1 | sort -u
```

If that prints more than one version, update the exact pin in
`mobile/package.json` to match the version `expo` now resolves, then
reinstall and re-run the command to confirm only one version remains.
