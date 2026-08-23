import XCTest
@testable import WidgetCore

/// Intercepts requests so tests never touch the network.
final class StubURLProtocol: URLProtocol {
    nonisolated(unsafe) static var statusCode = 200
    nonisolated(unsafe) static var body = Data()
    nonisolated(unsafe) static var lastRequest: URLRequest?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        StubURLProtocol.lastRequest = request
        let response = HTTPURLResponse(url: request.url!,
                                       statusCode: StubURLProtocol.statusCode,
                                       httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: StubURLProtocol.body)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

final class SyllogicAPITests: XCTestCase {
    override func setUp() {
        super.setUp()
        StubURLProtocol.statusCode = 200
        StubURLProtocol.body = Data()
        StubURLProtocol.lastRequest = nil
    }

    private func makeAPI(cookie: String? = "syllogic.session=abc") -> SyllogicAPI {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubURLProtocol.self]
        return SyllogicAPI(baseURL: URL(string: "https://api.example")!,
                           session: URLSession(configuration: config),
                           cookieProvider: { cookie })
    }

    func testFetchesAndDecodesBalances() async throws {
        StubURLProtocol.statusCode = 200
        StubURLProtocol.body = """
        [{"account_id":"a1","name":"Main Checking","balance":7425.0,
          "currency":"EUR","account_type":"checking","logo_url":null}]
        """.data(using: .utf8)!

        let balances = try await makeAPI().fetchBalances()

        XCTAssertEqual(balances.count, 1)
        XCTAssertEqual(balances.first?.name, "Main Checking")
        XCTAssertEqual(balances.first?.balance, 7425.0)
    }

    func testSendsSessionCookie() async throws {
        StubURLProtocol.statusCode = 200
        StubURLProtocol.body = "[]".data(using: .utf8)!

        _ = try await makeAPI(cookie: "syllogic.session=abc").fetchBalances()

        XCTAssertEqual(
            StubURLProtocol.lastRequest?.value(forHTTPHeaderField: "Cookie"),
            "syllogic.session=abc"
        )
        XCTAssertEqual(StubURLProtocol.lastRequest?.url?.path, "/api/analytics/account-balances")
    }

    func testUnauthorizedWithoutCookie() async {
        StubURLProtocol.lastRequest = nil

        do {
            _ = try await makeAPI(cookie: nil).fetchBalances()
            XCTFail("expected unauthorized")
        } catch let error as SyllogicAPI.APIError {
            XCTAssertEqual(error, .unauthorized)
            XCTAssertNil(StubURLProtocol.lastRequest, "no request should have been made without a cookie")
        } catch {
            XCTFail("unexpected error \(error)")
        }
    }

    func testMapsHTTP401ToUnauthorized() async {
        StubURLProtocol.statusCode = 401
        StubURLProtocol.body = Data()

        do {
            _ = try await makeAPI().fetchBalances()
            XCTFail("expected unauthorized")
        } catch let error as SyllogicAPI.APIError {
            XCTAssertEqual(error, .unauthorized)
        } catch {
            XCTFail("unexpected error \(error)")
        }
    }

    func testMapsServerErrorToTransport() async {
        StubURLProtocol.statusCode = 500
        StubURLProtocol.body = Data()

        do {
            _ = try await makeAPI().fetchBalances()
            XCTFail("expected transport")
        } catch let error as SyllogicAPI.APIError {
            XCTAssertEqual(error, .transport)
        } catch {
            XCTFail("unexpected error \(error)")
        }
    }

    /// A `cookieProvider` that throws (mirrors `SessionStore.cookie()`
    /// throwing `AccessError.unavailable` when the Keychain is locked) must
    /// map to `.keychainUnavailable`, NOT `.unauthorized` — the whole point
    /// of the distinction is that `BalanceProvider` treats these
    /// differently (cache fallback vs. `.signedOut`).
    func testKeychainUnavailableCookieProviderMapsToKeychainUnavailable() async {
        struct StubError: Error {}
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubURLProtocol.self]
        let api = SyllogicAPI(baseURL: URL(string: "https://api.example")!,
                              session: URLSession(configuration: config),
                              cookieProvider: { throw StubError() })
        StubURLProtocol.lastRequest = nil

        do {
            _ = try await api.fetchBalances()
            XCTFail("expected keychainUnavailable")
        } catch let error as SyllogicAPI.APIError {
            XCTAssertEqual(error, .keychainUnavailable)
            XCTAssertNil(StubURLProtocol.lastRequest, "no request should have been made when the cookie couldn't be read")
        } catch {
            XCTFail("unexpected error \(error)")
        }
    }

    func testMapsBadJSONToDecoding() async {
        StubURLProtocol.statusCode = 200
        StubURLProtocol.body = "not json".data(using: .utf8)!

        do {
            _ = try await makeAPI().fetchBalances()
            XCTFail("expected decoding")
        } catch let error as SyllogicAPI.APIError {
            XCTAssertEqual(error, .decoding)
        } catch {
            XCTFail("unexpected error \(error)")
        }
    }
}

/// Pins the logo-URL resolution contract: company_logos.logo_url stores
/// relative paths that the web resolves against its page origin; the widget
/// must resolve them against the API origin or logos silently never load.
final class ResolveAssetURLTests: XCTestCase {
    private let base = URL(string: "https://app.syllogic.ai")!

    func testRelativePathResolvesAgainstBase() {
        XCTAssertEqual(
            SyllogicAPI.resolveAssetURL("/uploads/logos/abnamro.png", against: base)?.absoluteString,
            "https://app.syllogic.ai/uploads/logos/abnamro.png"
        )
    }

    func testAbsoluteURLPassesThroughUnchanged() {
        XCTAssertEqual(
            SyllogicAPI.resolveAssetURL("https://img.logo.dev/ing.com?size=64", against: base)?.absoluteString,
            "https://img.logo.dev/ing.com?size=64"
        )
    }

    func testNilEmptyAndWhitespaceReturnNil() {
        XCTAssertNil(SyllogicAPI.resolveAssetURL(nil, against: base))
        XCTAssertNil(SyllogicAPI.resolveAssetURL("", against: base))
        XCTAssertNil(SyllogicAPI.resolveAssetURL("   ", against: base))
    }

    func testGarbageWithoutSchemeOrSlashReturnsNil() {
        XCTAssertNil(SyllogicAPI.resolveAssetURL("logos/x.png", against: base))
    }

    func testBaseWithPathStillYieldsRootedResolution() {
        let deepBase = URL(string: "https://app.syllogic.ai/api")!
        XCTAssertEqual(
            SyllogicAPI.resolveAssetURL("/uploads/logos/x.png", against: deepBase)?.absoluteString,
            "https://app.syllogic.ai/uploads/logos/x.png"
        )
    }
}
