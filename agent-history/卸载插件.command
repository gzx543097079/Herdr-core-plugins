#!/bin/zsh
cd -- "${0:A:h}/.."
/usr/bin/python3 plugin-manager/server.py --action history uninstall
result=$?
printf "\n按回车关闭窗口…"
read
exit $result
