#!/bin/zsh
cd -- "${0:A:h}"
/usr/bin/python3 plugin-manager/build_desktop.py || exit 1
open 'Herdr 插件管理.app'
