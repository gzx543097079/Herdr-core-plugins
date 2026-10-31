#!/usr/bin/env python3
"""herdr-lang：Herdr 桌面端语言插件。

Herdr 没有多语言系统，界面文字直接写在 ~/.config/herdr-app 下的 JS 文件里：
  - mods/   侧边栏、标签栏、菜单等。自带的只读，启动时会被还原
            → 复制成 <mod>-i18n 再翻译，并复制主布局为 main-i18n 指向它们。
  - frame/  设置页、命令面板、欢迎页等。每次启动都会被重写
            → 后台任务（launchd）监听重写，自动重新注入。
这个插件把翻译放在 lang/<代码>.json 语言包里，并在「设置 › 外观」最上面注入一个
「语言」选择器，点一下就切换。

用法：
  python3 herdr_lang.py install [语言代码]   安装插件（默认 zh-CN）
  python3 herdr_lang.py set <语言代码|en>     切换语言（设置页里的选择器调用的就是它）
  python3 herdr_lang.py uninstall             卸载插件，恢复原版
  python3 herdr_lang.py status                查看状态
  python3 herdr_lang.py frame                 重新注入（后台任务用）
"""

import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

APP_HOME = Path.home() / ".config" / "herdr-app"
MODS_DIR = APP_HOME / "mods"
LAYOUTS_DIR = APP_HOME / "layouts"
FRAME_DIR = APP_HOME / "frame"
HERDR_APP = Path.home() / ".local" / "bin" / "herdr-app"

# 安装位置（不能放桌面：macOS 不让后台任务和 Herdr 读桌面）
INSTALL_DIR = Path.home() / ".local" / "share" / "herdr-lang"
ENGINE = INSTALL_DIR / "herdr_lang.py"
LANG_DIR = INSTALL_DIR / "lang"
ORIG_DIR = INSTALL_DIR / "frame-orig"
CONFIG = INSTALL_DIR / "config.json"
LOG = INSTALL_DIR / "agent.log"

AGENT_LABEL = "com.herdr-lang.frame"
AGENT_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{AGENT_LABEL}.plist"

SUFFIX = "-i18n"
BASE_LAYOUT = "main"
LANG_LAYOUT = BASE_LAYOUT + SUFFIX
MARK = "// herdr-lang: injected\n"

# 要翻译的 mod：主布局用到的，以及它们会打开的弹窗。
# confirm / prompt / toast / help / peek 由 App 本身直接打开，换不掉。
MODS = [
    "agents", "changes", "files", "menu", "new-menu", "pane", "picker",
    "spaces", "tabs", "workspace-chrome", "workspace-status", "worktree",
    "machine-add",
]
FRAMES = ["settings", "palette", "welcome", "feedback", "whatsnew"]

ENGLISH_UI = {"heading": "Language", "title": "Interface language",
              "about": "Translations are injected by the herdr-lang plugin. The window refreshes on switch."}


# ───────────── 基础 ─────────────

def log(msg):
    print(msg, flush=True)


def run_app(*args, check=True):
    r = subprocess.run([str(HERDR_APP), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"herdr-app {' '.join(args)} 失败：{(r.stdout + r.stderr).strip()}")
    return r


def do(command, payload):
    return run_app("do", command, json.dumps(payload, ensure_ascii=False))


def app_ready():
    return run_app("status", check=False).returncode == 0


def wait_app(start=False, seconds=30):
    if app_ready():
        return True
    if start:
        log("Herdr 没在运行，正在打开…")
        subprocess.run(["open", "-a", "Herdr"])
    for _ in range(seconds * 2):
        time.sleep(0.5)
        if app_ready():
            time.sleep(1)
            return True
    return False


def app_version():
    r = run_app("--version", check=False)
    return r.stdout.strip()


def current_layout():
    try:
        return json.loads(run_app("status").stdout).get("layout")
    except (json.JSONDecodeError, SystemExit):
        return None


def wait_for(path):
    for _ in range(40):
        if path.exists():
            return
        time.sleep(0.25)
    raise SystemExit(f"等待 {path} 超时。")


def load_config():
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"lang": "en"}


