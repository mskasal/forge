import SwiftUI

struct ForgeView: View {
    @Environment(ForgeStore.self) private var forge
    @AppStorage("forgeLight") private var presetName = LightPreset.studio.rawValue
    @AppStorage("forgeShowsGrid") private var showsGrid = true
    @State private var orbit = OrbitState()
    @State private var inspecting = false
    @State private var confirmPrint = false
    @State private var result: (ok: Bool, message: String)?

    private var preset: LightPreset { LightPreset(rawValue: presetName) ?? .studio }

    var body: some View {
        ScrollView(.vertical) {
            VStack(alignment: .leading, spacing: 28) {
                header

                if forge.needsSetup {
                    SetupCard()
                } else {
                    if let error = forge.error {
                        Label(error, systemImage: "wifi.exclamationmark")
                            .font(.callout)
                            .foregroundStyle(.red)
                    }

                    HStack(alignment: .top, spacing: 28) {
                        viewerCard
                        VStack(spacing: 24) {
                            printerCard
                            printCard
                        }
                        .frame(width: 560)
                    }

                    libraryCard
                }
            }
            .padding(.horizontal, 60)
            .padding(.vertical, 36)
            .frame(maxWidth: .infinity, alignment: .topLeading)
        }
        .onChange(of: forge.selectedProject) { orbit = OrbitState() }
        .fullScreenCover(isPresented: $inspecting) {
            InspectView(file: forge.modelFile, title: inspectTitle, orbit: $orbit, presetName: $presetName, showsGrid: showsGrid)
                .environment(forge)
        }
        .confirmationDialog(confirmTitle, isPresented: $confirmPrint, titleVisibility: .visible) {
            Button("Start print") { Task { result = await forge.startPrint() } }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text(confirmMessage)
        }
        .alert(result?.ok == true ? "Print started" : "Print failed",
               isPresented: Binding(get: { result != nil }, set: { if !$0 { result = nil } })) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(result?.message ?? "")
        }
    }

    // MARK: - Header

    private var header: some View {
        HStack(alignment: .center, spacing: 20) {
            Text("Forge").font(.largeTitle.bold())
            healthPill
            Spacer(minLength: 16)
            if !forge.needsSetup {
                Button("Hub settings") { forge.resetConnection() }
                    .buttonStyle(ChipStyle())
            }
        }
    }

    private var healthPill: some View {
        let (text, color): (String, Color) = switch forge.health {
        case .idle: ("Printer ready", .green)
        case .printing: ("Printing", .orange)
        case .attention: ("Attention", .red)
        case .previewOnly: ("Preview only", .blue)
        case .unreachable: ("Unreachable", .gray)
        case .unknown: ("Connecting", .gray)
        }
        return Label(text, systemImage: "circle.fill")
            .font(.callout.bold())
            .foregroundStyle(color)
            .padding(.horizontal, 18)
            .padding(.vertical, 8)
            .background(color.opacity(0.16), in: .capsule)
    }

    // MARK: - Top Hero: Full-Size 3D Viewer + Printer / Print

    private var viewerCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            Button { inspecting = forge.modelFile != nil } label: {
                ZStack {
                    if !inspecting {
                        ForgeModelView(file: forge.modelFile, orbit: orbit, preset: preset, showsGrid: showsGrid)
                    }
                    if forge.modelFile == nil {
                        if forge.isLoadingModel {
                            ProgressView("Downloading model…")
                        } else if !forge.hasLoaded {
                            ProgressView("Connecting…")
                        } else if forge.projects.isEmpty {
                            Label("No projects yet", systemImage: "cube.transparent").foregroundStyle(.secondary)
                        } else {
                            Label("No USDZ preview in this version", systemImage: "cube.transparent").foregroundStyle(.secondary)
                        }
                    }
                }
                .frame(maxWidth: .infinity)
                .frame(height: 580)
                .overlay(alignment: .topLeading) {
                    if let meta = forge.selectedMeta {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("\(meta.project) · v\(meta.version)")
                                .font(.headline)
                                .lineLimit(1)
                                .truncationMode(.tail)
                            if let note = meta.note, !note.isEmpty {
                                Text(note)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                                    .truncationMode(.tail)
                            }
                        }
                        .frame(maxWidth: 700, alignment: .leading)
                        .padding(.horizontal, 20)
                        .padding(.vertical, 12)
                        .background(.ultraThinMaterial, in: .rect(cornerRadius: 16))
                        .padding(20)
                    }
                }
                .overlay(alignment: .bottomTrailing) {
                    if forge.modelFile != nil {
                        Label("Full screen", systemImage: "arrow.up.left.and.arrow.down.right")
                            .font(.caption.bold())
                            .padding(.horizontal, 16)
                            .padding(.vertical, 8)
                            .background(.ultraThinMaterial, in: .capsule)
                            .padding(20)
                    }
                }
            }
            .buttonStyle(ViewerButtonStyle())

            HStack(spacing: 12) {
                ForEach(LightPreset.allCases) { item in
                    Button(item.label) { presetName = item.rawValue }
                        .buttonStyle(ChipStyle(isSelected: item == preset))
                }
                Spacer(minLength: 12)
                Button { showsGrid.toggle() } label: { Image(systemName: "grid") }
                    .buttonStyle(ChipStyle(isSelected: showsGrid))
            }
            .focusSection()
        }
        .frame(maxWidth: .infinity, alignment: .topLeading)
    }

    private var printerCard: some View {
        let status = forge.printer
        return VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text(status?.displayName ?? "Printer")
                    .font(.headline)
                    .lineLimit(1)
                    .truncationMode(.tail)
                Spacer()
                Text(status?.state?.rawValue.capitalized ?? (forge.printers.isEmpty ? "None" : "—"))
                    .font(.headline)
                    .foregroundStyle(status?.state?.isBusy == true ? .orange : .green)
            }

            if forge.printers.count > 1 {
                HStack(spacing: 10) {
                    ForEach(forge.printers) { p in
                        Button(p.displayName) { forge.selectPrinter(p.id) }
                            .buttonStyle(ChipStyle(isSelected: p.id == forge.selectedPrinterId))
                    }
                }
            }

            if let status, status.state?.isBusy == true {
                HStack(alignment: .firstTextBaseline) {
                    Text("\(status.percent ?? 0)%")
                        .font(.system(size: 52, weight: .semibold, design: .rounded))
                        .foregroundStyle(.orange)
                    Spacer()
                    if let mins = status.remainingMinutes {
                        Text("\(mins) min left").font(.title3).foregroundStyle(.secondary)
                    }
                }
                ProgressView(value: Double(status.percent ?? 0), total: 100).tint(.orange)
            } else if let error = forge.printerError {
                Label(error, systemImage: "exclamationmark.triangle")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }

            VStack(spacing: 10) {
                factRow("Nozzle", tempText(status?.nozzleTemp, target: status?.nozzleTarget))
                Divider()
                factRow("Bed", tempText(status?.bedTemp, target: status?.bedTarget))
            }
        }
        .padding(26)
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .background(.regularMaterial, in: .rect(cornerRadius: 24))
    }

    private var printCard: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Print").font(.headline)
            VStack(spacing: 10) {
                factRow("Duration", forge.summary?.minutes.map { "~\($0) min" } ?? "—")
                Divider()
                factRow("Filament", forge.summary?.grams.map { "\($0.formatted(.number.precision(.fractionLength(0...1)))) g" } ?? "—")
                Divider()
                factRow("Plate", forge.summary?.bedType ?? "—")
                Divider()
                factRow("Print code", forge.printCode ?? "—")
            }

            Button { confirmPrint = true } label: {
                Label(forge.isSubmittingPrint ? "Sending…" : "Print…", systemImage: "printer.fill")
                    .frame(maxWidth: .infinity)
            }
            .disabled(!forge.canPrint)

            if let blocker = forge.printBlocker {
                Label(blocker, systemImage: "lock.fill")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else if forge.printCode != nil {
                Text("Give this single-use code to your AI agent or press Print above.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(26)
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .background(.regularMaterial, in: .rect(cornerRadius: 24))
    }

    // MARK: - Unified Bottom Library (Projects → Versions in One Card)

    @ViewBuilder
    private var libraryCard: some View {
        if !forge.projects.isEmpty {
            HStack(alignment: .top, spacing: 0) {
                // Left pane: Projects list
                VStack(alignment: .leading, spacing: 14) {
                    paneHeader("Projects", count: forge.projects.count)
                    ScrollView(.vertical, showsIndicators: false) {
                        LazyVStack(spacing: 8) {
                            ForEach(forge.projects) { p in
                                let selected = p.name == forge.selectedProject
                                Button {
                                    Task { await forge.select(project: p.name) }
                                } label: {
                                    HStack(spacing: 12) {
                                        Text(p.name)
                                            .font(.callout.weight(selected ? .semibold : .regular))
                                            .lineLimit(1)
                                            .truncationMode(.tail)
                                            .frame(maxWidth: .infinity, alignment: .leading)
                                        if let latest = p.latest {
                                            Text("v\(latest)")
                                                .font(.caption.monospacedDigit())
                                                .padding(.horizontal, 10)
                                                .padding(.vertical, 4)
                                                .background(.quaternary, in: .capsule)
                                        }
                                    }
                                    .padding(.horizontal, 18)
                                    .padding(.vertical, 14)
                                }
                                .buttonStyle(ListRowStyle(isSelected: selected))
                            }
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                    }
                }
                .padding(22)
                .frame(width: 500)
                .focusSection()

                Divider()
                    .padding(.vertical, 20)

                // Right pane: Selected project's versions
                VStack(alignment: .leading, spacing: 14) {
                    paneHeader(
                        forge.selectedProject.map { "\($0) — Versions" } ?? "Versions",
                        count: forge.versions.count
                    )
                    if forge.versions.isEmpty {
                        Spacer(minLength: 0)
                        Text("No versions yet")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, alignment: .center)
                        Spacer(minLength: 0)
                    } else {
                        ScrollView(.vertical, showsIndicators: false) {
                            LazyVStack(spacing: 8) {
                                ForEach(Array(forge.versions.enumerated()), id: \.element.id) { index, v in
                                    let selected = v.version == forge.selectedVersion
                                    Button {
                                        Task { await forge.select(version: v.version) }
                                    } label: {
                                        HStack(spacing: 16) {
                                            Text("v\(v.version)")
                                                .font(.callout.monospacedDigit().bold())
                                                .frame(width: 64, alignment: .leading)
                                            if index == 0 {
                                                Text("Latest")
                                                    .font(.caption2.weight(.semibold))
                                                    .padding(.horizontal, 9)
                                                    .padding(.vertical, 3)
                                                    .background(.quaternary, in: .capsule)
                                            }
                                            Text(v.note?.isEmpty == false ? v.note! : "No note")
                                                .font(.callout)
                                                .opacity(0.85)
                                                .lineLimit(1)
                                                .truncationMode(.tail)
                                                .frame(maxWidth: .infinity, alignment: .leading)
                                            if v.hasPrintFile {
                                                Image(systemName: "printer.fill")
                                                    .font(.callout)
                                                    .opacity(0.75)
                                            }
                                        }
                                        .padding(.horizontal, 18)
                                        .padding(.vertical, 14)
                                    }
                                    .buttonStyle(ListRowStyle(isSelected: selected))
                                }
                            }
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                        }
                    }
                }
                .padding(22)
                .frame(maxWidth: .infinity)
                .focusSection()
            }
            .frame(maxWidth: .infinity)
            .frame(height: 460)
            .background(.regularMaterial, in: .rect(cornerRadius: 24))
        }
    }

    private func paneHeader(_ title: String, count: Int) -> some View {
        HStack(spacing: 12) {
            Text(title)
                .font(.headline)
                .lineLimit(1)
                .truncationMode(.tail)
            Spacer(minLength: 8)
            if count > 0 {
                Text("\(count)")
                    .font(.caption.monospacedDigit().weight(.semibold))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(Color.white.opacity(0.08), in: .capsule)
            }
        }
        .padding(.horizontal, 10)
    }

    // MARK: - Helpers

    private func factRow(_ title: String, _ value: String) -> some View {
        HStack {
            Text(title).foregroundStyle(.secondary)
            Spacer(minLength: 8)
            Text(value)
                .monospacedDigit()
                .lineLimit(1)
                .truncationMode(.tail)
        }
        .font(.callout)
    }

    private func tempText(_ current: Double?, target: Double?) -> String {
        guard let current else { return "—" }
        let base = "\(Int(current.rounded())) °C"
        guard let target, target > 0 else { return base }
        return "\(base) → \(Int(target.rounded())) °C"
    }

    private var inspectTitle: String {
        forge.selectedMeta.map { "\($0.project) · v\($0.version)" } ?? "Forge"
    }

    private var confirmTitle: String {
        forge.selectedMeta.map { "Print \($0.project) v\($0.version)?" } ?? "Start print?"
    }

    private var confirmMessage: String {
        let target = forge.printer?.displayName ?? "printer"
        return "Target: \(target). Ensure the build plate is empty, clean, and matches the sliced plate."
    }
}

private struct InspectView: View {
    let file: URL?
    let title: String
    @Binding var orbit: OrbitState
    @Binding var presetName: String
    let showsGrid: Bool

    @State private var view = OrbitState()
    @Environment(\.dismiss) private var dismiss
    @State private var touch = RemoteTouch()
    @FocusState private var focused: Bool
    @State private var showHelp = true

    private var preset: LightPreset { LightPreset(rawValue: presetName) ?? .studio }

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            ForgeModelView(file: file, orbit: view, preset: preset, showsGrid: showsGrid, labelInset: showHelp ? 140 : 50)
                .ignoresSafeArea()
        }
        .overlay(alignment: .topLeading) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.callout.bold())
                Text("Light: \(preset.label)").font(.caption2).foregroundStyle(.secondary)
            }
            .padding(.horizontal, 18).padding(.vertical, 10)
            .background(.ultraThinMaterial, in: .rect(cornerRadius: 14))
        }
        .overlay(alignment: .bottom) {
            if showHelp {
                HStack(spacing: 28) {
                    Label("Swipe: orbit", systemImage: "hand.draw")
                    Label("Up/Down click: zoom", systemImage: "plus.magnifyingglass")
                    Label("Left/Right: 45°", systemImage: "arrow.left.and.right")
                    Label("Center: reset", systemImage: "scope")
                    Label("Play/Pause: light", systemImage: "playpause")
                }
                .font(.callout)
                .padding(.horizontal, 32).padding(.vertical, 16)
                .background(.ultraThinMaterial, in: .capsule)
            }
        }
        .focusable()
        .focused($focused)
        .onAppear {
            view = orbit
            focused = true
            touch.onDrag = { step in view.rotate(dx: step.x * 1.6, dy: -step.y * 1.2) }
            touch.onClick = { zone in
                withAnimation(.easeInOut(duration: 0.3)) {
                    switch zone {
                    case .up: view.zoom(by: 0.75)
                    case .down: view.zoom(by: 1 / 0.75)
                    case .left: view.rotate(dx: -.pi / 4, dy: 0)
                    case .right: view.rotate(dx: .pi / 4, dy: 0)
                    case .center: view = OrbitState()
                    }
                }
            }
            touch.start()
        }
        .onDisappear { touch.stop(); orbit = view }
        .task { try? await Task.sleep(for: .seconds(6)); withAnimation { showHelp = false } }
        .onPlayPauseCommand { presetName = preset.next.rawValue }
        .onExitCommand { dismiss() }
    }
}

