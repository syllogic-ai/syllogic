import XCTest
@testable import WidgetCore

final class LogoCacheTests: XCTestCase {
    private var tempDir: URL!

    private let accountId = "3F2504E0-4F89-11D3-9A0C-0305E82C3301"

    override func setUpWithError() throws {
        tempDir = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)

        StubURLProtocol.statusCode = 200
        StubURLProtocol.body = Data()
        StubURLProtocol.lastRequest = nil
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: tempDir)
    }

    private func makeCache() -> LogoCache {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubURLProtocol.self]
        return LogoCache(directory: tempDir, session: URLSession(configuration: config))
    }

    func testLocalURLIsNilBeforeCaching() {
        XCTAssertNil(makeCache().localURL(forAccount: accountId))
    }

    func testCachesDownloadedImage() async {
        StubURLProtocol.statusCode = 200
        StubURLProtocol.body = Data([0x89, 0x50, 0x4E, 0x47])  // PNG magic bytes

        let cache = makeCache()
        await cache.cache(logoUrl: "https://logo.example/ing.png", forAccount: accountId)

        XCTAssertNotNil(cache.localURL(forAccount: accountId))
    }

    func testNilLogoUrlCachesNothing() async {
        let cache = makeCache()
        await cache.cache(logoUrl: nil, forAccount: accountId)
        XCTAssertNil(cache.localURL(forAccount: accountId))
    }

    func testFailedDownloadCachesNothing() async {
        // Non-empty body isolates the status-code branch: this must fail on
        // the status check alone, not merely because the body is empty.
        StubURLProtocol.statusCode = 404
        StubURLProtocol.body = Data([0x89, 0x50, 0x4E, 0x47])  // PNG magic bytes

        let cache = makeCache()
        await cache.cache(logoUrl: "https://logo.example/missing.png", forAccount: accountId)

        XCTAssertNil(cache.localURL(forAccount: accountId))
    }

    func testEmptyBodyCachesNothing() async {
        // 200 status with an empty body isolates the `!data.isEmpty` guard.
        StubURLProtocol.statusCode = 200
        StubURLProtocol.body = Data()

        let cache = makeCache()
        await cache.cache(logoUrl: "https://logo.example/empty.png", forAccount: accountId)

        XCTAssertNil(cache.localURL(forAccount: accountId))
    }

    func testUnparseableLogoUrlCachesNothing() async {
        let cache = makeCache()
        await cache.cache(logoUrl: "not a url", forAccount: accountId)
        XCTAssertNil(cache.localURL(forAccount: accountId))
    }

    func testTraversalAccountIdCachesNothing() async {
        StubURLProtocol.statusCode = 200
        StubURLProtocol.body = Data([0x89, 0x50, 0x4E, 0x47])  // PNG magic bytes

        let cache = makeCache()
        let traversalId = "../escape"
        await cache.cache(logoUrl: "https://logo.example/ing.png", forAccount: traversalId)

        XCTAssertNil(cache.localURL(forAccount: traversalId))

        // No file should have escaped into the parent of tempDir.
        let escapedPath = tempDir.deletingLastPathComponent().appendingPathComponent("escape.img")
        XCTAssertFalse(FileManager.default.fileExists(atPath: escapedPath.path))
    }

    func testLocalURLIsNilForTraversalAccountId() {
        XCTAssertNil(makeCache().localURL(forAccount: "../escape"))
    }
}
