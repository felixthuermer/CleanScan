import SwiftUI
import AppKit

/// One row in the queue: filename, live status/stage, progress, and controls.
struct QueueRowView: View {
    let item: QueueItem
    let onCancel: () -> Void

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            Image(systemName: item.status.symbolName)
                .foregroundStyle(statusColor)
                .frame(width: 20)
                .symbolRenderingMode(.hierarchical)

            VStack(alignment: .leading, spacing: 3) {
                Text(item.filename)
                    .font(.body)
                    .lineLimit(1)
                    .truncationMode(.middle)
                statusLine
                if item.status.isActive {
                    ProgressView(value: item.progress)
                        .progressViewStyle(.linear)
                        .frame(maxWidth: 320)
                }
            }

            Spacer()
            controls
        }
        .padding(.vertical, 6)
    }

    // MARK: - status text
    private var statusLine: some View {
        Group {
            switch item.status {
            case .failed:
                Text(item.errorMessage ?? "Failed")
                    .foregroundStyle(.red)
            case .done:
                Text(doneSummary)
                    .foregroundStyle(.secondary)
            default:
                Text(activeText)
                    .foregroundStyle(.secondary)
            }
        }
        .font(.caption)
        .lineLimit(1)
    }

    private var doneSummary: String {
        let modeText: String
        switch item.mode {
        case "faithful": modeText = "faithful overlay"
        case "clean":    modeText = "cleaned scan"
        default:         modeText = "reconstructed"
        }
        let toolText: String?
        switch item.tool {
        case "positioned": toolText = "layout-preserving"
        case "native":     toolText = "native OCR"
        case "mineru":     toolText = "MinerU"
        case "tesseract":  toolText = "Tesseract"
        default:           toolText = nil
        }
        return toolText.map { "Done · \(modeText) · \($0)" } ?? "Done · \(modeText)"
    }

    private var activeText: String {
        var parts = [item.status.label]
        if !item.stageDetail.isEmpty { parts.append(item.stageDetail) }
        if let pp = item.pageProgressText { parts.append(pp) }
        return parts.joined(separator: " · ")
    }

    private var statusColor: Color {
        switch item.status {
        case .done:      return .green
        case .failed:    return .red
        case .cancelled: return .secondary
        default:         return .accentColor
        }
    }

    // MARK: - controls
    @ViewBuilder private var controls: some View {
        switch item.status {
        case .done:
            HStack(spacing: 4) {
                Button {
                    if let url = item.outputURL { NSWorkspace.shared.open(url) }
                } label: { Image(systemName: "arrow.up.forward.app") }
                    .help("Open the finished PDF")
                Button {
                    if let url = item.outputURL {
                        NSWorkspace.shared.activateFileViewerSelecting([url])
                    }
                } label: { Image(systemName: "folder") }
                    .help("Reveal in Finder")
            }
            .buttonStyle(.borderless)
        case .queued, .preprocessing, .parsing, .rendering:
            Button(role: .destructive, action: onCancel) {
                Image(systemName: "stop.circle")
            }
            .buttonStyle(.borderless)
            .help("Cancel")
        case .failed, .cancelled:
            EmptyView()
        }
    }
}
