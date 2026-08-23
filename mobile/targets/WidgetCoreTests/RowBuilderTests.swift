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

    func testDuplicateAccountIdsDoNotTrapAndFirstEntryWins() {
        let fetched = [balance("a1", "First"), balance("a1", "Second")]

        let rows = RowBuilder.rows(from: fetched, selected: ["a1"]) { _ in nil }

        XCTAssertEqual(rows.count, 1)
        XCTAssertEqual(rows.first?.name, "First")
    }

    func testCapThenDropCanYieldFewerThanThreeEvenWithAFourthValidSelection() {
        // selected.prefix(3) takes the first 3 SELECTED ids before checking
        // existence in `fetched`. If one of those first 3 is missing, the
        // result is fewer than 3 rows even when a 4th selected id would have
        // been valid. This is intended behaviour (cap happens before drop);
        // this test pins it explicitly.
        let fetched = [balance("a1", "One"), balance("a3", "Three"), balance("a4", "Four")]

        let rows = RowBuilder.rows(from: fetched, selected: ["a1", "a2", "a3", "a4"]) { _ in nil }

        XCTAssertEqual(rows.map(\.id), ["a1", "a3"])
        XCTAssertFalse(rows.map(\.id).contains("a4"))
    }
}
