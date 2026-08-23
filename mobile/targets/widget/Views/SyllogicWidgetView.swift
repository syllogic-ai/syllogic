import SwiftUI
import WidgetKit

struct SyllogicWidgetView: View {
    var entry: WidgetEntry
    @Environment(\.widgetFamily) private var family
    @Environment(\.colorScheme) private var scheme

    private var dark: Bool { scheme == .dark }

    var body: some View {
        content
            .containerBackground(Theme.color(.background, dark: dark), for: .widget)
            .widgetURL(deepLink)
    }

    private var deepLink: URL? {
        switch entry.state {
        case .signedOut: return URL(string: "syllogic://login")
        case .noSelection, .ready: return URL(string: "syllogic://")
        }
    }

    @ViewBuilder
    private var content: some View {
        switch entry.state {
        case .signedOut:   stateView(chip: "401", message: "Tap to sign in")
        case .noSelection: stateView(chip: "—", message: "Open Syllogic to pick accounts")
        case .ready:
            if entry.rows.isEmpty {
                // Unreachable today — BalanceProvider forces .noSelection when rows are empty — but kept so an empty .ready never renders a blank card (or traps on rows[0]) if that invariant is ever loosened.
                stateView(chip: "—", message: "Open Syllogic to pick accounts")
            } else {
                switch family {
                case .systemSmall:  small
                case .systemLarge:  large
                default:            medium
                }
            }
        }
    }

    private var small: some View {
        VStack(alignment: .leading, spacing: 2) {
            LogoSquare(row: entry.rows[0], size: 28, dark: dark)
            Spacer()
            MicroLabel(text: entry.rows[0].name, dark: dark)
            BalanceText(row: entry.rows[0], size: 17, dark: dark)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    }

    private var medium: some View {
        VStack(alignment: .leading, spacing: 10) {
            HeroBlock(row: entry.rows[0], balanceSize: 20, logoSize: 24, dark: dark)
            if entry.rows.count > 1 {
                Hairline(dark: dark)
                HStack(alignment: .top, spacing: 14) {
                    ForEach(entry.rows.dropFirst().prefix(2)) { PairColumn(row: $0, dark: dark) }
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    }

    private var large: some View {
        VStack(alignment: .leading, spacing: 12) {
            HeroBlock(row: entry.rows[0], balanceSize: 26, logoSize: 28, dark: dark)
            if entry.rows.count > 1 {
                Hairline(dark: dark, weight: 2, strong: true)
                ForEach(Array(entry.rows.dropFirst().enumerated()), id: \.element.id) { index, row in
                    if index > 0 { Hairline(dark: dark) }
                    LargeRow(row: row, dark: dark)
                }
            }
            Spacer(minLength: 0)
            MicroLabel(text: "Syllogic", dark: dark).opacity(0.7)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private func stateView(chip: String, message: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            MicroLabel(text: chip, dark: dark)
                .padding(.horizontal, 6).padding(.vertical, 3)
                .overlay(Rectangle().strokeBorder(Theme.color(.hairline, dark: dark), lineWidth: 1))
            Text(message)
                .font(Theme.font(size: 11, weight: .medium))
                .foregroundStyle(Theme.color(.foreground, dark: dark))
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    }
}
