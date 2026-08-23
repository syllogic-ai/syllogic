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
        } catch SyllogicAPI.APIError.keychainUnavailable {
            // The Keychain was locked (e.g. before first unlock after a
            // reboot, or WidgetKit refreshing while the device is locked) —
            // not the same as a genuinely gone session. Same silent
            // cache-fallback path as a network error, deliberately NOT
            // `.signedOut`.
            fetched = BalanceCache.shared.load()
        } catch {
            // Network failures fall back to cache silently, by design.
            fetched = BalanceCache.shared.load()
        }

        // Only prefetch logos for accounts that will actually render: RowBuilder
        // caps rendering at 3, but iOS lets users select more (AppIntents cannot
        // cap an array parameter), so prefetching every `selected` account would
        // waste the widget's tight network/time budget on logos that never show.
        //
        // Fetched concurrently (rather than awaited one at a time) to stay
        // inside WidgetKit's ~30s provider budget: SyllogicAPI's request can
        // take up to 15s, and awaiting up to 3 logo fetches serially at 10s
        // each could add another 30s on top — 45s worst case, well past the
        // budget, which would kill the extension before even the silent
        // cache fallback above gets a chance to run. Logos are best-effort;
        // a missed one falls through to the monogram, the intended normal
        // case, so nothing here needs to wait for stragglers beyond the
        // group's own completion.
        let renderable = Set(selected.prefix(3))
        await withTaskGroup(of: Void.self) { group in
            for balance in fetched where renderable.contains(balance.accountId) {
                guard LogoCache.shared.localURL(forAccount: balance.accountId) == nil else { continue }
                group.addTask {
                    // logo_url is often a relative path; resolve against the
                    // API origin (the same origin the web app resolves against).
                    let resolved = SyllogicAPI.resolveAssetURL(
                        balance.logoUrl, against: SyllogicAPI.shared.baseURL)
                    await LogoCache.shared.cache(logoUrl: resolved?.absoluteString,
                                                 forAccount: balance.accountId)
                }
            }
        }

        let rows = RowBuilder.rows(from: fetched, selected: selected) { id in
            LogoCache.shared.localURL(forAccount: id)
        }

        return WidgetEntry(date: .now, rows: rows,
                           state: rows.isEmpty ? .noSelection : .ready)
    }
}
