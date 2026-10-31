#!/usr/bin/env python3
"""为独立布局组合已安装的插件；调用方必须显式提供配置目录。"""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

FEATURES = ('history', 'motion', 'language', 'commands', 'git')
META = '_plugin_controls'
LANG_MODS = {'workspace-chrome', 'spaces', 'agents', 'pane', 'tabs', 'files',
             'changes', 'workspace-status', 'menu'}


class UnsupportedLayout(ValueError):
    pass


def nodes(value):
    if isinstance(value, dict):
        yield value
        for key, child in value.items():
            if key != META:
                yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)


def one(tree, name):
    matches = [node for node in nodes(tree) if node.get('id') == name]
    if len(matches) != 1:
        raise UnsupportedLayout(f'布局必须包含唯一的 {name}。')
    return matches[0]


def mod(node):
    content = node.get('content')
    if not isinstance(content, dict) or not isinstance(content.get('mod'), str):
        raise UnsupportedLayout(f'{node.get("id")} 不是受支持的模块节点。')
    return content['mod']


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise UnsupportedLayout('模块源码结构不受支持：' + old[:80])
    return text.replace(old, new, 1)


def motion_module():
    path = Path(__file__).resolve().parent.parent / 'desktop-motion' / 'install.py'
    if not path.is_file():
        raise UnsupportedLayout('缺少 desktop-motion/install.py，无法生成动效模块。')
    spec = importlib.util.spec_from_file_location('_plugin_controls_motion', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_module(app, name):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
        raise UnsupportedLayout('模块名称不受支持：' + str(name))
    path = app / 'mods' / name
    if path.is_symlink() or not (path / 'mod.json').is_file() or not (path / 'main.js').is_file():
        raise UnsupportedLayout('缺少已安装模块：' + name)
    return path


def infer(tree):
    tabs = mod(one(tree, 'tabs'))
    files = mod(one(tree, 'files'))
    changes = mod(one(tree, 'changes'))
    status = mod(one(tree, 'status'))
    ids = [node.get('id') for node in nodes(tree)]
    history, git, commands = (name in ids for name in ('history-sidebar', 'git-workbench', 'command-hints'))
    motion = files == 'desktop-motion-files' and changes == 'desktop-motion-changes'
    if (files.startswith('desktop-motion-') or changes.startswith('desktop-motion-')) and not motion:
        raise UnsupportedLayout('动效模块不完整。')
    expected_tabs = 'git-workbench-tabs' if git else 'desktop-motion-tabs' if motion else 'agent-history-tabs' if history else None
    if expected_tabs and tabs != expected_tabs:
        raise UnsupportedLayout('标签栏模块与已启用功能不一致。')
    if commands != (status == 'command-hints-status'):
        raise UnsupportedLayout('命令提示模块不完整。')
    brand = mod(one(tree, 'brand'))
    if brand not in ('workspace-chrome', 'workspace-chrome-i18n'):
        raise UnsupportedLayout('无法识别语言模块。')
    language = brand.endswith('-i18n')
    suffix = '-i18n' if language else ''
    if not motion and (files != 'files' + suffix or changes != 'changes' + suffix):
        raise UnsupportedLayout('文件或改动面板不是支持的官方模块。')
    if not commands and status != 'workspace-status' + suffix:
        raise UnsupportedLayout('状态栏不是支持的官方模块。')
    if not expected_tabs and tabs != ('tabs-i18n' if language else 'tabs'):
        raise UnsupportedLayout('标签栏不是支持的官方模块。')
    return dict(zip(FEATURES, (history, motion, language, commands, git)))


def baseline(tree, state, official):
    result = copy.deepcopy(tree)
    suffix = '-i18n' if state['language'] else ''
    for name, base in (('tabs', 'tabs'), ('files', 'files'), ('changes', 'changes'), ('status', 'workspace-status')):
        one(result, name)['content']['mod'] = base + suffix
    body, work = one(result, 'panel-body'), one(result, 'work')
    for parent, name, expected in ((body, 'history-sidebar', 'agent-history'), (body, 'git-workbench', 'git-workbench'), (work, 'command-hints', 'command-hints')):
        matches = [n for n in parent.get('children', []) if isinstance(n, dict) and n.get('id') == name]
        if len(matches) != int(state[{'history-sidebar': 'history', 'git-workbench': 'git', 'command-hints': 'commands'}[name]]):
            raise UnsupportedLayout('插件节点的位置或数量不受支持：' + name)
        if matches:
            if mod(matches[0]) != expected:
                raise UnsupportedLayout('插件节点包含未知模块：' + name)
            parent['children'].remove(matches[0])
    if body.get('active') in ('history-sidebar', 'git-workbench'):
        body['active'] = one(official, 'panel-body').get('active', 'files')
    if state['git']:
        panel, original = one(result, 'panel'), one(official, 'panel')
        for key, value in (('size', {'px': 720}), ('max', 1100)):
            if panel.get(key) == value:
                if key in original:
                    panel[key] = copy.deepcopy(original[key])
                else:
                    panel.pop(key, None)
    return result


def compose(app, layout_name, changes):
    """更新指定独立布局并返回功能状态；不会切换布局或删除模块。"""
    app = Path(app)
    if layout_name != 'herdr-plugins':
        raise UnsupportedLayout('仅支持独立布局 herdr-plugins。')
    if not isinstance(changes, dict) or any(k not in FEATURES or type(v) is not bool for k, v in changes.items()):
        raise UnsupportedLayout('开关必须是五项已知功能的布尔值。')
    layout_path = app / 'layouts' / (layout_name + '.json')
    tree = json.loads(layout_path.read_text(encoding='utf-8'))
    official = json.loads((app / 'layouts' / 'main.json').read_text(encoding='utf-8'))
    metadata_path = app / 'plugin-controls' / (layout_name + '.json')
    metadata = json.loads(metadata_path.read_text(encoding='utf-8')) if metadata_path.exists() else tree.pop(META, None)
    if metadata is None:
        current = infer(tree)
        base = baseline(tree, current, official)
    else:
        if not isinstance(metadata, dict) or metadata.get('version') != 1:
            raise UnsupportedLayout('布局组合元数据版本不受支持。')
        current = metadata.get('state')
        base = metadata.get('base')
        rendered = metadata.get('rendered')
        if not isinstance(current, dict) or set(current) != set(FEATURES) or any(type(v) is not bool for v in current.values()) or not isinstance(base, dict) or not isinstance(rendered, dict):
            raise UnsupportedLayout('布局组合元数据无效。')
        # 将用户对非受控结构的修改合并回基准；受控位置冲突则拒绝覆盖。
        base = merge_changes(base, rendered, tree)
    desired = dict(current)
    desired.update(changes)
    output, generated = build(app, base, desired)
    metadata = {'version': 1, 'state': desired, 'base': base, 'rendered': copy.deepcopy(output)}
    # 先准备所有模块；名称由内容决定，绝不覆盖或删除已有模块。
    for name, source, text in generated:
        target = app / 'mods' / name
        if target.exists():
            if target.is_symlink() or not (target / 'main.js').is_file() or (target / 'main.js').read_text(encoding='utf-8') != text:
                raise UnsupportedLayout('生成模块名称冲突：' + name)
            continue
        with tempfile.TemporaryDirectory(prefix='.plugin-controls-', dir=app / 'mods') as tmp:
            stage = Path(tmp) / name
            shutil.copytree(source, stage, symlinks=False)
            (stage / 'main.js').write_text(text, encoding='utf-8')
            try:
                os.rename(stage, target)
            except OSError:
                if not target.is_dir() or (target / 'main.js').read_text(encoding='utf-8') != text:
                    raise
    encoded = json.dumps(output, ensure_ascii=False, indent=2) + '\n'
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=layout_path.parent, delete=False) as file:
        temporary = Path(file.name)
        try:
            file.write(encoded)
            file.flush()
            os.fsync(file.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=metadata_path.parent, delete=False) as file:
        metadata_tmp = Path(file.name)
        json.dump(metadata, file, ensure_ascii=False)
        file.flush()
        os.fsync(file.fileno())
    try:
        os.replace(metadata_tmp, metadata_path)
        os.replace(temporary, layout_path)
    finally:
        temporary.unlink(missing_ok=True)
        metadata_tmp.unlink(missing_ok=True)
    return desired


