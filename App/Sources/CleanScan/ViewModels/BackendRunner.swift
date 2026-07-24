import Foundation

/// A decoded backend event (subset of the JSON-lines protocol in events.py).
enum BackendEvent {
    case status(stage: ProcessingStatus, progress: Double?, page: Int?, pages: Int?, detail: String?)
    case log(level: String, message: String)
    case done(output: String, mode: String, tool: String?, pages: Int?)
    case error(message: String)
}

/// Raw JSON shape emitted by the backend.
private struct RawEvent: Decodable {
    let event: String
    let stage: String?
    let progress: Double?
    let page: Int?
    let pages: Int?
    let detail: String?
    let level: String?
    let message: String?
    let output: String?
    let mode: String?
    let tool: String?
}

/// Runs the Python backend for a single document and streams its JSON-lines
/// output. One runner processes one document; the view model drives them
/// sequentially. Callbacks are always delivered on the main queue.
final class BackendRunner {
    private var process: Process?
    private var stdoutBuffer = Data()
    private let ioQueue = DispatchQueue(label: "com.cleanscan.backend.io")

    func run(input: URL,
             outputDir: URL,
             configJSON: String,
             onEvent: @escaping (BackendEvent) -> Void,
             onFinish: @escaping (Int32) -> Void) {

        guard let python = BackendLocator.pythonExecutable(),
              let backendDir = BackendLocator.backendDirectory() else {
            DispatchQueue.main.async {
                onEvent(.error(message: "Backend not found. Run Backend/setup.sh first."))
                onFinish(1)
            }
            return
        }

        let proc = Process()
        proc.executableURL = python
        proc.arguments = ["-m", "pipeline.main",
                          "--input", input.path,
                          "--output-dir", outputDir.path,
                          "--config", configJSON]
        proc.currentDirectoryURL = backendDir

        var env = ProcessInfo.processInfo.environment
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        let existing = env["DYLD_FALLBACK_LIBRARY_PATH"].map { ":" + $0 } ?? ""
        env["DYLD_FALLBACK_LIBRARY_PATH"] = BackendLocator.dyldFallbackLibraryPath() + existing
        proc.environment = env

        let outPipe = Pipe()
        let errPipe = Pipe()
        proc.standardOutput = outPipe
        proc.standardError = errPipe

        outPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let self else { return }
            self.ioQueue.async {
                self.stdoutBuffer.append(data)
                self.drainLines(onEvent: onEvent)
            }
        }
        // Forward stderr straight through for debugging; never parsed as events.
        errPipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            guard !data.isEmpty else { return }
            FileHandle.standardError.write(data)
        }

        proc.terminationHandler = { [weak self] p in
            outPipe.fileHandleForReading.readabilityHandler = nil
            errPipe.fileHandleForReading.readabilityHandler = nil
            guard let self else {
                DispatchQueue.main.async { onFinish(p.terminationStatus) }
                return
            }
            self.ioQueue.async {
                self.drainLines(onEvent: onEvent, flush: true)
                DispatchQueue.main.async { onFinish(p.terminationStatus) }
            }
        }

        do {
            try proc.run()
            self.process = proc
        } catch {
            DispatchQueue.main.async {
                onEvent(.error(message: "Failed to start backend: \(error.localizedDescription)"))
                onFinish(1)
            }
        }
    }

    func cancel() {
        process?.terminate()
    }

    // MARK: - line parsing (all on ioQueue)

    private func drainLines(onEvent: @escaping (BackendEvent) -> Void, flush: Bool = false) {
        let newline = UInt8(ascii: "\n")
        while let idx = stdoutBuffer.firstIndex(of: newline) {
            let line = stdoutBuffer.subdata(in: stdoutBuffer.startIndex..<idx)
            stdoutBuffer.removeSubrange(stdoutBuffer.startIndex...idx)
            emit(line, onEvent: onEvent)
        }
        if flush, !stdoutBuffer.isEmpty {
            let line = stdoutBuffer
            stdoutBuffer.removeAll()
            emit(line, onEvent: onEvent)
        }
    }

    private func emit(_ line: Data, onEvent: @escaping (BackendEvent) -> Void) {
        guard !line.isEmpty,
              let raw = try? JSONDecoder().decode(RawEvent.self, from: line) else { return }
        let event: BackendEvent
        switch raw.event {
        case "status":
            event = .status(stage: ProcessingStatus(rawValue: raw.stage ?? "") ?? .parsing,
                            progress: raw.progress, page: raw.page,
                            pages: raw.pages, detail: raw.detail)
        case "log":
            event = .log(level: raw.level ?? "info", message: raw.message ?? "")
        case "done":
            event = .done(output: raw.output ?? "",
                          mode: raw.mode ?? "reconstruct", tool: raw.tool, pages: raw.pages)
        case "error":
            event = .error(message: raw.message ?? "unknown error")
        default:
            return
        }
        DispatchQueue.main.async { onEvent(event) }
    }
}
