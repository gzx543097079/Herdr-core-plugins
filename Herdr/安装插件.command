#!/bin/zsh
# 双击安装 herdr-lang 语言插件（默认切到简体中文）。改过语言包后再双击一次即可生效。
cd "$(dirname "$0")"
/usr/bin/python3 -I ./herdr_lang.py install zh-CN
echo; read "?按回车关闭窗口…"
