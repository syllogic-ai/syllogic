import XCTest
@testable import WidgetCore

/// Pins the palette to the spec's converted values. The web globals.css is the
/// source of truth; these were converted from oklch ONCE (they land exactly on
/// Tailwind stone). Any drift here is a bug, not a refresh.
final class ThemeTests: XCTestCase {
    private func hex(_ t: (r: Double, g: Double, b: Double, a: Double)) -> String {
        String(format: "#%02X%02X%02X", Int(round(t.r*255)), Int(round(t.g*255)), Int(round(t.b*255)))
    }

    func testLightPaletteIsPinned() {
        XCTAssertEqual(hex(Theme.rgba(.background, dark: false)), "#FFFFFF")
        XCTAssertEqual(hex(Theme.rgba(.foreground, dark: false)), "#0C0A09")
        XCTAssertEqual(hex(Theme.rgba(.mutedForeground, dark: false)), "#79716B")
        XCTAssertEqual(hex(Theme.rgba(.hairline, dark: false)), "#E7E5E4")
        XCTAssertEqual(Theme.rgba(.hairline, dark: false).a, 1.0)
        XCTAssertEqual(hex(Theme.rgba(.primary, dark: false)), "#1C1917")
        XCTAssertEqual(hex(Theme.rgba(.primaryForeground, dark: false)), "#FAFAF9")
    }

    func testDarkPaletteIsPinned() {
        XCTAssertEqual(hex(Theme.rgba(.background, dark: true)), "#131110")
        XCTAssertEqual(hex(Theme.rgba(.foreground, dark: true)), "#FAFAF9")
        XCTAssertEqual(hex(Theme.rgba(.mutedForeground, dark: true)), "#A6A09B")
        XCTAssertEqual(hex(Theme.rgba(.hairline, dark: true)), "#FFFFFF")
        XCTAssertEqual(Theme.rgba(.hairline, dark: true).a, 0.12, accuracy: 0.001)
        XCTAssertEqual(hex(Theme.rgba(.logoPlate, dark: true)), "#FAFAF9")
        XCTAssertEqual(Theme.rgba(.logoPlate, dark: true).a, 0.9, accuracy: 0.001)
    }

    func testGrayRampIsPinnedAndSchemeInvariant() {
        let hexes = Theme.grayRamp.map { String(format: "#%02X%02X%02X",
            Int(round($0.r*255)), Int(round($0.g*255)), Int(round($0.b*255))) }
        XCTAssertEqual(hexes, ["#0A0A0A", "#525252", "#8A8A8A", "#A1A1A1", "#D4D4D4"])
    }

    func testFontNamesArePinned() {
        XCTAssertEqual(Theme.jetBrainsMonoNames[.regular], "JetBrainsMono-Regular")
        XCTAssertEqual(Theme.jetBrainsMonoNames[.medium], "JetBrainsMono-Medium")
        XCTAssertEqual(Theme.jetBrainsMonoNames[.bold], "JetBrainsMono-Bold")
    }

    func testGrayRampColorWrapsNegativeIndexWithoutTrapping() {
        XCTAssertEqual(Theme.grayRampColor(-1), Theme.grayRampColor(4))
        XCTAssertEqual(Theme.grayRampColor(-5), Theme.grayRampColor(0))
    }
}
