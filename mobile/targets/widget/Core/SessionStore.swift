import Foundation
import Security

/// The only unit that reads the Keychain. Mirrors @better-auth/expo's storage
/// format, including its chunking scheme for values over 1800 characters and
/// its JSON cookie-jar shape (see `cookie()`/`parseCookieHeader` below).
enum SessionStore {
    /// The keychain-access-groups entitlement (see `expo-target.config.js`
    /// and the generated `mobile/ios` entitlements) declares
    /// `$(AppIdentifierPrefix)ai.syllogic.mobile`. Xcode expands
    /// `$(AppIdentifierPrefix)` to `<TeamID>.` only at signing time — neither
    /// `SecItemAdd`/`SecItemCopyMatching` nor expo-secure-store performs that
    /// expansion for us, so `kSecAttrAccessGroup` at runtime must be the
    /// fully-expanded string. `accessGroupPrefix()` below resolves
    /// `<TeamID>.` at runtime (the standard throwaway-keychain-item trick)
    /// instead of hardcoding a team ID, since none is configured yet
    /// (`expo.ios.appleTeamId` is unset in `mobile/app.json`). The
    /// TypeScript half of this — reading
    /// `Constants.expoConfig?.ios?.appleTeamId` and building the same
    /// string, or omitting `accessGroup` entirely when that's absent — lives
    /// in `mobile/src/auth/shared-secure-store.ts`. Both sides must resolve
    /// to the same fully-expanded group once a team ID exists, or the app
    /// and the widget will read/write different keychain access groups and
    /// neither will see the other's session.
    static var accessGroup: String? {
        guard let prefix = accessGroupPrefix() else { return nil }
        return "\(prefix)ai.syllogic.mobile"
    }

    /// Cached per-process. `nil` (the outer Optional) means "not resolved
    /// yet"; `.some(nil)` (a present value wrapping a nil String) means
    /// "resolution ran and failed", so a failed resolution isn't retried on
    /// every keychain read.
    private static var cachedAccessGroupPrefix: String??

    /// Adds (or finds) a throwaway generic-password item with no explicit
    /// `kSecAttrAccessGroup`, then reads back the access group the Keychain
    /// assigned it — which, when the process holds a keychain-access-groups
    /// entitlement, is `<TeamID>.<first-declared-group>`. Only the
    /// `<TeamID>.` prefix is needed, so this works even though the probe
    /// item's own suffix doesn't match our real group. Resolves to `nil`
    /// (meaning: pass no access group) when there is no entitlement at all —
    /// unsigned `swift test` runs, and per Apple's docs the iOS Simulator's
    /// keychain, which does not enforce access groups.
    private static func accessGroupPrefix() -> String? {
        if let cached = cachedAccessGroupPrefix { return cached }

        let probeAccount = "ai.syllogic.mobile.access-group-probe"
        let probeService = "ai.syllogic.mobile.access-group-probe"
        let baseQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: probeService,
            kSecAttrAccount as String: probeAccount,
        ]

        var lookupQuery = baseQuery
        lookupQuery[kSecReturnAttributes as String] = true
        var item: CFTypeRef?
        var status = SecItemCopyMatching(lookupQuery as CFDictionary, &item)

        if status == errSecItemNotFound {
            var addQuery = baseQuery
            addQuery[kSecValueData as String] = Data()
            addQuery[kSecReturnAttributes as String] = true
            status = SecItemAdd(addQuery as CFDictionary, &item)
        }

        guard status == errSecSuccess,
              let attributes = item as? [String: Any],
              let group = attributes[kSecAttrAccessGroup as String] as? String,
              let dotIndex = group.firstIndex(of: ".")
        else {
            cachedAccessGroupPrefix = .some(nil)
            return nil
        }

