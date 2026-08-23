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

## Why the version is a range, matching `expo`'s own range

`mobile/package.json` pins `expo-modules-core` to `~57.0.6` — the same range
`expo@57.0.7` itself declares for it. The two pins must resolve to the
*same* version, not merely the same value today: an **exact** pin (e.g. a
bare `57.0.6`) looks equivalent right now but is a trap, because it doesn't
move when `expo`'s own range does. The moment a patch release of
`expo-modules-core` (e.g. `57.0.7`) ships, `expo`'s `~57.0.6` range resolves
to it while an exact `57.0.6` pin here stays put — and pnpm then hoists two
copies, one per pin, which duplicates the native module registry and breaks
native module lookups at runtime. Matching `expo`'s own range instead lets
pnpm dedupe both pins onto whatever single version satisfies them both,
automatically, as `expo-modules-core` patch releases roll forward.

**Re-verify after every `expo` upgrade** (a major/minor bump can change what
range `expo` declares, not just what version it resolves to). After bumping
`expo`, run:

```sh
ls -d node_modules/.pnpm/expo-modules-core@* | sed 's|.*expo-modules-core@||' | cut -d_ -f1 | sort -u
```

If that prints more than one version, update the range in
`mobile/package.json` to match whatever range `expo`'s own `package.json`
now declares for `expo-modules-core`, then reinstall and re-run the command
to confirm only one version remains.
