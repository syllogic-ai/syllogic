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

    /// Account IDs are validated as UUID strings before any path is built, so
    /// a malformed id (e.g. containing "/" or "..") can never escape the
    /// `logos/` directory.
    private func fileURL(forAccount accountId: String) -> URL? {
        guard UUID(uuidString: accountId) != nil else { return nil }
        return directory.appendingPathComponent("\(accountId).img")
    }

    func localURL(forAccount accountId: String) -> URL? {
        guard let url = fileURL(forAccount: accountId) else { return nil }
        return FileManager.default.fileExists(atPath: url.path) ? url : nil
    }

    /// Best-effort. A missing logo is the normal case, not an error — callers
    /// fall back to Monogram.
    func cache(logoUrl: String?, forAccount accountId: String) async {
        guard let logoUrl, let remote = URL(string: logoUrl),
              let destination = fileURL(forAccount: accountId)
        else { return }

        var request = URLRequest(url: remote)
        // Logos are prefetched concurrently for up to 3 accounts (see
        // BalanceProvider's TaskGroup), so this timeout no longer sums
        // serially across accounts — but it still bounds a single entry's
        // worst case (15s API request + this timeout for the slowest
        // concurrent logo fetch) well inside WidgetKit's ~30s provider
        // budget. Best-effort: a missed logo falls through to the monogram,
        // the normal case.
        request.timeoutInterval = 5

        guard let (data, response) = try? await session.data(for: request),
              let http = response as? HTTPURLResponse,
              (200..<300).contains(http.statusCode),
              !data.isEmpty
        else { return }

        try? data.write(to: destination, options: .atomic)
    }
}
