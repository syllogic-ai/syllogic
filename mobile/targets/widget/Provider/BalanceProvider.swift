import WidgetKit
import AppIntents

struct BalanceProvider: AppIntentTimelineProvider {
    /// Balances do not move minute to minute, and 30 minutes stays inside
    /// iOS's refresh budget while remaining useful.
    private static let refreshInterval: TimeInterval = 30 * 60

    func placeholder(in context: Context) -> WidgetEntry {
        .placeholder
    }

    func snapshot(for configuration: SelectAccountsIntent, in context: Context) async -> WidgetEntry {
        if context.isPreview { return .placeholder }
        return await entry(for: configuration)
    }

    func timeline(for configuration: SelectAccountsIntent, in context: Context) async -> Timeline<WidgetEntry> {
        let entry = await entry(for: configuration)
        let next = Date().addingTimeInterval(Self.refreshInterval)
        return Timeline(entries: [entry], policy: .after(next))
    }

    private func entry(for configuration: SelectAccountsIntent) async -> WidgetEntry {
        let selected = (configuration.accounts ?? []).map(\.id)
        guard !selected.isEmpty else {
            return WidgetEntry(date: .now, rows: [], state: .noSelection)
        }

        let fetched: [AccountBalance]
        do {
            fetched = try await SyllogicAPI.shared.fetchBalances()
            BalanceCache.shared.save(fetched)
        } catch SyllogicAPI.APIError.unauthorized {
            // A 401 is a hard signal: never render stale balances for a session
            // that is definitively gone.
            return WidgetEntry(date: .now, rows: [], state: .signedOut)
        } catch {
            // Network failures fall back to cache silently, by design.
            fetched = BalanceCache.shared.load()
        }

        for balance in fetched where selected.contains(balance.accountId) {
            if LogoCache.shared.localURL(forAccount: balance.accountId) == nil {
                await LogoCache.shared.cache(logoUrl: balance.logoUrl,
                                             forAccount: balance.accountId)
            }
        }

        let rows = RowBuilder.rows(from: fetched, selected: selected) { id in
            LogoCache.shared.localURL(forAccount: id)
        }

        return WidgetEntry(date: .now, rows: rows,
                           state: rows.isEmpty ? .noSelection : .ready)
    }
}
