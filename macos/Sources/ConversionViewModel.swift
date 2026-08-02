import AppKit
import Foundation

struct ConversionOptions {
    let inputPDF: URL
    let outputDirectory: URL
    let overwrite: Bool
    let useAI: Bool
    let aiModel: String
    let aiBaseURL: String
    let apiKey: String
    let automaticallyOpenOutput: Bool
}

private final class LineStreamReader: @unchecked Sendable {
    private let handle: FileHandle
    private let queue: DispatchQueue
    private var buffer = Data()
    private let onLine: @Sendable (String) -> Void

    init(handle: FileHandle, label: String, onLine: @escaping @Sendable (String) -> Void) {
        self.handle = handle
        self.queue = DispatchQueue(label: label)
        self.onLine = onLine
        handle.readabilityHandler = { [weak self] readableHandle in
            let data = readableHandle.availableData
            guard let self else { return }
            self.queue.async {
                self.consume(data)
            }
        }
    }

    private func consume(_ data: Data) {
        if data.isEmpty {
            flush()
            handle.readabilityHandler = nil
            return
        }
        buffer.append(data)
        while let newline = buffer.firstIndex(of: 0x0A) {
            let lineData = buffer[..<newline]
            buffer.removeSubrange(...newline)
            if let line = String(data: lineData, encoding: .utf8) {
                onLine(line)
            }
        }
    }

    private func flush() {
        guard !buffer.isEmpty else { return }
        if let line = String(data: buffer, encoding: .utf8) {
            onLine(line)
        }
        buffer.removeAll()
    }
}

@MainActor
final class ConversionViewModel: ObservableObject {
    @Published var selectedPDF: URL?
    @Published var outputParent: URL?
    @Published var statusMessage = "等待选择 PDF"
    @Published var isRunning = false
    @Published var isDropTargeted = false
    @Published var markdownCount = 0
    @Published var chapterCount = 0
    @Published var outputURL: URL?
    @Published var logPath: URL?
    @Published var logText = ""
    @Published var errorMessage: String?
    @Published var didSucceed = false
    @Published var developerDiagnostics: [String: String] = [:]

    private var process: Process?
    private var stdoutReader: LineStreamReader?
    private var stderrReader: LineStreamReader?
    private var receivedTerminalEvent = false
    private var optionsForCurrentRun: ConversionOptions?

    var proposedOutputURL: URL? {
        guard let selectedPDF, let outputParent else { return nil }
        let stem = selectedPDF.deletingPathExtension().lastPathComponent
        return outputParent.appendingPathComponent("\(stem)-Markdown", isDirectory: true)
    }

    var canStart: Bool {
        selectedPDF != nil && outputParent != nil && !isRunning
    }

    func selectPDF(_ url: URL) {
        guard url.pathExtension.lowercased() == "pdf" else {
            errorMessage = "请选择 PDF 文件。"
            return
        }
        selectedPDF = url
        statusMessage = "已选择 PDF"
        errorMessage = nil
        didSucceed = false
    }

