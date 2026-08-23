import SwiftUI

/// Logo fallback. Accounts frequently have no logo_url, so this renders as the
/// normal case rather than an error state.
enum Monogram {
    static func initials(for name: String) -> String {
        let words = name
            .split(whereSeparator: { $0.isWhitespace })
            .filter { $0.contains(where: { $0.isLetter || $0.isNumber }) }

        guard let first = words.first else { return "?" }

        if words.count >= 2 {
            let a = first.prefix(1)
            let b = words[1].prefix(1)
            return (a + b).uppercased()
        }
        return first.prefix(2).uppercased()
    }

    /// Computes the palette index for `id` using a fixed DJB2 hash (seed
    /// 5381, multiplier 33). Deterministic across process launches — unlike
    /// Swift's built-in hashValue/Hasher, which are reseeded per launch and
    /// must not be used here. Exposed internally so tests can pin exact
    /// index values instead of only asserting idempotence within one run.
    static func paletteIndex(for id: String) -> Int {
        var hash: UInt64 = 5381
        for byte in id.utf8 {
            hash = (hash &* 33) &+ UInt64(byte)
        }
        return Int(hash % UInt64(Theme.grayRamp.count))
    }

    /// Square monogram background: a step on the web chart-gray ramp. The
    /// web inverts its chart ramp in dark mode; here we deliberately pin
    /// the LIGHT ramp for both schemes, because `initialsColor` below flips
    /// the initials' foreground/background instead of the ramp itself.
    static func backgroundColor(for id: String) -> Color {
        Theme.grayRampColor(paletteIndex(for: id))
    }

    /// Light initials on the two dark steps, dark initials on the three
    /// light steps — same rule both schemes.
    static func initialsColor(for id: String) -> Color {
        paletteIndex(for: id) >= 2
            ? Theme.color(.foreground, dark: false)   // #0C0A09
            : Theme.color(.foreground, dark: true)    // #FAFAF9
    }
}
