import { View, div } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { exec, theme, props, closeOverlay } from "herdr";

const MANAGER = "MANAGER_PATH";
const plugins = [["history", "对话历史"], ["motion", "桌面动效"], ["language", "简体中文"], ["commands", "命令提示"], ["git", "Git 工作台"]];

export default class PluginControls extends View {
  init(_props, cx) {
    this.status = null; this.error = ""; this.pending = false; this.reading = false;
    this.refresh(cx);
  }
  async request(args) {
    const result = await exec("/usr/bin/python3", ["-I", MANAGER, ...args]);
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
        this.error = status.running ? "" : (status.error || "无法读取 Herdr 状态");
      } catch (error) { this.error = error?.message || String(error); }
      this.reading = false; cx.notify();
    });
  }
  toggle(id, cx) {
    if (this.pending || this.reading || !this.status?.running) return;
    const enabled = !!this.status.plugins?.[id];
    const previous = JSON.stringify(this.status.last_operation || {});
    this.pending = true; this.error = ""; cx.notify();
    cx.spawn(async cx => {
      try {
        await this.request(["--launch-action", id, enabled ? "uninstall" : "install"]);
        let attempts = 0;
        const poll = cx => {
          cx.spawn(async cx => {
            try {
              const status = JSON.parse(await this.request(["--status"]));
              this.status = status;
              if (!status.running) throw new Error(status.error || "无法读取 Herdr 状态");
              const message = status.last_operation?.message || "";
              if (JSON.stringify(status.last_operation || {}) !== previous) {
                if (message.startsWith("操作失败：")) this.error = message;
                else if (!!status.plugins?.[id] !== !enabled) this.error = "操作已结束，但插件状态没有达到预期。";
                this.pending = false;
              } else if (++attempts >= 90) {
                this.error = "无法确认操作结果，请刷新状态后查看。"; this.pending = false;
              } else cx.timer.after(1000, poll);
            } catch (error) { this.error = error?.message || String(error); this.pending = false; }
            cx.notify();
          });
        };
        cx.timer.after(1000, poll);
      } catch (error) { this.error = error?.message || String(error); this.pending = false; cx.notify(); }
    });
  }
  render() {
    const t = theme();
    const root = v_flex().size_full().bg(t.popover).p(20).gap(10).text_color(t.foreground);
    root.child(h_flex().items_center().child(div().flex_1().text_size(16).font_semibold().child("插件设置"))
      .child(div().id("close").px(8).py(4).rounded(6).cursor_pointer().hover(s => s.bg(t.hover)).on_click(() => { if (props()?.overlay) closeOverlay(props().overlay); }).child("关闭")));
    root.child(div().text_size(12).text_color(t.dim).child(this.pending ? "正在处理，请稍候…" : "管理当前布局中的插件"));
    if (this.status?.managed === false) root.child(div().text_size(12).text_color(t.dim).child("当前布局暂不支持修改插件开关。"));
    for (const [id, label] of plugins) {
      const available = this.status?.running && typeof this.status.plugins?.[id] === "boolean";
      const on = available && this.status.plugins[id];
      root.child(h_flex().id("plugin-" + id).h(42).px(10).gap(10).items_center().rounded(7).hover(s => s.bg(t.hover))
        .child(div().flex_1().text_size(13).child(label))
        .child(div().id("toggle-" + id).px(10).py(5).rounded(6).text_size(12)
          .text_color(available && !this.pending ? t.foreground : t.dim).bg(on ? t.accent : t.hover)
          .on_click((_e, cx) => this.toggle(id, cx)).child(available ? (on ? "已开启" : "已关闭") : "未知")));
    }
    if (this.error) root.child(div().text_size(12).text_color(t.ansi1).child(this.error));
    root.child(div().id("refresh").px(10).py(6).rounded(6).text_size(12).text_color(t.muted).cursor_pointer().hover(s => s.bg(t.hover))
      .on_click((_e, cx) => this.refresh(cx)).child("刷新状态"));
    return root;
  }
}
