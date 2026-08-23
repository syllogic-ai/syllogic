import SwiftUI

/// Building blocks for all three families. Pure functions of their inputs —
/// no networking or storage — so the preview matrix is meaningful.
/// Sharp corners throughout: the web system is --radius: 0.

struct LogoSquare: View {
    let row: AccountRow
    let size: CGFloat
    let dark: Bool

    var body: some View {
        if let url = row.logoFileURL, let image = UIImage(contentsOfFile: url.path) {
            // Deliberate render-pass disk read: TimelineEntry values are
            // archived by WidgetKit, so embedding decoded bytes inflates every
            // archived entry. <=3 small cached PNGs on a 30-minute cadence.
            Image(uiImage: image)
                .resizable().scaledToFill()
                .frame(width: size, height: size)
                .clipped()
                // Dark bank logos vanish on the dark background; a light plate
                // behind IMAGES ONLY (monograms flip on their own).
                .background(dark ? Theme.color(.logoPlate, dark: true) : Color.clear)
        } else {
            Rectangle()
                .fill(Monogram.backgroundColor(for: row.id))
                .frame(width: size, height: size)
                .overlay(
                    Text(Monogram.initials(for: row.name))
                        .font(Theme.font(size: size * 0.36, weight: .bold))
                        .foregroundStyle(Monogram.initialsColor(for: row.id))
                )
        }
    }
}

struct MicroLabel: View {
    let text: String
    let dark: Bool
    var body: some View {
        Text(text.uppercased())
            .font(Theme.font(size: 10, weight: .medium))
            .kerning(0.6)
            .foregroundStyle(Theme.color(.mutedForeground, dark: dark))
            .lineLimit(1)
    }
}

struct BalanceText: View {
    let row: AccountRow
    let size: CGFloat
    let dark: Bool

    var body: some View {
        Text(Self.formatted(row))
            .font(Theme.font(size: size, weight: .bold))
            .foregroundStyle(Theme.color(.foreground, dark: dark))
            .lineLimit(1)
            .minimumScaleFactor(0.7)
    }

    static func formatted(_ row: AccountRow) -> String {
        let f = formatter(for: row.currency)
        return f.string(from: NSNumber(value: row.balance)) ?? "\(String(format: "%.2f", row.balance)) \(row.currency)"
    }

    private static var cache: [String: NumberFormatter] = [:]
    private static let lock = NSLock()
    private static func formatter(for code: String) -> NumberFormatter {
        lock.lock(); defer { lock.unlock() }
        if let f = cache[code] { return f }
        let f = NumberFormatter()
        f.numberStyle = .currency
        f.currencyCode = code
        f.maximumFractionDigits = 2
        cache[code] = f
        return f
    }
}

/// Hero block: micro-label + logo row, big balance under.
struct HeroBlock: View {
    let row: AccountRow
    let balanceSize: CGFloat
    let logoSize: CGFloat
    let dark: Bool

    private var label: String {
        if let inst = row.institution, !inst.isEmpty { return "\(row.name) · \(inst)" }
        return row.name
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                MicroLabel(text: label, dark: dark)
                Spacer(minLength: 6)
                LogoSquare(row: row, size: logoSize, dark: dark)
            }
            BalanceText(row: row, size: balanceSize, dark: dark)
        }
    }
}

/// One column of the medium pair: small logo + label over the balance.
struct PairColumn: View {
    let row: AccountRow
    let dark: Bool
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 6) {
                LogoSquare(row: row, size: 18, dark: dark)
                MicroLabel(text: row.name, dark: dark)
            }
            BalanceText(row: row, size: 14, dark: dark)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// Full-width row for the large family: logo, name + type, right balance.
struct LargeRow: View {
    let row: AccountRow
    let dark: Bool
    var body: some View {
        HStack(spacing: 10) {
            LogoSquare(row: row, size: 24, dark: dark)
            VStack(alignment: .leading, spacing: 0) {
                Text(row.name)
                    .font(Theme.font(size: 12, weight: .medium))
                    .foregroundStyle(Theme.color(.foreground, dark: dark))
                    .lineLimit(1)
                if let type = row.accountType, !type.isEmpty {
                    MicroLabel(text: type, dark: dark)
                }
            }
            Spacer(minLength: 6)
            BalanceText(row: row, size: 15, dark: dark)
        }
    }
}

struct Hairline: View {
    let dark: Bool
    var weight: CGFloat = 1
    var strong: Bool = false
    var body: some View {
        Rectangle()
            .fill(strong ? Theme.color(.foreground, dark: dark) : Theme.color(.hairline, dark: dark))
            .frame(height: weight)
    }
}
