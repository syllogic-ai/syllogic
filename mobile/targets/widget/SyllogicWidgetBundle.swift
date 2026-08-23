import WidgetKit
import SwiftUI

struct SyllogicWidget: Widget {
    let kind = "SyllogicBalances"

    var body: some WidgetConfiguration {
        AppIntentConfiguration(kind: kind,
                               intent: SelectAccountsIntent.self,
                               provider: BalanceProvider()) { entry in
            SyllogicWidgetView(entry: entry)
        }
        .configurationDisplayName("Balances")
        .description("See up to 3 account balances at a glance.")
        .supportedFamilies([.systemSmall, .systemMedium, .systemLarge])
    }
}

@main
struct SyllogicWidgetBundle: WidgetBundle {
    var body: some Widget {
        SyllogicWidget()
    }
}

#Preview("Medium", as: .systemMedium) { SyllogicWidget() } timeline: { WidgetEntry.placeholder }
#Preview("Small", as: .systemSmall) { SyllogicWidget() } timeline: { WidgetEntry.placeholder }
#Preview("Large", as: .systemLarge) { SyllogicWidget() } timeline: { WidgetEntry.placeholder }
#Preview("Medium — long name", as: .systemMedium) { SyllogicWidget() } timeline: {
    WidgetEntry(date: .now, rows: [
        AccountRow(id: "l1", name: "Interactive Brokers Ireland Limited", balance: 43154.12,
                   currency: "EUR", logoFileURL: nil, institution: "Interactive Brokers", accountType: "investment"),
        AccountRow(id: "l2", name: "Travel Card", balance: 1096.06,
                   currency: "USD", logoFileURL: nil, institution: nil, accountType: "credit"),
    ], state: .ready)
}
#Preview("Medium — signed out", as: .systemMedium) { SyllogicWidget() } timeline: {
    WidgetEntry(date: .now, rows: [], state: .signedOut)
}
#Preview("Small — no selection", as: .systemSmall) { SyllogicWidget() } timeline: {
    WidgetEntry(date: .now, rows: [], state: .noSelection)
}
#Preview("Large — 1 account", as: .systemLarge) { SyllogicWidget() } timeline: {
    WidgetEntry(date: .now, rows: [
        AccountRow(id: "s1", name: "Main Checking", balance: 7425.00,
                   currency: "EUR", logoFileURL: nil, institution: "ING", accountType: "checking"),
    ], state: .ready)
}
