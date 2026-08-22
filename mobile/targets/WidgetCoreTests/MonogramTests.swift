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

    /// Pins the actual DJB2-derived palette indices for fixed ids. This only
    /// proves the hash algorithm itself (seed 5381, multiplier 33) is
    /// launch-stable — it does NOT prove `color(for:)` is stable across
    /// process launches by running it twice in one process, since Swift's
    /// per-launch-seeded Hasher/hashValue would also return the same value
    /// twice within a single run and pass trivially. A future swap to
    /// Hasher-based hashing changes these indices and fails this test.
    func testPaletteIndexIsPinnedForKnownIDs() {
        XCTAssertEqual(Monogram.paletteIndex(for: "a1b2c3"), 3)
        XCTAssertEqual(Monogram.paletteIndex(for: "user-1"), 4)
        XCTAssertEqual(Monogram.paletteIndex(for: "acct-42"), 5)
        XCTAssertEqual(Monogram.paletteIndex(for: "xyz"), 2)
    }

    func testColorDiffersForDifferentIDs() {
        let colors = Set(["a", "b", "c", "d", "e", "f"].map { Monogram.color(for: $0) })
        XCTAssertGreaterThan(colors.count, 1)
    }
}
