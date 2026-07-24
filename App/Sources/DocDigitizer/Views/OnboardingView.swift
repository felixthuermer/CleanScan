import SwiftUI

/// One-time backend setup, driven from inside the app. Shown as the main content
/// until the backend is ready, and reused as a "manage backend" sheet.
struct OnboardingView: View {
    @ObservedObject var setup: BackendSetup
    var presentedAsSheet: Bool = false
    @Environment(\.dismiss) private var dismiss

    @State private var withMineru = false

    var body: some View {
        VStack(spacing: 18) {
            VStack(spacing: 8) {
                Image(systemName: setup.isReady ? "checkmark.seal.fill" : "shippingbox")
                    .font(.system(size: 42))
                    .foregroundStyle(setup.isReady ? AnyShapeStyle(.green) : AnyShapeStyle(.tint))
                Text(setup.isReady ? "Backend ready" : "Set up the processing backend")
                    .font(.title2.weight(.semibold))
                Text("A one-time local setup installs a Python environment, the native OCR helper, and rendering tools. After this, everything runs fully offline.")
                    .font(.callout).foregroundStyle(.secondary)
                    .multilineTextAlignment(.center).frame(maxWidth: 470)
            }

            Toggle(isOn: $withMineru) {
                VStack(alignment: .leading, spacing: 1) {
                    Text("Also install MinerU (optional)")
                    Text("Several GB — only needed for reflow reconstruction of complex tables.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            .toggleStyle(.checkbox)
            .disabled(setup.state == .installing)
            .frame(maxWidth: 470, alignment: .leading)

            content

            if presentedAsSheet {
                Button(setup.isReady ? "Done" : "Close") { dismiss() }
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding(28)
        .frame(minWidth: 540, minHeight: 380)
        .onAppear { setup.refresh() }
    }

    @ViewBuilder private var content: some View {
        switch setup.state {
        case .installing:
            VStack(spacing: 10) {
                ProgressView("Installing… this can take several minutes")
                    .frame(maxWidth: 470)
                logView
                Button("Cancel", role: .destructive) { setup.cancel() }
                    .buttonStyle(.bordered)
            }
        case .failed(let message):
            VStack(spacing: 10) {
                Label(message, systemImage: "exclamationmark.triangle.fill")
                    .foregroundStyle(.orange).multilineTextAlignment(.center)
                logView
                Button { setup.install(withMineru: withMineru) } label: {
                    Label("Try again", systemImage: "arrow.clockwise")
                }.buttonStyle(.borderedProminent)
            }
        case .ready:
            VStack(spacing: 8) {
                Label(setup.mineruInstalled ? "Native OCR + MinerU installed"
                                            : "Native OCR installed (MinerU optional)",
                      systemImage: "checkmark.circle.fill")
                    .foregroundStyle(.green)
                Button { setup.install(withMineru: withMineru) } label: {
                    Label("Reinstall / update", systemImage: "arrow.triangle.2.circlepath")
                }.buttonStyle(.bordered)
            }
        default:
            VStack(spacing: 8) {
                Button { setup.install(withMineru: withMineru) } label: {
                    Label("Install backend", systemImage: "arrow.down.circle.fill")
                        .frame(maxWidth: 220)
                }
                .buttonStyle(.borderedProminent).controlSize(.large)
                Text("Requires Homebrew. Needs the internet for this one-time download.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private var logView: some View {
        ScrollViewReader { proxy in
            ScrollView {
                Text(setup.log.isEmpty ? "…" : setup.log)
                    .font(.system(.caption2, design: .monospaced))
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(8)
                    .id("logEnd")
            }
            .frame(width: 470, height: 150)
            .background(Color.primary.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
            .onChange(of: setup.log) { _ in proxy.scrollTo("logEnd", anchor: .bottom) }
        }
    }
}
