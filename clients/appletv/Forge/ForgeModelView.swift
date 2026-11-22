import GameController
import RealityKit
import SwiftUI

enum LightPreset: String, CaseIterable, Identifiable {
    case studio, top, side, camera, flat
    var id: String { rawValue }

    var label: String {
        switch self {
        case .studio: "Studio"
        case .top: "Top"
        case .side: "Side"
        case .camera: "Camera"
        case .flat: "Flat"
        }
    }

    enum Direction { case vector(SIMD3<Float>), camera }
    struct Light { let intensity: Float; let direction: Direction }

    var hemi: Float {
        switch self {
        case .studio: 0.6
        case .top: 0.35
        case .side: 0.12
        case .camera: 0.35
        case .flat: 1.6
        }
    }

    var key: Light {
        switch self {
        case .studio: Light(intensity: 1.2, direction: .vector([1, 1.6, 1.2]))
        case .top: Light(intensity: 1.4, direction: .vector([0.15, 1, 0.1]))
        case .side: Light(intensity: 1.2, direction: .vector([1, 0.12, 0.25]))
        case .camera: Light(intensity: 1.2, direction: .camera)
        case .flat: Light(intensity: 0, direction: .vector([0, 1, 0]))
        }
    }

    var fill: Light {
        switch self {
        case .studio: Light(intensity: 0.4, direction: .vector([-1.2, 0.6, 0.8]))
        case .top: Light(intensity: 0.2, direction: .vector([-1, 0.4, -0.6]))
        case .side: Light(intensity: 0.08, direction: .vector([-1, 0.2, 0]))
        case .camera: Light(intensity: 0.25, direction: .vector([-1, 1, -0.5]))
        case .flat: Light(intensity: 0, direction: .vector([0, 1, 0]))
        }
    }

    var rim: Light {
        switch self {
        case .studio: Light(intensity: 0.4, direction: .vector([0, 0.8, -1.5]))
        default: Light(intensity: 0, direction: .vector([0, 1, 0]))
        }
    }

    var next: LightPreset {
        let all = Self.allCases
        return all[(all.firstIndex(of: self)! + 1) % all.count]
    }
}

struct OrbitState: Equatable {
    var yaw: Float = .pi / 4
    var pitch: Float = 0.45
    var zoom: Float = 1

    static let pitchRange: ClosedRange<Float> = -1.2...1.45
    static let zoomRange: ClosedRange<Float> = 0.35...12

    mutating func rotate(dx: Float, dy: Float) {
        yaw -= dx
        pitch = (pitch + dy).clamped(to: Self.pitchRange)
    }

    mutating func zoom(by factor: Float) {
        zoom = (zoom * factor).clamped(to: Self.zoomRange)
    }

    var direction: SIMD3<Float> {
        [cos(pitch) * sin(yaw), sin(pitch), cos(pitch) * cos(yaw)]
    }
}

extension Comparable {
    func clamped(to range: ClosedRange<Self>) -> Self { min(max(self, range.lowerBound), range.upperBound) }
}

struct ForgeModelView: View {
    let file: URL?
    let orbit: OrbitState
    let preset: LightPreset
    var showsGrid = true
    var labelInset: CGFloat = 20

    @State private var scene = ForgeScene()
    @State private var loadError: String?
    @State private var size: SIMD3<Float>?

    var body: some View {
        RealityView { content in
            content.camera = .virtual
            content.add(scene.root)
        } update: { _ in
            scene.apply(orbit: orbit, preset: preset, showsGrid: showsGrid)
        }
        .task(id: file) {
            loadError = nil
            size = nil
            guard let file else { scene.setModel(nil); return }
            do {
                let entity = try await Entity(contentsOf: file)
                size = scene.setModel(entity)
                scene.apply(orbit: orbit, preset: preset, showsGrid: showsGrid)
            } catch {
                loadError = "Failed to load model."
            }
        }
        .overlay {
            if let loadError {
                Label(loadError, systemImage: "exclamationmark.triangle").foregroundStyle(.secondary)
            }
        }
        .overlay(alignment: .bottomLeading) {
            if showsGrid, let size {
                SizeLabel(size: size, gridStep: ForgeGrid.minorStep(for: size))
                    .padding(.leading, 20)
                    .padding(.bottom, labelInset)
            }
        }
    }
}

private struct SizeLabel: View {
    let size: SIMD3<Float>
    let gridStep: Float

    var body: some View {
        let mm = { (m: Float) in (Double(m) * 1000).formatted(.number.precision(.fractionLength(0...1))) }
        Text("\(mm(size.x)) × \(mm(size.z)) × \(mm(size.y)) mm · grid \(mm(gridStep)) mm")
            .font(.caption.monospacedDigit())
            .foregroundStyle(.secondary)
            .padding(.horizontal, 14).padding(.vertical, 8)
            .background(.ultraThinMaterial, in: .capsule)
    }
}

enum ForgeGrid {
    static let plate: Float = 0.256

