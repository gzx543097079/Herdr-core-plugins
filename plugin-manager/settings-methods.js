  loadPluginState(cx) {
    cx.spawn(async cx => {
      try {
        const result = await exec('/usr/bin/python3', [HERDR_PLUGIN_MANAGER, '--status']);
        if (result.code !== 0) throw new Error(result.stderr || result.stdout);
        this.pluginState = JSON.parse(result.stdout);
        if (this.pluginState.last_operation?.message) this.pluginNotice = this.pluginState.last_operation.message;
      } catch (e) { this.pluginNotice = String(e); }
      cx.notify();
    });
  }
  pluginAction(id, action, cx) {
    if (this.pluginBusy) return;
    this.pluginBusy = true; this.pluginNotice = '正在' + (action === 'install' ? '注入' : '卸载') + '…'; cx.notify();
    cx.spawn(async cx => {
      try {
        const result = await exec('/usr/bin/python3', [HERDR_PLUGIN_MANAGER, '--launch-action', id, action]);
        if (result.code !== 0) throw new Error(result.stderr || result.stdout);
        this.pluginNotice = '正在应用，即将返回插件页…';
      } catch (e) { this.pluginNotice = String(e); }
      this.pluginBusy = false; this.loadPluginState(cx); cx.notify();
    });
  }
  pluginManager(t) {
    const plugins = [
      ['history', '对话历史', '文件夹分组、连续滚动、双击恢复；点击外部自动收起。'],
      ['motion', '桌面动效', '轻量原生过渡，优化文件与改动列表的读取和绘制。'],
      ['language', '简体中文', '为工作区、标签栏和菜单启用中文模块副本。'],
    ];
    return v_flex().gap(10)
      .child(h_flex().items_center().gap(12)
        .child(div().flex_1().text_size(18).font_semibold().text_color(t.foreground).child('插件管理'))
        .child(this.button(t, 'plugins-refresh', '刷新状态', (_e, cx) => this.loadPluginState(cx))))
      .child(div().text_size(12.5).text_color(t.muted).child('独立启用或卸载，不会删除本地对话记录。'))
      .children(plugins.map(([id, name, about]) => {
        const enabled = this.pluginState?.plugins?.[id] === true;
        const busy = this.pluginBusy;
        const action = (verb) => (_e, cx) => { if (!busy) this.pluginAction(id, verb, cx); };
        return this.row(t, name + (enabled ? ' · 已启用' : ' · 未启用'), about,
          h_flex().gap(8).opacity(busy ? 0.5 : 1)
            .when(enabled, el => el.child(this.button(t, 'uninstall-' + id, '卸载', action('uninstall'))))
            .child(this.button(t, 'install-' + id, enabled ? '重新注入' : '注入插件', action('install'))));
      }))
      .when(Boolean(this.pluginNotice), el => el.child(div().text_size(12.5).text_color(t.muted).child(this.pluginNotice)))
      .child(div().pt(8).text_size(12).text_color(t.dim).child('界面切换后会自动回到这里。卸载一个插件时保留其他已启用插件。'));
  }
