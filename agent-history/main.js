import { View, div, svg, image } from "gpui-kit";
import { v_flex, h_flex, InputState, Input, v_virtual_list, Scrollbar } from "gpui-base";
import { exec, run, theme, props, closeOverlay, spaces, layout, nextCommand } from "herdr";

export default class History extends View {
  init(_p, cx) {
    this.historyShown = false; this.motionVersion = 0;
    cx.timer.after(20, cx => this.reveal(cx));
    cx.spawn(async cx => { for (;;) {
      const command = await nextCommand();
      if (command === 'reveal') this.reveal(cx);
      if (command === 'dismiss') this.dismiss(cx);
    } });
    this.rows = []; this.filter = ""; this.loading = true; this.error = ""; this.expanded = {}; this.revision = 0; this.agentTab = 'Claude';
    try {
      const cached = JSON.parse(localStorage.getItem('agent-history.rows.v1') || '[]');
      if (Array.isArray(cached) && cached.length) { this.rows = cached; this.loading = false; }
    } catch (_) {}
    this.input = InputState.new({ placeholder: "搜索对话或项目路径…" });
    this.input.on("change", (_e, cx) => { this.filter = this.input.value().toLowerCase(); this.expanded = {}; cx.notify(); });
    if (!props()?.sidebar) this.input.focus();
    this.refresh(cx);
    cx.timer.every(10000, cx => this.refresh(cx));
  }
  panelNode(id, node = layout()) {
    if (node?.id === id) return node;
    for (const child of node?.children || []) {
      const found = this.panelNode(id, child); if (found) return found;
    }
    return null;
  }
  reveal(cx) {
    this.motionVersion++; this.closing = false; this.historyShown = true; cx.notify();
  }
  dismiss(cx) {
    const panel = this.panelNode('panel'), body = this.panelNode('panel-body');
    if (this.closing || panel?.hidden || body?.active !== 'history-sidebar') return;
    this.closing = true; this.historyShown = false;
    const version = ++this.motionVersion;
    cx.notify();
    cx.timer.after(150, cx => {
      if (version !== this.motionVersion) return;
      this.closing = false;
      if (this.panelNode('panel-body')?.active === 'history-sidebar') run('layout.hide', {id:'panel'});
      cx.notify();
    });
  }
  refresh(cx) {
    if (this.refreshing) return;
    this.refreshing = true;
    const revision = this.revision;
    cx.spawn(async (cx) => {
      try {
        const r = await exec("/usr/bin/python3", ["-I", "HISTORY_SCRIPT"]);
        if (r.code !== 0) throw new Error(r.stderr || "读取失败");
        const rows = JSON.parse(r.stdout);
        if (revision === this.revision && JSON.stringify(rows) !== JSON.stringify(this.rows)) {
          this.rows = rows;
          cx.notify();
          try { localStorage.setItem('agent-history.rows.v1', JSON.stringify(rows)); } catch (_) {}
        }
      } catch (e) { if (!this.rows.length) this.error = String(e); }
      this.refreshing = false;
      if (this.loading) { this.loading = false; cx.notify(); }
    });
  }
  open(r) {
    const overlay = props()?.overlay;
    const argv = r.agent === "Codex" ? [CODEX_BIN, "resume", r.id] : [CLAUDE_BIN, "--resume", r.id];
    const args = { folder: r.cwd, name: r.title.slice(0, 35), argv };
    const space = spaces().find(s => s.active);
    if (space) run("tab.new", { ...args, space: space.id });
    else run("space.new", args);
    if (overlay) closeOverlay(overlay);
  }
  deleteRows(rows, cx) {
    cx.spawn(async cx => {
    const paths = rows.map(r => r.path).filter(Boolean);
    if (!paths.length) return;
    this.revision++;
    const result = await exec("/usr/bin/python3", ["-I", "HISTORY_SCRIPT", "delete", ...paths]);
    if (result.code !== 0) { this.error = '删除失败：' + (result.stderr || '请重试'); cx.notify(); return; }
    this.rows = JSON.parse(result.stdout);
    try { localStorage.setItem('agent-history.rows.v1', JSON.stringify(this.rows)); } catch (_) {}
    cx.notify();
    });
  }
  groups() {
    const rows = this.rows.filter(r => (r.title + ' ' + r.cwd + ' ' + r.agent).toLowerCase().includes(this.filter));
    const out = {};
    for (const r of rows) {
      const agent = r.agent;
      const folder = r.cwd || '未知文件夹';
      out[agent] ??= {};
      out[agent][folder] ??= [];
      out[agent][folder].push(r);
    }
    return out;
  }
  toggleFolder(key, cx) {
    this.expanded = this.expanded[key] ? {} : { [key]: true };
    cx.notify();
  }
  historyRow(row, t) {
    const { agent, key } = row;
    if (row.kind === 'folder') {
      const open = this.expanded[key] === true;
      return h_flex().id('folder-' + key).h(36).flex_none().text_size(12.8).px(8).gap(7).items_center().rounded(7).cursor_pointer().hover(s => s.bg(t.hover))
        .child(svg('mods/files/chevron-' + (open ? 'down' : 'right') + '.svg').size(12).text_color(t.dim))
        .child(svg('mods/files/folder.svg').size(14).text_color(t.muted))
        .child(div().flex_1().truncate().text_color(t.foreground).child(row.folder.replace(/[\\/]+$/, '').split(/[\\/]/).pop() || row.folder))
        .child(div().text_size(11).text_color(t.dim).child(String(row.items.length)))
        .child(div().w(44).flex_none().text_right().px(6).text_color(t.dim).hover(s => s.text_color(t.foreground)).child('删除'));
    }
    const r = row.record;
    return h_flex().id(key).h(50).flex_none().text_size(12.8).ml(23).px(8).py(7).gap(8).rounded(7).cursor_pointer().hover(s => s.bg(t.hover))
      .child(image('icons/' + agent.toLowerCase() + '.svg').size(14))
      .child(v_flex().min_w(0).flex_1().gap(2)
        .child(div().text_color(t.foreground).truncate().child(r.title))
        .child(div().text_size(11).text_color(t.dim).truncate().child(new Date(r.time * 1000).toLocaleDateString())))
      .child(div().w(44).flex_none().text_right().px(6).text_color(t.dim).hover(s => s.text_color(t.foreground))
        .child('删除'));
  }
  render() {
    const t = theme(), agent = this.agentTab || 'Claude';
    const folders = Object.entries(this.groups()[agent] || {}).map(([folder, items]) => ({folder, items: items.sort((a, b) => b.time - a.time)}))
      .sort((a, b) => b.items[0].time - a.items[0].time);
    const visible = [];
    let count = 0;
    for (const {folder, items} of folders) {
      const key = agent + ':' + folder;
      count += items.length;
      visible.push({kind: 'folder', key, agent, folder, items});
      if (this.expanded[key]) for (const record of items)
        visible.push({kind: 'conversation', key: 'history-' + agent + '-' + record.id, agent, record});
    }
    return div().id('history-surface').size_full().overflow_hidden()
      .on_mouse_down_out((_event, cx) => this.dismiss(cx))
      .child(v_flex().id('history-content').relative().left(this.historyShown ? 0 : 18)
      .opacity(this.historyShown ? 1 : 0)
      .transition('left', {duration: this.closing ? 140 : 180, easing: 'ease-out'})
      .transition('opacity', {duration: this.closing ? 120 : 160, easing: 'ease-out'})
      .size_full().min_h(0).p(12).gap(10).bg(t.popover).text_size(13)
      .on_key_down((e) => { if (e.key === 'escape' && props()?.overlay) closeOverlay(props()?.overlay); })
      .child(h_flex().items_center().child(div().flex_1().font_semibold().text_color(t.foreground).child('对话历史')).child(div().id('history-hide').text_size(12).text_color(t.muted).cursor_pointer().on_click((_event, cx) => this.dismiss(cx)).child('收起')))
      .child(h_flex().h(32).gap(4).children(['Claude', 'Codex'].map(agent => h_flex().id('nav-' + agent).flex_1().h_full().gap(6).items_center().justify_center().rounded(6).text_size(12.8).cursor_pointer().bg(this.agentTab === agent ? t.selected : t.popover).text_color(this.agentTab === agent ? t.foreground : t.muted).hover(s => s.bg(t.hover)).on_click((_e, cx) => { this.agentTab = agent; this.expanded = {}; cx.notify(); }).child(image('icons/' + agent.toLowerCase() + '.svg').size(15)).child(agent))))
      .child(h_flex().h(36).px(10).gap(8).items_center().rounded(9).border_1().border_color(t.accent).bg(t.background)
        .child(svg('mods/workspace-chrome/search.svg').size(15).text_color(t.dim)).child(Input.new(this.input).flex_1().h_full().text_size(12.8).text_color(t.foreground)))
      .child(h_flex().gap(8).items_center().text_size(12.8)
        .child(image('icons/' + agent.toLowerCase() + '.svg').size(16))
        .child(div().text_color(t.foreground).child(agent))
        .child(div().text_size(11).text_color(t.dim).child(`${count} 条对话`)))
      .child(v_flex().flex_1().min_h(0).relative()
        .on_mouse_down('left', event => { this.historyPress = { remove: event.local_position && event.bounds && event.local_position.x >= event.bounds.width - 52, count: event.click_count }; })
        .when(this.loading, e => e.child(div().p(12).text_color(t.dim).child('正在读取本地对话…')))
        .when(!!this.error, e => e.child(div().p(12).text_color(t.dim).child('读取失败：' + this.error)))
        .when(!this.loading && !this.error && !visible.length, e => e.child(div().p(12).text_color(t.dim).child('没有找到匹配的对话')))
        .child(v_virtual_list('history-list-' + agent, visible.length,
          visible.map(row => row.kind === 'folder' ? 36 : 50), i => visible[i].key,
          range => visible.slice(range.start, range.end).map(row => this.historyRow(row, t))).size_full()
          .on_item_click((key, cx) => {
            const row = visible.find(item => item.key === key);
            if (!row) return;
            const press = this.historyPress || {}; this.historyPress = null;
            if (press.remove) this.deleteRows(row.kind === 'folder' ? row.items : [row.record], cx);
            else if (row.kind === 'folder') this.toggleFolder(key, cx);
            else if (press.count === 2) this.open(row.record);
          }))
        .child(Scrollbar.vertical('history-list-' + agent).viewport_from_layout().absolute().inset_0())));
  }
}
