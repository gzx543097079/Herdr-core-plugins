import { View, div, svg } from "gpui-kit";
import { h_flex, v_flex, Switch } from "gpui-base";
import { exec, theme, props, closeOverlay, appHome } from "herdr";

const MANAGER = () => appHome() + "/mods/plugin-controls/runtime/manager.py";
const plugins = [
  ["history", "对话历史", "浏览和恢复本地对话", "clock"],
  ["motion", "桌面动效", "界面过渡与列表优化", "layers"],
  ["language", "简体中文", "工作区界面中文化", "file-text"],
  ["commands", "命令提示", "在底部查看常用命令", "terminal"],
  ["git", "Git 工作台", "查看提交、差异和 PR", "git-branch"],
];

export default class PluginControls extends View {
  init(_props, cx) {
    this.status = null; this.error = ""; this.pending = false; this.reading = false;
    try { this.status = JSON.parse(localStorage.getItem('plugin-controls.status.v1') || 'null'); } catch (_) {}
    this.refresh(cx);
  }
  async request(args) {
    const result = await exec("/usr/bin/python3", ["-I", MANAGER(), "--app-home", appHome(), ...args]);
    if (result.code !== 0) throw new Error((result.stderr || result.stdout || "插件管理器执行失败").trim());
    return result.stdout;
  }
  refresh(cx) {
    if (this.reading || this.pending) return;
    this.reading = true;
    cx.spawn(async cx => {
      try {
        const status = JSON.parse(await this.request(["--status"]));
        this.status = status;
        if (status.running) { try { localStorage.setItem('plugin-controls.status.v1', JSON.stringify(status)); } catch (_) {} }
        this.error = status.running ? "" : (status.error || "无法读取 Herdr 状态");
      } catch (error) { this.error = error?.message || String(error); }
      this.reading = false; cx.notify();
      if (this.status?.busy && !this.pending) cx.timer.after(500, cx => this.refresh(cx));
    });
  }
  toggle(id, cx) {
    if (this.pending || this.reading || this.status?.busy || !this.status?.running || this.status?.managed === false) return;
    const enabled = !!this.status.plugins?.[id];
    const previous = JSON.stringify(this.status.last_operation || {});
    this.pending = true; this.pendingId = id; this.error = ""; cx.notify();
    cx.spawn(async cx => {
      try {
        await this.request(["--launch-action", id, enabled ? "uninstall" : "install"]);
        let attempts = 0;
        const poll = cx => {
          cx.spawn(async cx => {
            try {
              const status = JSON.parse(await this.request(["--status"]));
              this.status = status;
              if (status.running) { try { localStorage.setItem('plugin-controls.status.v1', JSON.stringify(status)); } catch (_) {} }
              if (!status.running) throw new Error(status.error || "无法读取 Herdr 状态");
              const message = status.last_operation?.message || "";
              if (JSON.stringify(status.last_operation || {}) !== previous) {
                if (message.startsWith("操作失败：")) this.error = message;
                else if (!!status.plugins?.[id] !== !enabled) this.error = "操作已结束，但插件状态没有达到预期。";
                this.pending = false;
              } else if (++attempts >= 300) {
                this.error = "无法确认操作结果，请刷新状态后查看。"; this.pending = false;
              } else cx.timer.after(300, poll);
            } catch (error) { this.error = error?.message || String(error); this.pending = false; }
            cx.notify();
          });
        };
        cx.timer.after(300, poll);
      } catch (error) { this.error = error?.message || String(error); this.pending = false; cx.notify(); }
    });
  }
  render() {
    const t = theme();
    const root = v_flex().size_full().bg(t.popover).px(20).pt(18).pb(14).gap(10).text_color(t.foreground);
    root.child(h_flex().items_center().gap(10)
      .child(div().size(34).rounded(9).flex().items_center().justify_center().bg(t.accent + '1a')
        .child(svg('mods/plugin-controls/plugins.svg').size(17).text_color(t.accent)))
      .child(v_flex().flex_1().gap(2)
        .child(div().text_size(16).font_semibold().child('插件设置'))
        .child(div().text_size(11.5).text_color(t.dim).child(this.pending ? '正在更新当前布局…' : '为当前布局选择需要的功能')))
      .child(div().id('close').size(28).flex().items_center().justify_center().rounded(7).cursor_pointer()
        .text_color(t.muted).hover(s => s.bg(t.hover).text_color(t.foreground)).tooltip('关闭')
        .on_click(() => { if (props()?.overlay) closeOverlay(props().overlay); })
        .child(svg('mods/workspace-chrome/x.svg').size(15))));
    if (this.status?.managed === false) root.child(div().text_size(12).text_color(t.dim).child('当前布局暂不支持修改插件开关。'));
    const list = v_flex().flex_1().min_h(0).gap(2);
    for (const [id, label, description, icon] of plugins) {
      const available = !!this.status?.running && typeof this.status.plugins?.[id] === 'boolean';
      const on = available && this.status.plugins[id];
      const disabled = !available || this.pending || this.reading || this.status?.busy || this.status?.managed === false;
      const control = Switch.new('toggle-' + id).checked(on).disabled(disabled).accessibility_label(label)
        .relative().w(38).h(22).rounded_full().bg(on ? t.accent : t.border)
        .opacity(disabled ? 0.55 : 1).transition('opacity', 140)
        .on_change((_value, cx) => this.toggle(id, cx))
        .child(div().absolute().top(3).left(on ? 19 : 3).size(16).rounded_full().bg('#ffffff')
          .transition('left', {duration: 160, easing: 'ease-out'}));
      list.child(h_flex().id('plugin-' + id).flex_1().min_h(0).px(8).gap(10).items_center().rounded(8).hover(s => s.bg(t.hover))
        .child(div().size(32).flex_none().rounded(8).flex().items_center().justify_center().bg(t.hover)
          .child(svg('mods/workspace-chrome/' + icon + '.svg').size(15).text_color(t.muted)))
        .child(v_flex().flex_1().min_w(0).gap(2)
          .child(div().text_size(13).font_medium().child(label))
          .child(div().text_size(11).text_color(t.dim).truncate().child(description)))
        .when(this.pending && this.pendingId === id, e => e.child(svg('mods/workspace-chrome/spinner.svg').size(13).text_color(t.muted).spin(900)))
        .child(control));
    }
    root.child(list);
    if (this.error) root.child(div().text_size(11).text_color(t.ansi1).child(this.error));
    root.child(h_flex().pt(8).border_t(1).border_color(t.border).items_center()
      .child(div().flex_1().text_size(11).text_color(t.dim).child(this.reading ? '正在读取状态…' : '设置仅应用于当前布局'))
      .child(div().id('refresh').px(8).py(4).rounded(6).text_size(11.5).text_color(t.muted).cursor_pointer()
        .hover(s => s.bg(t.hover).text_color(t.foreground)).on_click((_e, cx) => this.refresh(cx)).child('刷新')));
    return root;
  }
}
