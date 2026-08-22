import Foundation
import Security

/// The only unit that reads the Keychain. Mirrors @better-auth/expo's storage
/// format, including its chunking scheme for values over 1800 characters.
enum SessionStore {
    static let accessGroup = "ai.syllogic.mobile"
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

    static func cookie() -> String? {
        assemble(marker: readKeychain(key: cookieKey)) { index in
            readKeychain(key: "\(cookieKey).\(index)")
        }
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
