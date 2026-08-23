import Foundation
import Security

/// The only unit that reads the Keychain. Mirrors @better-auth/expo's storage
/// format, including its chunking scheme for values over 1800 characters and
/// its JSON cookie-jar shape (see `cookie()`/`parseCookieHeader` below).
enum SessionStore {
    /// Reads (`readKeychain`, below) deliberately never specify
    /// `kSecAttrAccessGroup`. `SecItemCopyMatching` without that attribute
    /// searches every access group the process is entitled to — which
    /// includes the shared `$(AppIdentifierPrefix)ai.syllogic.mobile` group
    /// both the app and widget declare under `keychain-access-groups` — so
    /// there is nothing to resolve at read time, and specifying one only
    /// creates a way to get it wrong.
    ///
    /// `$(AppIdentifierPrefix)` is expanded by Xcode at signing time, not by
    /// `SecItemAdd`/`SecItemCopyMatching` or expo-secure-store, so any
    /// runtime-constructed access-group string risks not matching the
    /// entitlement's real expansion. A previous version of this file
    /// "resolved" a team-ID prefix at runtime via a throwaway-keychain-item
    /// probe and built `<prefix>ai.syllogic.mobile` from it; with no team ID
    /// configured (`expo.ios.appleTeamId` is unset in `mobile/app.json`),
    /// `$(AppIdentifierPrefix)` expands to nothing, the real entitlement is
    /// the bare `ai.syllogic.mobile`, and that probe instead produced
    /// `ai.ai.syllogic.mobile` — a group the process was never entitled to —
    /// so every read silently matched nothing and the widget was permanently
    /// stuck on "Tap to sign in". Do not reintroduce an access group on the
    /// read side.
    ///
    /// The *write* side is different and is handled separately:
    /// `SecItemAdd` without an access group falls back to the first entry in
    /// `keychain-access-groups`, which is also the shared group, so
    /// `mobile/src/auth/shared-secure-store.ts` omitting `accessGroup` when
    /// `appleTeamId` is unset is correct by construction — see that file's
    /// comment for the full reasoning.
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

    /// Thrown by `cookie()` when the Keychain itself could not be queried —
    /// e.g. `errSecInteractionNotAllowed` because the device is locked and
    /// no item has become accessible yet since boot — as opposed to the
    /// session being genuinely absent or expired. Callers must not conflate
    /// this with "signed out": see `BalanceProvider`, which routes it to the
    /// silent cache fallback (same path as a network error) instead of
    /// `.signedOut`. Only a real 401/403 from the server, or a session that
    /// is genuinely absent/empty once the Keychain *was* readable, may
    /// produce `.signedOut`.
    enum AccessError: Error, Equatable {
        case unavailable
    }

    /// Returns a ready-to-send `Cookie` header string, or `nil` when there is
    /// no usable session. Reassembles any chunking first (`assemble`), then
    /// parses the reassembled JSON cookie jar the same way
    /// `@better-auth/expo`'s own client does (`parseCookieHeader`).
    ///
    /// Throws `AccessError.unavailable` if any underlying Keychain read (of
    /// the marker or of any chunk) was temporarily unavailable rather than
    /// genuinely absent. All of the actual unavailable-vs-absent decision
    /// logic lives in `resolveCookie(markerResult:chunk:)`, below, which is
    /// unit-tested directly with synthetic `KeychainReadResult`s — there is
    /// no reliable way to induce a real `errSecInteractionNotAllowed` from
    /// `swift test` (an unsigned process with no data-protection keychain),
    /// so this thin wrapper is the only piece that actually touches
    /// `SecItemCopyMatching`.
    static func cookie() throws -> String? {
        try resolveCookie(markerResult: readKeychainResult(key: cookieKey)) { index in
            readKeychainResult(key: "\(cookieKey).\(index)")
        }
    }

    /// Pure decision logic behind `cookie()`, split out so the
    /// unavailable-vs-absent distinction is testable without a real
    /// Keychain. `assemble`'s `chunk` closure is typed `(Int) -> String?`
    /// and stays that way (its signature is depended on elsewhere), so the
    /// distinction is captured out-of-band via `sawUnavailable` rather than
    /// threaded through `assemble` itself.
    static func resolveCookie(
        markerResult: KeychainReadResult,
        chunk: (Int) -> KeychainReadResult
    ) throws -> String? {
        var sawUnavailable = false
        func value(from result: KeychainReadResult) -> String? {
            switch result {
            case .value(let value): return value
            case .absent: return nil
            case .unavailable: sawUnavailable = true; return nil
            }
        }

        let json = assemble(marker: value(from: markerResult), chunk: { index in
            value(from: chunk(index))
        })

        if sawUnavailable { throw AccessError.unavailable }
        guard let json else { return nil }
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

    /// The outcome of a single Keychain query, distinguishing "found" and
    /// "genuinely absent" (`errSecItemNotFound`) from "could not be queried
    /// right now" (any other non-success `OSStatus`, most notably
    /// `errSecInteractionNotAllowed` — returned before first unlock or while
    /// the device is locked, once the item's accessibility class permits
    /// being read only after unlock). Only the first two mean anything about
    /// whether a session exists; the third means the question couldn't be
    /// answered yet.
    enum KeychainReadResult: Equatable {
        case value(String)
        case absent
        case unavailable
    }

    /// No `kSecAttrAccessGroup` is set here — see the doc comment at the top
    /// of this type for why: omitting it makes `SecItemCopyMatching` search
    /// every access group the process is entitled to, which is exactly what
    /// both production (the shared app/widget group) and `swift test`
    /// (no keychain-access-groups entitlement at all, so there is nothing to
    /// search but the default group) need.
    static func readKeychainResult(key: String) -> KeychainReadResult {
        // Matches expo-secure-store's `query(with:options:requireAuthentication:)` exactly:
        // both the account and the generic attribute are the UTF-8 bytes of the storage
        // key (not the key as a CFString) — see the `Data(key.utf8)` encoding there.
        let encodedKey = Data(key.utf8)
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: encodedKey,
            kSecAttrGeneric as String: encodedKey,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]

        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        switch status {
        case errSecSuccess:
            guard let data = item as? Data, let string = String(data: data, encoding: .utf8) else {
                return .absent
            }
            return .value(string)
        case errSecItemNotFound:
            return .absent
        default:
            // Covers errSecInteractionNotAllowed and any other unexpected
            // status: the Keychain declined to answer, it did not say "no".
            return .unavailable
        }
    }

    /// Thin `String?`-returning wrapper over `readKeychainResult` that
    /// collapses `.absent` and `.unavailable` together. Kept for call sites
    /// (and existing tests) that only ever cared about "is there a value" —
    /// `cookie()` uses `readKeychainResult` directly instead, since it needs
    /// to keep those two cases apart.
    static func readKeychain(key: String) -> String? {
        if case .value(let value) = readKeychainResult(key: key) { return value }
        return nil
    }
}
