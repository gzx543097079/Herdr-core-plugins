import { View, div } from 'gpui-kit';
import { h_flex } from 'gpui-base';
import { theme, exec, appHome, panes, focused, agents, hc } from 'herdr';

// 聚焦终端里 Claude 会话的模式、上下文和模型；点击可切换。
export default class AgentStatus extends View {
  init(_p, cx) {
    this.data = null;
    this.busy = false;
    this.address = null;
    cx.timer.every(2000, cx => this.refresh(cx));
  }
  focusedPane() {
    const address = focused()?.terminal;
    return address ? panes().find(p => p.terminal === address) || null : null;
  }
  claude(pane) {
    const agent = agents().find(a => a.focused);
    const text = (pane?.program?.key || '') + ' ' + (pane?.program?.name || '') + ' ' + (agent?.app || '');
    return /claude/i.test(text);
  }
  modelLabel(screen) {
    for (const line of String(screen || '').split('\n')) {
      if (!/ctx\s*\d+%/i.test(line)) continue;
      const parts = line.split('|').map(part => part.trim());
      const index = parts.findIndex(part => /ctx\s*\d+%/i.test(part));
      if (index > 0 && parts[index - 1]) return parts[index - 1];
    }
    return '';
  }
  refresh(cx) {
    if (this.busy) return;
    const pane = this.focusedPane();
    if (!pane || !this.claude(pane)) {
      if (this.data) { this.data = null; cx.notify(); }
      return;
    }
    this.busy = true;
    this.address = pane.terminal;
    cx.spawn(async cx => {
      try {
        const result = await exec('/usr/bin/python3', [appHome() + '/mods/agent-status/status.py',
                                                       pane.cwd || '', pane.title || '']);
        let data = result.code === 0 && result.stdout.trim() ? JSON.parse(result.stdout) : null;
        if (data && data.context) {
          data.percent = Math.min(99, Math.round(data.context / (data.window || 200000) * 100));
          try {
            const screen = await hc(['read', pane.terminal]);
            data.label = (screen.code === 0 && this.modelLabel(screen.stdout)) || data.model;
          } catch (_) { data.label = data.model; }
        }
        if (JSON.stringify(data) !== JSON.stringify(this.data)) { this.data = data; cx.notify(); }
      } catch (_) {
        if (this.data) { this.data = null; cx.notify(); }
      }
      this.busy = false;
    });
  }
  cycleMode(cx) {
    const address = this.address;
    if (!address) return;
    cx.spawn(async cx => {
      try { await hc(['keys', address, 'shift+tab']); } catch (_) {}
      cx.timer.after(500, cx => this.refresh(cx));
    });
  }
  pickModel(cx) {
    const address = this.address;
    if (!address) return;
    const agent = agents().find(a => a.focused);
    if (agent?.status && agent.status !== 'idle') return;  // 忙时回车会把命令当提问提交
    cx.spawn(async cx => {
      try {
        await hc(['keys', address, '/', 'm', 'o', 'd', 'e', 'l']);
        cx.timer.after(500, cx => cx.spawn(async cx => {
          try { await hc(['keys', address, 'enter']); } catch (_) {}
        }));
      } catch (_) {}
    });
  }
  chip(id, text, tooltip, handler, t) {
    return div().id(id).flex_none().cursor_pointer().text_color(t.foreground)
      .tooltip(tooltip).on_click(handler).child(text);
  }
  render() {
    const data = this.data;
    if (!data || !data.context) return div();
    const t = theme();
    const label = String(data.label || data.model || 'Claude').slice(0, 24);
    return h_flex().id('agent-status').h(24).px(6).gap(7).items_center().text_size(11.5)
      .child(this.chip('agent-mode', data.mode_label || '普通', '点击切换模式（Shift+Tab）',
                       (_e, cx) => this.cycleMode(cx), t))
      .child(div().text_color(t.dim).child('·'))
      .child(div().flex_none().text_color(t.muted)
        .child(Math.round(data.context / 1000) + 'k · ' + data.percent + '%'))
      .child(div().text_color(t.dim).child('·'))
      .child(this.chip('agent-model', label, '点击切换模型',
                       (_e, cx) => this.pickModel(cx), t));
  }
}