def merge_changes(base, old, new):
    if old == new:
        return copy.deepcopy(base)
    if isinstance(base, dict) and isinstance(old, dict) and isinstance(new, dict):
        result = copy.deepcopy(base)
        for key in old.keys() | new.keys():
            if key in old and key in new and old[key] == new[key]:
                continue
            if key not in old:
                if key in base:
                    raise UnsupportedLayout('新增字段与组合基准冲突：' + key)
                result[key] = copy.deepcopy(new[key])
            elif key not in new:
                if key not in base or base[key] != old[key]:
                    raise UnsupportedLayout('删除了插件控制的字段：' + key)
                result.pop(key, None)
            else:
                result[key] = merge_changes(base.get(key), old[key], new[key])
        return result
    if isinstance(base, list) and isinstance(old, list) and isinstance(new, list):
        if len(old) != len(new):
            raise UnsupportedLayout('布局子节点已改变，请先恢复组合后的结构。')
        if len(base) == len(old):
            return [merge_changes(b, o, n) for b, o, n in zip(base, old, new)]
        # 插件添加的节点不得被更改，其余节点按 ID 合并。
        result = copy.deepcopy(base)
        for o, n in zip(old, new):
            if o == n:
                continue
            if not isinstance(o, dict) or not isinstance(n, dict) or o.get('id') != n.get('id'):
                raise UnsupportedLayout('布局子节点顺序已改变。')
            hits = [i for i, b in enumerate(result) if isinstance(b, dict) and b.get('id') == o.get('id')]
            if len(hits) != 1:
                raise UnsupportedLayout('插件节点已被修改。')
            i = hits[0]
            result[i] = merge_changes(result[i], o, n)
        return result
    if base != old:
        raise UnsupportedLayout('插件控制的布局字段已被修改。')
    return copy.deepcopy(new)


