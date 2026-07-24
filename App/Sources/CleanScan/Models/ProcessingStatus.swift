import Foundation

/// Lifecycle of one queued document. Mirrors the backend's stage names so the
/// JSON-lines events map straight onto UI state.
enum ProcessingStatus: String, Codable {
    case queued
    case preprocessing
    case parsing
    case rendering
    case done
    case failed
    case cancelled

    /// Short label shown in the queue row.
    var label: String {
        switch self {
        case .queued:        return "Queued"
        case .preprocessing: return "Preprocessing"
        case .parsing:       return "Parsing"
        case .rendering:     return "Rendering"
        case .done:          return "Done"
        case .failed:        return "Failed"
        case .cancelled:     return "Cancelled"
        }
    }

    var isActive: Bool {
        self == .preprocessing || self == .parsing || self == .rendering
    }

    var isTerminal: Bool {
        self == .done || self == .failed || self == .cancelled
    }

    /// SF Symbol used in the row.
    var symbolName: String {
        switch self {
        case .queued:        return "clock"
        case .preprocessing: return "wand.and.stars"
        case .parsing:       return "doc.text.magnifyingglass"
        case .rendering:     return "printer"
        case .done:          return "checkmark.circle.fill"
        case .failed:        return "xmark.octagon.fill"
        case .cancelled:     return "minus.circle"
        }
    }
}
