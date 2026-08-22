import Foundation

/// The only unit that reads or writes the balances JSON in the App Group.
struct BalanceCache {
    static let appGroupIdentifier = "group.ai.syllogic.mobile"

    let fileURL: URL

    init(fileURL: URL) {
        self.fileURL = fileURL
    }

    static let shared: BalanceCache = {
        let container = FileManager.default
            .containerURL(forSecurityApplicationGroupIdentifier: appGroupIdentifier)
        let url = (container ?? URL(fileURLWithPath: NSTemporaryDirectory()))
            .appendingPathComponent("balances.json")
        return BalanceCache(fileURL: url)
    }()

    func save(_ balances: [AccountBalance]) {
        guard let data = try? JSONEncoder().encode(balances) else { return }
        try? data.write(to: fileURL, options: .atomic)
    }

    /// Returns [] for a missing or unreadable cache. A corrupt cache must never
    /// crash the extension — the widget renders a placeholder instead.
    func load() -> [AccountBalance] {
        guard let data = try? Data(contentsOf: fileURL),
              let balances = try? JSONDecoder().decode([AccountBalance].self, from: data)
        else { return [] }
        return balances
    }
}
