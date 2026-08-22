import WidgetKit
import SwiftUI

struct PlaceholderEntry: TimelineEntry {
    let date: Date
}

struct PlaceholderProvider: TimelineProvider {
    func placeholder(in context: Context) -> PlaceholderEntry {
        PlaceholderEntry(date: .now)
    }

    func getSnapshot(in context: Context, completion: @escaping (PlaceholderEntry) -> Void) {
        completion(PlaceholderEntry(date: .now))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<PlaceholderEntry>) -> Void) {
        completion(Timeline(entries: [PlaceholderEntry(date: .now)], policy: .never))
    }
}

struct SyllogicWidget: Widget {
    let kind = "SyllogicBalances"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: PlaceholderProvider()) { _ in
            Text("Syllogic")
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("Balances")
        .description("See your account balances at a glance.")
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}

@main
struct SyllogicWidgetBundle: WidgetBundle {
    var body: some Widget {
        SyllogicWidget()
    }
}
