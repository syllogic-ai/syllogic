import AppIntents

/// One selectable account in iOS's widget configuration UI.
///
/// The id is the account's UUID from the backend, which is stable across
/// sessions. Unstable ids (array indices, for example) cause silent
/// "entity not found" failures in saved widget configurations.
struct AccountEntity: AppEntity, Identifiable, Hashable {
    let id: String
    let name: String
    let currency: String
    let logoUrl: String?

    static var typeDisplayRepresentation: TypeDisplayRepresentation {
        TypeDisplayRepresentation(name: "Account")
    }

    var displayRepresentation: DisplayRepresentation {
        DisplayRepresentation(title: "\(name)", subtitle: "\(currency)")
    }

    static var defaultQuery = AccountEntityQuery()

    init(id: String, name: String, currency: String, logoUrl: String?) {
        self.id = id
        self.name = name
        self.currency = currency
        self.logoUrl = logoUrl
    }

    init(balance: AccountBalance) {
        self.init(id: balance.accountId,
                  name: balance.name,
                  currency: balance.currency,
                  logoUrl: balance.logoUrl)
    }
}

/// Feeds iOS's picker. Falls back to the cache so the picker still populates
/// when the network or session is unavailable.
struct AccountEntityQuery: EntityQuery {
    func entities(for identifiers: [String]) async throws -> [AccountEntity] {
        let all = await allAccounts()
        return all.filter { identifiers.contains($0.id) }
    }

    func suggestedEntities() async throws -> [AccountEntity] {
        await allAccounts()
    }

    private func allAccounts() async -> [AccountEntity] {
        if let fresh = try? await SyllogicAPI.shared.fetchBalances(), !fresh.isEmpty {
            BalanceCache.shared.save(fresh)
            return fresh.map(AccountEntity.init(balance:))
        }
        return BalanceCache.shared.load().map(AccountEntity.init(balance:))
    }
}
