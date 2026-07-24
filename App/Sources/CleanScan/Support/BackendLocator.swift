import Foundation

/// Locates the Python backend and its virtual-env interpreter, both in
/// development (running from `.build/…`) and when bundled inside CleanScan.app.
enum BackendLocator {

    /// Directory containing `pipeline/` and `.venv/`.
    static func backendDirectory() -> URL? {
        // 1) explicit override (handy for development)
        if let p = ProcessInfo.processInfo.environment["CLEANSCAN_BACKEND"] {
            let u = URL(fileURLWithPath: p, isDirectory: true)
            if hasBackend(u) { return u }
        }
        // 2) bundled: CleanScan.app/Contents/Resources/Backend
        if let res = Bundle.main.resourceURL {
            let u = res.appendingPathComponent("Backend", isDirectory: true)
            if hasBackend(u) { return u }
        }
        // 3) development: walk up from the executable looking for a Backend dir
        var dir = Bundle.main.bundleURL
        for _ in 0..<8 {
            let candidate = dir.appendingPathComponent("Backend", isDirectory: true)
            if hasBackend(candidate) { return candidate }
            let sibling = dir.deletingLastPathComponent()
                .appendingPathComponent("Backend", isDirectory: true)
            if hasBackend(sibling) { return sibling }
            dir = dir.deletingLastPathComponent()
        }
        return nil
    }

    /// The venv interpreter used to run `-m pipeline.main`.
    static func pythonExecutable() -> URL? {
        guard let dir = backendDirectory() else { return nil }
        let py = dir.appendingPathComponent(".venv/bin/python")
        return FileManager.default.isExecutableFile(atPath: py.path) ? py : nil
    }

    private static func hasBackend(_ url: URL) -> Bool {
        FileManager.default.fileExists(
            atPath: url.appendingPathComponent("pipeline/main.py").path)
    }

    /// Homebrew lib dir so the WeasyPrint subprocess can find Pango/Cairo.
    static func dyldFallbackLibraryPath() -> String {
        for p in ["/opt/homebrew/lib", "/usr/local/lib"]
        where FileManager.default.fileExists(atPath: p) {
            return p
        }
        return "/opt/homebrew/lib"
    }
}
