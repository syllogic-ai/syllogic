import Security
import XCTest
@testable import WidgetCore

final class SessionStoreTests: XCTestCase {
    func testPlainValuePassesThrough() {
        let result = SessionStore.assemble(marker: "syllogic.session=abc123") { _ in nil }
        XCTAssertEqual(result, "syllogic.session=abc123")
    }

    func testNilMarkerReturnsNil() {
        XCTAssertNil(SessionStore.assemble(marker: nil) { _ in nil })
    }

    /// Single-digit counts are where @better-auth/expo's own reader returns nil.
    func testReassemblesSingleDigitChunkCount() {
        let parts = ["aaa", "bbb", "ccc"]
        let result = SessionStore.assemble(marker: "ba-chunks:3") { parts[$0] }
        XCTAssertEqual(result, "aaabbbccc")
    }

    /// Two-digit counts are where their reader silently truncates to 2 chunks.
    func testReassemblesTwoDigitChunkCount() {
        let parts = (0..<12).map { "\($0)," }
        let result = SessionStore.assemble(marker: "ba-chunks:12") { parts[$0] }
        XCTAssertEqual(result, "0,1,2,3,4,5,6,7,8,9,10,11,")
    }

    func testMissingChunkReturnsNil() {
        XCTAssertNil(SessionStore.assemble(marker: "ba-chunks:3") { $0 == 1 ? nil : "x" })
    }

    func testMalformedCountReturnsNil() {
        XCTAssertNil(SessionStore.assemble(marker: "ba-chunks:banana") { _ in "x" })
    }

    // MARK: - parseCookieHeader (real @better-auth/expo jar shapes)
    //
    // The Keychain does not store a raw `Cookie` header — it stores a JSON
    // cookie jar written by @better-auth/expo's `getSetCookie`, shaped like
    // `{"<cookie-name>":{"value":"<token>.<sig>","expires":"<ISO8601>"|null}}`.
    // These mirror that library's own `getCookie` (dist/client.js) so the
    // widget sends the same header the app's own better-auth client would.

    func testValidJarProducesCookieHeader() {
        let jar = """
        {"better-auth.session_token":{"value":"tok.sig","expires":"2999-01-01T00:00:00.000Z"}}
        """
        XCTAssertEqual(
            SessionStore.parseCookieHeader(fromJarJSON: jar),
            "better-auth.session_token=tok.sig"
        )
    }

    func testJarWithOnlyExpiredCookiesReturnsNil() {
        let jar = """
        {"better-auth.session_token":{"value":"tok.sig","expires":"2000-01-01T00:00:00.000Z"}}
        """
        XCTAssertNil(SessionStore.parseCookieHeader(fromJarJSON: jar))
    }

    /// @better-auth/expo's `clearSessionCache` (run on sign-out) overwrites
    /// the stored jar with the literal string `"{}"` rather than deleting
    /// the Keychain item. A naive port that treated any non-nil Keychain
    /// value as a valid session would read this as authenticated forever
    /// after a sign-out — this must produce no Cookie header at all.
    func testEmptyJarObjectReturnsNil() {
        XCTAssertNil(SessionStore.parseCookieHeader(fromJarJSON: "{}"))
    }

    func testMalformedJSONReturnsNil() {
        XCTAssertNil(SessionStore.parseCookieHeader(fromJarJSON: "not json"))
    }

    /// The cookie name differs by scheme (`better-auth.session_token` over
    /// http, `__Secure-better-auth.session_token` over https) and the
    /// backend accepts either, so every non-expired entry must be emitted,
    /// not just one.
    func testMultiCookieJarEmitsAllNonExpiredPairsSortedByName() {
        let jar = """
        {
          "__Secure-better-auth.session_token": {"value": "secure-tok", "expires": "2999-01-01T00:00:00.000Z"},
          "better-auth.session_token": {"value": "plain-tok", "expires": null},
          "better-auth.dropped": {"value": "old", "expires": "2000-01-01T00:00:00.000Z"}
        }
        """
        XCTAssertEqual(
            SessionStore.parseCookieHeader(fromJarJSON: jar),
            "__Secure-better-auth.session_token=secure-tok; better-auth.session_token=plain-tok"
        )
    }

    func testChunkedJarReassemblesThenParsesAsAValidSession() {
        let jar = """
        {"better-auth.session_token":{"value":"tok.sig","expires":null}}
        """
        let parts = [String(jar.prefix(20)), String(jar.dropFirst(20))]
        let reassembled = SessionStore.assemble(marker: "ba-chunks:2") { parts[$0] }
        XCTAssertEqual(
            SessionStore.parseCookieHeader(fromJarJSON: reassembled ?? ""),
            "better-auth.session_token=tok.sig"
        )
    }

