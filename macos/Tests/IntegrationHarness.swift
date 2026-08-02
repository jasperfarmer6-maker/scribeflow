import Darwin
import Foundation

@main
struct IntegrationHarness {
    static func main() async {
        guard CommandLine.arguments.count == 3 else {
            print("usage: GUIIntegrationHarness INPUT_PDF OUTPUT_PARENT")
            exit(2)
        }
        let input = URL(fileURLWithPath: CommandLine.arguments[1])
        let outputParent = URL(fileURLWithPath: CommandLine.arguments[2], isDirectory: true)
        let output = outputParent.appendingPathComponent(
            "\(input.deletingPathExtension().lastPathComponent)-Markdown",
            isDirectory: true
        )

        let viewModel = await MainActor.run { ConversionViewModel() }
        await MainActor.run {
            viewModel.start(
                ConversionOptions(
                    inputPDF: input,
                    outputDirectory: output,
                    overwrite: true,
                    useAI: false,
                    aiModel: "",
                    aiBaseURL: "",
                    apiKey: "",
                    automaticallyOpenOutput: false
                )
            )
        }

        let deadline = Date().addingTimeInterval(180)
        while Date() < deadline {
            try? await Task.sleep(for: .milliseconds(200))
            let snapshot = await MainActor.run {
                (
                    running: viewModel.isRunning,
                    success: viewModel.didSucceed,
                    status: viewModel.statusMessage,
                    markdownCount: viewModel.markdownCount,
                    chapterCount: viewModel.chapterCount,
                    output: viewModel.outputURL?.path,
                    error: viewModel.errorMessage,
                    log: viewModel.logText
                )
            }
            if !snapshot.running {
                let payload: [String: Any] = [
                    "success": snapshot.success,
                    "status": snapshot.status,
                    "markdown_count": snapshot.markdownCount,
                    "chapter_count": snapshot.chapterCount,
                    "output": snapshot.output ?? "",
                    "error": snapshot.error ?? "",
                    "log_received": !snapshot.log.isEmpty,
                ]
                let data = try! JSONSerialization.data(
                    withJSONObject: payload,
                    options: [.prettyPrinted, .sortedKeys]
                )
                print(String(data: data, encoding: .utf8)!)
                exit(snapshot.success ? 0 : 1)
            }
        }
        print("{\"success\":false,\"error\":\"integration timeout\"}")
        exit(3)
    }
}
