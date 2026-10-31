# Herdr 插件布局

基于 Herdr 官方 Layout 和 Mod 机制的 macOS 布局，包含对话历史、桌面动效、工作区中文、命令提示和 Git 工作台。插件开关位于左下角「设置」行最右侧。

## 安装

在安装并启动 Herdr 的 Mac 上，把下面的指令交给 Claude Code 或 Codex：

```text
Read ~/.config/herdr-app/AGENTS.md, then add this layout: https://github.com/gzx543097079/Herdr-core-plugins/tree/main/layouts/herdr-plugins
```

Agent 会根据本机 Herdr 指南读取 [布局配方](layouts/herdr-plugins/RECIPE.md)和包内文件，将布局与 Mod 复制到 Herdr 配置目录，检查并切换布局。遇到同名布局或 Mod 时，应先处理名称冲突，不覆盖现有文件。

这个布局会运行本地程序、读取和删除本机历史记录，Git 工作台可使用 `gh` 访问 GitHub。安装前请阅读配方中的依赖、限制和数据行为。对话历史只显示当前电脑的记录；工作区中文不修改 Herdr 设置页等 frame。

布局针对 macOS 和 Herdr 0.1.10 构建。当前配色为浅色，暗色外观尚未适配；其他版本需要先验证官方组件兼容性。

## 开源协议

[MIT License](LICENSE)。
