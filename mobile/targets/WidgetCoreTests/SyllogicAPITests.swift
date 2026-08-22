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
    }

    func testUnauthorizedWithoutCookie() async {
        do {
            _ = try await makeAPI(cookie: nil).fetchBalances()
            XCTFail("expected unauthorized")
        } catch let error as SyllogicAPI.APIError {
            XCTAssertEqual(error, .unauthorized)
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
