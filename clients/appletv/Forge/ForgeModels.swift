import Foundation

struct ForgeProject: Decodable, Sendable, Identifiable, Hashable {
    let name: String
    let latest: Int?
    let versions: Int?
    var id: String { name }
}

struct ForgeFile: Decodable, Sendable, Hashable {
    let name: String
    let size: Int?
}

struct ForgeVersion: Decodable, Sendable, Identifiable, Hashable {
    let project: String
    let version: Int
    let createdAt: String?
    let note: String?
    let files: [ForgeFile]?

    var id: Int { version }

    enum CodingKeys: String, CodingKey {
        case project, version, note, files
        case createdAt = "created_at"
    }

    var createdDate: Date? {
        createdAt.flatMap { ISO8601DateFormatter().date(from: $0) }
    }

    var hasModel: Bool { files?.contains { $0.name == "model.usdz" } ?? false }
    var hasAssembly: Bool { files?.contains { $0.name == "assembly.json" } ?? false }
    var hasPrintFile: Bool { files?.contains { $0.name.hasSuffix(".gcode.3mf") } ?? false }
}

struct AssemblyPlate: Decodable, Sendable, Equatable {
    let translateMm: [Float]
    let rotDeg: [Float]

    enum CodingKeys: String, CodingKey {
        case translateMm = "translate_mm"
        case rotDeg = "rot_deg"
    }
}

struct AssemblyStep: Decodable, Sendable, Equatable, Identifiable {
    let part: String
    let label: String?
    let step: Int
    let slideMm: [Float]
    let rotateDeg: [Float]
    let pivotMm: [Float]
    let plate: AssemblyPlate?

    var id: String { "\(step)-\(part)" }
    var displayName: String { label?.isEmpty == false ? label! : part }
    var isAnimated: Bool {
        slideMm.contains { abs($0) > 1e-4 } || rotateDeg.contains { abs($0) > 1e-4 }
    }

    enum CodingKeys: String, CodingKey {
        case part, label, step, plate
        case slideMm = "slide_mm"
        case rotateDeg = "rotate_deg"
        case pivotMm = "pivot_mm"
    }
}

struct AssemblySpec: Decodable, Sendable, Equatable {
    let version: Int
    let units: String?
    let steps: [AssemblyStep]

    var hasAnimation: Bool { steps.contains { $0.isAnimated } }
    var hasPlate: Bool { steps.contains { $0.plate != nil } }
}

struct RevisionItem: Decodable, Sendable, Identifiable, Equatable {
    let id: String
    let project: String
    let version: Int?
    let prompt: String
    let status: String
    let createdAt: String?
    let resultVersion: Int?
    let note: String?
    let sessionConnected: Bool?

    enum CodingKeys: String, CodingKey {
        case id, project, version, prompt, status, note
        case createdAt = "created_at"
        case resultVersion = "result_version"
        case sessionConnected = "session_connected"
    }
}

struct RevisionListResponse: Decodable, Sendable, Equatable {
    let project: String
    let sessionConnected: Bool
    let revisions: [RevisionItem]

    enum CodingKeys: String, CodingKey {
        case project, revisions
        case sessionConnected = "session_connected"
    }
}

struct ForgeSummary: Decodable, Sendable {
    let printable: Bool?
    let reason: String?
    let minutes: Int?
    let grams: Double?
    let bedType: String?
    let printerModel: String?
    let nozzle: String?

    enum CodingKeys: String, CodingKey {
        case printable, reason, minutes, grams, nozzle
        case bedType = "bed_type"
        case printerModel = "printer_model"
    }
}

struct ForgePrintCode: Decodable, Sendable {
    let code: String
}

enum PrinterState: String, Decodable, Sendable {
    case idle, finished, failed, running, preparing, paused, unknown

    init(from decoder: Decoder) throws {
        switch try decoder.singleValueContainer().decode(String.self) {
        case "IDLE": self = .idle
        case "FINISH": self = .finished
        case "FAILED": self = .failed
        case "RUNNING": self = .running
        case "PREPARE", "SLICING": self = .preparing
        case "PAUSE": self = .paused
        default: self = .unknown
        }
    }

    var acceptsPrint: Bool { self == .idle || self == .finished || self == .failed }
    var isBusy: Bool { self == .running || self == .preparing || self == .paused }
}

struct PrinterStatus: Decodable, Sendable, Identifiable {
    let id: String
    let name: String?
    let model: String?
    let nozzle: String?
    let state: PrinterState?
    let percent: Int?
    let layer: Int?
    let totalLayers: Int?
    let remainingMinutes: Int?
    let nozzleTemp: Double?
    let nozzleTarget: Double?
    let bedTemp: Double?
    let bedTarget: Double?
    let jobName: String?
    let wifiSignal: String?
    let error: String?

    var displayName: String { name ?? id }

    enum CodingKeys: String, CodingKey {
        case id, name, model, nozzle, error
        case state = "gcode_state"
        case percent = "mc_percent"
        case layer = "layer_num"
        case totalLayers = "total_layer_num"
        case remainingMinutes = "mc_remaining_time"
        case nozzleTemp = "nozzle_temper"
        case nozzleTarget = "nozzle_target_temper"
        case bedTemp = "bed_temper"
        case bedTarget = "bed_target_temper"
        case jobName = "subtask_name"
        case wifiSignal = "wifi_signal"
    }
}

struct PrintResult: Decodable, Sendable {
    let started: Bool?
    let minutes: Int?
    let printerId: String?

    enum CodingKeys: String, CodingKey {
        case started, minutes
        case printerId = "printer_id"
    }
}

struct ForgeErrorBody: Decodable, Sendable {
    let detail: String?
}