def save_config(cfg):
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def lang_dir():
    # 从桌面直接运行时用旁边的 lang/，装好之后用安装目录里的
    here = Path(__file__).resolve().parent / "lang"
    return here if here.is_dir() else LANG_DIR


def packs():
    out = {}
    for f in sorted(lang_dir().glob("*.json")):
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
            out[p["code"]] = p
        except (OSError, json.JSONDecodeError, KeyError) as e:
            log(f"  语言包 {f.name} 读不了：{e}")
    return out


def pack_for(code):
    if code == "en":
        return None
    p = packs().get(code)
    if not p:
        raise SystemExit(f"没有 {code} 语言包。可用：en, {', '.join(packs())}")
    return p


# ───────────── 翻译 ─────────────

def replace_words(src, words, keep=()):
    for en, zh in words.items():
        if en in keep:
            continue
        for q in ('"', "'"):
            src = src.replace(f"{q}{en}{q}", f"{q}{zh}{q}")
    return src


def translate(src, table, keep=()):
    for old, new in table.get("fragments", []):
        src = src.replace(old, new)
    for pat, rep in table.get("regexes", []):
        src = re.sub(pat, rep, src)
    return replace_words(src, table.get("words", {}), keep)


def translate_palette(src, table):
    # 命令条目 [命令, 参数, "分组", "标题", "搜索词"]：标题翻译，英文标题并入搜索词，英文照样能搜
    words = table.get("words", {})

    def entry(m):
        group, title, extra = m.group(1), m.group(2), m.group(3)
        if title not in words:
            return m.group(0)
        return f', "{group}", "{words[title]}", "{(title + " " + extra).strip()}"]'

    src = re.sub(r', "([A-Z][a-z]+)", "([^"]+)", "([^"]*)"\]', entry, src)
    # 分组名会和 App 动态生成的命令比较，只在显示时翻译
    groups = json.dumps(table.get("palette_groups", {}), ensure_ascii=False)
    src = src.replace("\nconst GROUPS = [", f"\nconst GROUPS_I18N = {groups};\nconst GROUPS = [", 1)
    src = src.replace(".child(r.head));", ".child(GROUPS_I18N[r.head] ?? r.head));")
    return translate(src, table, keep=set(table.get("palette_keep", [])))


# ───────────── 设置页注入「语言」选择器 ─────────────

def inject_settings(src, code, pack):
    choices = [["en", "English"]] + [[c, p["name"]] for c, p in packs().items()]
    state = {
        "current": code,
        "choices": choices,
        "engine": str(ENGINE),
        "ui": (pack or {}).get("ui", ENGLISH_UI),
        "layout": LANG_LAYOUT,
        "layoutName": (pack or {}).get("layout_name", "Herdr i18n"),
    }
    const = f"\nconst HERDR_LANG = {json.dumps(state, ensure_ascii=False)};\n"

    steps = [
        ('closeOverlay } from "herdr";', 'closeOverlay, exec, notify } from "herdr";'),
        ('\nconst LOOKS = { main: "Herdr", terminals: "Terminals", win98: "Herdr 98" };\n',
         '\nconst LOOKS = { main: "Herdr", terminals: "Terminals", win98: "Herdr 98" };\n'
         + const + 'LOOKS[HERDR_LANG.layout] = HERDR_LANG.layoutName;\n'),
        ('    return v_flex()\n      .w_full()\n      .child(this.heading(t, "Layout"))',
         '    return v_flex()\n      .w_full()\n'
         '      .child(this.heading(t, HERDR_LANG.ui.heading))\n'
         '      .child(this.row(t, HERDR_LANG.ui.title, HERDR_LANG.ui.about, this.langPicker(t, cx)))\n'
         '      .child(div().h(18))\n'
         '      .child(this.heading(t, "Layout"))'),
        ('\n  themePicker(t, light) {', '\n' + LANG_PICKER + '\n  themePicker(t, light) {'),
    ]
    for old, new in steps:
        if old not in src:
            raise ValueError(f"设置页结构变了，找不到注入点：{old.strip()[:60]}")
        src = src.replace(old, new, 1)
    return src


