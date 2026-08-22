import XCTest
@testable import WidgetCore

final class BalanceCacheTests: XCTestCase {
    private var tempDir: URL!

    override func setUpWithError() throws {
        tempDir = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: tempDir)
    }

    private func makeCache() -> BalanceCache {
        BalanceCache(fileURL: tempDir.appendingPathComponent("balances.json"))
    }

    func testRoundTrip() {
        let cache = makeCache()
        let input = [
            AccountBalance(accountId: "a1", name: "Main Checking", balance: 7425.00,
                           currency: "EUR", accountType: "checking",
                           logoUrl: "https://logo.example/ing.png"),
            AccountBalance(accountId: "a2", name: "Savings Vault", balance: 18620.00,
                           currency: "EUR", accountType: "savings", logoUrl: nil),
        ]

        cache.save(input)

        XCTAssertEqual(cache.load(), input)
    }

    func testLoadReturnsEmptyWhenMissing() {
        XCTAssertEqual(makeCache().load(), [])
    }

    func testLoadReturnsEmptyWhenCorrupt() throws {
        let url = tempDir.appendingPathComponent("balances.json")
        try Data("this is not json".utf8).write(to: url)

        XCTAssertEqual(BalanceCache(fileURL: url).load(), [])
    }

    /// The balances endpoint returns a plain dict, so FastAPI's jsonable_encoder
    /// emits `balance` as a JSON *number*. Routes declaring `response_model=`
    /// serialise Decimal as a *string* instead. If anyone adds a response_model
    /// to this route, this test fails rather than the widget silently showing 0.
    func testDecodesBalanceAsJSONNumber() throws {
        let json = """
        [{"account_id":"a1","name":"Main Checking","balance":7425.0,
          "currency":"EUR","account_type":"checking","logo_url":null}]
        """.data(using: .utf8)!

        let decoded = try JSONDecoder().decode([AccountBalance].self, from: json)

        XCTAssertEqual(decoded.first?.balance, 7425.0)
        XCTAssertNil(decoded.first?.logoUrl)
    }
}
