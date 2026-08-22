import SwiftUI

/// Logo fallback. Accounts frequently have no logo_url, so this renders as the
/// normal case rather than an error state.
enum Monogram {
    private static let palette: [Color] = [
        Color(red: 0.13, green: 0.54, blue: 0.94),  // blue
        Color(red: 0.07, green: 0.63, blue: 0.36),  // green
        Color(red: 0.88, green: 0.46, blue: 0.11),  // orange
        Color(red: 0.55, green: 0.36, blue: 0.86),  // purple
        Color(red: 0.85, green: 0.25, blue: 0.35),  // red
        Color(red: 0.11, green: 0.62, blue: 0.66),  // teal
    ]

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
        return Int(hash % UInt64(palette.count))
    }

    /// Deterministic across process launches. Swift's built-in hashValue is
    /// seeded per launch and must not be used here.
    static func color(for id: String) -> Color {
        palette[paletteIndex(for: id)]
    }
}
