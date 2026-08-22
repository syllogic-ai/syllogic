import Foundation

/// Selection, ordering and the 3-account cap. Pure and platform-neutral so
/// `swift test` can cover it without a simulator; BalanceProvider does the
/// WidgetKit-facing work and delegates here.
enum RowBuilder {
    /// Selection order wins over fetch order, and at most 3 rows are returned.
    /// iOS allows more than 3 accounts to be chosen — AppIntents cannot cap an
    /// array parameter — so the cap is enforced here.
    static func rows(from fetched: [AccountBalance],
                     selected: [String],
                     logoURL: (String) -> URL?) -> [AccountRow] {
        let byId = Dictionary(uniqueKeysWithValues: fetched.map { ($0.accountId, $0) })
        return selected.prefix(3).compactMap { id in
            guard let balance = byId[id] else { return nil }
            return AccountRow(id: balance.accountId,
                              name: balance.name,
                              balance: balance.balance,
                              currency: balance.currency,
                              logoFileURL: logoURL(id))
        }
    }
}
