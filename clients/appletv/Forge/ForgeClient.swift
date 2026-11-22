import Foundation

enum ForgeConfig {
    static let urlDefaultsKey = "forgeHubURL"
    static let tokenKey = "forgeHubToken"
}

enum ForgeError: LocalizedError {
    case unauthorized
    case server(status: Int, detail: String?)

    var errorDescription: String? {
        switch self {
        case .unauthorized:
            return "Invalid Hub token. Please re-enter your Hub URL and token."
        case .server(let status, let detail):
            if let detail, !detail.isEmpty { return detail }
            return "Forge Hub returned HTTP \(status)."
        }
    }
}

struct ForgeClient: Sendable {
    var baseURL: URL
    var token: String

    private static let session: URLSession = {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 6
        config.waitsForConnectivity = false
        return URLSession(configuration: config)
    }()

    private static let downloadSession: URLSession = {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        config.waitsForConnectivity = false
        return URLSession(configuration: config)
    }()

    func projects() async throws -> [ForgeProject] {
        try await get("projects")
    }

    func versions(of project: String) async throws -> [ForgeVersion] {
        try await get("projects/\(project)/versions")
    }

    func summary(of project: String, version: Int) async throws -> ForgeSummary {
        try await get("projects/\(project)/versions/\(version)/summary")
    }

    func printCode(project: String, version: Int) async throws -> String {
        let info: ForgePrintCode = try await get("projects/\(project)/versions/\(version)/print")
        return info.code
    }

    func printers() async throws -> [PrinterStatus] {
        try await get("printers", timeout: 12)
    }

    func startPrint(project: String, version: Int, printerId: String?) async throws -> PrintResult {
        var request = request(for: "projects/\(project)/versions/\(version)/print", timeout: 60)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body: [String: String] = printerId.map { ["printer_id": $0] } ?? [:]
        request.httpBody = try JSONEncoder().encode(body)
        let (data, response) = try await Self.session.data(for: request)
        try Self.check(response, data: data)
        return try JSONDecoder().decode(PrintResult.self, from: data)
    }

    func download(project: String, version: Int, file: String, to destination: URL) async throws {
        let request = request(for: "projects/\(project)/versions/\(version)/files/\(file)", timeout: 30)
        let (temp, response) = try await Self.downloadSession.download(for: request)
        try Self.check(response, data: nil)
        try? FileManager.default.removeItem(at: destination)
        try FileManager.default.moveItem(at: temp, to: destination)
    }

    private func request(for path: String, timeout: TimeInterval = 6) -> URLRequest {
        var req = URLRequest(url: baseURL.appending(path: path))
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.timeoutInterval = timeout
        return req
    }

    private func get<T: Decodable>(_ path: String, timeout: TimeInterval = 6) async throws -> T {
        let (data, response) = try await Self.session.data(for: request(for: path, timeout: timeout))
        try Self.check(response, data: data)
        return try JSONDecoder().decode(T.self, from: data)
    }

    private static func check(_ response: URLResponse, data: Data?) throws {
        guard let http = response as? HTTPURLResponse else { throw URLError(.badServerResponse) }
        guard !(200..<300).contains(http.statusCode) else { return }
        if http.statusCode == 401 { throw ForgeError.unauthorized }
        let detail = data.flatMap { try? JSONDecoder().decode(ForgeErrorBody.self, from: $0) }?.detail
        throw ForgeError.server(status: http.statusCode, detail: detail)
    }

    static func describe(_ error: Error) -> String {
        if let forgeError = error as? ForgeError { return forgeError.errorDescription ?? "Unknown error." }
        if let urlError = error as? URLError {
            switch urlError.code {
            case .cannotFindHost, .dnsLookupFailed: return "Forge Hub host not found."
            case .cannotConnectToHost: return "Could not connect to Forge Hub."
            case .timedOut: return "Forge Hub timed out."
            case .notConnectedToInternet, .networkConnectionLost: return "Network unavailable."
            default: return urlError.localizedDescription
            }
        }
        if error is DecodingError { return "Unexpected response from Forge Hub." }
        return error.localizedDescription
    }
}
