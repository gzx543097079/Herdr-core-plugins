# Herdr

Herdr 桌面端插件集合。

双击根目录的 [打开插件管理.command](打开插件管理.command)，构建并打开独立的 macOS 应用 **Herdr 插件管理.app**。
也可直接打开已经生成的 app。管理器不嵌入 Herdr 设置，不需要浏览器或本地网页服务。
首次构建需要 Xcode Command Line Tools；插件脚本部署到 `~/.local/share/herdr-plugins/`。

每个插件独立显示状态，提供注入、重新注入、卸载按钮及操作日志。
各目录的安装、卸载 `.command` 与外置管理器使用同一套组合逻辑，卸载一个插件保留其他插件，不删除对话记录。
升级时会移除旧的“设置 → 插件”入口和它的后台任务。
不修改 Herdr 应用包；功能插件使用模块副本及派生布局。汉化另对生成的 frame 界面做可恢复的文字注入，与原版汉化方式一致。

历史面板点击外部会收起；展开为 180ms 的轻移入和淡入，收起为 140ms 的轻移出和淡出。
动画由原生 GPUI 执行，延迟隐藏带状态校验，避免误关闭切换后的文件、改动面板。

## 插件

### Agent History

`agent-history/` 用于检索本机 Claude Code 和 Codex 的对话历史：

- Claude 和 Codex 分开显示，并使用对应图标
- 按项目文件夹分组，只显示文件夹名称，完整路径仍可搜索
- 默认折叠，同时只展开一个文件夹；无分页，连续滚动时只绘制可见行
- 文件、改动和对话历史共用同一个互斥右侧面板
- 支持按智能体、项目路径和对话标题搜索
- 双击记录，在新的 Herdr 标签页中恢复对话
- 删除需再次点击确认（Esc 取消），删除的是本机对话文件，无法恢复
- 只读取本机记录，不上传对话内容

安装方式：打开 Herdr 后，双击 [`agent-history/安装插件.command`](agent-history/安装插件.command)。

### Desktop Motion

`desktop-motion/` 是独立的桌面动效与面板性能插件，可与对话历史插件叠加使用。

- 标签、文件/改动按钮选中状态使用 140ms 原生透明度过渡
- 文件和改动面板由加载态平滑过渡到内容态；不使用全局动画广播或逐帧 JS 计时器
- 文件树与改动文件列表只构建可见行，避免长列表完整渲染
- 文件目录先显示，Git 状态稍后补充；改动列表先显示，差异预览随后加载
- 合并 180ms 内的文件变化通知，避免构建过程反复触发 Git 查询

打开 Herdr 后运行 `python3 desktop-motion/install.py`，或双击
[`desktop-motion/安装插件.command`](desktop-motion/安装插件.command)。
`python3 desktop-motion/install.py --reduce-motion` 关闭过渡，保留性能优化。
恢复安装前布局：`~/.local/bin/herdr-app do layout.switch '{"name":"agent-history-layout"}'`
（独立安装时使用安装输出中的原布局名称）。不会修改官方模块。

### Command Hints

`command-hints/` 是独立的底部命令提示插件，外置管理器中显示为「命令提示」。

- 点击底部状态栏「命令提示」手动展开/收起；新布局默认折叠，Herdr 会记住之后的开关状态
- 跟随当前聚焦终端里运行的 CLI 自动切换 Claude / Codex（绿点标出），也可手动切换；以六个紧凑列展示 24 项常用命令与控制提示，「终端启动」列用于 shell，其余为 CLI 内部命令；点击复制，不自动执行。Ctrl+C 项仅提示手动按键；窄窗口可横向滚动
- 右侧 Skill 默认隐藏，首次展开才读取本地用户/当前项目的 Skill；切换项目后点击刷新加载
- 按项目和 CLI 缓存最多 12 份列表，手动刷新；没有轮询、全盘递归扫描或后台监视
- 每个目录最多检查 500 项，每个文件最多读取 8 KiB；长列表只绘制可见行
- Claude 读取 `.claude/skills`、旧式 `.claude/commands`；Codex 读取 `.agents/skills`、`.codex/skills` 及用户 `.system`，支持链接目录；不扫描插件缓存，列表并非全部市场插件

双击 [`command-hints/安装插件.command`](command-hints/安装插件.command)，或在外置管理器独立注入/卸载。
命令参考：[Claude Code](https://code.claude.com/docs/en/commands)、[Codex CLI](https://developers.openai.com/codex/cli/slash-commands)。可用命令以本机 CLI 版本为准。

### Git 工作台

`git-workbench/` 是独立的只读 Git 工作台插件，外置插件管理器中显示为「Git 工作台」。

- 右上角 Git 按钮打开右侧面板，与文件、改动、对话历史互斥
- 自动跟随当前聚焦终端识别本地 Git 仓库；可切换「固定工作区」保持查看对象
- 支持多个分屏终端：同一仓库复用提交缓存，不同仓库随焦点切换；worktree 分别缓存 HEAD 标记和未提交改动，避免串用分支状态
- 提交树按父提交计算泳道，用曲线连接分叉与合并，HEAD 为空心节点，未提交改动显示在最上方；支持分支/标签筛选、提交搜索、作者搜索、虚拟滚动、提交详情和文件差异（打开提交自动显示第一个文件）
- 分支、标签分为两个页签；标签解析到实际提交，并标出与它同处一个提交的分支末端；分支页显示当前分支、上游、领先 / 落后和上游失效状态；支持查看历史和与 HEAD 对比（状态来自本地引用，不自动 fetch）
- 提交详情可「设为起点」，再选择另一个提交「对比至此」，逐文件查看两次提交之间的变化
- 详情采用左侧文件列表、右侧带行号和彩色增删的差异，可放大查看；PR 文件差异也在面板内按需读取
- PR 文件列表最多显示 300 个文件，单文件补丁最多 200 KB；二进制或 GitHub 未提供的补丁可跳转 GitHub
- PR 记录支持当前分支、全部、我创建的、待我审查、打开、已合并、已关闭筛选；详情显示说明、审查、检查和文件，完整页面可在 GitHub 打开
- 面板关闭时不读取；提交树缓存 30 秒，PR 缓存 60 秒，Git 目录变化合并刷新；详情和差异点击后才读取
- PR 只读 GitHub API，不执行 `git fetch`、提交、切换分支、推送、评论或合并；需要本机 `gh auth login`
- 远程 SSH 终端第一版显示明确提示，避免把远程路径误当成本机仓库；后续可增加远程 core 读取

安装：双击 [`git-workbench/安装插件.command`](git-workbench/安装插件.command)，或在外置插件管理器中单独注入。卸载不会改动仓库。

### Herdr Lang

`Herdr/` 是桌面端简体中文语言插件。安装说明见 [`Herdr/使用说明.txt`](Herdr/使用说明.txt)。

## 本地数据来源

- Claude Code：`~/.claude/projects`
- Codex：`~/.codex/sessions`

## 开源协议

本项目采用 [MIT License](LICENSE)。