LANG_PICKER = """  // herdr-lang：界面语言选择器，切换时调用插件重新注入
  langPicker(t, cx) {
    const now = this.langBusy ?? HERDR_LANG.current;
    return h_flex()
      .p(2)
      .gap(2)
      .rounded(8)
      .border_1()
      .border_color(t.border)
      .bg(t.background)
      .children(
        HERDR_LANG.choices.map(([code, label]) =>
          div()
            .id(`st-lang-${code}`)
            .px(12)
            .py(4)
            .rounded(6)
            .text_size(13)
            .cursor_pointer()
            .when(now === code, (el) => el.bg(t.raised).text_color(t.foreground).border_1().border_color(t.border))
            .when(now !== code, (el) => el.text_color(t.muted).hover((s) => s.text_color(t.foreground)))
            .on_click((_e, cx) => {
              if (now === code || this.langBusy) return;
              this.langBusy = code;
              cx.notify();
              exec("/usr/bin/python3", ["-I", HERDR_LANG.engine, "set", code]).then((r) => {
                this.langBusy = null;
                if (r.code !== 0) notify({ title: "herdr-lang", body: (r.stderr || r.stdout || "").trim().slice(-300), level: "error" });
              });
            })
            .child(this.langBusy === code ? `${label}…` : label),
        ),
      );
  }
"""


# ───────────── frame（App 自己的界面） ─────────────

def fresh_original(name):
    """拿到 frame 的英文原文：文件没被注入过就是原文（顺便备份），否则用备份。"""
    js = FRAME_DIR / name / "main.js"
    mj = FRAME_DIR / name / "mod.json"
    backup = ORIG_DIR / name
    src = js.read_text(encoding="utf-8")
    if not src.startswith(MARK):
        backup.mkdir(parents=True, exist_ok=True)
        shutil.copy2(js, backup / "main.js")
        if mj.exists():
            shutil.copy2(mj, backup / "mod.json")
        return src
    if (backup / "main.js").exists():
        return (backup / "main.js").read_text(encoding="utf-8")
    return None


def patch_frames(code):
    pack = pack_for(code)
    table = (pack or {}).get("frame", {})
    errors = []
    for name in FRAMES:
        js = FRAME_DIR / name / "main.js"
        if not js.exists():
            continue
        src = fresh_original(name)
        if src is None:
            continue
        out = src
        try:
            if name == "settings":
                out = inject_settings(out, code, pack)
        except ValueError as e:
            errors.append(str(e))
        if pack:
            out = translate_palette(out, table) if name == "palette" else translate(out, table)
        # 没有任何改动（英文且不需要注入）就写回原文，否则加标记写入
        want = src if out == src else MARK + out
        if js.read_text(encoding="utf-8") != want:
            js.write_text(want, encoding="utf-8")
        # 窗口标题
        mj, orig_mj = FRAME_DIR / name / "mod.json", ORIG_DIR / name / "mod.json"
        if orig_mj.exists() and mj.exists():
            text = orig_mj.read_text(encoding="utf-8")
            meta = json.loads(text)
            title = table.get("titles", {}).get(meta.get("title"))
            if title:
                meta["title"] = title
                text = json.dumps(meta, ensure_ascii=False, indent=2)
            if mj.read_text(encoding="utf-8") != text:
                mj.write_text(text, encoding="utf-8")
    for e in errors:
        log(f"  ⚠️ {e}")


def unpatch_frames():
    for name in FRAMES:
        js, backup = FRAME_DIR / name / "main.js", ORIG_DIR / name
        if js.exists() and js.read_text(encoding="utf-8").startswith(MARK) and (backup / "main.js").exists():
            shutil.copy2(backup / "main.js", js)
            if (backup / "mod.json").exists():
                shutil.copy2(backup / "mod.json", FRAME_DIR / name / "mod.json")


# ───────────── mods（侧边栏、标签栏等） ─────────────

def remove_mod_clones():
    if current_layout() == LANG_LAYOUT:
        do("layout.switch", {"name": BASE_LAYOUT})
        time.sleep(0.5)
    for m in MODS:
        d = MODS_DIR / (m + SUFFIX)
        if d.is_dir():
            shutil.rmtree(d)
    f = LAYOUTS_DIR / f"{LANG_LAYOUT}.json"
    if f.exists():
        f.unlink()


