import Foundation
import UserNotifications

/// Thin wrapper around UserNotifications for the "queue finished" alert.
///
/// UNUserNotificationCenter requires a real bundle identifier, which only exists
/// when running the assembled CleanScan.app (not a bare `swift run`). Every
/// call is guarded so development runs degrade gracefully instead of crashing.
enum NotificationManager {
    private static var isAvailable: Bool { Bundle.main.bundleIdentifier != nil }

    static func requestAuthorization() {
        guard isAvailable else { return }
        UNUserNotificationCenter.current()
            .requestAuthorization(options: [.alert, .sound]) { _, _ in }
    }

    static func notifyQueueFinished(completed: Int, failed: Int) {
        guard isAvailable else { return }
        let content = UNMutableNotificationContent()
        content.title = "CleanScan"
        if failed == 0 {
            content.body = "Finished processing \(completed) document"
                + (completed == 1 ? "." : "s.")
        } else {
            content.body = "Finished: \(completed) done, \(failed) failed."
        }
        content.sound = .default
        let request = UNNotificationRequest(
            identifier: UUID().uuidString, content: content, trigger: nil)
        UNUserNotificationCenter.current().add(request)
    }
}
