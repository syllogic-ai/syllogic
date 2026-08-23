#!/usr/bin/env bash
#
# Regenerate the native iOS project configured for production.
#
# Run this INSTEAD of a bare `expo prebuild`, because three things about this
# project's prebuild are easy to get wrong and all three fail quietly:
#
#   1. CocoaPods needs a UTF-8 locale. Without it `pod install` dies with
#      "Unicode Normalization not appropriate for ASCII-8BIT" — and
#      `expo prebuild` still exits 0, leaving you with no Pods.
#   2. The widget extension reads its API base URL from Info.plist, baked HERE
#      at prebuild time. Setting the env var only for the JS build gives you an
#      app on production and a widget on localhost, with nothing on screen
#      indicating the split.
#   3. FastAPI is not publicly reachable. Both URLs point at the Next.js origin,
#      which authenticates the session cookie and forwards with HMAC headers.
#
# Usage:
#   ./scripts/prebuild-prod.sh                       # defaults to app.syllogic.ai
#   EXPO_PUBLIC_API_URL=https://staging.example ./scripts/prebuild-prod.sh
#
set -euo pipefail

cd "$(dirname "$0")/.."

export LANG="${LANG:-en_US.UTF-8}"
export LC_ALL="${LC_ALL:-en_US.UTF-8}"
export EXPO_PUBLIC_AUTH_URL="${EXPO_PUBLIC_AUTH_URL:-https://app.syllogic.ai}"
export EXPO_PUBLIC_API_URL="${EXPO_PUBLIC_API_URL:-https://app.syllogic.ai}"

echo "auth : $EXPO_PUBLIC_AUTH_URL"
echo "api  : $EXPO_PUBLIC_API_URL"

case "$EXPO_PUBLIC_API_URL" in
  https://*) ;;
  *) echo "WARNING: not https. The widget's ATS config only permits local" >&2
     echo "         networking, so cleartext to a public host is blocked." >&2 ;;
esac

log=$(mktemp -t syllogic-prebuild)
if ! npx expo prebuild --clean > "$log" 2>&1; then
  echo "FAILED: prebuild returned non-zero" >&2; tail -30 "$log" >&2; exit 1
fi

# prebuild exits 0 even when pod install fails, so check the log, not the code.
if grep -q "Something went wrong" "$log" || ! grep -q "Installed CocoaPods" "$log"; then
  echo "FAILED: pod install did not complete (prebuild still exited 0)" >&2
  grep -iE "something went wrong|error|warning: cocoapods" "$log" | head -10 >&2
  exit 1
fi

baked=$(/usr/libexec/PlistBuddy -c "Print :SyllogicAPIBaseURL" targets/widget/Info.plist)
if [ "$baked" != "$EXPO_PUBLIC_API_URL" ]; then
  echo "FAILED: widget Info.plist has '$baked', expected '$EXPO_PUBLIC_API_URL'" >&2
  exit 1
fi

echo
echo "OK — pods installed, widget baked with: $baked"
echo
echo "NOTE: targets/widget/Info.plist is a committed file and now carries the"
echo "      production URL. Restore the default before committing unrelated work:"
echo "        git checkout mobile/targets/widget/Info.plist"
echo
echo "Next: npx expo run:ios --device   (requires expo.ios.appleTeamId to be set)"
