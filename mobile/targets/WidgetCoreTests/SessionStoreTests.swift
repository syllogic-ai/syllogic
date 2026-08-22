import XCTest
@testable import WidgetCore

final class SessionStoreTests: XCTestCase {
    func testPlainValuePassesThrough() {
        let result = SessionStore.assemble(marker: "syllogic.session=abc123") { _ in nil }
        XCTAssertEqual(result, "syllogic.session=abc123")
    }

    func testNilMarkerReturnsNil() {
        XCTAssertNil(SessionStore.assemble(marker: nil) { _ in nil })
    }

    /// Single-digit counts are where @better-auth/expo's own reader returns nil.
    func testReassemblesSingleDigitChunkCount() {
        let parts = ["aaa", "bbb", "ccc"]
        let result = SessionStore.assemble(marker: "ba-chunks:3") { parts[$0] }
        XCTAssertEqual(result, "aaabbbccc")
    }

    /// Two-digit counts are where their reader silently truncates to 2 chunks.
    func testReassemblesTwoDigitChunkCount() {
        let parts = (0..<12).map { "\($0)," }
        let result = SessionStore.assemble(marker: "ba-chunks:12") { parts[$0] }
        XCTAssertEqual(result, "0,1,2,3,4,5,6,7,8,9,10,11,")
    }

    func testMissingChunkReturnsNil() {
        XCTAssertNil(SessionStore.assemble(marker: "ba-chunks:3") { $0 == 1 ? nil : "x" })
    }

    func testMalformedCountReturnsNil() {
        XCTAssertNil(SessionStore.assemble(marker: "ba-chunks:banana") { _ in "x" })
    }
}
