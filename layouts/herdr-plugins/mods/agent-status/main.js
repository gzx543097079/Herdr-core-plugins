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
  screenInfo(screen) {
    for (const line of String(screen || '').split('\n')) {
      const match = line.match(/ctx\s*(\d+)%/i);
      if (!match) continue;
      const parts = line.split('|').map(part => part.trim());
      const index = parts.findIndex(part => /ctx\s*\d+%/i.test(part));
      return { percent: Number(match[1]), label: index > 0 ? parts[index - 1] : '' };
    }
    return { percent: null, label: '' };
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
          try {
            const screen = await hc(['read', pane.terminal]);
            const info = screen.code === 0 ? this.screenInfo(screen.stdout) : { percent: null, label: '' };
            data.label = info.label || data.model;
            data.percent = info.percent ?? Math.min(99, Math.round(data.context / (data.window || 200000) * 100));
          } catch (_) {
            data.label = data.model;
            data.percent = Math.min(99, Math.round(data.context / (data.window || 200000) * 100));
          }
        }
        if (JSON.stringify(data) !== JSON.stringify(this.data)) { this.data = data; cx.notify(); }
      } catch (_) {
        if (this.data) { this.data = null; cx.notify(); }
      }
      this.busy = false;
    });
  }
  render() {
    const data = this.data;
    if (!data || !data.context) return div();
    const t = theme();
    const label = String(data.label || data.model || 'Claude').slice(0, 24);
    return h_flex().id('agent-status').h(24).px(6).gap(7).items_center().text_size(11.5)
      .child(div().flex_none().text_color(t.foreground).child(data.mode_label || '普通'))
      .child(div().text_color(t.dim).child('·'))
      .child(div().flex_none().text_color(t.muted)
        .child(Math.round(data.context / 1000) + 'k · ' + data.percent + '%'))
      .child(div().text_color(t.dim).child('·'))
      .child(div().flex_none().text_color(t.foreground).child(label));
  }
}
