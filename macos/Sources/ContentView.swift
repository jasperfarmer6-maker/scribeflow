import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @StateObject private var viewModel = ConversionViewModel()
    @AppStorage("useAI") private var useAI = false
    @AppStorage("aiModel") private var aiModel = ""
    @AppStorage("aiBaseURL") private var aiBaseURL = ""
    @AppStorage("overwriteOutput") private var overwriteOutput = false
    @AppStorage("developerMode") private var developerMode = false
    @State private var apiKey = ""
    @State private var showAdvanced = false

    var body: some View {
        VStack(spacing: 18) {
            header
            dropZone
            outputSection
            optionsSection
            actionSection
            statusSection
            Spacer(minLength: 0)
        }
        .padding(24)
        .onAppear {
            apiKey = KeychainStore.loadAPIKey()
        }
    }

    private var header: some View {
        HStack(spacing: 14) {
            Image(systemName: "doc.text.magnifyingglass")
                .font(.system(size: 34))
                .foregroundStyle(Color.accentColor)
            VStack(alignment: .leading, spacing: 3) {
                Text("ScribeFlow")
                    .font(.title2.bold())
                Text("扫描件 OCR、保真清洗、按章节输出")
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
    }

    private var dropZone: some View {
        VStack(spacing: 12) {
            Image(systemName: viewModel.selectedPDF == nil ? "arrow.down.doc" : "doc.fill")
                .font(.system(size: 40))
                .foregroundStyle(viewModel.isDropTargeted ? Color.accentColor : .secondary)
            if let pdf = viewModel.selectedPDF {
                Text(pdf.lastPathComponent)
                    .font(.headline)
                    .lineLimit(1)
                Text(pdf.deletingLastPathComponent().path)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            } else {
                Text("将扫描版 PDF 拖到这里")
                    .font(.headline)
                Text("或者点击下方按钮选择文件")
                    .foregroundStyle(.secondary)
            }
            Button("选择 PDF…") {
                viewModel.choosePDF()
            }
            .disabled(viewModel.isRunning)
        }
        .frame(maxWidth: .infinity, minHeight: 170)
        .background(
            RoundedRectangle(cornerRadius: 14)
                .fill(viewModel.isDropTargeted ? Color.accentColor.opacity(0.10) : Color.secondary.opacity(0.06))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(
                    viewModel.isDropTargeted ? Color.accentColor : Color.secondary.opacity(0.35),
                    style: StrokeStyle(lineWidth: 2, dash: [8])
                )
        )
        .dropDestination(for: URL.self) { urls, _ in
            guard let pdf = urls.first(where: { $0.pathExtension.lowercased() == "pdf" }) else {
                return false
            }
            viewModel.selectPDF(pdf)
            return true
        } isTargeted: { targeted in
            viewModel.isDropTargeted = targeted
        }
    }

    private var outputSection: some View {
        GroupBox("输出位置") {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(viewModel.outputParent?.path ?? "尚未选择")
                        .lineLimit(1)
                    if let target = viewModel.proposedOutputURL {
                        Text("将生成：\(target.lastPathComponent)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                Spacer()
                Button("选择文件夹…") {
                    viewModel.chooseOutputDirectory()
                }
                .disabled(viewModel.isRunning)
            }
            .padding(.vertical, 4)
        }
    }

    private var optionsSection: some View {
        GroupBox {
            DisclosureGroup("转换设置", isExpanded: $showAdvanced) {
                VStack(alignment: .leading, spacing: 12) {
                    Toggle("覆盖同名的既有转换结果", isOn: $overwriteOutput)
                    Toggle("使用 AI 清洗格式（不改写正文）", isOn: $useAI)
                    Toggle("开发者模式（显示实时模型诊断）", isOn: $developerMode)
                    if useAI {
                        TextField("模型名称，例如 gpt-4.1-mini", text: $aiModel)
                        TextField("兼容接口地址（使用 OpenAI 默认接口时留空）", text: $aiBaseURL)
                        SecureField("API 密钥（保存到 macOS 钥匙串）", text: $apiKey)
                    }
                }
                .padding(.top, 10)
            }
        }
    }

    private var actionSection: some View {
        HStack {
            if viewModel.isRunning {
                Button("停止", role: .destructive) {
                    viewModel.cancel()
                }
            }
            Spacer()
            Button {
                guard let input = viewModel.selectedPDF,
                      let output = viewModel.proposedOutputURL else { return }
                viewModel.start(
                    ConversionOptions(
                        inputPDF: input,
                        outputDirectory: output,
                        overwrite: overwriteOutput,
                        useAI: useAI,
                        aiModel: aiModel,
                        aiBaseURL: aiBaseURL,
                        apiKey: apiKey,
                        automaticallyOpenOutput: true
                    )
                )
            } label: {
                Label("开始转换", systemImage: "play.fill")
                    .frame(minWidth: 120)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(!viewModel.canStart)
        }
    }

    private var statusSection: some View {
        GroupBox("处理状态") {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    if viewModel.isRunning {
                        ProgressView()
                            .controlSize(.small)
                    } else {
                        Image(systemName: viewModel.didSucceed ? "checkmark.circle.fill" : "circle")
                            .foregroundStyle(viewModel.didSucceed ? .green : .secondary)
                    }
                    Text(viewModel.statusMessage)
                        .font(.headline)
                    Spacer()
                    if viewModel.didSucceed {
                        Text("生成 \(viewModel.markdownCount) 个 Markdown")
                            .foregroundStyle(.secondary)
                    }
                }

                if let error = viewModel.errorMessage {
                    Text(error)
                        .foregroundStyle(.red)
                        .textSelection(.enabled)
                }

                if developerMode && !viewModel.developerDiagnostics.isEmpty {
                    developerPanel
                }

                if !viewModel.logText.isEmpty {
                    ScrollView {
                        Text(viewModel.logText)
                            .font(.system(.caption, design: .monospaced))
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .textSelection(.enabled)
                    }
                    .frame(minHeight: 80, maxHeight: 150)
                    .padding(8)
                    .background(Color.black.opacity(0.04))
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                }

                if viewModel.didSucceed {
                    HStack {
                        Button("打开输出文件夹") {
                            viewModel.revealOutput()
                        }
                        if viewModel.logPath != nil {
                            Button("查看日志") {
                                viewModel.openLog()
                            }
                        }
                        Spacer()
                        Text("章节：\(viewModel.chapterCount)")
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .padding(.vertical, 4)
        }
    }

    private var developerPanel: some View {
        DisclosureGroup("开发者诊断") {
            VStack(alignment: .leading, spacing: 5) {
                ForEach(viewModel.developerDiagnostics.keys.sorted(), id: \.self) { key in
                    if let value = viewModel.developerDiagnostics[key] {
                        HStack(alignment: .top) {
                            Text(key).foregroundStyle(.secondary).frame(width: 110, alignment: .leading)
                            Text(value).textSelection(.enabled).font(.system(.caption, design: .monospaced))
                            Spacer()
                        }
                    }
                }
            }
            .padding(.top, 6)
        }
    }
}
