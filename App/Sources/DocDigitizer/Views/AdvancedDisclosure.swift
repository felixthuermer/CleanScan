import SwiftUI

/// Collapsed-by-default advanced settings: language override, correction pass,
/// render engine, and the reconstruction quality threshold.
struct AdvancedDisclosure: View {
    @EnvironmentObject var settings: AppSettings
    @State private var expanded = false

    var body: some View {
        DisclosureGroup("Advanced", isExpanded: $expanded) {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text("OCR languages")
                        .frame(width: 130, alignment: .leading)
                    TextField("de+en", text: $settings.language)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 160)
                    Text("e.g. de+en")
                        .font(.caption).foregroundStyle(.secondary)
                }

                Toggle(isOn: $settings.dewarp) {
                    Text("De-warp curved/folded pages (Clean mode)")
                }
                Text("Off by default. Only for photos of curved or folded pages — it can distort letters on flat scanner output, which is straightened by deskew (rotation) anyway.")
                    .font(.caption).foregroundStyle(.secondary)

                Toggle(isOn: $settings.correctionEnabled) {
                    Text("German correction pass (local Ollama)")
                }
                if settings.correctionEnabled {
                    HStack {
                        Text("Model")
                            .frame(width: 130, alignment: .leading)
                        TextField("llama3.2:3B", text: $settings.correctionModel)
                            .textFieldStyle(.roundedBorder)
                            .frame(width: 200)
                    }
                }

                HStack {
                    Text("Render engine")
                        .frame(width: 130, alignment: .leading)
                    Picker("", selection: $settings.engine) {
                        ForEach(RenderEngine.allCases) { Text($0.label).tag($0) }
                    }
                    .labelsHidden()
                    .frame(width: 200)
                    InfoButton(text: settings.engine.help)
                }
                Text("Only used by “flow” reconstruction. The default layout-preserving reconstruction renders directly and ignores this.")
                    .font(.caption).foregroundStyle(.secondary)

                HStack {
                    Text("Quality threshold")
                        .frame(width: 130, alignment: .leading)
                    Slider(value: $settings.qualityThreshold, in: 0...1)
                        .frame(width: 200)
                    Text(String(format: "%.2f", settings.qualityThreshold))
                        .font(.caption).monospacedDigit()
                        .frame(width: 34)
                }
                Text("Below this OCR confidence, DocDigitizer switches to faithful overlay.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            .padding(.top, 8)
            .padding(.leading, 4)
        }
        .font(.subheadline)
    }
}
