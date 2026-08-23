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
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}

@main
struct SyllogicWidgetBundle: WidgetBundle {
    var body: some Widget {
        SyllogicWidget()
    }
}

#Preview("Medium — 3 accounts", as: .systemMedium) {
    SyllogicWidget()
} timeline: {
    WidgetEntry.placeholder
}

#Preview("Small — 1 account", as: .systemSmall) {
    SyllogicWidget()
} timeline: {
    WidgetEntry.placeholder
}

#Preview("Medium — long name", as: .systemMedium) {
    SyllogicWidget()
} timeline: {
    WidgetEntry(date: .now, rows: [
        AccountRow(id: "l1", name: "Interactive Brokers Ireland Limited",
                   balance: 43154.12, currency: "EUR", logoFileURL: nil),
        AccountRow(id: "l2", name: "Travel Card", balance: 1096.06,
                   currency: "USD", logoFileURL: nil),
    ], state: .ready)
}

#Preview("Medium — signed out", as: .systemMedium) {
    SyllogicWidget()
} timeline: {
    WidgetEntry(date: .now, rows: [], state: .signedOut)
}
