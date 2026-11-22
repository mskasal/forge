import SwiftUI

@main
struct ForgeApp: App {
    @State private var store = ForgeStore()

    var body: some Scene {
        WindowGroup {
            RootForgeView()
                .environment(store)
        }
    }
}

private struct RootForgeView: View {
    @Environment(ForgeStore.self) private var store
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        ForgeView()
            .task(id: scenePhase) {
                guard scenePhase == .active else { return }
                await store.run()
            }
    }
}
