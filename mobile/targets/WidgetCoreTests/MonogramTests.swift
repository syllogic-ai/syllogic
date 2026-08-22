import XCTest
import SwiftUI
@testable import WidgetCore

final class MonogramTests: XCTestCase {
    func testInitialsFromTwoWords() {
        XCTAssertEqual(Monogram.initials(for: "Main Checking"), "MC")
    }

    func testInitialsFromSingleWord() {
        XCTAssertEqual(Monogram.initials(for: "Revolut"), "RE")
    }

    func testInitialsUsesFirstTwoWordsOnly() {
        XCTAssertEqual(Monogram.initials(for: "Interactive Brokers Ireland"), "IB")
    }

    func testInitialsHandlesEmptyName() {
        XCTAssertEqual(Monogram.initials(for: "   "), "?")
    }

    /// Swift's Hasher is seeded per launch, so hashValue must not be used —
    /// the colour would change every time the widget process restarts.
    func testColorIsStableForSameID() {
        let first = Monogram.color(for: "a1b2c3")
        let second = Monogram.color(for: "a1b2c3")
        XCTAssertEqual(first, second)
    }

    func testColorDiffersForDifferentIDs() {
        let colors = Set(["a", "b", "c", "d", "e", "f"].map { Monogram.color(for: $0) })
        XCTAssertGreaterThan(colors.count, 1)
    }
}