    func choosePDF() {
        let panel = NSOpenPanel()
        panel.title = "选择扫描版 PDF"
        panel.allowedContentTypes = [.pdf]
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            selectPDF(url)
        }
    }

    func chooseOutputDirectory() {
        let panel = NSOpenPanel()
        panel.title = "选择输出位置"
        panel.prompt = "选择"
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.canCreateDirectories = true
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            outputParent = url
            errorMessage = nil
        }
    }

    func start(_ options: ConversionOptions) {
        guard !isRunning else { return }
        if options.useAI {
            guard !options.aiModel.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                errorMessage = "启用 AI 清洗时必须填写模型名称。"
                return
            }
            guard !options.apiKey.isEmpty else {
                errorMessage = "启用 AI 清洗时必须填写 API 密钥。"
                return
            }
            do {
                try KeychainStore.saveAPIKey(options.apiKey)
            } catch {
                errorMessage = error.localizedDescription
                return
            }
        }

        resetForRun()
        optionsForCurrentRun = options
        do {
            let runtime = try BackendLocator.locate()
            let task = Process()
            let stdoutPipe = Pipe()
            let stderrPipe = Pipe()
            var arguments = [
                "-m", "pdf_to_md.gui_backend",
                options.inputPDF.path,
                "--output", options.outputDirectory.path,
                "--model-source", "modelscope",
                "--resume",
            ]
            if options.overwrite {
                arguments.append("--overwrite")
            }
            if options.useAI {
                arguments.append("--use-ai")
                arguments += ["--ai-model", options.aiModel]
                if !options.aiBaseURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    arguments += ["--ai-base-url", options.aiBaseURL]
                }
            } else {
                arguments.append("--no-ai")
            }

            var environment = runtime.environment
            if options.useAI {
                environment["PDF2MD_AI_API_KEY"] = options.apiKey
            }
            task.executableURL = runtime.pythonURL
            task.arguments = arguments
            task.environment = environment
            task.standardOutput = stdoutPipe
            task.standardError = stderrPipe

            stdoutReader = LineStreamReader(
                handle: stdoutPipe.fileHandleForReading,
                label: "com.local.PDFToMarkdown.stdout"
            ) { [weak self] line in
                Task { @MainActor in
                    self?.handleJSONLine(line)
                }
            }
            stderrReader = LineStreamReader(
                handle: stderrPipe.fileHandleForReading,
                label: "com.local.PDFToMarkdown.stderr"
            ) { [weak self] line in
                Task { @MainActor in
                    self?.appendLog(line)
                }
            }
            task.terminationHandler = { [weak self] finishedTask in
                Task { @MainActor in
                    self?.handleTermination(exitCode: finishedTask.terminationStatus)
                }
            }
            process = task
            isRunning = true
            statusMessage = "正在启动转换"
            try task.run()
        } catch {
            isRunning = false
            statusMessage = "转换失败"
            errorMessage = error.localizedDescription
            appendLog("启动失败：\(error.localizedDescription)")
        }
    }

    func cancel() {
        guard let process, process.isRunning else { return }
        process.terminate()
        statusMessage = "正在停止"
    }

    func revealOutput() {
        guard let outputURL else { return }
        NSWorkspace.shared.open(outputURL)
    }

    func openLog() {
        guard let logPath else { return }
        NSWorkspace.shared.open(logPath)
    }

    private func resetForRun() {
        errorMessage = nil
        logText = ""
        markdownCount = 0
        chapterCount = 0
        outputURL = nil
        logPath = nil
        developerDiagnostics = [:]
        didSucceed = false
        receivedTerminalEvent = false
    }

    private func handleJSONLine(_ line: String) {
        guard let data = line.data(using: .utf8),
              let event = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = event["type"] as? String else {
            appendLog("无法解析后端事件：\(line)")
            return
        }
        switch type {
        case "model_info":
            let labels: [(String, String)] = [
                ("模型类型", "model_type"), ("模型名称", "model_name"),
                ("模型源", "model_source"), ("模型路径", "model_path"),
                ("路径状态", "model_path_status"), ("CLI 路径", "mineru_cli_path"),
                ("Python 路径", "python_path"), ("接口地址", "base_url"),
                ("backend", "backend"), ("method", "method"),
                ("language", "language"), ("页数", "page_count"),
                ("超时秒数", "timeout_seconds"), ("处理窗口", "processing_window_size"),
                ("temperature", "temperature"), ("响应格式", "response_format"),
                ("API 密钥", "api_key")
            ]
            for (label, key) in labels {
                if let value = event[key] {
                    developerDiagnostics[label] = String(describing: value)
                }
            }
        case "progress":
            if let message = event["message"] as? String {
                statusMessage = message
            }
            if let segment = event["segment"] as? Int,
               let segmentCount = event["segment_count"] as? Int,
               let startPage = event["start_page"] as? Int,
               let endPage = event["end_page"] as? Int {
                statusMessage = "第 \(segment)/\(segmentCount) 段：第 \(startPage)-\(endPage) 页"
            }
            if let count = event["markdown_count"] as? Int {
                markdownCount = count
            }
        case "result":
            receivedTerminalEvent = true
            markdownCount = event["markdown_count"] as? Int ?? 0
            chapterCount = event["chapter_count"] as? Int ?? 0
            if let path = event["output_dir"] as? String {
                outputURL = URL(fileURLWithPath: path)
            }
            if let path = event["log_path"] as? String {
                logPath = URL(fileURLWithPath: path)
            }
            didSucceed = true
            statusMessage = "已完成"
            isRunning = false
            if optionsForCurrentRun?.automaticallyOpenOutput == true, let outputURL {
                NSWorkspace.shared.open(outputURL)
            }
        case "error":
            receivedTerminalEvent = true
            let message = event["message"] as? String ?? "后端返回未知错误。"
            errorMessage = message
            statusMessage = "转换失败"
            isRunning = false
            appendLog(message)
        default:
            appendLog("未知后端事件：\(line)")
        }
    }

    private func handleTermination(exitCode: Int32) {
        isRunning = false
        process = nil
        stdoutReader = nil
        stderrReader = nil
        if exitCode != 0 && !receivedTerminalEvent {
            statusMessage = "转换失败"
            errorMessage = "转换进程异常退出（代码 \(exitCode)）。请查看下方日志。"
        }
    }

    private func appendLog(_ line: String) {
        let newText = logText.isEmpty ? line : "\(logText)\n\(line)"
        logText = String(newText.suffix(120_000))
    }
}
