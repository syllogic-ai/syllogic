import Foundation

enum WidgetState {
    case ready
    case signedOut
    case noSelection
}

struct AccountRow: Identifiable, Hashable {
    let id: String
    let name: String
    let balance: Double
    let currency: String
    let logoFileURL: URL?
}
