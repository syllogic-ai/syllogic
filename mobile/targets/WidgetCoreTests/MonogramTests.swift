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

    /// Pins the actual DJB2-derived palette indices for fixed ids (mod 5,
    /// matching the 5-entry gray ramp). This only proves the hash algorithm
    /// itself (seed 5381, multiplier 33) is launch-stable — it does NOT
    /// prove `backgroundColor(for:)` is stable across process launches by
    /// running it twice in one process, since Swift's per-launch-seeded
    /// Hasher/hashValue would also return the same value twice within a
    /// single run and pass trivially. A future swap to Hasher-based hashing
    /// changes these indices and fails this test.
    func testPaletteIndexIsPinnedForKnownIDs() {
        XCTAssertEqual(Monogram.paletteIndex(for: "a1b2c3"), 3)
        XCTAssertEqual(Monogram.paletteIndex(for: "user-1"), 2)
        XCTAssertEqual(Monogram.paletteIndex(for: "acct-42"), 4)
        XCTAssertEqual(Monogram.paletteIndex(for: "xyz"), 2)
    }

    func testBackgroundColorsVaryAcrossRamp() {
        let colors = Set(["a", "b", "c", "d", "e", "f"].map { Monogram.paletteIndex(for: $0) })
        XCTAssertGreaterThan(colors.count, 1)
    }

    /// Steps 0-1 are dark squares (light initials); 2-4 light squares (dark
    /// initials). Pin via index so the rule can't silently invert.
    func testInitialsColorFollowsRampStep() {
        for id in ["a1b2c3", "user-1", "acct-42", "xyz", "q", "zz"] {
            let step = Monogram.paletteIndex(for: id)
            let expectDark = step >= 2
            XCTAssertEqual(Monogram.initialsColor(for: id) == Theme.color(.foreground, dark: false),
                           expectDark, "id \(id) step \(step)")
        }
    }
}
