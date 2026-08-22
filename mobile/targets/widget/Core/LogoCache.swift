import Foundation

/// Downloads logo images during timeline construction and stores them in the
/// App Group. Widget extensions cannot reliably fetch images at render time.
struct LogoCache {
    let directory: URL
    let session: URLSession

    init(directory: URL, session: URLSession) {
        self.directory = directory
        self.session = session
    }

    static let shared: LogoCache = {
        let container = FileManager.default
            .containerURL(forSecurityApplicationGroupIdentifier: BalanceCache.appGroupIdentifier)
        let dir = (container ?? URL(fileURLWithPath: NSTemporaryDirectory()))
            .appendingPathComponent("logos", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return LogoCache(directory: dir, session: .shared)
    }()

    /// Account IDs are UUID strings, so they are already filesystem-safe.
    private func fileURL(forAccount accountId: String) -> URL {
        directory.appendingPathComponent("\(accountId).img")
    }

    func localURL(forAccount accountId: String) -> URL? {
        let url = fileURL(forAccount: accountId)
        return FileManager.default.fileExists(atPath: url.path) ? url : nil
    }

    /// Best-effort. A missing logo is the normal case, not an error — callers
    /// fall back to Monogram.
    func cache(logoUrl: String?, forAccount accountId: String) async {
        guard let logoUrl, let remote = URL(string: logoUrl) else { return }

        var request = URLRequest(url: remote)
        request.timeoutInterval = 10

        guard let (data, response) = try? await session.data(for: request),
              let http = response as? HTTPURLResponse,
              (200..<300).contains(http.statusCode),
              !data.isEmpty
        else { return }

        try? data.write(to: fileURL(forAccount: accountId), options: .atomic)
    }
}
