#!/bin/zsh
# 双击卸载 herdr-lang 语言插件，Herdr 恢复原版英文
/usr/bin/python3 -I "$HOME/.local/share/herdr-lang/herdr_lang.py" uninstall 2>/dev/null || /usr/bin/python3 -I "$(dirname "$0")/herdr_lang.py" uninstall
echo; read "?按回车关闭窗口…"
