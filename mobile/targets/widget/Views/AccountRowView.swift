import SwiftUI

/// One account row. Pure function of its input — no networking or storage,
/// which is what makes the previews below meaningful.
struct AccountRowView: View {
    let row: AccountRow
    var compact: Bool = false

    private var formattedBalance: String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .currency
        formatter.currencyCode = row.currency
        formatter.maximumFractionDigits = 2
        return formatter.string(from: NSNumber(value: row.balance))
            ?? String(format: "%.2f", row.balance)
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