def build_mods(code):
    """按语言重新复制并翻译 mod，生成 main-i18n 布局并切换过去。"""
    pack = pack_for(code)
    table = pack["mods"]
    keep = set(table.get("keep_english", []))
    remove_mod_clones()

    names = "|".join(re.escape(m) for m in MODS)
    for m in MODS:
        if not (MODS_DIR / m).is_dir():
            continue
        do("mod.clone", {"name": m, "as": m + SUFFIX})
        d = MODS_DIR / (m + SUFFIX)
        wait_for(d / "main.js")
        js = d / "main.js"
        src = js.read_text(encoding="utf-8")
        # mod 之间互相打开的弹窗也指向翻译过的副本
        src = re.sub(rf'((?:mod|name):\s*)"({names})"', rf'\1"\2{SUFFIX}"', src)
        js.write_text(translate(src, table, keep), encoding="utf-8")
        mj = d / "mod.json"
        if mj.exists():
            meta = json.loads(mj.read_text(encoding="utf-8"))
            if meta.get("title") in table.get("titles", {}):
                meta["title"] = table["titles"][meta["title"]]
                mj.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    do("layout.clone", {"name": BASE_LAYOUT, "as": LANG_LAYOUT})  # 会自动切换过去
    lf = LAYOUTS_DIR / f"{LANG_LAYOUT}.json"
    wait_for(lf)
    layout = json.loads(lf.read_text(encoding="utf-8"))

    def walk(node):
        if isinstance(node, dict):
            if node.get("mod") in MODS:
                node["mod"] += SUFFIX
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(layout)
    layout["terminal_menu"] = "menu" + SUFFIX
    lf.write_text(json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    cfg["mods_built"] = {"lang": code, "app": app_version()}
    save_config(cfg)


def check_mods():
    bad = []
    for m in MODS:
        d = MODS_DIR / (m + SUFFIX)
        if d.is_dir():
            r = run_app("check", str(d), check=False)
            if r.returncode != 0:
                bad.append(f"{m}{SUFFIX}: {(r.stdout + r.stderr).strip()}")
    return bad


def apply_mods(code, force=False):
    if code == "en":
        if current_layout() == LANG_LAYOUT:
            do("layout.switch", {"name": BASE_LAYOUT})
        return
    built = load_config().get("mods_built") or {}
    fresh = built.get("lang") == code and built.get("app") == app_version() \
        and (LAYOUTS_DIR / f"{LANG_LAYOUT}.json").exists()
    if force or not fresh:
        build_mods(code)
    elif current_layout() == BASE_LAYOUT:
        do("layout.switch", {"name": LANG_LAYOUT})


# ───────────── 后台任务 ─────────────

def install_agent():
    watch = "".join(f"\n    <string>{FRAME_DIR / n / 'main.js'}</string>" for n in FRAMES)
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{AGENT_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string><string>-I</string><string>{ENGINE}</string><string>frame</string>
  </array>
  <key>WatchPaths</key>
  <array>{watch}
  </array>
  <key>RunAtLoad</key><true/>
  <key>ThrottleInterval</key><integer>2</integer>
  <key>StandardOutPath</key><string>{LOG}</string>
  <key>StandardErrorPath</key><string>{LOG}</string>
</dict>
</plist>
"""
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", f"{domain}/{AGENT_LABEL}"], capture_output=True)
    AGENT_PLIST.parent.mkdir(parents=True, exist_ok=True)
    AGENT_PLIST.write_text(plist, encoding="utf-8")
    subprocess.run(["launchctl", "bootstrap", domain, str(AGENT_PLIST)], capture_output=True)


def uninstall_agent():
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{AGENT_LABEL}"], capture_output=True)
    if AGENT_PLIST.exists():
        AGENT_PLIST.unlink()


# ───────────── 命令 ─────────────

def locked(fn):
    """同一时间只跑一个（设置页切换和后台任务可能同时触发）。"""
    def wrapper(*a, **kw):
        INSTALL_DIR.mkdir(parents=True, exist_ok=True)
        with open(INSTALL_DIR / ".lock", "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            return fn(*a, **kw)
    return wrapper


def cmd_install(code="zh-CN"):
    src_dir = Path(__file__).resolve().parent
    if not HERDR_APP.exists():
        raise SystemExit(f"找不到 {HERDR_APP}，请先安装 Herdr 桌面端。")
    pack_for(code)  # 先确认语言包存在
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    if src_dir != INSTALL_DIR:
        shutil.copy2(src_dir / "herdr_lang.py", ENGINE)
        if LANG_DIR.exists():
            shutil.rmtree(LANG_DIR)
        shutil.copytree(src_dir / "lang", LANG_DIR)
    if not wait_app(start=True):
        raise SystemExit("Herdr 没有启动起来，请手动打开 Herdr 后再运行。")
    cfg = load_config()
    cfg.pop("mods_built", None)  # 重新安装时强制重建（语言包可能更新了）
    save_config(cfg)
    cmd_set(code, force=True)
    install_agent()
    log(f"✅ 插件已安装，当前语言：{code}。以后可在「设置 › 外观 › 语言」里切换。")


@locked
def cmd_set(code, force=False):
    pack_for(code)
    cfg = load_config()
    cfg["lang"] = code
    save_config(cfg)
    patch_frames(code)
    if wait_app(start=False, seconds=20):
        apply_mods(code, force=force)
        bad = check_mods() if code != "en" else []
        for b in bad:
            log(f"  ⚠️ {b}")
        reopen_settings()
    log(f"语言已切换为 {code}")


def reopen_settings():
    """打开着的设置页不会重新加载文件，关掉再打开才能看到新语言。"""
    try:
        overlays = json.loads(run_app("status").stdout).get("overlays", [])
    except (json.JSONDecodeError, SystemExit):
        return
    if "frame-settings" in overlays:
        do("overlay.close", {"id": "frame-settings"})
        time.sleep(0.3)
        do("app.settings", {"section": "look"})


@locked
def cmd_frame():
    """后台任务：frame 被 Herdr 重写后重新注入；Herdr 升级后顺便重建 mod 翻译。"""
    code = load_config().get("lang", "en")
    patch_frames(code)
    if code != "en" and wait_app(start=False, seconds=30):
        built = load_config().get("mods_built") or {}
        if built.get("app") != app_version() or built.get("lang") != code:
            log(f"{time.strftime('%F %T')} Herdr 版本变了，重建 mod 翻译")
            build_mods(code)


def cmd_uninstall():
    uninstall_agent()
    unpatch_frames()
    if wait_app(start=False, seconds=5):
        remove_mod_clones()
    else:
        for m in MODS:
            shutil.rmtree(MODS_DIR / (m + SUFFIX), ignore_errors=True)
        (LAYOUTS_DIR / f"{LANG_LAYOUT}.json").unlink(missing_ok=True)
    shutil.rmtree(INSTALL_DIR, ignore_errors=True)
    log("✅ 插件已卸载，Herdr 恢复原版英文。")


def cmd_status():
    cfg = load_config()
    log(f"已安装：{'是' if ENGINE.exists() else '否'}（{INSTALL_DIR}）")
    log(f"当前语言：{cfg.get('lang', 'en')}")
    log(f"可用语言：en, {', '.join(packs())}")
    log(f"后台任务：{'已加载' if subprocess.run(['launchctl', 'list', AGENT_LABEL], capture_output=True).returncode == 0 else '未加载'}")
    log(f"Herdr 版本：{app_version()}，mod 翻译基于：{cfg.get('mods_built')}")


if __name__ == "__main__":
    args = sys.argv[1:] or ["install"]
    cmd, rest = args[0], args[1:]
    if cmd == "install":
        cmd_install(*(rest[:1] or ["zh-CN"]))
    elif cmd == "set" and rest:
        cmd_set(rest[0])
    elif cmd == "frame":
        cmd_frame()
    elif cmd == "uninstall":
        cmd_uninstall()
    elif cmd == "status":
        cmd_status()
    else:
        print(__doc__)
