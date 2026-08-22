import Foundation
import Security

/// The only unit that reads the Keychain. Mirrors @better-auth/expo's storage
/// format, including its chunking scheme for values over 1800 characters.
enum SessionStore {
    static let accessGroup = "ai.syllogic.mobile"
    static let cookieKey = "syllogic_cookie"

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

    private static func readKeychain(key: String) -> String? {
        var query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        query[kSecAttrAccessGroup as String] = accessGroup

        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data
        else { return nil }
        return String(data: data, encoding: .utf8)
    }
}