    static func minorStep(for size: SIMD3<Float>) -> Float {
        let span = max(size.x, size.z, size.y)
        return [0.001, 0.002, 0.005, 0.01, 0.02].first { $0 >= span / 10 } ?? 0.05
    }

    static func entity(for bounds: BoundingBox) -> ModelEntity {
        let size = bounds.extents
        let minor = minorStep(for: size)
        let major = minor * 10
        let radius = max(length(size) / 2, 0.001)
        let width = radius * 0.004
        let y = bounds.min.y - radius * 0.002
        let cx = bounds.center.x, cz = bounds.center.z
        let half = plate / 2

        var minorQuads = Quads(), majorQuads = Quads(), plateQuads = Quads()
        var xAxis = Quads(), yAxis = Quads(), zAxis = Quads()

        let near = min(half, max(radius * 3, major))
        let lines = { (step: Float, extent: Float, into: inout Quads, w: Float, lift: Float) in
            let n = Int((extent / step).rounded(.down))
            for i in -n...n {
                let o = Float(i) * step
                into.add(from: [cx - extent, y + lift, cz + o], to: [cx + extent, y + lift, cz + o], width: w)
                into.add(from: [cx + o, y + lift, cz - extent], to: [cx + o, y + lift, cz + extent], width: w)
            }
        }
        lines(minor, near, &minorQuads, width, 0)
        lines(major, half, &majorQuads, width * 1.6, radius * 0.0005)

        let corners: [SIMD3<Float>] = [
            [cx - half, y, cz - half], [cx + half, y, cz - half],
            [cx + half, y, cz + half], [cx - half, y, cz + half],
        ]
        for i in 0..<4 {
            plateQuads.add(
                from: corners[i] + [0, radius * 0.001, 0],
                to: corners[(i + 1) % 4] + [0, radius * 0.001, 0],
                width: width * 3
            )
        }

        let axis = radius * 1.4, lift = radius * 0.0015
        let origin: SIMD3<Float> = [cx, y + lift, cz]
        xAxis.add(from: origin, to: origin + [axis, 0, 0], width: width * 3)
        yAxis.add(from: origin, to: origin + [0, 0, -axis], width: width * 3)
        zAxis.add(from: origin, to: origin + [0, axis, 0], width: width * 3, vertical: true)

        let parts: [(Quads, UIColor)] = [
            (minorQuads, UIColor(white: 0.22, alpha: 1)),
            (majorQuads, UIColor(white: 0.36, alpha: 1)),
            (plateQuads, UIColor(white: 0.6, alpha: 1)),
            (xAxis, UIColor(red: 0.85, green: 0.3, blue: 0.3, alpha: 1)),
            (yAxis, UIColor(red: 0.35, green: 0.75, blue: 0.4, alpha: 1)),
            (zAxis, UIColor(red: 0.35, green: 0.55, blue: 0.95, alpha: 1)),
        ]
        var descriptors: [MeshDescriptor] = []
        var materials: [any RealityKit.Material] = []
        for (quads, color) in parts where !quads.indices.isEmpty {
            var d = MeshDescriptor()
            d.positions = MeshBuffer(quads.positions)
            d.primitives = .triangles(quads.indices)
            d.materials = .allFaces(UInt32(materials.count))
            descriptors.append(d)
            var material = UnlitMaterial(color: color)
            material.faceCulling = .none
            materials.append(material)
        }
        guard let mesh = try? MeshResource.generate(from: descriptors) else { return ModelEntity() }
        return ModelEntity(mesh: mesh, materials: materials)
    }

    struct Quads {
        var positions: [SIMD3<Float>] = []
        var indices: [UInt32] = []

        mutating func add(from a: SIMD3<Float>, to b: SIMD3<Float>, width: Float, vertical: Bool = false) {
            let side: SIMD3<Float>
            if vertical {
                side = [width / 2, 0, 0]
                add(quadFrom: a, to: b, side: [0, 0, width / 2])
            } else {
                let d = normalize(b - a)
                side = [-d.z * width / 2, 0, d.x * width / 2]
            }
            add(quadFrom: a, to: b, side: side)
        }

        private mutating func add(quadFrom a: SIMD3<Float>, to b: SIMD3<Float>, side: SIMD3<Float>) {
            let base = UInt32(positions.count)
            positions += [a - side, a + side, b + side, b - side]
            indices += [base, base + 1, base + 2, base, base + 2, base + 3]
        }
    }
}

@MainActor
final class ForgeScene {
    let root = Entity()
    private let camera = PerspectiveCamera()
    private var model: Entity?
    private var grid: ModelEntity?
    private var center: SIMD3<Float> = .zero
    private var radius: Float = 0.05
    private let lights: [String: DirectionalLight]

    init() {
        var lights: [String: DirectionalLight] = [:]
        for name in ["key", "fill", "rim", "sky", "ground"] {
            let light = DirectionalLight()
            light.light.color = .white
            lights[name] = light
            root.addChild(light)
        }
        self.lights = lights
        camera.camera.fieldOfViewInDegrees = 40
        root.addChild(camera)
    }

