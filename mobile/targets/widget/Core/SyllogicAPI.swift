import Foundation

/// The only unit in the extension that performs HTTP.
struct SyllogicAPI {
    enum APIError: Error, Equatable {
        case unauthorized
        case transport
        case decoding
        /// The Keychain could not be queried right now (e.g. locked before
        /// first unlock) — distinct from `.unauthorized`, which means the
        /// session is genuinely gone. Callers must not treat this as a sign-
        /// out; see `SessionStore.AccessError` and `BalanceProvider`.
        case keychainUnavailable
    }

    let baseURL: URL
    let session: URLSession
    let cookieProvider: () throws -> String?

    init(baseURL: URL, session: URLSession, cookieProvider: @escaping () throws -> String?) {
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

    /// Resolve a stored logo reference into a fetchable URL.
    ///
    /// `company_logos.logo_url` stores RELATIVE paths ("/uploads/logos/x.png");
    /// the web app works because the browser resolves them against the page
    /// origin. The widget has no page origin, so an unresolved relative path
    /// fails silently and every account falls back to a monogram. Pure and
    /// static so the contract is unit-testable.
    static func resolveAssetURL(_ raw: String?, against base: URL) -> URL? {
        guard let raw = raw?.trimmingCharacters(in: .whitespacesAndNewlines),
              !raw.isEmpty else { return nil }
        if raw.hasPrefix("http://") || raw.hasPrefix("https://") {
            return URL(string: raw)
        }
        if raw.hasPrefix("/") {
            return URL(string: raw, relativeTo: base)?.absoluteURL
        }
        return nil
    }

    func fetchBalances() async throws -> [AccountBalance] {
        let cookie: String?
        do {
            cookie = try cookieProvider()
        } catch {
            // The Keychain itself couldn't be read (e.g. still locked) — not
            // the same as a genuinely absent session.
            throw APIError.keychainUnavailable
        }
        guard let cookie else { throw APIError.unauthorized }

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
