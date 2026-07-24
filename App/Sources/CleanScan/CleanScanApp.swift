import SwiftUI
import AppKit
import UserNotifications

@main
struct CleanScanApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var settings: AppSettings
    @StateObject private var queue: QueueViewModel
    @StateObject private var backend = BackendSetup()

    init() {
        let s = AppSettings()
        _settings = StateObject(wrappedValue: s)
        _queue = StateObject(wrappedValue: QueueViewModel(settings: s))
    }

    var body: some Scene {
        WindowGroup("CleanScan") {
            ContentView()
                .environmentObject(settings)
                .environmentObject(queue)
                .environmentObject(backend)
        }
        .windowStyle(.hiddenTitleBar)          // merge title bar with content (native look)
        .windowResizability(.contentMinSize)
    }
}

/// Handles notification authorization and lets banners show while in foreground.
final class AppDelegate: NSObject, NSApplicationDelegate, UNUserNotificationCenterDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        // UNUserNotificationCenter requires a real bundle id (assembled .app only).
        if Bundle.main.bundleIdentifier != nil {
            UNUserNotificationCenter.current().delegate = self
            NotificationManager.requestAuthorization()
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .sound])
    }
}