    @discardableResult
    func setModel(_ entity: Entity?) -> SIMD3<Float>? {
        model?.removeFromParent()
        grid?.removeFromParent()
        model = entity
        grid = nil
        guard let entity else { return nil }
        root.addChild(entity)
        let bounds = entity.visualBounds(relativeTo: root)
        center = bounds.center
        radius = max(length(bounds.extents) / 2, 0.001)
        camera.camera.near = radius / 100
        camera.camera.far = max(radius * 100, ForgeGrid.plate * 10)
        let grid = ForgeGrid.entity(for: bounds)
        root.addChild(grid)
        self.grid = grid
        return bounds.extents
    }

    func apply(orbit: OrbitState, preset: LightPreset, showsGrid: Bool) {
        let eye = center + orbit.direction * radius * 3 * orbit.zoom
        camera.look(at: center, from: eye, relativeTo: root)
        if grid?.isEnabled != showsGrid { grid?.isEnabled = showsGrid }

        func place(_ name: String, _ light: LightPreset.Light) {
            guard let entity = lights[name] else { return }
            entity.light.intensity = light.intensity * 350
            let dir: SIMD3<Float> = switch light.direction {
            case .vector(let v): normalize(v)
            case .camera: orbit.direction
            }
            entity.look(at: center, from: center + dir * radius * 4, relativeTo: root)
        }
        place("key", preset.key)
        place("fill", preset.fill)
        place("rim", preset.rim)
        place("sky", .init(intensity: preset.hemi * 0.8, direction: .vector([0, 1, 0])))
        place("ground", .init(intensity: preset.hemi * 0.8 * 0.27, direction: .vector([0, -1, 0])))
    }
}

struct TouchTracker {
    static let deadZone: Float = 0.08
    static let maxStep: Float = 0.3
    static let newTouchGap: TimeInterval = 0.2

    private(set) var position: SIMD2<Float>?
    private(set) var isSliding = false
    private var lastTime: TimeInterval = 0
    private var travelled: Float = 0

    mutating func sample(_ point: SIMD2<Float>, at time: TimeInterval) -> SIMD2<Float>? {
        defer { lastTime = time }
        if point == .zero { end(); return nil }
        guard let previous = position,
              time - lastTime < Self.newTouchGap,
              length(point - previous) < Self.maxStep else {
            position = point; travelled = 0; isSliding = false; return nil
        }
        position = point
        let step = point - previous
        guard isSliding else {
            travelled += length(step)
            isSliding = travelled >= Self.deadZone
            return nil
        }
        return step
    }

    mutating func end() { position = nil; travelled = 0; isSliding = false }
}

enum ClickZone {
    case up, down, left, right, center

    init(_ point: SIMD2<Float>) {
        if max(abs(point.x), abs(point.y)) < 0.45 { self = .center }
        else if abs(point.y) >= abs(point.x) { self = point.y > 0 ? .up : .down }
        else { self = point.x > 0 ? .right : .left }
    }
}

@MainActor
final class RemoteTouch {
    var onDrag: ((SIMD2<Float>) -> Void)?
    var onClick: ((ClickZone) -> Void)?

    private var tracker = TouchTracker()
    private var observers: [NSObjectProtocol] = []

    func start() {
        GCController.controllers().forEach(attach)
        observers.append(NotificationCenter.default.addObserver(
            forName: .GCControllerDidConnect, object: nil, queue: .main
        ) { [weak self] _ in
            MainActor.assumeIsolated { GCController.controllers().forEach { self?.attach($0) } }
        })
    }

    func stop() {
        observers.forEach(NotificationCenter.default.removeObserver)
        observers = []
        GCController.controllers().forEach {
            $0.microGamepad?.dpad.valueChangedHandler = nil
            $0.microGamepad?.buttonA.pressedChangedHandler = nil
        }
        tracker.end()
    }

    private func attach(_ controller: GCController) {
        guard let pad = controller.microGamepad else { return }
        pad.reportsAbsoluteDpadValues = true
        pad.dpad.valueChangedHandler = { [weak self] _, x, y in
            let time = ProcessInfo.processInfo.systemUptime
            MainActor.assumeIsolated { self?.move(to: [x, y], at: time) }
        }
        pad.buttonA.pressedChangedHandler = { [weak self] _, _, pressed in
            guard pressed else { return }
            let point = SIMD2(pad.dpad.xAxis.value, pad.dpad.yAxis.value)
            MainActor.assumeIsolated { self?.click(at: point) }
        }
    }

    private func move(to point: SIMD2<Float>, at time: TimeInterval) {
        if let step = tracker.sample(point, at: time) { onDrag?(step) }
    }

    private func click(at point: SIMD2<Float>) {
        guard !tracker.isSliding else { return }
        onClick?(ClickZone(tracker.position ?? point))
    }
}
