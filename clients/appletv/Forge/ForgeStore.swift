import Foundation
import Observation

@MainActor
@Observable
final class ForgeStore {
    private(set) var projects: [ForgeProject] = []
    private(set) var versions: [ForgeVersion] = []
    private(set) var summary: ForgeSummary?
    private(set) var printCode: String?
    private(set) var printers: [PrinterStatus] = []
    private(set) var selectedPrinterId: String?
    private(set) var modelFile: URL?
    private(set) var isLoadingModel = false

    private(set) var selectedProject: String?
    private(set) var selectedVersion: Int?
    private(set) var followsLatest = true

    private(set) var lastUpdated: Date?
    private(set) var printerUpdated: Date?
    private(set) var error: String?
    private(set) var printerError: String?
    private(set) var hasLoaded = false
    private(set) var needsSetup: Bool
    private(set) var isSubmittingPrint = false

    private(set) var hubURLString: String
    private var baseURL: URL?
    private var token: String?

    private static let busyInterval: Duration = .seconds(5)
    private static let idleInterval: Duration = .seconds(20)
    private static let projectsEvery: TimeInterval = 15
    private static let staleAfter: TimeInterval = 60

    init() {
        var storedURL = UserDefaults.standard.string(forKey: ForgeConfig.urlDefaultsKey) ?? ""
        var storedToken = Keychain.string(for: ForgeConfig.tokenKey)
        #if DEBUG
        let env = ProcessInfo.processInfo.environment
        if storedURL.isEmpty, let envURL = env["FORGE_HUB_URL"] { storedURL = envURL }
        if (storedToken?.isEmpty ?? true), let envTok = env["FORGE_HUB_TOKEN"] { storedToken = envTok }
        #endif
        let parsedURL = URL(string: storedURL)
        hubURLString = storedURL
        baseURL = parsedURL
        token = storedToken
        needsSetup = parsedURL == nil || (storedToken?.isEmpty ?? true)
    }

    private var client: ForgeClient? {
        guard let baseURL, let token, !token.isEmpty else { return nil }
        return ForgeClient(baseURL: baseURL, token: token)
    }

    func saveConnection(url: String, token value: String) async {
        let cleanURL = url.trimmingCharacters(in: .whitespacesAndNewlines).trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let cleanToken = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let parsed = URL(string: cleanURL), parsed.scheme?.hasPrefix("http") == true, !cleanToken.isEmpty else {
            error = "Enter a valid http:// Hub URL and token."
            return
        }
        hubURLString = cleanURL
        baseURL = parsed
        token = cleanToken
        UserDefaults.standard.set(cleanURL, forKey: ForgeConfig.urlDefaultsKey)
        Keychain.set(cleanToken, for: ForgeConfig.tokenKey)
        needsSetup = false
        error = nil
        await refreshProjects()
        await refreshPrinters()
    }

    func resetConnection() {
        token = nil
        Keychain.set(nil, for: ForgeConfig.tokenKey)
        needsSetup = true
    }

    func selectPrinter(_ id: String) {
        selectedPrinterId = id
    }

    func run() async {
        var lastProjects = Date.distantPast
        while !Task.isCancelled {
            if !needsSetup {
                if Date().timeIntervalSince(lastProjects) >= Self.projectsEvery {
                    await refreshProjects()
                    lastProjects = Date()
                }
                let wasBusy = printer?.state?.isBusy == true
                await refreshPrinters()
                if wasBusy != (printer?.state?.isBusy == true) { await refreshPrintCode() }
            }
            try? await Task.sleep(for: printer?.state?.isBusy == true ? Self.busyInterval : Self.idleInterval)
        }
    }

    func refreshPrinters() async {
        guard let client else { return }
        do {
            let list = try await client.printers()
            printers = list
            if selectedPrinterId == nil || !list.contains(where: { $0.id == selectedPrinterId }) {
                selectedPrinterId = list.first?.id
            }
            printerError = printer?.error
            printerUpdated = Date()
        } catch {
            handle(error, isPrinter: true)
        }
    }

    func refreshProjects() async {
        guard let client else { return }
        do {
            projects = try await client.projects()
            error = nil
            lastUpdated = Date()
            hasLoaded = true
            if selectedProject == nil || !projects.contains(where: { $0.name == selectedProject }) {
                selectedProject = projects.first?.name
                followsLatest = true
            }
            await refreshVersions()
            await refreshPrintCode()
        } catch {
            handle(error, isPrinter: false)
        }
    }

    private func refreshVersions() async {
        guard let client, let project = selectedProject else { versions = []; return }
        do {
            let list = try await client.versions(of: project).sorted { $0.version > $1.version }
            guard project == selectedProject else { return }
            versions = list
            if followsLatest || selectedVersion == nil || !list.contains(where: { $0.version == selectedVersion }) {
                await select(version: list.first?.version, followLatest: true)
            }
        } catch {
            handle(error, isPrinter: false)
        }
    }

