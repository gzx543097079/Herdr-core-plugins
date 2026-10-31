import AppKit

/// 圆角色块：NSBox 的颜色是动态色，切换深浅色时自动更新。
func tinted(_ color: NSColor, radius: CGFloat, alpha: CGFloat = 0.14) -> NSBox {
    let box = NSBox(); box.boxType = .custom; box.borderWidth = 0; box.cornerRadius = radius
    box.fillColor = color.withAlphaComponent(alpha); box.contentViewMargins = .zero; box.titlePosition = .noTitle
    box.translatesAutoresizingMaskIntoConstraints = false
    return box
}

func label(_ text: String, size: CGFloat = 13, weight: NSFont.Weight = .regular, color: NSColor = .labelColor) -> NSTextField {
    let field = NSTextField(labelWithString: text)
    field.font = .systemFont(ofSize: size, weight: weight); field.textColor = color
    field.lineBreakMode = .byTruncatingTail; field.maximumNumberOfLines = 1
    field.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
    return field
}

/// 状态胶囊：小圆点 + 文字。
final class Pill: NSView {
    private let box = tinted(.secondaryLabelColor, radius: 9)
    private let dot = tinted(.secondaryLabelColor, radius: 3, alpha: 1)
    private let text = label("", size: 11, weight: .medium)
    init() {
        super.init(frame: .zero); translatesAutoresizingMaskIntoConstraints = false
        addSubview(box); box.addSubview(dot); box.addSubview(text)
        text.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([
            box.leadingAnchor.constraint(equalTo: leadingAnchor), box.trailingAnchor.constraint(equalTo: trailingAnchor),
            box.topAnchor.constraint(equalTo: topAnchor), box.bottomAnchor.constraint(equalTo: bottomAnchor),
            box.heightAnchor.constraint(equalToConstant: 20),
            dot.widthAnchor.constraint(equalToConstant: 6), dot.heightAnchor.constraint(equalToConstant: 6),
            dot.leadingAnchor.constraint(equalTo: box.leadingAnchor, constant: 8), dot.centerYAnchor.constraint(equalTo: box.centerYAnchor),
            text.leadingAnchor.constraint(equalTo: dot.trailingAnchor, constant: 6),
            text.trailingAnchor.constraint(equalTo: box.trailingAnchor, constant: -9),
            text.centerYAnchor.constraint(equalTo: box.centerYAnchor),
        ])
        setContentHuggingPriority(.required, for: .horizontal)
    }
    required init?(coder: NSCoder) { nil }
    func set(_ value: String, _ color: NSColor) {
        text.stringValue = value; text.textColor = color == .secondaryLabelColor ? .secondaryLabelColor : color
        box.fillColor = color.withAlphaComponent(color == .secondaryLabelColor ? 0.1 : 0.13); dot.fillColor = color
    }
}

struct Plugin { let id: String; let name: String; let detail: String; let symbol: String; let tint: NSColor }

final class Row {
    let view = NSStackView()
    let pill = Pill()
    let spinner = NSProgressIndicator()
    let remove: NSButton
    let install: NSButton
    init(_ plugin: Plugin, index: Int, target: AnyObject, action: Selector) {
        let tile = tinted(plugin.tint, radius: 8)
        let icon = NSImageView(image: NSImage(systemSymbolName: plugin.symbol, accessibilityDescription: plugin.name) ?? NSImage())
        icon.symbolConfiguration = .init(pointSize: 15, weight: .medium); icon.contentTintColor = plugin.tint
        icon.translatesAutoresizingMaskIntoConstraints = false; tile.addSubview(icon)
        NSLayoutConstraint.activate([tile.widthAnchor.constraint(equalToConstant: 34), tile.heightAnchor.constraint(equalToConstant: 34),
                                     icon.centerXAnchor.constraint(equalTo: tile.centerXAnchor), icon.centerYAnchor.constraint(equalTo: tile.centerYAnchor)])
        let title = NSStackView(views: [label(plugin.name, size: 13, weight: .semibold), pill]); title.spacing = 8
        let desc = label(plugin.detail, size: 12, color: .secondaryLabelColor)
        let text = NSStackView(views: [title, desc]); text.orientation = .vertical; text.alignment = .leading; text.spacing = 3
        text.setContentHuggingPriority(.defaultLow, for: .horizontal)
        text.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        remove = NSButton(title: "卸载", target: target, action: action); remove.tag = index * 2
        remove.bezelStyle = .rounded; remove.controlSize = .regular
        install = NSButton(title: "注入", target: target, action: action); install.tag = index * 2 + 1
        install.bezelStyle = .rounded; install.controlSize = .regular
        install.widthAnchor.constraint(greaterThanOrEqualToConstant: 84).isActive = true
        spinner.style = .spinning; spinner.controlSize = .small; spinner.isDisplayedWhenStopped = false
        for view in [remove, install, spinner] as [NSView] { view.setContentHuggingPriority(.required, for: .horizontal) }
        view.setViews([tile, text, spinner, remove, install], in: .leading)
        view.spacing = 12; view.alignment = .centerY
        view.edgeInsets = NSEdgeInsets(top: 12, left: 14, bottom: 12, right: 14)
        view.setCustomSpacing(14, after: tile)
        view.setHuggingPriority(.defaultLow, for: .horizontal)
    }
}

