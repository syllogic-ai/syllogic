import AppIntents

/// The widget's configuration. AppIntents cannot cap an array parameter's
/// length declaratively, so iOS will allow more than three selections; the
/// provider renders the first three via .prefix(3).
struct SelectAccountsIntent: WidgetConfigurationIntent {
    static var title: LocalizedStringResource = "Select Accounts"
    static var description = IntentDescription("Choose up to 3 accounts to show.")

    @Parameter(title: "Accounts")
    var accounts: [AccountEntity]?

    init() {}

    init(accounts: [AccountEntity]?) {
        self.accounts = accounts
    }
}
