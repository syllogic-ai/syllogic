// swift-tools-version: 5.9
import PackageDescription

// Tests the platform-neutral half of the widget. `swift test` needs no Xcode,
// no simulator, and survives `expo prebuild --clean`, which regenerates
// mobile/ios/ wholesale. The widget extension compiles these same files
// directly; this package is a second consumer of one source of truth.
let package = Package(
    name: "WidgetCore",
    platforms: [.iOS(.v17), .macOS(.v14)],
    targets: [
        .target(name: "WidgetCore", path: "widget/Core"),
        .testTarget(name: "WidgetCoreTests", dependencies: ["WidgetCore"], path: "WidgetCoreTests"),
    ]
)