final class PluginManager: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var rows: [String: Row] = [:]
    let connection = Pill()
    let refresh = NSButton()
    let message = label("正在读取 Herdr 状态…", size: 12, color: .secondaryLabelColor)
    let logToggle = NSButton()
    let logContainer = NSScrollView()
    let log = NSTextView()
    let plugins = [
        Plugin(id: "history", name: "对话历史", detail: "按文件夹浏览 Claude / Codex 记录，双击恢复对话", symbol: "clock.arrow.circlepath", tint: .systemBlue),
        Plugin(id: "motion", name: "桌面动效", detail: "原生轻量过渡，加快文件和改动列表的读取与绘制", symbol: "sparkles", tint: .systemPurple),
        Plugin(id: "language", name: "简体中文", detail: "工作区、设置、命令面板等界面显示简体中文", symbol: "character.bubble", tint: .systemOrange),
        Plugin(id: "commands", name: "命令提示", detail: "底部紧凑命令提示，切换 Claude / Codex，按需展开 Skill", symbol: "command", tint: .systemTeal),
        Plugin(id: "git", name: "Git 工作台", detail: "提交树、差异与 PR，跟随当前终端或固定工作区", symbol: "arrow.triangle.branch", tint: .systemGreen),
    ]
    var busy = false
    var running = false
    var script: String { FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".local/share/herdr-plugins/plugin-manager/server.py").path }

    func applicationDidFinishLaunching(_ note: Notification) {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 640, height: 560),
                          styleMask: [.titled, .closable, .miniaturizable, .fullSizeContentView], backing: .buffered, defer: false)
        window.title = "Herdr 插件管理"; window.titleVisibility = .hidden; window.titlebarAppearsTransparent = true
        window.isMovableByWindowBackground = true; window.isReleasedWhenClosed = false

        let root = NSStackView(); root.orientation = .vertical; root.alignment = .leading; root.spacing = 0
        root.edgeInsets = NSEdgeInsets(top: 44, left: 24, bottom: 20, right: 24)
        window.contentView = root
        let width = { (view: NSView) in view.widthAnchor.constraint(equalTo: root.widthAnchor, constant: -48).isActive = true }

        // 标题区
        let titles = NSStackView(views: [label("Herdr 插件", size: 20, weight: .bold),
                                         label("单独注入、重新注入或卸载，其他已启用的插件不受影响。", size: 12, color: .secondaryLabelColor)])
        titles.orientation = .vertical; titles.alignment = .leading; titles.spacing = 4
        titles.setContentHuggingPriority(.defaultLow, for: .horizontal)
        refresh.image = NSImage(systemSymbolName: "arrow.clockwise", accessibilityDescription: "刷新状态")
        refresh.bezelStyle = .rounded; refresh.title = ""; refresh.toolTip = "刷新状态"
        refresh.target = self; refresh.action = #selector(refreshState)
        connection.set("正在连接", .secondaryLabelColor)
        let header = NSStackView(views: [titles, connection, refresh]); header.alignment = .centerY; header.spacing = 10
        root.addArrangedSubview(header); width(header)
        root.setCustomSpacing(20, after: header)

        // 插件列表：一个分组容器，行之间是缩进分隔线（系统设置的样式）
        let group = NSBox(); group.boxType = .custom; group.cornerRadius = 10; group.borderWidth = 1
        group.borderColor = .separatorColor; group.fillColor = .controlBackgroundColor; group.contentViewMargins = .zero; group.titlePosition = .noTitle
        let list = NSStackView(); list.orientation = .vertical; list.spacing = 0; list.alignment = .leading
        list.translatesAutoresizingMaskIntoConstraints = false
        group.contentView = NSView(); group.contentView!.addSubview(list)
        NSLayoutConstraint.activate([list.leadingAnchor.constraint(equalTo: group.contentView!.leadingAnchor),
                                     list.trailingAnchor.constraint(equalTo: group.contentView!.trailingAnchor),
                                     list.topAnchor.constraint(equalTo: group.contentView!.topAnchor),
                                     list.bottomAnchor.constraint(equalTo: group.contentView!.bottomAnchor)])
        for (index, plugin) in plugins.enumerated() {
            let row = Row(plugin, index: index, target: self, action: #selector(operate(_:))); rows[plugin.id] = row
            row.pill.set("读取中", .secondaryLabelColor); row.remove.isHidden = true; row.install.isEnabled = false
            list.addArrangedSubview(row.view); row.view.widthAnchor.constraint(equalTo: list.widthAnchor).isActive = true
            if index < plugins.count - 1 {
                let line = NSBox(); line.boxType = .separator; list.addArrangedSubview(line)
                line.leadingAnchor.constraint(equalTo: list.leadingAnchor, constant: 62).isActive = true
                line.trailingAnchor.constraint(equalTo: list.trailingAnchor).isActive = true
            }
        }
        root.addArrangedSubview(group); width(group)
        root.setCustomSpacing(14, after: group)

        // 状态与日志
        logToggle.title = "显示日志"; logToggle.bezelStyle = .inline; logToggle.controlSize = .small
        logToggle.target = self; logToggle.action = #selector(toggleLog)
        message.setContentHuggingPriority(.defaultLow, for: .horizontal)
        let footer = NSStackView(views: [message, logToggle]); footer.alignment = .centerY
        root.addArrangedSubview(footer); width(footer)
        root.setCustomSpacing(10, after: footer)
        log.isEditable = false; log.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        log.textColor = .secondaryLabelColor; log.textContainerInset = NSSize(width: 8, height: 8); log.string = "暂无操作。"
        log.isVerticallyResizable = true; log.autoresizingMask = [.width]
        logContainer.documentView = log; logContainer.hasVerticalScroller = true; logContainer.borderType = .bezelBorder
        logContainer.isHidden = true
        root.addArrangedSubview(logContainer); width(logContainer)
        logContainer.heightAnchor.constraint(equalToConstant: 120).isActive = true

        // 宽度固定为 640，高度按内容计算，避免说明文字被压缩截断。
        let fixedWidth = root.widthAnchor.constraint(equalToConstant: 640); fixedWidth.priority = .defaultHigh; fixedWidth.isActive = true
        root.layoutSubtreeIfNeeded()
        window.setContentSize(NSSize(width: 640, height: root.fittingSize.height))
        window.center(); window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
        refreshState()
    }

    @objc func toggleLog() { setLog(visible: logContainer.isHidden) }
    func setLog(visible: Bool) {
        guard logContainer.isHidden == visible else { return }
        logContainer.isHidden = !visible; logToggle.title = visible ? "隐藏日志" : "显示日志"
        var frame = window.frame; let delta: CGFloat = visible ? 130 : -130
        frame.size.height += delta; frame.origin.y -= delta
        window.setFrame(frame, display: true, animate: true)
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
        running = state["running"] as? Bool ?? false
        connection.set(running ? "Herdr 已连接" : "Herdr 未运行", running ? .systemGreen : .secondaryLabelColor)
        for plugin in plugins {
            guard let row = rows[plugin.id] else { continue }
            let on = active[plugin.id] ?? false
            row.pill.set(running ? (on ? "已启用" : "未启用") : "未知", on && running ? .systemGreen : .secondaryLabelColor)
            row.remove.isHidden = !(running && on); row.remove.isEnabled = !busy
            row.install.title = on ? "重新注入" : "注入"
            row.install.bezelColor = on ? nil : .controlAccentColor
            row.install.keyEquivalent = ""
            row.install.isEnabled = running && !busy
        }
        refresh.isEnabled = !busy
        if !running { message.stringValue = "请先打开 Herdr，然后点击右上角刷新。" }
    }

    @objc func refreshState() {
        guard !busy else { return }
        refresh.isEnabled = false
        execute(["--status"]) { _, text in
            self.refresh.isEnabled = true
            if let data = text.data(using: .utf8), let value = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                self.render(value)
                if self.running { self.message.stringValue = "卸载插件不会删除对话记录，也不会修改 Herdr 应用本身。" }
            } else {
                self.connection.set("读取失败", .systemRed)
                self.message.stringValue = "读取状态失败，详见日志。"; self.log.string = text; self.setLog(visible: true)
            }
        }
    }

    @objc func operate(_ button: NSButton) {
        guard !busy else { return }
        let plugin = plugins[button.tag / 2], action = button.tag % 2 == 0 ? "uninstall" : "install"
        busy = true
        for row in rows.values { row.install.isEnabled = false; row.remove.isEnabled = false }
        refresh.isEnabled = false
        rows[plugin.id]?.spinner.startAnimation(nil)
        message.stringValue = (action == "install" ? "正在注入「" : "正在卸载「") + plugin.name + "」…"
        execute(["--action", plugin.id, action]) { code, text in
            self.busy = false; self.rows[plugin.id]?.spinner.stopAnimation(nil)
            if code == 0, let data = text.data(using: .utf8), let value = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                self.message.stringValue = value["message"] as? String ?? "操作完成"
                self.log.string = value["log"] as? String ?? text
                self.render(value["status"] as? [String: Any] ?? [:])
            } else {
                self.message.stringValue = "「" + plugin.name + "」操作失败，日志已展开。"
                self.log.string = text; self.setLog(visible: true)
                self.refreshState()
            }
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

let app = NSApplication.shared
app.setActivationPolicy(.regular)
let delegate = PluginManager(); app.delegate = delegate
app.run()
