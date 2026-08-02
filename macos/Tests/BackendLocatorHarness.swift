import Darwin
import Foundation

@main
struct BackendLocatorHarness {
    static func main() {
        do {
            let runtime = try BackendLocator.locate()
            let payload = [
                "python": runtime.pythonURL.path,
                "executable": FileManager.default.isExecutableFile(atPath: runtime.pythonURL.path),
                "unbuffered": runtime.environment["PYTHONUNBUFFERED"] == "1",
            ] as [String: Any]
            let data = try! JSONSerialization.data(
                withJSONObject: payload,
                options: [.prettyPrinted, .sortedKeys]
            )
            print(String(data: data, encoding: .utf8)!)
        } catch {
            print(error.localizedDescription)
            exit(1)
        }
    }
}
