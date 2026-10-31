# Herdr 插件组合配方

此仓库为现有 Herdr 布局组合本地 Mod，保留用户原有布局。安装前请阅读本机 `~/.config/herdr-app/AGENTS.md`，以当前 Herdr 版本的 API 和布局格式为准。

## 组成

- `agent-history/`：对话历史面板和本地历史读取脚本。
- `desktop-motion/`：基于当前布局的原生过渡与列表优化。
- `command-hints/`：底部命令提示及状态栏入口。
- `git-workbench/`：只读 Git 工作台及面板入口。
- `Herdr/`：简体中文支持。
- `plugin-manager/`：插件组合管理器。

## 重建与验证

1. 安装并启动 Herdr，确认 `~/.local/bin/herdr-app status` 正常返回。
2. 使用各插件目录中的安装命令启用需要的功能。管理器依次建立派生布局，并保留原布局。
3. 通过 `herdr-app status` 检查当前布局和错误；各安装器使用 `herdr-app check` 验证生成的 Mod。
4. 使用各插件目录中的卸载命令关闭功能。对话历史卸载不删除对话记录。

这是基于本机 Herdr 主布局生成的组合，不是固定的可直接导入 Layout 包；启用语言插件会改写生成的 frame 文案。发布到 Herdr Layouts 前，还需按官方格式准备 `layouts/<name>.json`、`mods/` 和实际运行截图 `preview.png`，并在干净安装中验证。
