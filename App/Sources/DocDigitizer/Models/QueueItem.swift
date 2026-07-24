import Foundation

/// One document in the processing queue. Value type — the view model mutates
/// items in place through the `@Published` array, which drives live UI updates.
struct QueueItem: Identifiable {
    let id = UUID()
    let url: URL

    var status: ProcessingStatus = .queued
    var stageDetail: String = ""       // fine-grained step from the backend ("deskew", …)
    var progress: Double = 0           // 0.0–1.0 within the current run
    var page: Int? = nil               // current page being worked on
    var pageCount: Int? = nil

    var outputURL: URL? = nil          // set when done
    var mode: String? = nil            // "reconstruct" | "faithful"
    var tool: String? = nil            // "native" | "mineru" | "tesseract"
    var errorMessage: String? = nil

    var filename: String { url.lastPathComponent }

    /// "page 2 / 3" when the backend reports page progress.
    var pageProgressText: String? {
        guard let p = page, let n = pageCount, n > 0 else { return nil }
        return "page \(p) / \(n)"
    }
}
