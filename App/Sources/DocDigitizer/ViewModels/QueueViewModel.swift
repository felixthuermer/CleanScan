import Foundation
import Combine

/// Owns the queue and runs documents through the backend **one at a time**
/// (no parallelism — predictable resource use on a laptop). New files can be
/// added while processing; a completion notification fires when the queue drains.
final class QueueViewModel: ObservableObject {
    @Published private(set) var items: [QueueItem] = []
    let settings: AppSettings

    private var runner: BackendRunner?
    private var activeID: QueueItem.ID?
    private var isProcessing = false
    private var cancelRequestedForActive = false

    // Per-session tallies for the "queue finished" notification.
    private var sessionCompleted = 0
    private var sessionFailed = 0

    static let supportedExtensions: Set<String> =
        ["pdf", "jpg", "jpeg", "png", "heic", "heif", "tif", "tiff", "bmp", "webp"]

    init(settings: AppSettings) {
        self.settings = settings
    }

    // MARK: - derived state (for the UI)
    var activeItem: QueueItem? { items.first { $0.id == activeID } }
    var hasQueued: Bool { items.contains { $0.status == .queued } }
    var isBusy: Bool { isProcessing }

    static func isSupported(_ url: URL) -> Bool {
        supportedExtensions.contains(url.pathExtension.lowercased())
    }

    // MARK: - intents
    func addFiles(_ urls: [URL]) {
        let supported = urls.filter { Self.isSupported($0) }
        guard !supported.isEmpty else { return }
        items.append(contentsOf: supported.map { QueueItem(url: $0) })
        startNextIfIdle()
    }

    func cancel(_ id: QueueItem.ID) {
        guard let idx = items.firstIndex(where: { $0.id == id }) else { return }
        if items[idx].id == activeID {
            cancelRequestedForActive = true
            runner?.cancel()               // termination handler finalizes the item
        } else if items[idx].status == .queued {
            items[idx].status = .cancelled
        }
    }

    func clearFinished() {
        items.removeAll { $0.status.isTerminal && $0.id != activeID }
    }

    // MARK: - sequential runner
    private func startNextIfIdle() {
        guard !isProcessing else { return }
        guard let idx = items.firstIndex(where: { $0.status == .queued }) else {
            finishSessionIfNeeded()
            return
        }

        isProcessing = true
        cancelRequestedForActive = false
        activeID = items[idx].id
        items[idx].status = .preprocessing
        items[idx].progress = 0
        let item = items[idx]

        let outputDir = settings.outputDirectory
        try? FileManager.default.createDirectory(
            at: outputDir, withIntermediateDirectories: true)

        let runner = BackendRunner()
        self.runner = runner
        runner.run(input: item.url,
                   outputDir: outputDir,
                   configJSON: settings.makeConfigJSON(),
                   onEvent: { [weak self] event in self?.handle(event, for: item.id) },
                   onFinish: { [weak self] code in self?.finishActive(code: code) })
    }

    private func handle(_ event: BackendEvent, for id: QueueItem.ID) {
        guard let idx = items.firstIndex(where: { $0.id == id }) else { return }
        switch event {
        case let .status(stage, progress, page, pages, detail):
            if !items[idx].status.isTerminal { items[idx].status = stage }
            if let progress { items[idx].progress = progress }
            if let page { items[idx].page = page }
            if let pages { items[idx].pageCount = pages }
            if let detail { items[idx].stageDetail = detail }
        case .log:
            break   // reserved for a future details panel
        case let .done(output, mode, tool, _):
            items[idx].status = .done
            items[idx].mode = mode
            items[idx].tool = tool
            items[idx].outputURL = URL(fileURLWithPath: output)
            items[idx].progress = 1
            items[idx].stageDetail = ""
        case let .error(message):
            items[idx].status = .failed
            items[idx].errorMessage = message
        }
    }

    private func finishActive(code: Int32) {
        if let idx = items.firstIndex(where: { $0.id == activeID }) {
            if cancelRequestedForActive {
                items[idx].status = .cancelled
            } else if items[idx].status == .done {
                sessionCompleted += 1
            } else if items[idx].status == .failed {
                sessionFailed += 1
            } else {
                items[idx].status = .failed
                items[idx].errorMessage = items[idx].errorMessage
                    ?? "Backend exited unexpectedly (code \(code))."
                sessionFailed += 1
            }
        }
        runner = nil
        activeID = nil
        isProcessing = false
        cancelRequestedForActive = false
        startNextIfIdle()
    }

    private func finishSessionIfNeeded() {
        guard sessionCompleted + sessionFailed > 0 else { return }
        NotificationManager.notifyQueueFinished(
            completed: sessionCompleted, failed: sessionFailed)
        sessionCompleted = 0
        sessionFailed = 0
    }
}
