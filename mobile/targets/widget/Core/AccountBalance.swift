import Foundation

/// One row of GET /api/analytics/account-balances.
///
/// `balance` is a JSON number because that route returns a plain dict and
/// FastAPI's jsonable_encoder converts Decimal to float. Routes that declare
/// `response_model=` serialise Decimal as a String instead — do not copy this
/// type for those endpoints.
struct AccountBalance: Codable, Identifiable, Hashable {
    let accountId: String
    let name: String
    let balance: Double
    let currency: String
    let accountType: String
    let logoUrl: String?
    let institution: String?

    var id: String { accountId }

    enum CodingKeys: String, CodingKey {
        case accountId = "account_id"
        case name
        case balance
        case currency
        case accountType = "account_type"
        case logoUrl = "logo_url"
        case institution
    }
}
