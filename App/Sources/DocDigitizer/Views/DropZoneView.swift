import SwiftUI

/// Compact drop affordance. The whole window is the actual drop target (see
/// ContentView); this view highlights when a drag is over the window and offers
/// an "Add Files…" button.
struct DropZoneView: View {
    let isTargeted: Bool
    let onURLs: ([URL]) -> Void

    private var shape: RoundedRectangle {
        RoundedRectangle(cornerRadius: 18, style: .continuous)
    }

    var body: some View {
        let iconColor = isTargeted ? Color.accentColor : Color(nsColor: .tertiaryLabelColor)
        let borderColor = isTargeted ? Color.accentColor : Color(nsColor: .separatorColor)

        return VStack(spacing: 8) {
            Spacer(minLength: 0)
            Image(systemName: "arrow.down.doc")
                .font(.system(size: 30))
                .foregroundStyle(iconColor)
            Text("Drop scans")
                .font(.headline)
            Text("anywhere in the window")
                .font(.caption).foregroundStyle(.secondary)
            Text("PDF · JPEG · PNG\nHEIC · TIFF")
                .font(.caption2).foregroundStyle(.tertiary)
                .multilineTextAlignment(.center)
            Button {
                let urls = Panels.chooseInputFiles()
                if !urls.isEmpty { onURLs(urls) }
            } label: {
                Label("Add Files…", systemImage: "plus")
            }
            .buttonStyle(.borderedProminent)
            .padding(.top, 4)
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(14)
        .glassPanel(cornerRadius: 18)
        .overlay(shape.fill(Color.accentColor.opacity(isTargeted ? 0.10 : 0)))
        .overlay(shape.strokeBorder(borderColor,
                                    style: StrokeStyle(lineWidth: 1.5, dash: [7, 5])))
        .animation(.easeInOut(duration: 0.15), value: isTargeted)
    }
}
