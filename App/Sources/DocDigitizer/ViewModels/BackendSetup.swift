import Foundation
import Combine

enum BackendState: Equatable {
    case checking
    case notInstalled
    case installing
    case ready
    case failed(String)
}

/// Detects whether the Python backend is installed and drives `setup.sh` from
/// inside the app, so the user never has to touch the terminal.
final class BackendSetup: ObservableObject {
    @Published var state: BackendState = .checking
    @Published var log: String = ""
    @Published var mineruInstalled: Bool = false

    private var process: Process?

    var isReady: Bool { state == .ready }

    /// Backend is "ready" once the venv interpreter and the native OCR helper exist.
    func refresh() {
        guard let dir = BackendLocator.backendDirectory() else {
            state = .notInstalled
            return
        }
        let py = dir.appendingPathComponent(".venv/bin/python")
        let helper = dir.appendingPathComponent("bin/visionocr")
        let fm = FileManager.default
        if fm.isExecutableFile(atPath: py.path) && fm.fileExists(atPath: helper.path) {
            mineruInstalled = fm.fileExists(atPath: dir.appendingPathComponent(".venv/bin/mineru").path)
            state = .ready
        } else if case .installing = state {
            // don't clobber an in-progress install
        } else {
            state = .notInstalled
        }
    }

    func install(withMineru: Bool) {
        guard let dir = BackendLocator.backendDirectory() else {
            state = .failed("Couldn't find the Backend folder next to the app.")
            return
        }
        let script = dir.appendingPathComponent("setup.sh")
        guard FileManager.default.fileExists(atPath: script.path) else {
            state = .failed("setup.sh not found in \(dir.path)")
            return
        }

        state = .installing
        log = ""

        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/bin/bash")
        proc.arguments = withMineru ? [script.path, "--with-mineru"] : [script.path]
        proc.currentDirectoryURL = dir

        // A Finder-launched app has a minimal PATH; make sure Homebrew + the
        // toolchain are discoverable so setup.sh can find brew/swiftc/python.
        var env = ProcessInfo.processInfo.environment
        let toolPaths = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        env["PATH"] = toolPaths + ":" + (env["PATH"] ?? "")
        proc.environment = env

        let pipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError = pipe
        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let s = String(data: data, encoding: .utf8) else { return }
            DispatchQueue.main.async { self?.appendLog(s) }
        }
        proc.terminationHandler = { [weak self] p in
            pipe.fileHandleForReading.readabilityHandler = nil
            DispatchQueue.main.async {
                guard let self else { return }
                self.process = nil
                if p.terminationStatus == 0 {
                    self.refresh()
                    if !self.isReady {
                        self.state = .failed("Setup finished but the backend still isn't ready — see the log.")
                    }
                } else {
                    self.state = .failed("Setup failed (exit code \(p.terminationStatus)) — see the log below.")
                }
            }
        }

        do {
            try proc.run()
            process = proc
        } catch {
            state = .failed("Couldn't start setup: \(error.localizedDescription)")
        }
    }

    func cancel() {
        process?.terminate()
    }

    private func appendLog(_ s: String) {
        log += s
        if log.count > 40_000 { log = String(log.suffix(30_000)) }
    }
}