        let prefix = String(group[...dotIndex]) // includes the trailing "."
        cachedAccessGroupPrefix = .some(prefix)
        return prefix
    }

    static let cookieKey = "syllogic_cookie"

    /// expo-secure-store's iOS module builds `kSecAttrService` as
    /// `(keychainService ?? "app") + ":" + (requireAuthentication ? "auth" : "no-auth")`
    /// — see `SecureStoreModule.swift`'s private `query(with:options:requireAuthentication:)`
    /// in the installed `expo-secure-store` package, plus `SecureStoreOptions.swift` where
    /// `requireAuthentication` is a non-optional `Bool` that defaults to `false` when the
    /// JS caller never sets it. `mobile/src/auth/shared-secure-store.ts` passes neither
    /// `keychainService` nor `requireAuthentication` to `SecureStore.setItemAsync` /
    /// `SecureStore.getItem`, so real session items always land under this exact service
    /// string. If either file starts passing those options (or expo-secure-store changes
    /// how it derives the service string), this constant must change to match, or
    /// `readKeychain` will silently stop finding anything again.
    static let keychainService = "app:no-auth"

    /// 10 characters. @better-auth/expo's reader slices at 11, which is why
    /// chunked values fail there; do not copy that offset.
    private static let chunkMarker = "ba-chunks:"

    /// Returns a ready-to-send `Cookie` header string, or `nil` when there is
    /// no usable session. Reassembles any chunking first (`assemble`), then
    /// parses the reassembled JSON cookie jar the same way
    /// `@better-auth/expo`'s own client does (`parseCookieHeader`).
    static func cookie() -> String? {
        guard let json = assemble(marker: readKeychain(key: cookieKey), chunk: { index in
            readKeychain(key: "\(cookieKey).\(index)")
        }) else { return nil }
        return parseCookieHeader(fromJarJSON: json)
    }

    /// Split out from Keychain access so the chunking logic is testable.
    static func assemble(marker: String?, chunk: (Int) -> String?) -> String? {
        guard let marker else { return nil }
        guard marker.hasPrefix(chunkMarker) else { return marker }

        let countText = String(marker.dropFirst(chunkMarker.count))
        guard let count = Int(countText), count >= 1 else { return nil }

        var value = ""
        for index in 0..<count {
            guard let part = chunk(index) else { return nil }
            value += part
        }
        return value
    }

    /// Mirrors `@better-auth/expo`'s `getCookie` in `dist/client.js`:
    ///
    ///     function getCookie(cookie) {
    ///         let parsed = {};
    ///         try {
    ///             parsed = JSON.parse(cookie);
    ///         } catch {}
    ///         return Object.entries(parsed).reduce((acc, [key, value]) => {
    ///             if (value.expires && new Date(value.expires) < new Date()) return acc;
    ///             return acc ? `${acc}; ${key}=${value.value}` : `${key}=${value.value}`;
    ///         }, "");
    ///     }
    ///
    /// The stored value is NOT a raw `Cookie` header — it's a JSON object
    /// keyed by cookie name, e.g.
    /// `{"better-auth.session_token":{"value":"<token>.<sig>","expires":"2026-..."}}`.
    /// The cookie name differs by scheme (`better-auth.session_token` over
    /// http, `__Secure-better-auth.session_token` over https) and the
    /// backend accepts either, so every non-expired entry is emitted — not
    /// just one. `expires: null` (no expiry set) never counts as expired,
    /// matching JS's `value.expires &&` short-circuit.
    ///
    /// Unlike the JS helper — which returns `""` for a malformed or empty
    /// jar and leaves the empty-string-vs-real-header distinction to the
    /// caller — this returns `nil` for an empty result. That matters
    /// because `@better-auth/expo` overwrites the stored jar with the
    /// literal string `"{}"` on sign-out (`clearSessionCache`) instead of
    /// deleting the Keychain item, so a jar that parses to zero usable
    /// cookies must not be mistaken for "no session" being merely
    /// unreachable — it must produce no `Cookie` header at all.
    ///
    /// Key order in the output isn't semantically meaningful to an HTTP
    /// `Cookie` header, so pairs are sorted by name for deterministic
    /// output (Swift's `JSONSerialization` does not preserve source key
    /// order the way JS's `Object.entries` does).
    static func parseCookieHeader(fromJarJSON json: String) -> String? {
        guard let data = json.data(using: .utf8),
              let object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        else { return nil }

        let now = Date()
        var pairs: [(name: String, value: String)] = []

        for (name, rawAttributes) in object {
            guard let attributes = rawAttributes as? [String: Any],
                  let value = attributes["value"] as? String
            else { continue }

            if let expiresString = attributes["expires"] as? String,
               let expiresDate = parseISO8601(expiresString),
               expiresDate < now {
                continue
            }

            pairs.append((name: name, value: value))
        }

        guard !pairs.isEmpty else { return nil }
        return pairs
            .sorted { $0.name < $1.name }
            .map { "\($0.name)=\($0.value)" }
            .joined(separator: "; ")
    }

    /// `expires` is written via `Date.toISOString()` on the JS side, which
    /// always includes fractional seconds (`"2026-01-01T00:00:00.000Z"`).
    /// Falls back to the no-fractional-seconds variant defensively.
    private static func parseISO8601(_ text: String) -> Date? {
        let withFraction = ISO8601DateFormatter()
        withFraction.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = withFraction.date(from: text) { return date }

        let withoutFraction = ISO8601DateFormatter()
        withoutFraction.formatOptions = [.withInternetDateTime]
        return withoutFraction.date(from: text)
    }

    /// `accessGroup` is injectable (defaulting to the production `SessionStore.accessGroup`)
    /// purely so tests can pass `nil`: `swift test` runs as a plain process with no
    /// keychain-access-groups entitlement, and any query carrying an access group fails
    /// with `errSecMissingEntitlement` there. Production call sites never override this.
    static func readKeychain(key: String, accessGroup: String? = SessionStore.accessGroup) -> String? {
        // Matches expo-secure-store's `query(with:options:requireAuthentication:)` exactly:
        // both the account and the generic attribute are the UTF-8 bytes of the storage
        // key (not the key as a CFString) — see the `Data(key.utf8)` encoding there.
        let encodedKey = Data(key.utf8)
        var query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: encodedKey,
            kSecAttrGeneric as String: encodedKey,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        if let accessGroup {
            query[kSecAttrAccessGroup as String] = accessGroup
        }

        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data
        else { return nil }
        return String(data: data, encoding: .utf8)
    }
}
