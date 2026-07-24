// swift-tools-version: 5.9
import PackageDescription

// DocDigitizer — native SwiftUI front-end.
//
// Built as a Swift Package so it compiles with the command-line Swift toolchain
// (no full Xcode required). `build-app.sh` assembles the executable into a
// proper DocDigitizer.app bundle with an Info.plist. The same Package.swift can
// also be opened directly in Xcode (`open Package.swift`).
let package = Package(
    name: "DocDigitizer",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(
            name: "DocDigitizer",
            path: "Sources/DocDigitizer"
        )
    ]
)
