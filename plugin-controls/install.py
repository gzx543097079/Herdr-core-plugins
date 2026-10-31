#!/usr/bin/env python3
"""为指定布局创建带插件设置入口的独立副本。"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

APP = Path.home() / '.config/herdr-app'
BIN = Path.home() / '.local/bin/herdr-app'
MANAGER = Path.home() / '.local/share/herdr-plugins/plugin-manager/server.py'
SOURCE = Path(__file__).resolve().parent


def nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)


def install(layout_name, activate):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', layout_name):
        raise ValueError('布局名称只能包含字母、数字、下划线和连字符。')
    if not MANAGER.is_file():
        raise ValueError('未找到已部署的插件管理器：' + str(MANAGER))
    layout_path = APP / 'layouts' / (layout_name + '.json')
    tree = json.loads(layout_path.read_text(encoding='utf-8'))
    footer = [n for n in nodes(tree) if n.get('id') == 'sidebar-footer']
    if len(footer) != 1:
        raise ValueError('指定布局没有唯一的 sidebar-footer。')
    content = footer[0].get('content', {})
    original = content.get('mod')
    if original not in ('workspace-chrome', 'workspace-chrome-i18n') or content.get('props', {}).get('footer') is not True:
        raise ValueError('指定布局的设置栏不是支持的 workspace-chrome，已停止以保护自定义 Mod。')
    original_dir = APP / 'mods' / original
    text = (original_dir / 'main.js').read_text(encoding='utf-8')
    import_old = 'updates, layout } from "herdr";'
    marker = '.when(Boolean(updates().app.ready), el => el.child(div().size(6).rounded_full().bg(t.accent))))'
    if text.count(import_old) != 1 or text.count(marker) != 1:
        raise ValueError('设置栏源码结构不受支持，未创建文件。')
    text = text.replace(import_old, 'updates, layout, openOverlay } from "herdr";', 1)
    icon = '''.when(Boolean(updates().app.ready), el => el.child(div().size(6).rounded_full().bg(t.accent)))
          .child(div().flex_1())
          .child(div().id("plugin-controls-open").size(24).flex_none().flex().items_center().justify_center().rounded(6).cursor_pointer().hover(s => s.bg(t.hover))
            .on_mouse_down("left", (_e, cx) => cx.stop_propagation())
            .on_click((_e, cx) => { cx.stop_propagation(); openOverlay({mod: "plugin-controls", kind: "dialog", width: 420, height: 430}); })
            .child(svg("mods/plugin-controls/plugins.svg").size(15))))'''
    text = text.replace(marker, icon, 1)
    target_mod = APP / 'mods' / 'plugin-controls'
    chrome_mod = APP / 'mods' / 'plugin-controls-chrome'
    target_layout = layout_path
    for target in (target_mod, chrome_mod):
        if target.exists():
            raise ValueError('目标已存在，拒绝覆盖：' + str(target))
    content['mod'] = chrome_mod.name
    created = []
    try:
        shutil.copytree(SOURCE, target_mod, ignore=shutil.ignore_patterns('install.py', '__pycache__', '*.pyc'))
        created.append(target_mod)
        source_js = (target_mod / 'main.js').read_text(encoding='utf-8')
        (target_mod / 'main.js').write_text(source_js.replace('"MANAGER_PATH"', json.dumps(str(MANAGER), ensure_ascii=False)), encoding='utf-8')
        shutil.copytree(original_dir, chrome_mod)
        created.append(chrome_mod)
        (chrome_mod / 'main.js').write_text(text, encoding='utf-8')
        for mod in (target_mod, chrome_mod):
            subprocess.run([str(BIN), 'check', str(mod)], check=True)
        import tempfile
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=target_layout.parent, delete=False) as out:
            temporary = Path(out.name)
            json.dump(tree, out, ensure_ascii=False, indent=2)
            out.write('\n')
        temporary.replace(target_layout)
    except Exception:
        for path in reversed(created):
            if path.is_dir(): shutil.rmtree(path)
            else: path.unlink(missing_ok=True)
        raise
    print('已为布局添加插件设置入口：' + target_layout.stem)
    if activate:
        subprocess.run([str(BIN), 'do', 'layout.switch', json.dumps({'name': target_layout.stem})], check=True)
        print('已切换到新布局。')


def main():
    parser = argparse.ArgumentParser(description='为指定布局创建插件设置入口。')
    parser.add_argument('--layout', required=True, help='要复制的现有布局名称')
    parser.add_argument('--activate', action='store_true', help='创建后切换到新布局')
    args = parser.parse_args()
    try:
        install(args.layout, args.activate)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print('安装失败：' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