private struct SetupCard: View {
    @Environment(ForgeStore.self) private var forge
    @State private var url = ""
    @State private var token = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            Label("Connect to Forge Hub", systemImage: "network")
                .font(.headline)
            Text("Enter your local Forge Hub URL (for example http://192.168.1.20:8590) and your appletv or owner token. The token is stored in Keychain only.")
                .font(.callout).foregroundStyle(.secondary)
            TextField("http://192.168.1.20:8590", text: $url)
            SecureField("Hub token", text: $token)
            Button("Save & Connect") { Task { await forge.saveConnection(url: url, token: token) } }
                .disabled(url.trimmingCharacters(in: .whitespaces).isEmpty || token.trimmingCharacters(in: .whitespaces).isEmpty)
            if let error = forge.error {
                Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.red)
            }
        }
        .onAppear { if url.isEmpty { url = forge.hubURLString } }
        .padding(32)
        .frame(maxWidth: 1100, alignment: .leading)
        .background(.regularMaterial, in: .rect(cornerRadius: 24))
    }
}

private struct ListRowStyle: ButtonStyle {
    var isSelected = false

    func makeBody(configuration: Configuration) -> some View {
        StyledBody(configuration: configuration, isSelected: isSelected)
    }

    private struct StyledBody: View {
        let configuration: Configuration
        let isSelected: Bool
        @Environment(\.isFocused) private var isFocused

