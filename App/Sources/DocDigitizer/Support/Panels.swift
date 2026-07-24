import AppKit
import UniformTypeIdentifiers

/// Native open/save panels for picking input files and the output folder.
enum Panels {
    static func chooseInputFiles() -> [URL] {
        let panel = NSOpenPanel()
        panel.title = "Add Scans"
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.allowedContentTypes = [.pdf, .png, .jpeg, .tiff, .heic, .bmp, .webP]
        return panel.runModal() == .OK ? panel.urls : []
    }

    static func chooseOutputDirectory(start: URL?) -> URL? {
        let panel = NSOpenPanel()
        panel.title = "Choose Output Folder"
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.canCreateDirectories = true
        if let start { panel.directoryURL = start }
        return panel.runModal() == .OK ? panel.urls.first : nil
    }
}
