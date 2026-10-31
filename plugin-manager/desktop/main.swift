import AppKit

final class PluginManager: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var buttons: [NSButton] = []
    var states: [String: NSTextField] = [:]
    let message = NSTextField(wrappingLabelWithString: "正在读取 Herdr 状态…")
    let log = NSTextView()
    let plugins = [("history", "对话历史", "按文件夹浏览 Claude / Codex 记录，双击恢复对话。"),
                   ("motion", "桌面动效", "原生轻量过渡，优化文件和改动列表的读取、绘制。"),
                   ("language", "简体中文", "恢复工作区、设置、命令面板等界面的简体中文。"),
                   ("commands", "命令提示", "底部紧凑命令提示，切换 Claude / Codex，按需展开 Skill。"),
                   ("git", "Git 工作台", "提交树、差异与 PR，跟随当前终端或固定工作区。") ]
    var busy = false
    var script: String { FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".local/share/herdr-plugins/plugin-manager/server.py").path }
    func label(_ text: String, size: CGFloat = 13, bold: Bool = false) -> NSTextField {
        let field = NSTextField(labelWithString: text)
        field.font = bold ? .boldSystemFont(ofSize: size) : .systemFont(ofSize: size)
        return field
    }
    func applicationDidFinishLaunching(_ note: Notification) {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 780, height: 750), styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
        window.title = "Herdr 插件管理"
        window.isReleasedWhenClosed = false
        let root = NSStackView(); root.orientation = .vertical; root.alignment = .leading; root.spacing = 18
        root.edgeInsets = NSEdgeInsets(top: 26, left: 28, bottom: 24, right: 28)
        window.contentView = root
        let header = NSStackView(views: [label("Herdr 插件管理", size: 23, bold: true)])
        let refresh = NSButton(title: "刷新状态", target: self, action: #selector(refreshState)); buttons.append(refresh)
        header.addArrangedSubview(NSView()); header.addArrangedSubview(refresh)
        root.addArrangedSubview(header); header.widthAnchor.constraint(equalTo: root.widthAnchor, constant: -56).isActive = true
        root.addArrangedSubview(label("单独注入、重新注入或卸载；其他已启用插件会保留。"))
        for (index, item) in plugins.enumerated() {
            let text = NSStackView(); text.orientation = .vertical; text.alignment = .leading; text.spacing = 6
            let state = label(item.1 + " · 正在读取", size: 15, bold: true); states[item.0] = state
            text.addArrangedSubview(state)
            let desc = label(item.2, size: 12); desc.textColor = .secondaryLabelColor; text.addArrangedSubview(desc)
            let remove = NSButton(title: "卸载", target: self, action: #selector(operate(_:))); remove.tag = index * 2
            let install = NSButton(title: "注入插件", target: self, action: #selector(operate(_:))); install.tag = index * 2 + 1
            buttons += [remove, install]
            let row = NSStackView(views: [text, NSView(), remove, install]); row.spacing = 10
            root.addArrangedSubview(row); row.widthAnchor.constraint(equalTo: root.widthAnchor, constant: -56).isActive = true
            row.heightAnchor.constraint(equalToConstant: 62).isActive = true
            let line = NSBox(); line.boxType = .separator; root.addArrangedSubview(line)
            line.widthAnchor.constraint(equalTo: row.widthAnchor).isActive = true
        }
        message.font = .systemFont(ofSize: 12); root.addArrangedSubview(message)
        message.widthAnchor.constraint(equalTo: root.widthAnchor, constant: -56).isActive = true
        let scroll = NSScrollView(); scroll.hasVerticalScroller = true; scroll.borderType = .bezelBorder
        log.isEditable = false; log.font = .monospacedSystemFont(ofSize: 11, weight: .regular); log.string = "操作日志会显示在这里。"
        scroll.documentView = log; root.addArrangedSubview(scroll)
        scroll.widthAnchor.constraint(equalTo: root.widthAnchor, constant: -56).isActive = true
        scroll.heightAnchor.constraint(equalToConstant: 94).isActive = true
        window.center(); window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
        refreshState()
    }
    func execute(_ args: [String], completion: @escaping (Int32, String) -> Void) {
        let path = script
        DispatchQueue.global(qos: .userInitiated).async {
            let process = Process(); let pipe = Pipe()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/python3"); process.arguments = [path] + args
            process.standardOutput = pipe; process.standardError = pipe
            do {
                try process.run()
                let data = pipe.fileHandleForReading.readDataToEndOfFile(); process.waitUntilExit()
                let result = String(data: data, encoding: .utf8) ?? "无法读取结果"
                DispatchQueue.main.async { completion(process.terminationStatus, result) }
            } catch { DispatchQueue.main.async { completion(1, error.localizedDescription) } }
        }
    }
    func render(_ state: [String: Any]) {
        let active = state["plugins"] as? [String: Bool] ?? [:]
        let running = state["running"] as? Bool ?? false
        for (index, item) in plugins.enumerated() {
            let on = active[item.0] ?? false
            states[item.0]?.stringValue = item.1 + (on ? " · 已启用" : " · 未启用")
            let remove = buttons[index * 2 + 1], install = buttons[index * 2 + 2]
            remove.isEnabled = running && on && !busy
            install.isEnabled = running && !busy; install.title = on ? "重新注入" : "注入插件"
        }
        buttons[0].isEnabled = !busy
        if !running { message.stringValue = "请先打开 Herdr，再点击刷新状态。" }
    }
    @objc func refreshState() {
        guard !busy else { return }
        execute(["--status"]) { code, text in
            if let data = text.data(using: .utf8), let value = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                self.render(value)
                if value["running"] as? Bool == true { self.message.stringValue = "Herdr 已连接。卸载插件不会删除对话记录。" }
            } else { self.message.stringValue = "读取失败"; self.log.string = text }
        }
    }
    @objc func operate(_ button: NSButton) {
        guard !busy else { return }
        let item = plugins[button.tag / 2], action = button.tag % 2 == 0 ? "uninstall" : "install"
        busy = true; buttons.forEach { $0.isEnabled = false }
        message.stringValue = "正在" + (action == "install" ? "注入 " : "卸载 ") + item.1 + "…"
        execute(["--action", item.0, action]) { code, text in
            self.busy = false
            if code == 0, let data = text.data(using: .utf8), let value = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                self.message.stringValue = value["message"] as? String ?? "操作完成"
                self.log.string = value["log"] as? String ?? text
                self.render(value["status"] as? [String: Any] ?? [:])
            } else {
                self.message.stringValue = "操作失败，详见日志。"; self.log.string = text
                self.buttons[0].isEnabled = true
            }
        }
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}
let app = NSApplication.shared
app.setActivationPolicy(.regular)
let delegate = PluginManager(); app.delegate = delegate
app.run()
