import Foundation
import WidgetKit

struct WidgetEntry: TimelineEntry {
    let date: Date
    let rows: [AccountRow]
    let state: WidgetState

    static let placeholder = WidgetEntry(
        date: .now,
        rows: [
            AccountRow(id: "p1", name: "Main Checking", balance: 7425.00,
                       currency: "EUR", logoFileURL: nil),
            AccountRow(id: "p2", name: "Savings Vault", balance: 18620.00,
                       currency: "EUR", logoFileURL: nil),
            AccountRow(id: "p3", name: "Travel Card", balance: 1096.06,
                       currency: "USD", logoFileURL: nil),
        ],
        state: .ready
    )
}
