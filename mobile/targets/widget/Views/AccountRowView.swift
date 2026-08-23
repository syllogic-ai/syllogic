import SwiftUI

/// Thread-safe cache of currency-keyed `NumberFormatter`s. Constructing a
/// `NumberFormatter` is relatively expensive and this row view can be
/// rendered several times per widget timeline refresh, so formatters are
/// built once per currency code and reused rather than allocated on every
/// body evaluation.
private final class CurrencyFormatterCache {
    static let shared = CurrencyFormatterCache()

    private var formatters: [String: NumberFormatter] = [:]
    private let lock = NSLock()

    func formatter(for currencyCode: String) -> NumberFormatter {
        lock.lock()
        defer { lock.unlock() }
        if let existing = formatters[currencyCode] {
            return existing
        }
        let formatter = NumberFormatter()
        formatter.numberStyle = .currency
        formatter.currencyCode = currencyCode
        formatter.maximumFractionDigits = 2
        formatters[currencyCode] = formatter
        return formatter
    }
}

/// One account row. Pure function of its input — no networking or storage,
/// which is what makes the previews below meaningful.
struct AccountRowView: View {
    let row: AccountRow
    var compact: Bool = false

    private var formattedBalance: String {
        let formatter = CurrencyFormatterCache.shared.formatter(for: row.currency)
        // Fall back keeps the currency code attached — a bare number here
        // would be misleading next to a correctly formatted row in a
        // different currency (this widget explicitly supports mixed
        // currencies across rows).
        return formatter.string(from: NSNumber(value: row.balance))
            ?? "\(String(format: "%.2f", row.balance)) \(row.currency)"
    }

    var body: some View {
        HStack(spacing: 10) {
            logo
            Text(row.name)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
            Spacer(minLength: 4)
            Text(formattedBalance)
                .font(compact ? .title2 : .headline)
                .fontWeight(.semibold)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
        }
    }

    @ViewBuilder
    private var logo: some View {
        let size: CGFloat = compact ? 34 : 26
        // Deliberately synchronous disk read at render time, not hoisted
        // into the entry: `TimelineEntry` values are archived by WidgetKit,
        // and stashing decoded image bytes there would inflate every
        // archived timeline entry. Reading small cached logo files at
        // render time is the standard tradeoff for widgets. Bounded by at
        // most 3 rows, small cached logo files on disk, and a 30-minute
        // refresh cadence, so the cost per render stays negligible.
        if let url = row.logoFileURL, let image = UIImage(contentsOfFile: url.path) {
            Image(uiImage: image)
                .resizable()
                .scaledToFill()
                .frame(width: size, height: size)
                .clipShape(Circle())
        } else {
            Circle()
                .fill(Monogram.color(for: row.id))
                .frame(width: size, height: size)
                .overlay(
                    Text(Monogram.initials(for: row.name))
                        .font(.system(size: size * 0.4, weight: .bold))
                        .foregroundStyle(.white)
                )
        }
    }
}
