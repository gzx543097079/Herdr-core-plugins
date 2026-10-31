# Herdr

Herdr 桌面端插件集合。

## 插件

### Agent History

`agent-history/` 用于检索本机 Claude Code 和 Codex 的对话历史：

- Claude 和 Codex 分开显示，并使用对应图标
- 按项目文件夹分组，支持折叠和展开
- 支持按智能体、项目路径和对话标题搜索
- 双击记录，在新的 Herdr 标签页中恢复对话
- 只读取本机记录，不上传对话内容

安装方式：打开 Herdr 后，双击 [`agent-history/安装插件.command`](agent-history/安装插件.command)。

### Herdr Lang

`Herdr/` 是桌面端简体中文语言插件。安装说明见 [`Herdr/使用说明.txt`](Herdr/使用说明.txt)。

## 本地数据来源

- Claude Code：`~/.claude/projects`
- Codex：`~/.codex/sessions`

## 开源协议

本项目采用 [MIT License](LICENSE)。
