import SwiftUI

/// The web app's design system, pinned. Source of truth is
/// frontend/app/globals.css (oklch), converted once to sRGB — see the design
/// spec's token table. Values land exactly on Tailwind stone; do not
/// re-derive them, change them only by re-pinning spec + tests together.
enum Theme {
    enum Token { case background, foreground, mutedForeground, hairline, primary, primaryForeground, logoPlate }
    enum Weight { case regular, medium, bold }

    private static func v(_ hex: UInt32, _ alpha: Double = 1.0) -> (r: Double, g: Double, b: Double, a: Double) {
        (Double((hex >> 16) & 0xFF) / 255, Double((hex >> 8) & 0xFF) / 255, Double(hex & 0xFF) / 255, alpha)
    }

    static func rgba(_ token: Token, dark: Bool) -> (r: Double, g: Double, b: Double, a: Double) {
        switch (token, dark) {
        case (.background, false):        return v(0xFFFFFF)
        case (.background, true):         return v(0x131110)
        case (.foreground, false):        return v(0x0C0A09)
        case (.foreground, true):         return v(0xFAFAF9)
        case (.mutedForeground, false):   return v(0x79716B)
        case (.mutedForeground, true):    return v(0xA6A09B)
        case (.hairline, false):          return v(0xE7E5E4)
        case (.hairline, true):           return v(0xFFFFFF, 0.12)
        case (.primary, false):           return v(0x1C1917)
        case (.primary, true):            return v(0xE7E5E4)
        case (.primaryForeground, false): return v(0xFAFAF9)
        case (.primaryForeground, true):  return v(0x1C1917)
        case (.logoPlate, _):             return v(0xFAFAF9, 0.9) // dark-mode-only by usage
        }
    }

    static func color(_ token: Token, dark: Bool) -> Color {
        let c = rgba(token, dark: dark)
        return Color(red: c.r, green: c.g, blue: c.b, opacity: c.a)
    }

    /// --chart-1..5, scheme-invariant.
    static let grayRamp: [(r: Double, g: Double, b: Double)] = [
        (0x0A/255, 0x0A/255, 0x0A/255), (0x52/255, 0x52/255, 0x52/255),
        (0x8A/255, 0x8A/255, 0x8A/255), (0xA1/255, 0xA1/255, 0xA1/255),
        (0xD4/255, 0xD4/255, 0xD4/255),
    ]

    static func grayRampColor(_ index: Int) -> Color {
        let c = grayRamp[index % grayRamp.count]
        return Color(red: c.r, green: c.g, blue: c.b)
    }

    static let jetBrainsMonoNames: [Weight: String] = [
        .regular: "JetBrainsMono-Regular", .medium: "JetBrainsMono-Medium", .bold: "JetBrainsMono-Bold",
    ]

    /// Custom face with a monospaced-system fallback: a packaging failure
    /// degrades to SF Mono, never to the default sans.
    static func font(size: CGFloat, weight: Weight) -> Font {
        guard let name = jetBrainsMonoNames[weight] else {
            return .system(size: size, design: .monospaced)
        }
        return Font.custom(name, size: size)
    }
}
