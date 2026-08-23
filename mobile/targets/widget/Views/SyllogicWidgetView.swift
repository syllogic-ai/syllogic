import SwiftUI
import WidgetKit

struct SyllogicWidgetView: View {
    var entry: WidgetEntry
    @Environment(\.widgetFamily) private var family

    var body: some View {
        content
            .containerBackground(.fill.tertiary, for: .widget)
            .widgetURL(deepLink)
    }

    /// The spec requires the signed-out row to deep-link into sign-in. The
    /// `syllogic://` scheme is already registered in app.json.
    private var deepLink: URL? {
        switch entry.state {
        case .signedOut:
            return URL(string: "syllogic://login")
        case .noSelection, .ready:
            return URL(string: "syllogic://")
        }
    }

    @ViewBuilder
    private var content: some View {
        switch entry.state {
        case .signedOut:
            message("Tap to sign in")
        case .noSelection:
            message("Open Syllogic to pick accounts")
        case .ready:
            if family == .systemSmall {
                if let row = entry.rows.first {
                    AccountRowView(row: row, compact: true)
                } else {
                    message("Open Syllogic to pick accounts")
                }
            } else {
                VStack(spacing: 14) {
                    ForEach(entry.rows) { row in
                        AccountRowView(row: row)
                    }
                }
            }
        }
    }

    private func message(_ text: String) -> some View {
        VStack(spacing: 6) {
            Image(systemName: "lock.circle")
                .font(.title2)
                .foregroundStyle(.secondary)
            Text(text)
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
    }
}
