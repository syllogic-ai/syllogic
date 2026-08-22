import XCTest
@testable import WidgetCore

final class LogoCacheTests: XCTestCase {
    private var tempDir: URL!

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
        XCTAssertNil(makeCache().localURL(forAccount: "a1"))
    }

    func testCachesDownloadedImage() async {
        StubURLProtocol.statusCode = 200
        StubURLProtocol.body = Data([0x89, 0x50, 0x4E, 0x47])  // PNG magic bytes

        let cache = makeCache()
        await cache.cache(logoUrl: "https://logo.example/ing.png", forAccount: "a1")

        XCTAssertNotNil(cache.localURL(forAccount: "a1"))
    }

    func testNilLogoUrlCachesNothing() async {
        let cache = makeCache()
        await cache.cache(logoUrl: nil, forAccount: "a1")
        XCTAssertNil(cache.localURL(forAccount: "a1"))
    }

    func testFailedDownloadCachesNothing() async {
        StubURLProtocol.statusCode = 404
        StubURLProtocol.body = Data()

        let cache = makeCache()
        await cache.cache(logoUrl: "https://logo.example/missing.png", forAccount: "a1")

        XCTAssertNil(cache.localURL(forAccount: "a1"))
    }
}
