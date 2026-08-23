const { withDangerousMod } = require('expo/config-plugins');
const fs = require('fs');
const path = require('path');

// Matches the default in mobile/src/config.ts's API_URL -- the widget and
// the app should point at the same place when nothing is configured.
const DEFAULT_API_URL = 'http://localhost:8000';

function escapeXml(value) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

/**
 * `@bacons/apple-targets`' `Config` type has no `infoPlist` key (see
 * node_modules/@bacons/apple-targets/build/config.d.ts) -- an `infoPlist`
 * block in `expo-target.config.js` is silently discarded, not applied (see
 * the comment there). That leaves no supported way to get
 * `EXPO_PUBLIC_API_URL` into the widget extension's Info.plist through the
 * plugin itself, so this small local plugin fills that one gap: it writes
 * `SyllogicAPIBaseURL` directly into the committed
 * `mobile/targets/widget/Info.plist`, sourced from
 * `process.env.EXPO_PUBLIC_API_URL` -- the exact env var
 * `mobile/src/config.ts` reads for the app's own `API_URL` -- falling back
 * to the same `http://localhost:8000` default when it's unset, so a plain
 * `expo prebuild` with no env configured still produces a working (if
 * localhost-pointed) build.
 *
 * Must be registered in `mobile/app.json`'s `plugins` array AFTER
 * `@bacons/apple-targets`, since it must run after that plugin has turned
 * `targets/widget` into a real Xcode target -- ordering it earlier risks
 * running against a target that doesn't exist yet.
 *
 * This edits the *source* Info.plist under `mobile/targets/widget/`, not a
 * generated file under `mobile/ios/`: `@bacons/apple-targets` only writes a
 * *default* Info.plist when none is committed, and otherwise copies this
 * committed one through untouched (see the comment inside
 * `mobile/targets/widget/Info.plist` itself), so mutating the committed file
 * is what actually reaches the built widget.
 */
const withWidgetApiUrl = (config) => {
  return withDangerousMod(config, [
    'ios',
    (config) => {
      const infoPlistPath = path.join(
        config.modRequest.projectRoot,
        'targets',
        'widget',
        'Info.plist'
      );

      const apiUrl = process.env.EXPO_PUBLIC_API_URL || DEFAULT_API_URL;
      const contents = fs.readFileSync(infoPlistPath, 'utf8');

      const keyPattern = /(<key>SyllogicAPIBaseURL<\/key>\s*<string>)([^<]*)(<\/string>)/;
      if (!keyPattern.test(contents)) {
        throw new Error(
          `[with-widget-api-url] Could not find <key>SyllogicAPIBaseURL</key> in ${infoPlistPath}. ` +
            'Has the widget Info.plist template changed shape?'
        );
      }

      const updated = contents.replace(keyPattern, `$1${escapeXml(apiUrl)}$3`);
      fs.writeFileSync(infoPlistPath, updated);

      return config;
    },
  ]);
};

module.exports = withWidgetApiUrl;
