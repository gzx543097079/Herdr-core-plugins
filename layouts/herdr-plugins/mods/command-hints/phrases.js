// 终端里出现的英文文案与中文对照。只做本地匹配，不联网、不改终端内容。
// quiet: 页脚/状态栏这类常驻文案，只在已经显示对照时一并展示，不单独触发面板切换。

export const PHRASES = [
  // Claude Code：确认与权限
  { en: 'Do you want to proceed?', zh: '要继续吗？' },
  { en: 'Allow once', zh: '仅允许一次' },
  { en: 'Allow always', zh: '始终允许' },
  { en: 'Bypass permissions', zh: '跳过权限检查' },
  { en: 'Esc to cancel', zh: 'Esc 取消' },
  { en: 'Enter confirm · Esc cancel', zh: 'Enter 确认 · Esc 取消' },
  { en: 'Press Enter to continue', zh: '按 Enter 继续' },
  { en: 'Press Esc to go back', zh: '按 Esc 返回' },
  { en: 'Select an option', zh: '选择一个选项' },
  { en: 'Deny', zh: '拒绝' },
  { en: 'Yes', zh: '是', exact: true },
  { en: 'No', zh: '否', exact: true },

  // 运行状态与提示
  { en: 'esc to interrupt', zh: 'Esc 中断' },
  { en: 'ctrl+r to expand', zh: 'Ctrl+R 展开' },
  { en: 'Tip:', zh: '提示：' },
  { en: '? for shortcuts', zh: '? 查看快捷键' },
  { en: 'shift+tab to cycle', zh: 'Shift+Tab 切换', quiet: true },
  { en: 'auto mode on', zh: '自动模式已开启', quiet: true },
  { en: 'Working…', zh: '处理中…' },
  { en: 'Thinking…', zh: '思考中…' },
  { en: 'Running…', zh: '运行中…' },
  { en: 'Reading…', zh: '读取中…' },
  { en: 'Searching…', zh: '搜索中…' },
  { en: 'Waiting…', zh: '等待中…' },

  // 告警、错误与额度
  { en: 'weekly limit', zh: '每周额度' },
  { en: 'resets at', zh: '重置于' },
  { en: 'Rate limit', zh: '请求频率受限' },
  { en: 'API Error', zh: 'API 错误' },
  { en: 'Invalid API key', zh: 'API 密钥无效' },
  { en: '1 warning', zh: '1 条警告' },
  { en: 'f2 to view', zh: 'F2 查看' },
  { en: 'Context left', zh: '剩余上下文' },

  // Codex
  { en: 'Ask Codex to do anything', zh: '让 Codex 做任何事', quiet: true },
  { en: 'choose what model and reasoning effort to use', zh: '选择模型与推理强度' },
  { en: '1.5x speed', zh: '1.5 倍速度' },
  { en: 'run or save reusable prompts and slash commands', zh: '运行或保存可复用的提示与斜杠命令' },
  { en: 'Manage broader access for cybersecurity work', zh: '管理网络安全相关的访问权限' },
  { en: 'include current selection, open files, and other context from your IDE', zh: '从 IDE 引入当前选中与已打开文件' },
  { en: 'choose what Codex is allowed to do', zh: '选择 Codex 允许执行的操作' },
  { en: 'remap TUI shortcuts', zh: '重新映射终端快捷键' },
  { en: 'toggle Vim mode for the composer', zh: '切换输入框的 Vim 模式' },
  { en: 'Context 0% used', zh: '上下文已用 0%', quiet: true },
];
