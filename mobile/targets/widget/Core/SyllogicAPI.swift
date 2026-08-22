import Foundation

/// The only unit in the extension that performs HTTP.
struct SyllogicAPI {
    enum APIError: Error, Equatable {
        case unauthorized
        case transport
        case decoding
    }

    let baseURL: URL
    let session: URLSession
    let cookieProvider: () -> String?

    init(baseURL: URL, session: URLSession, cookieProvider: @escaping () -> String?) {
        self.baseURL = baseURL
        self.session = session
        self.cookieProvider = cookieProvider
    }

    static let shared: SyllogicAPI = {
        let configured = Bundle.main.object(forInfoDictionaryKey: "SyllogicAPIBaseURL") as? String
        let url = URL(string: configured ?? "") ?? URL(string: "http://localhost:8000")!
        return SyllogicAPI(baseURL: url,
                           session: .shared,
                           cookieProvider: SessionStore.cookie)
    }()

    func fetchBalances() async throws -> [AccountBalance] {
        guard let cookie = cookieProvider() else { throw APIError.unauthorized }

        var request = URLRequest(url: baseURL.appendingPathComponent("/api/analytics/account-balances"))
        request.setValue(cookie, forHTTPHeaderField: "Cookie")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.timeoutInterval = 15

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.transport
        }

        guard let http = response as? HTTPURLResponse else { throw APIError.transport }
        if http.statusCode == 401 || http.statusCode == 403 { throw APIError.unauthorized }
        guard (200..<300).contains(http.statusCode) else { throw APIError.transport }

        do {
            return try JSONDecoder().decode([AccountBalance].self, from: data)
        } catch {
            throw APIError.decoding
        }
    }
}
