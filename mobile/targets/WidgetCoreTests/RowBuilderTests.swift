import XCTest
@testable import WidgetCore

final class RowBuilderTests: XCTestCase {
    private func balance(_ id: String, _ name: String) -> AccountBalance {
        AccountBalance(accountId: id, name: name, balance: 100,
                       currency: "EUR", accountType: "checking", logoUrl: nil)
    }

    func testRendersAtMostThreeAccounts() {
        let fetched = (1...5).map { balance("a\($0)", "Account \($0)") }
        let selected = fetched.map { $0.accountId }

        let rows = RowBuilder.rows(from: fetched, selected: selected) { _ in nil }

        XCTAssertEqual(rows.count, 3)
        XCTAssertEqual(rows.map(\.id), ["a1", "a2", "a3"])
    }

    func testPreservesSelectionOrder() {
        let fetched = [balance("a1", "One"), balance("a2", "Two"), balance("a3", "Three")]

        let rows = RowBuilder.rows(from: fetched, selected: ["a3", "a1"]) { _ in nil }

        XCTAssertEqual(rows.map(\.id), ["a3", "a1"])
    }

    func testDropsSelectedAccountsThatNoLongerExist() {
        let fetched = [balance("a1", "One")]

        let rows = RowBuilder.rows(from: fetched, selected: ["a1", "deleted"]) { _ in nil }

        XCTAssertEqual(rows.map(\.id), ["a1"])
    }

    func testAttachesLogoFileURL() {
        let fetched = [balance("a1", "One")]
        let stub = URL(fileURLWithPath: "/tmp/a1.img")

        let rows = RowBuilder.rows(from: fetched, selected: ["a1"]) { id in
            id == "a1" ? stub : nil
        }

        XCTAssertEqual(rows.first?.logoFileURL, stub)
    }
}
