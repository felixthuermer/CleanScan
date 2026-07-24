import SwiftUI

/// Two independent axes — Resize (target size + fit) and processing Mode — plus
/// the collapsed Advanced disclosure.
struct SettingsBar: View {
    @EnvironmentObject var settings: AppSettings

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // --- Resize (independent of the mode) ---
            HStack(spacing: 16) {
                sectionLabel("Resize")
                field("Fit") {
                    Picker("", selection: $settings.resizeFit) {
                        ForEach(ResizeFit.allCases) { Text($0.label).tag($0) }
                    }
                    .labelsHidden().frame(width: 135)
                    InfoButton(text: settings.resizeFit.help)
                }
                field("Size") {
                    Picker("", selection: $settings.pageSize) {
                        ForEach(TargetPageSize.allCases) { Text($0.label).tag($0) }
                    }
                    .labelsHidden().frame(width: 175)
                    .disabled(!settings.resizeFit.usesTargetSize)
                }
                Spacer()
            }

            // --- Processing mode ---
            HStack(spacing: 10) {
                sectionLabel("Mode")
                Picker("", selection: $settings.mode) {
                    ForEach(ProcessingMode.allCases) { Text($0.label).tag($0) }
                }
                .labelsHidden().frame(width: 175)
                InfoButton(text: settings.mode.help)
                Text(settings.mode.summary)
                    .font(.caption).foregroundStyle(.secondary).lineLimit(1)
                Spacer()
            }

            AdvancedDisclosure()
        }
    }

    private func sectionLabel(_ text: String) -> some View {
        Text(text)
            .font(.subheadline.weight(.semibold))
            .frame(width: 56, alignment: .leading)
    }

    @ViewBuilder
    private func field<Content: View>(_ label: String,
                                      @ViewBuilder _ content: () -> Content) -> some View {
        HStack(spacing: 6) {
            Text(label).foregroundStyle(.secondary)
            content()
        }
    }
}
