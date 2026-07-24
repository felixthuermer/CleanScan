import Foundation
import Combine

enum TargetPageSize: String, CaseIterable, Identifiable {
    case a4, letter, match
    var id: String { rawValue }
    var label: String {
        switch self {
        case .a4:     return "A4"
        case .letter: return "US Letter"
        case .match:  return "Match most common"
        }
    }
}

/// How pages are fit to the target size (independent of the processing mode).
enum ResizeFit: String, CaseIterable, Identifiable {
    case fit, width, none
    var id: String { rawValue }
    var label: String {
        switch self {
        case .fit:   return "Fit to page"
        case .width: return "Width only"
        case .none:  return "Original size"
        }
    }
    var help: String {
        switch self {
        case .fit:   return "Fit each page into the full target box (uniform width and height; may add margins)."
        case .width: return "Normalize width only — height stays proportional, so nothing is stretched into a new aspect ratio."
        case .none:  return "Don’t resize — keep each page at its original size. Pages may end up different sizes (Size is ignored)."
        }
    }
    /// The target Size picker is meaningless when not resizing.
    var usesTargetSize: Bool { self != .none }
}

enum ProcessingMode: String, CaseIterable, Identifiable {
    case auto, reconstruct, faithful, clean
    var id: String { rawValue }
    var label: String {
        switch self {
        case .auto:        return "Auto"
        case .reconstruct: return "Reconstruct"
        case .faithful:    return "Faithful"
        case .clean:       return "Clean"
        }
    }
    /// One-line gist shown next to the picker.
    var summary: String {
        switch self {
        case .auto:        return "Chooses the best mode per document automatically."
        case .reconstruct: return "Rebuilds the page as crisp digital text in the original layout."
        case .faithful:    return "Keeps the original scan image, adds searchable text."
        case .clean:       return "Cleans & straightens the scan, adds searchable text."
        }
    }
    /// Full explanation incl. constraints (shown on the info popover).
    var help: String {
        switch self {
        case .auto:
            return """
            Decides per document: rebuilds the original layout as digital text \
            when OCR is confident, otherwise keeps a faithful scan overlay.
            • Best general default.
            • Constraint: the choice depends on OCR confidence, so very noisy \
            scans may fall back to Faithful.
            """
        case .reconstruct:
            return """
            Rebuilds the page as crisp, selectable digital text with logos, \
            figures and redactions kept in place — looks born-digital, layout \
            preserved.
            • Best for reasonably clean scans you want fully digital.
            • Constraints: text must OCR well; very dense multi-column pages can \
            have minor misplacements; graphics are re-embedded as image crops.
            """
        case .faithful:
            return """
            Keeps the exact original scan image and adds an invisible, searchable \
            text layer. Nothing is re-rendered, so layout is 100 % preserved.
            • Best when fidelity to the original matters most.
            • Constraints: output is still the scan (not crisp digital text) and \
            stays image-based; no shadow/skew cleanup.
            """
        case .clean:
            return """
            Like Faithful, but the scan is cleaned first: fold shadows & uneven \
            lighting removed, paper snapped to white, and text straightened by \
            deskew (rotation — letter-safe).
            • Best for messy or slightly skewed scans you want to look tidy.
            • Constraints: image-based (not re-typeset). A non-linear de-warp for \
            genuinely curved/folded photos is optional (Advanced) and off by \
            default, since it can distort letters on flat scans.
            """
        }
    }
}

enum RenderEngine: String, CaseIterable, Identifiable {
    case weasyprint, chromium
    var id: String { rawValue }
    var label: String { self == .weasyprint ? "WeasyPrint" : "Headless Chromium" }
    var help: String {
        switch self {
        case .weasyprint:
            return """
            Pure-Python renderer — fast, fully offline, no browser needed.
            • Best for text- and table-heavy documents.
            • Restriction: limited CSS support, so very complex or web-styled \
            layouts may render imperfectly.
            """
        case .chromium:
            return """
            Renders via headless Chrome — highest fidelity for complex, \
            HTML/CSS-heavy layouts.
            • Restrictions: needs Playwright + Chromium installed (~hundreds of \
            MB), slower to start, uses more memory.
            """
        }
    }
}

