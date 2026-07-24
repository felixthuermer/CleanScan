// swift-tools-version: 5.9
import PackageDescription

// CleanScan — native SwiftUI front-end.
//
// Built as a Swift Package so it compiles with the command-line Swift toolchain
// (no full Xcode required). `build-app.sh` assembles the executable into a
// proper CleanScan.app bundle with an Info.plist. The same Package.swift can
// also be opened directly in Xcode (`open Package.swift`).
let package = Package(
    name: "CleanScan",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(
            name: "CleanScan",
            path: "Sources/CleanScan"
        )
    ]
)
