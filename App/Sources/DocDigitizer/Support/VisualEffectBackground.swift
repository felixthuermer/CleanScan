import SwiftUI
import AppKit

/// A translucent window backing (NSVisualEffectView, blending behind the window)
/// so the desktop shows through slightly — the modern macOS "vibrant" look.
struct VisualEffectBackground: NSViewRepresentable {
    // `.hudWindow` is noticeably more see-through than `.underWindowBackground`
    // (the transparency lever — swap this to taste).
    var material: NSVisualEffectView.Material = .hudWindow

    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = material
        view.blendingMode = .behindWindow
        view.state = .active
        return view
    }

    func updateNSView(_ view: NSVisualEffectView, context: Context) {
        view.material = material
    }
}