        var body: some View {
            configuration.label
                .frame(maxWidth: .infinity, alignment: .leading)
                .foregroundStyle(isFocused ? Color.black : Color.primary)
                .background(
                    isFocused
                        ? Color.white
                        : (isSelected ? Color.accentColor.opacity(0.22) : Color.white.opacity(0.05)),
                    in: .rect(cornerRadius: 14)
                )
                .overlay(alignment: .leading) {
                    if isSelected && !isFocused {
                        Capsule()
                            .fill(Color.accentColor)
                            .frame(width: 4, height: 24)
                            .padding(.leading, 4)
                    }
                }
                .scaleEffect(isFocused ? 1.02 : 1)
                .shadow(color: isFocused ? .black.opacity(0.35) : .clear, radius: 10, y: 5)
                .animation(.easeOut(duration: 0.14), value: isFocused)
        }
    }
}

private struct ViewerButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View { StyledBody(configuration: configuration) }
    private struct StyledBody: View {
        let configuration: Configuration
        @Environment(\.isFocused) private var isFocused
        var body: some View {
            configuration.label
                .background(Color.black.opacity(0.35), in: .rect(cornerRadius: 24))
                .clipShape(.rect(cornerRadius: 24))
                .overlay {
                    RoundedRectangle(cornerRadius: 24)
                        .strokeBorder(isFocused ? Color.white : Color.white.opacity(0.08), lineWidth: isFocused ? 4 : 1)
                }
                .scaleEffect(isFocused ? 1.01 : 1)
                .animation(.easeOut(duration: 0.15), value: isFocused)
        }
    }
}

private struct ChipStyle: ButtonStyle {
    var isSelected = false
    func makeBody(configuration: Configuration) -> some View { StyledBody(configuration: configuration, isSelected: isSelected) }
    private struct StyledBody: View {
        let configuration: Configuration
        let isSelected: Bool
        @Environment(\.isFocused) private var isFocused
        var body: some View {
            configuration.label
                .font(.callout.weight(isSelected ? .semibold : .regular))
                .lineLimit(1)
                .padding(.horizontal, 20)
                .padding(.vertical, 10)
                .foregroundStyle(isFocused ? Color.black : (isSelected ? Color.primary : Color.secondary))
                .background(isFocused ? Color.white : (isSelected ? Color.white.opacity(0.18) : Color.white.opacity(0.06)), in: .capsule)
                .scaleEffect(isFocused ? 1.05 : 1)
                .animation(.easeOut(duration: 0.14), value: isFocused)
        }
    }
}