def build(app, base, state):
    tree = copy.deepcopy(base)
    generated = []
    suffix = '-i18n' if state['language'] else ''
    # 只转换已知官方模块，其他结构和模块保持原样。
    for node in nodes(tree):
        if isinstance(node.get('mod'), str):
            name = node['mod']
            plain = name[:-5] if name.endswith('-i18n') else name
            if plain in LANG_MODS:
                node['mod'] = plain + suffix
        if node.get('terminal_menu') in ('menu', 'menu-i18n'):
            node['terminal_menu'] = 'menu' + suffix
    if 'terminal_menu' not in tree and state['language']:
        tree['terminal_menu'] = 'menu-i18n'
    for name in ('tabs', 'files', 'changes', 'workspace-status'):
        read_module(app, name + suffix)
    for feature, name in (('history', 'agent-history'), ('git', 'git-workbench'), ('commands', 'command-hints')):
        if state[feature]:
            read_module(app, name)
    for node in nodes(tree):
        name = node.get('mod')
        if isinstance(name, str) and (name in LANG_MODS or name in {m + '-i18n' for m in LANG_MODS}):
            read_module(app, name)
    if tree.get('terminal_menu') in ('menu', 'menu-i18n'):
        read_module(app, tree['terminal_menu'])

    def generated_mod(source_name, text):
        source = read_module(app, source_name)
        digest = hashlib.sha256((source_name + '\0' + text).encode()).hexdigest()[:20]
        name = 'plugin-controls-' + digest
        generated.append((name, source, text))
        return name

    # 从官方组件生成独立副本，保持语言切换和插件组合可重复构建。
    for node_id, module in (('spaces', 'spaces'),):
        node = one(tree, node_id)
        if mod(node) != module + suffix:
            raise UnsupportedLayout(node_id + ' 不是支持的官方模块。')
        source = read_module(app, module + suffix)
        text = (source / 'main.js').read_text(encoding='utf-8')
        if module == 'spaces':
            text = replace_once(text, '.child(h_flex().h(31).pl(16).pr(10)', '.child(h_flex().h(36).pl(16).pr(10)')
            text = replace_once(text, '.px(8)\n      .h(rowHeight({ tree }))', '.px(10)\n      .h(rowHeight({ tree }))')
            text = replace_once(text, '.when(on, (el) => el.bg(t.selected))', '.when(on, (el) => el.bg(t.raised).border(1).border_color(t.border))')
        node['content']['mod'] = generated_mod(module + suffix, text)

    tabs = one(tree, 'tabs')
    if mod(tabs) != 'tabs' + suffix:
        raise UnsupportedLayout('标签栏不是支持的官方模块。')
    if mod(tabs) == 'tabs' + suffix:
        source = read_module(app, 'tabs' + suffix)
        text = (source / 'main.js').read_text(encoding='utf-8')
        if state['history']:
            installed = (read_module(app, 'agent-history-tabs') / 'main.js').read_text(encoding='utf-8')
            lines = [line for line in installed.splitlines() if '.child(div().id("agent-history")' in line]
            if len(lines) != 1:
                raise UnsupportedLayout('已安装的历史标签栏结构不受支持。')
            text = replace_once(text, '      .when(w?.buttons,', lines[0] + '\n      .when(w?.buttons,')
            text = replace_once(text, 'const enabled = shared("workspace.panels") ?? ["files", "changes"];', 'const enabled = [...(shared("workspace.panels") ?? ["files", "changes"]), "history-sidebar"];')
        if state['git']:
            anchor = '      .child(div().id("agent-history")' if state['history'] else '      .when(w?.buttons,'
            text = replace_once(text, anchor, '      .child(panelButton("git-workbench", "Git", "mods/git-workbench/git.svg"))\n' + anchor)
            text = replace_once(text, 'const enabled = ', 'const gitEnabled = ["git-workbench"];\n    const enabled = ')
            text = replace_once(text, 'this.syncPanel(space, panel, body, enabled);', 'this.syncPanel(space, panel, body, [...enabled, ...gitEnabled]);')
        if state['motion']:
            try:
                text = motion_module().patch_tabs(text, 140)
            except (ValueError, RuntimeError, AssertionError) as error:
                raise UnsupportedLayout('标签栏动效源码不受支持：' + str(error)) from error
        text = replace_once(text, '.h(29).px(10).gap(7).rounded(7)', '.h(32).px(12).gap(8).rounded(8)')
        text = replace_once(text, '.gap(3).items_center().bg(t.chrome).border_b(1)', '.gap(5).items_center().bg(t.chrome).border_b(1)')
        tabs['content']['mod'] = generated_mod('tabs' + suffix, text)
    if state['motion']:
        motion = motion_module()
        for name in ('files', 'changes'):
            node = one(tree, name)
            if mod(node) != name + suffix:
                raise UnsupportedLayout(name + ' 不是支持的官方模块。')
            source = read_module(app, name + suffix)
            try:
                text = getattr(motion, 'patch_' + name)((source / 'main.js').read_text(encoding='utf-8'), 140)
            except (ValueError, RuntimeError, AssertionError) as error:
                raise UnsupportedLayout(name + ' 动效源码不受支持：' + str(error)) from error
            node['content']['mod'] = generated_mod(name + suffix, text)
    body = one(tree, 'panel-body')
    work = one(tree, 'work')
    panel = one(tree, 'panel')
    if not isinstance(body.get('children'), list) or not isinstance(work.get('children'), list):
        raise UnsupportedLayout('面板容器缺少 children。')
    for enabled, name, content in ((state['history'], 'history-sidebar', {'mod': 'agent-history', 'props': {'sidebar': True}}), (state['git'], 'git-workbench', {'mod': 'git-workbench'})):
        if enabled:
            if any(n.get('id') == name for n in nodes(tree)):
                raise UnsupportedLayout('插件节点已存在：' + name)
            body['children'].append({'id': name, 'type': 'block', 'content': content})
    if state['git']:
        panel['size'], panel['max'] = {'px': 720}, 1100
    if state['commands']:
        if any(n.get('id') == 'command-hints' for n in nodes(tree)):
            raise UnsupportedLayout('命令提示节点已存在。')
        status = one(tree, 'status')
        if mod(status) != 'workspace-status' + suffix or status not in work['children']:
            raise UnsupportedLayout('状态栏位置或模块不受支持。')
        source = read_module(app, 'workspace-status' + suffix)
        text = (source / 'main.js').read_text(encoding='utf-8')
        anchor = '      .child(div().flex_1())'
        button = '\n      .child(div().id("command-hints-toggle").px(8).h(24).flex().items_center().rounded(5).cursor_pointer().hover(s=>s.bg(t.hover)).on_click(()=>run("layout.toggle",{id:"command-hints"})).child("命令提示"))'
        text = replace_once(text, anchor, anchor + button)
        status['content']['mod'] = generated_mod('workspace-status' + suffix, text)
        work['children'].insert(work['children'].index(status), {'id': 'command-hints', 'type': 'block', 'content': {'mod': 'command-hints'}, 'size': {'px': 185}, 'min': 175, 'max': 440, 'hidden': True})
    return tree, generated