    // MARK: - readKeychain round trip
    //
    // These write real items into the process's default Keychain with
    // `SecItemAdd`, using the exact attribute scheme expo-secure-store's iOS
    // module uses to write them on device (service "app:no-auth", account and
    // generic both the UTF-8 bytes of the storage key — see SessionStore's
    // `keychainService` doc comment and `readKeychain`), then read them back
    // through `SessionStore.readKeychain`/`SessionStore.assemble`, the same
    // path `SessionStore.cookie()` uses.
    //
    // Neither the items added here nor `SessionStore.readKeychain` specify
    // `kSecAttrAccessGroup` — production code never does either (see
    // `SessionStore`'s top-of-type doc comment for why), so there is no
    // access-group mismatch to worry about here: `swift test` runs as a
    // plain, unsigned process with no keychain-access-groups entitlement,
    // and every query in this file, exactly like production, just searches
    // whatever default group that process has.

    private func addKeychainItem(key: String, value: String) {
        let encodedKey = Data(key.utf8)
        let addQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: SessionStore.keychainService,
            kSecAttrAccount as String: encodedKey,
            kSecAttrGeneric as String: encodedKey,
            kSecValueData as String: Data(value.utf8),
        ]
        // Best-effort: clear out any leftover item from a previous crashed run
        // before adding, so this doesn't spuriously fail with errSecDuplicateItem.
        SecItemDelete(addQuery as CFDictionary)
        let status = SecItemAdd(addQuery as CFDictionary, nil)
        XCTAssertEqual(status, errSecSuccess, "SecItemAdd failed for key \(key): OSStatus \(status)")
    }

    private func deleteKeychainItem(key: String) {
        let encodedKey = Data(key.utf8)
        let deleteQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: SessionStore.keychainService,
            kSecAttrAccount as String: encodedKey,
        ]
        SecItemDelete(deleteQuery as CFDictionary)
    }

    func testReadKeychainRoundTripsAPlainValue() {
        let key = "widget-core-tests.plain.\(UUID().uuidString)"
        addKeychainItem(key: key, value: "syllogic.session=abc123")
        defer { deleteKeychainItem(key: key) }

        XCTAssertEqual(SessionStore.readKeychain(key: key), "syllogic.session=abc123")
    }

    func testReadKeychainReturnsNilWhenItemIsAbsent() {
        let key = "widget-core-tests.missing.\(UUID().uuidString)"
        XCTAssertNil(SessionStore.readKeychain(key: key))
    }

    /// Every other test in this file exercises `parseCookieHeader` directly,
    /// never `SessionStore.cookie()` itself — so a regression that stopped
    /// `cookie()` from calling into `assemble`/`parseCookieHeader` at all
    /// (e.g. returning the raw Keychain value, or always `nil`) would pass
    /// every other test here. This writes a real jar into the Keychain under
    /// `SessionStore.cookieKey` — the exact key `cookie()` reads — using the
    /// same expo-secure-store attribute scheme as the round-trip tests
    /// above, then asserts `cookie()` returns the parsed `name=value` header,
    /// not the untouched JSON jar.
    func testCookieReturnsTheParsedHeaderNotTheRawJar() throws {
        let jar = """
        {"better-auth.session_token":{"value":"tok.sig","expires":null}}
        """
        addKeychainItem(key: SessionStore.cookieKey, value: jar)
        defer { deleteKeychainItem(key: SessionStore.cookieKey) }

        XCTAssertEqual(try SessionStore.cookie(), "better-auth.session_token=tok.sig")
    }

    // MARK: - readKeychainResult: absent vs. present

    func testReadKeychainResultIsAbsentWhenItemIsMissing() {
        let key = "widget-core-tests.result-missing.\(UUID().uuidString)"
        XCTAssertEqual(SessionStore.readKeychainResult(key: key), .absent)
    }

    func testReadKeychainResultIsValueWhenItemIsPresent() {
        let key = "widget-core-tests.result-present.\(UUID().uuidString)"
        addKeychainItem(key: key, value: "syllogic.session=abc123")
        defer { deleteKeychainItem(key: key) }

        XCTAssertEqual(SessionStore.readKeychainResult(key: key), .value("syllogic.session=abc123"))
    }

    // MARK: - resolveCookie: unavailable vs. absent
    //
    // There is no reliable way to force a real `errSecInteractionNotAllowed`
    // from `swift test` (it runs as an unsigned process against the classic
    // file-based login Keychain, which has no data-protection lock state),
    // so the unavailable-vs-absent decision is exercised directly through
    // `resolveCookie(markerResult:chunk:)` with synthetic `KeychainReadResult`s
    // instead of going through the real Keychain. This is the same logic
    // `cookie()` runs in production — `cookie()` itself is just a thin
    // wrapper that supplies real `readKeychainResult` calls.

    func testResolveCookieThrowsUnavailableWhenMarkerIsUnavailable() {
        XCTAssertThrowsError(
            try SessionStore.resolveCookie(markerResult: .unavailable) { _ in .absent }
        ) { error in
            XCTAssertEqual(error as? SessionStore.AccessError, .unavailable)
        }
    }

    func testResolveCookieThrowsUnavailableWhenAChunkIsUnavailable() {
        let jar = """
        {"better-auth.session_token":{"value":"tok.sig","expires":null}}
        """
        let parts = [String(jar.prefix(20)), String(jar.dropFirst(20))]

        XCTAssertThrowsError(
            try SessionStore.resolveCookie(markerResult: .value("ba-chunks:2")) { index in
                // First chunk reads fine, second is locked mid-reassembly.
                index == 0 ? .value(parts[0]) : .unavailable
            }
        ) { error in
            XCTAssertEqual(error as? SessionStore.AccessError, .unavailable)
        }
    }

    /// A genuinely absent marker (never signed in, or signed out and the
    /// jar deleted rather than zeroed) must NOT throw — it must return `nil`
    /// so callers can distinguish "no session" from "couldn't check right
    /// now". This is the exact case the fix must not regress: before it, an
    /// absent/unreadable marker and a locked Keychain were indistinguishable.
    func testResolveCookieReturnsNilWithoutThrowingWhenMarkerIsAbsent() throws {
        let result = try SessionStore.resolveCookie(markerResult: .absent) { _ in .absent }
        XCTAssertNil(result)
    }

    func testResolveCookieSucceedsWhenEverythingIsReadable() throws {
        let jar = """
        {"better-auth.session_token":{"value":"tok.sig","expires":null}}
        """
        let result = try SessionStore.resolveCookie(markerResult: .value(jar)) { _ in .absent }
        XCTAssertEqual(result, "better-auth.session_token=tok.sig")
    }

    /// macOS's Keychain (the one `swift test` runs against — a plain, unsigned
    /// process has no data-protection keychain, so this always lands in the
    /// classic file-based login Keychain) does not honor a `Data`-typed
    /// `kSecAttrAccount` as a unique item identity. Verified directly: two
    /// `SecItemAdd` calls with the same `kSecAttrService` but different
    /// `Data`-typed `kSecAttrAccount` values collide with `errSecDuplicateItem`
    /// (-25299) — the second add fails as if the first item's account were
    /// empty — and a `Data`-typed account query fails to match an item stored
    /// with a `String`-typed account (`errSecItemNotFound`). That is exactly
    /// the encoding expo-secure-store uses and that `readKeychain` mirrors, so
    /// on a real iOS device (the data-protection keychain `expo-secure-store`
    /// actually targets) distinct `Data`-typed accounts under one service
    /// coexist and match correctly — this is a macOS-test-Keychain-only
    /// limitation, not a bug in `SessionStore`.
    ///
    /// Because of that, this environment cannot hold the marker item and all
    /// three chunk items in the Keychain at once under the shared
    /// "app:no-auth" service. Rather than fake full coexistence, this test
    /// keeps only the single item currently being looked up present at any
    /// moment — swapping it for the next chunk just before `assemble` asks for
    /// it — so every read still goes through the real `SecItemAdd`-written
    /// item and the real `SessionStore.readKeychain` / `SessionStore.assemble`
    /// production code paths.
    func testChunkedCookieReassemblesThroughTheRealKeychain() {
        let cookieKey = "widget-core-tests.cookie.\(UUID().uuidString)"
        let chunks = ["first-chunk-", "second-chunk-", "third-chunk"]

        addKeychainItem(key: cookieKey, value: "ba-chunks:3")
        var currentlyStored = cookieKey
        defer { deleteKeychainItem(key: currentlyStored) }

        let result = SessionStore.assemble(
            marker: SessionStore.readKeychain(key: cookieKey)
        ) { index in
            deleteKeychainItem(key: currentlyStored)
            let chunkKey = "\(cookieKey).\(index)"
            addKeychainItem(key: chunkKey, value: chunks[index])
            currentlyStored = chunkKey
            return SessionStore.readKeychain(key: chunkKey)
        }

        XCTAssertEqual(result, "first-chunk-second-chunk-third-chunk")
    }
}
