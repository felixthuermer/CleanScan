import SwiftUI

extension View {
    /// A translucent "card" surface: real Liquid Glass on macOS 26+, a frosted
    /// material fallback below. Used to group the app's panels.
    @ViewBuilder
    func glassPanel(cornerRadius: CGFloat = 16) -> some View {
        let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
        if #available(macOS 26.0, *) {
            self.glassEffect(.regular, in: shape)
        } else {
            self
                .background(.regularMaterial, in: shape)
                .overlay(shape.strokeBorder(Color.primary.opacity(0.06)))
                .shadow(color: .black.opacity(0.08), radius: 8, y: 2)
        }
    }
}