/// The JSON the backend expects (`RunConfig` on the Python side). CodingKeys map
/// to the snake_case field names in `config.py`.
private struct BackendConfig: Encodable {
    let page_size: String
    let resize_fit: String
    let mode: String
    let language: String
    let correction: Bool
    let correction_model: String
    let engine: String
    let quality_threshold: Double
    let dewarp: Bool
}

/// User-facing settings. Persists to UserDefaults; surfaced settings are page
/// size + mode, everything else lives under the Advanced disclosure.
final class AppSettings: ObservableObject {
    @Published var pageSize: TargetPageSize { didSet { save() } }
    @Published var resizeFit: ResizeFit { didSet { save() } }
    @Published var mode: ProcessingMode { didSet { save() } }
    @Published var outputDirectoryPath: String { didSet { save() } }

    // Advanced
    @Published var language: String { didSet { save() } }
    @Published var correctionEnabled: Bool { didSet { save() } }
    @Published var correctionModel: String { didSet { save() } }
    @Published var engine: RenderEngine { didSet { save() } }
    @Published var qualityThreshold: Double { didSet { save() } }
    @Published var dewarp: Bool { didSet { save() } }   // Clean mode: optional non-linear de-warp

    private let defaults = UserDefaults.standard

    init() {
        let d = UserDefaults.standard
        pageSize = TargetPageSize(rawValue: d.string(forKey: "pageSize") ?? "") ?? .a4
        resizeFit = ResizeFit(rawValue: d.string(forKey: "resizeFit") ?? "") ?? .fit
        mode = ProcessingMode(rawValue: d.string(forKey: "mode") ?? "") ?? .auto
        outputDirectoryPath = d.string(forKey: "outputDirectoryPath")
            ?? AppSettings.defaultOutputDirectory().path
        language = d.string(forKey: "language") ?? "de+en"
        correctionEnabled = d.bool(forKey: "correctionEnabled")
        correctionModel = d.string(forKey: "correctionModel") ?? "llama3.2:3B"
        engine = RenderEngine(rawValue: d.string(forKey: "engine") ?? "") ?? .weasyprint
        qualityThreshold = d.object(forKey: "qualityThreshold") as? Double ?? 0.60
        dewarp = d.bool(forKey: "dewarp")   // default false
    }

    var outputDirectory: URL {
        URL(fileURLWithPath: outputDirectoryPath, isDirectory: true)
    }

    static func defaultOutputDirectory() -> URL {
        let downloads = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first
            ?? FileManager.default.homeDirectoryForCurrentUser
        return downloads.appendingPathComponent("CleanScan", isDirectory: true)
    }

    /// Inline JSON passed to the backend via `--config`.
    func makeConfigJSON() -> String {
        let cfg = BackendConfig(
            page_size: pageSize.rawValue,
            resize_fit: resizeFit.rawValue,
            mode: mode.rawValue,
            language: language,
            correction: correctionEnabled,
            correction_model: correctionModel,
            engine: engine.rawValue,
            quality_threshold: qualityThreshold,
            dewarp: dewarp
        )
        let data = (try? JSONEncoder().encode(cfg)) ?? Data("{}".utf8)
        return String(data: data, encoding: .utf8) ?? "{}"
    }

    private func save() {
        defaults.set(pageSize.rawValue, forKey: "pageSize")
        defaults.set(resizeFit.rawValue, forKey: "resizeFit")
        defaults.set(mode.rawValue, forKey: "mode")
        defaults.set(outputDirectoryPath, forKey: "outputDirectoryPath")
        defaults.set(language, forKey: "language")
        defaults.set(correctionEnabled, forKey: "correctionEnabled")
        defaults.set(correctionModel, forKey: "correctionModel")
        defaults.set(engine.rawValue, forKey: "engine")
        defaults.set(qualityThreshold, forKey: "qualityThreshold")
        defaults.set(dewarp, forKey: "dewarp")
    }
}
