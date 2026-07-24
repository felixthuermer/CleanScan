import SwiftUI

/// Main window. Shows the one-time onboarding until the backend is ready, then
/// the working UI: settings, a compact drop affordance beside the live queue
/// (the whole window is a drop target), and the output-folder bar.
struct ContentView: View {
    @EnvironmentObject var queue: QueueViewModel
    @EnvironmentObject var settings: AppSettings
    @EnvironmentObject var backend: BackendSetup

    @State private var windowTargeted = false
    @State private var showManageBackend = false

    var body: some View {
        ZStack {
            VisualEffectBackground().ignoresSafeArea()

            if backend.isReady {
                working
            } else {
                OnboardingView(setup: backend)
            }
        }
        .frame(minWidth: 600, idealWidth: 940, minHeight: 440, idealHeight: 820)
        .onAppear { backend.refresh() }
        .sheet(isPresented: $showManageBackend) {
            OnboardingView(setup: backend, presentedAsSheet: true)
        }
    }

    // MARK: - working UI
    private var working: some View {
        VStack(spacing: 12) {
            header

            SettingsBar()
                .padding(16)
                .glassPanel()

            HStack(alignment: .top, spacing: 12) {
                DropZoneView(isTargeted: windowTargeted) { queue.addFiles($0) }
                    .frame(width: 240)
                queuePanel
            }

            outputBar
                .padding(.horizontal, 16)
                .padding(.vertical, 11)
                .glassPanel(cornerRadius: 14)
        }
        .padding(.horizontal, 18)
        .padding(.top, 6)
        .padding(.bottom, 16)
        // Extend under the (hidden) title bar so the header sits flush at the very
        // top, aligned with the traffic-light buttons.
        .ignoresSafeArea(.container, edges: .top)
        // The entire window is a drop target.
        .dropDestination(for: URL.self) { urls, _ in
            queue.addFiles(urls)
            return true
        } isTargeted: { windowTargeted = $0 }
        .overlay(dragOverlay)
    }

    // Title row: flush to the top, offset past the traffic-light buttons.
    private var header: some View {
        HStack(spacing: 9) {
            Image(systemName: "doc.text.viewfinder")
                .font(.title3).foregroundStyle(.tint)
            Text("CleanScan")
                .font(.title3.weight(.semibold))
            Spacer()
            if queue.isBusy { ProgressView().controlSize(.small) }
            Button { showManageBackend = true } label: {
                Image(systemName: "gearshape")
            }
            .buttonStyle(.borderless)
            .help("Manage / reinstall backend")
        }
        .padding(.leading, 72)     // clear the window's traffic-light buttons
        .padding(.trailing, 4)
        .frame(height: 24)
    }

    @ViewBuilder private var dragOverlay: some View {
        if windowTargeted {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .strokeBorder(Color.accentColor, lineWidth: 2)
                .padding(6)
                .allowsHitTesting(false)
        }
    }

    // MARK: - queue
    private var queuePanel: some View {
        Group {
            if queue.items.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "tray")
                        .font(.system(size: 30)).foregroundStyle(.tertiary)
                    Text("No documents yet").foregroundStyle(.secondary)
                    Text("Drop scans anywhere to get started")
                        .font(.caption).foregroundStyle(.tertiary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    LazyVStack(spacing: 2) {
                        ForEach(queue.items) { item in
                            QueueRowView(item: item) { queue.cancel(item.id) }
                                .padding(.horizontal, 14)
                                .padding(.vertical, 2)
                            if item.id != queue.items.last?.id {
                                Divider().padding(.leading, 46)
                            }
                        }
                    }
                    .padding(.vertical, 8)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .glassPanel()
    }

    // MARK: - output folder + summary
    private var outputBar: some View {
        HStack(spacing: 12) {
            Image(systemName: "folder.fill").foregroundStyle(.tint)
            VStack(alignment: .leading, spacing: 1) {
                Text("Output folder").font(.caption2).foregroundStyle(.secondary)
                Text(settings.outputDirectory.path)
                    .font(.callout).lineLimit(1).truncationMode(.middle)
            }
            Button("Change…") {
                if let dir = Panels.chooseOutputDirectory(start: settings.outputDirectory) {
                    settings.outputDirectoryPath = dir.path
                }
            }
            .buttonStyle(.bordered)

            Spacer()

            Button("Clear Finished") { queue.clearFinished() }
                .buttonStyle(.bordered)
                .disabled(!queue.items.contains { $0.status.isTerminal })
        }
    }
}
