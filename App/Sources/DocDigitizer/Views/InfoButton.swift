import SwiftUI

/// Small ⓘ button that reveals a longer explanation (with constraints) in a
/// popover — keeps the main UI uncluttered while the details stay one click away.
struct InfoButton: View {
    let text: String
    @State private var show = false

    var body: some View {
        Button { show.toggle() } label: {
            Image(systemName: "info.circle")
                .foregroundStyle(.secondary)
        }
        .buttonStyle(.borderless)
        .help("Details")
        .popover(isPresented: $show, arrowEdge: .bottom) {
            Text(text)
                .font(.callout)
                .fixedSize(horizontal: false, vertical: true)
                .frame(width: 330, alignment: .leading)
                .padding(16)
        }
    }
}