    private func handle(_ error: Error, isPrinter: Bool) {
        if case ForgeError.unauthorized = error { resetConnection() }
        let text = ForgeClient.describe(error)
        if isPrinter { printerError = text } else { self.error = text }
    }

    func select(project: String) async {
        guard project != selectedProject else { return }
        selectedProject = project
        selectedVersion = nil
        versions = []
        summary = nil
        printCode = nil
        modelFile = nil
        followsLatest = true
        await refreshVersions()
    }

    func select(version: Int?, followLatest: Bool? = nil) async {
        followsLatest = followLatest ?? (version == versions.first?.version)
        guard version != selectedVersion || modelFile == nil else { return }
        selectedVersion = version
        summary = nil
        printCode = nil
        guard let client, let project = selectedProject, let version,
              let meta = versions.first(where: { $0.version == version }) else {
            modelFile = nil
            return
        }
        async let summaryTask = try? client.summary(of: project, version: version)
        await loadModel(meta, client: client)
        let fetched = await summaryTask
        if project == selectedProject && version == selectedVersion { summary = fetched }
        await refreshPrintCode()
    }

    func refreshPrintCode() async {
        guard let client, let project = selectedProject, let version = selectedVersion else { return }
        let code = try? await client.printCode(project: project, version: version)
        if project == selectedProject && version == selectedVersion { printCode = code }
    }

    private func loadModel(_ meta: ForgeVersion, client: ForgeClient) async {
        guard meta.hasModel else { modelFile = nil; return }
        let folder = URL.cachesDirectory.appending(path: "forge", directoryHint: .isDirectory)
        let file = folder.appending(path: "\(meta.project)-v\(meta.version).usdz")
        if !FileManager.default.fileExists(atPath: file.path()) {
            isLoadingModel = true
            defer { isLoadingModel = false }
            do {
                try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
                try await client.download(project: meta.project, version: meta.version, file: "model.usdz", to: file)
            } catch {
                handle(error, isPrinter: false)
                return
            }
        }
        if meta.project == selectedProject && meta.version == selectedVersion { modelFile = file }
    }

    func startPrint() async -> (ok: Bool, message: String) {
        guard let client, let project = selectedProject, let version = selectedVersion else {
            return (false, "Select a version first.")
        }
        guard canPrint else { return (false, printBlocker ?? "Cannot print right now.") }
        isSubmittingPrint = true
        defer { isSubmittingPrint = false }
        do {
            let result = try await client.startPrint(project: project, version: version, printerId: selectedPrinterId)
            await refreshPrinters()
            await refreshPrintCode()
            let minutes = result.minutes.map { " (~\($0) min)" } ?? ""
            return (true, "Sent \(project) v\(version) to \(printer?.displayName ?? "printer")\(minutes).")
        } catch {
            await refreshPrinters()
            return (false, ForgeClient.describe(error))
        }
    }

    // MARK: Derived

    var printer: PrinterStatus? {
        printers.first { $0.id == selectedPrinterId } ?? printers.first
    }

    var selectedMeta: ForgeVersion? { versions.first { $0.version == selectedVersion } }
    var printerAge: TimeInterval? { printerUpdated.map { Date().timeIntervalSince($0) } }
    var isPrinterStale: Bool { printerAge.map { $0 > Self.staleAfter } ?? false }

    var isPrinterCompatible: Bool {
        guard let p = printer, let s = summary else { return true }
        let modelOK = s.printerModel == nil || p.model == nil || s.printerModel == p.model
        let nozzleOK = s.nozzle == nil || p.nozzle == nil || s.nozzle == p.nozzle
        return modelOK && nozzleOK
    }

    var printBlocker: String? {
        guard let meta = selectedMeta else { return "No version selected." }
        if !meta.hasPrintFile { return "Preview only (not sliced)." }
        if let summary, summary.printable == false { return summary.reason ?? "File is not printable." }
        if printers.isEmpty { return "No printers configured on Hub." }
        if !isPrinterCompatible { return "Sliced for a different printer model or nozzle." }
        if printerError != nil || printer == nil || isPrinterStale { return "Printer unreachable." }
        guard let state = printer?.state else { return "Printer state unknown." }
        if state.isBusy { return "Printer is busy." }
        if !state.acceptsPrint { return "Printer is not ready." }
        return nil
    }

    var canPrint: Bool { printBlocker == nil && !isSubmittingPrint }

    enum Health { case idle, printing, attention, unreachable, previewOnly, unknown }

    var health: Health {
        if hasLoaded && printers.isEmpty { return .previewOnly }
        if printer == nil { return printerError == nil ? .unknown : .unreachable }
        if printerError != nil || isPrinterStale { return .unreachable }
        switch printer?.state {
        case .running, .preparing: return .printing
        case .paused, .failed: return .attention
        case .idle, .finished: return .idle
        case .unknown, nil: return .unknown
        }
    }
}
