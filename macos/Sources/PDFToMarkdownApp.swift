import SwiftUI

@main
struct PDFToMarkdownApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .frame(minWidth: 720, minHeight: 680)
        }
        .windowStyle(.titleBar)
        .defaultSize(width: 820, height: 760)
    }
}
