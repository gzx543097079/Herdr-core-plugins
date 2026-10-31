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
    this.armed = null; this.armToken = 0; this.selected = null; this.typing = false;
    this.rows = []; this.filter = ""; this.loading = true; this.error = ""; this.expanded = {}; this.revision = 0; this.agentTab = 'Claude';
    try {
      const cached = JSON.parse(localStorage.getItem('agent-history.rows.v1') || '[]');
      if (Array.isArray(cached) && cached.length) { this.rows = cached; this.loading = false; }
    } catch (_) {}
    this.input = InputState.new({ placeholder: "搜索对话或项目路径…" });
    this.input.on("change", (_e, cx) => { this.filter = this.input.value().toLowerCase(); this.expanded = {}; cx.notify(); });
    this.input.on("focus", (_e, cx) => { this.typing = true; cx.notify(); });
    this.input.on("blur", (_e, cx) => { this.typing = false; cx.notify(); });
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
      } catch (e) { if (!this.rows.length) this.error = e?.message || String(e); }
      this.refreshing = false;
      if (this.loading) { this.loading = false; cx.notify(); }
    });
  }
  open(r) {
    const overlay = props()?.overlay;
    const argv = r.agent === "Codex" ? [CODEX_BIN, "resume", r.id] : [CLAUDE_BIN, "--resume", r.id];
    const title = (r.title || '未命名对话').slice(0, 35);
    const folder = path => (path || '').replace(/\/+$/, '') || '/';
    const candidates = spaces().filter(s => !s.machine && s.folder && folder(s.folder) === folder(r.cwd));
    const space = candidates.find(s => s.active) || candidates[0];
    if (space) {
      run("space.select", { id: space.id });
      run("tab.new", { folder: r.cwd, name: title, argv, space: space.id });
    } else run("space.new", { folder: r.cwd, tab: title, argv });
    if (overlay) closeOverlay(overlay);
  }
  deleteRows(rows, cx) {
    cx.spawn(async cx => {
    const paths = rows.map(r => r.path).filter(Boolean);
    if (!paths.length) return;
    this.revision++;
    const result = await exec("/usr/bin/python3", ["-I", "HISTORY_SCRIPT", "delete", ...paths]);
    if (result.code !== 0) { this.error = '删除失败：' + (result.stderr || '请重试'); cx.notify(); return; }
    this.error = '';
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
  ago(time) {
    const s = Math.max(0, Date.now() / 1000 - time);
    if (s < 60) return '刚刚';
    if (s < 3600) return Math.floor(s / 60) + ' 分钟前';
    if (s < 86400) return Math.floor(s / 3600) + ' 小时前';
    if (s < 86400 * 7) return Math.floor(s / 86400) + ' 天前';
    const d = new Date(time * 1000), now = new Date();
    return (d.getFullYear() === now.getFullYear() ? '' : d.getFullYear() + '年') + (d.getMonth() + 1) + '月' + d.getDate() + '日';
  }
  arm(key, cx) {
    this.armed = key; const token = ++this.armToken;
    cx.timer.after(3500, cx => { if (this.armToken === token) { this.armed = null; cx.notify(); } });
    cx.notify();
  }
  removeZone(row, t) {
    const armed = this.armed === row.key;
    if (armed) return div().h(24).px(8).flex_none().flex().items_center().rounded(6).bg(t.ansi1 + '1f').text_size(11.5).font_medium().text_color(t.ansi1)
      .child(row.kind === 'folder' ? `删除 ${row.items.length} 条` : '确认删除');
    return div().size(24).flex_none().flex().items_center().justify_center().rounded(6).opacity(0.45).hover(s => s.bg(t.hover).opacity(1)).tooltip(row.kind === 'folder' ? '删除此文件夹下的全部对话' : '删除这条对话')
      .child(svg('mods/agent-history/trash.svg').size(13).text_color(t.dim));
  }
  historyRow(row, t) {
    const { key } = row, selected = this.selected === key;
    const base = h_flex().id(key).flex_none().px(8).gap(8).items_center().rounded(7).cursor_pointer()
      .bg(selected ? t.selected : t.popover).hover(s => s.bg(selected ? t.selected : t.hover));
    if (row.kind === 'folder') {
      const open = this.expanded[key] === true;
      const name = row.folder.replace(/[\\/]+$/, '').split(/[\\/]/).pop() || row.folder;
      return base.h(34).text_size(12.8)
        .child(svg('mods/files/chevron-' + (open ? 'down' : 'right') + '.svg').size(12).text_color(t.dim))
        .child(svg('mods/files/folder.svg').size(14).text_color(open ? t.foreground : t.muted))
        .child(div().flex_1().min_w(0).truncate().font_medium().text_color(t.foreground).child(name))
        .child(div().text_size(11).text_color(t.dim).child(String(row.items.length)))
        .child(this.removeZone(row, t));
    }
    const r = row.record;
    return base.h(42).ml(20)
      .child(v_flex().min_w(0).flex_1().gap(1)
        .child(div().text_size(12.8).text_color(t.foreground).truncate().child(r.title || '未命名对话'))
        .child(div().text_size(11).text_color(t.dim).truncate().child(this.ago(r.time))))
      .child(this.removeZone(row, t));
  }
  segment(agent, count, t) {
    const on = this.agentTab === agent;
    return h_flex().id('nav-' + agent).flex_1().h_full().gap(6).items_center().justify_center().rounded(6).text_size(12.5).cursor_pointer()
      .when(on, e => e.bg(t.background).shadow_xs()).text_color(on ? t.foreground : t.muted).when(!on, e => e.hover(s => s.text_color(t.foreground)))
      .on_click((_e, cx) => { this.agentTab = agent; this.expanded = {}; this.armed = null; this.selected = null; cx.notify(); })
      .child(image('icons/' + agent.toLowerCase() + '.svg').size(14)).child(agent)
      .child(div().text_size(11).text_color(t.dim).child(String(count)));
  }
  notice(title, detail, t) {
    return v_flex().absolute().inset_0().items_center().justify_center().gap(4).px(24)
      .child(div().text_size(12.8).text_color(t.muted).child(title))
      .when(!!detail, e => e.child(div().text_size(11.5).text_color(t.dim).text_center().child(detail)));
  }
  render() {
    const t = theme(), agent = this.agentTab || 'Claude', groups = this.groups();
    const counts = a => Object.values(groups[a] || {}).reduce((n, items) => n + items.length, 0);
    const folders = Object.entries(groups[agent] || {}).map(([folder, items]) => ({folder, items: items.sort((a, b) => b.time - a.time)}))
      .sort((a, b) => b.items[0].time - a.items[0].time);
    const visible = [];
    for (const {folder, items} of folders) {
      const key = agent + ':' + folder;
      visible.push({kind: 'folder', key, agent, folder, items});
      if (this.expanded[key]) for (const record of items)
        visible.push({kind: 'conversation', key: 'history-' + agent + '-' + record.id, agent, record});
    }
    const empty = !this.loading && !this.error && !visible.length;
    return div().id('history-surface').size_full().overflow_hidden()
      .on_mouse_down_out((_event, cx) => this.dismiss(cx))
      .child(v_flex().id('history-content').relative().left(this.historyShown ? 0 : 18)
      .opacity(this.historyShown ? 1 : 0)
      .transition('left', {duration: this.closing ? 140 : 180, easing: 'ease-out'})
      .transition('opacity', {duration: this.closing ? 120 : 160, easing: 'ease-out'})
      .size_full().min_h(0).px(10).pt(10).pb(8).gap(8).bg(t.popover).text_size(13)
      .on_key_down((e, cx) => {
        if (e.key !== 'escape') return;
        if (this.armed) { this.armed = null; cx.notify(); }
        else if (props()?.overlay) closeOverlay(props()?.overlay);
      })
      .child(h_flex().h(28).pl(4).gap(8).items_center()
        .child(div().flex_1().font_semibold().text_color(t.foreground).child('对话历史'))
        .child(div().id('history-hide').size(26).flex().items_center().justify_center().rounded(6).cursor_pointer().hover(s => s.bg(t.hover)).tooltip('收起')
          .on_click((_event, cx) => this.dismiss(cx)).child(svg('mods/workspace-chrome/x.svg').size(14).text_color(t.muted))))
      .child(h_flex().h(30).p(2).gap(2).rounded(8).bg(t.hover)
        .child(this.segment('Claude', counts('Claude'), t)).child(this.segment('Codex', counts('Codex'), t)))
      .child(h_flex().h(32).px(10).gap(8).items_center().rounded(8).border_1().border_color(this.typing ? t.accent : t.border).bg(t.background)
        .child(svg('mods/workspace-chrome/search.svg').size(14).text_color(t.dim)).child(Input.new(this.input).flex_1().h_full().text_size(12.8).text_color(t.foreground)))
      .child(v_flex().flex_1().min_h(0).relative()
        .on_mouse_down('left', event => { this.historyPress = { x: event.local_position?.x, width: event.bounds?.width, count: event.click_count }; })
        .child(v_virtual_list('history-list-' + agent, visible.length,
          visible.map(row => row.kind === 'folder' ? 34 : 42), i => visible[i].key,
          range => visible.slice(range.start, range.end).map(row => this.historyRow(row, t))).size_full()
          .on_item_click((key, cx) => {
            const row = visible.find(item => item.key === key);
            if (!row) return;
            const press = this.historyPress || {}; this.historyPress = null;
            const zone = this.armed === key ? 96 : 40;
            const remove = press.x !== undefined && press.width && press.x >= press.width - zone;
            if (remove) {
              if (this.armed === key) { this.armed = null; this.deleteRows(row.kind === 'folder' ? row.items : [row.record], cx); }
              else this.arm(key, cx);
              return;
            }
            if (this.armed) this.armed = null;
            if (row.kind === 'folder') this.toggleFolder(key, cx);
            else if (press.count === 2) this.open(row.record);
            else { this.selected = key; cx.notify(); }
          }))
        .child(Scrollbar.vertical('history-list-' + agent).viewport_from_layout().absolute().inset_0())
        .when(this.loading && !visible.length, e => e.child(this.notice('正在读取本地对话…', '', t)))
        .when(!!this.error, e => e.child(this.notice('读取失败', this.error, t)))
        .when(empty, e => e.child(this.filter ? this.notice('没有匹配的对话', '试试项目文件夹名或标题中的关键词', t) : this.notice('还没有 ' + agent + ' 对话', '在终端运行 ' + agent.toLowerCase() + ' 后会出现在这里', t))))
      .child(h_flex().h(18).px(4).items_center().text_size(11).text_color(t.dim)
        .child(div().flex_1().truncate().child(this.armed ? '再次点击确认删除，删除后无法恢复 · Esc 取消' : '双击对话，在新标签页中恢复'))));
  }
}
