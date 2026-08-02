import Foundation

enum BackendLocatorError: LocalizedError {
    case runtimeNotFound

    var errorDescription: String? {
        switch self {
        case .runtimeNotFound:
            return "找不到应用内 Python 后端。请重新安装应用，或联系开发者查看打包日志。"
        }
    }
}

struct BackendRuntime {
    let pythonURL: URL
    let environment: [String: String]
}

enum BackendLocator {
    static func locate() throws -> BackendRuntime {
        let fileManager = FileManager.default
        var environment = ProcessInfo.processInfo.environment

        if let resourceURL = Bundle.main.resourceURL {
            let bundledPython = resourceURL
                .appendingPathComponent("runtime", isDirectory: true)
                .appendingPathComponent("python", isDirectory: true)
                .appendingPathComponent("bin", isDirectory: true)
                .appendingPathComponent("python3.12")
            if fileManager.isExecutableFile(atPath: bundledPython.path) {
                let sitePackages = resourceURL
                    .appendingPathComponent("runtime", isDirectory: true)
                    .appendingPathComponent("site-packages", isDirectory: true)
                environment["PYTHONPATH"] = sitePackages.path
                environment["PYTHONUNBUFFERED"] = "1"
                environment["PYTHONDONTWRITEBYTECODE"] = "1"
                return BackendRuntime(pythonURL: bundledPython, environment: environment)
            }

            let developmentRootFile = resourceURL.appendingPathComponent("development-project-root.txt")
            if let root = try? String(contentsOf: developmentRootFile, encoding: .utf8)
                .trimmingCharacters(in: .whitespacesAndNewlines),
               !root.isEmpty {
                let python = URL(fileURLWithPath: root)
                    .appendingPathComponent(".venv/bin/python")
                if fileManager.isExecutableFile(atPath: python.path) {
                    environment["PYTHONUNBUFFERED"] = "1"
                    return BackendRuntime(pythonURL: python, environment: environment)
                }
            }
        }

        if let root = environment["PDF2MD_PROJECT_ROOT"] {
            let python = URL(fileURLWithPath: root).appendingPathComponent(".venv/bin/python")
            if fileManager.isExecutableFile(atPath: python.path) {
                environment["PYTHONUNBUFFERED"] = "1"
                return BackendRuntime(pythonURL: python, environment: environment)
            }
        }

        let currentRoot = URL(fileURLWithPath: fileManager.currentDirectoryPath)
        let currentPython = currentRoot.appendingPathComponent(".venv/bin/python")
        if fileManager.isExecutableFile(atPath: currentPython.path) {
            environment["PYTHONUNBUFFERED"] = "1"
            return BackendRuntime(pythonURL: currentPython, environment: environment)
        }
        throw BackendLocatorError.runtimeNotFound
    }
}
