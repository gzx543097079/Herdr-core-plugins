#!/bin/zsh
cd "${0:A:h}"
/usr/bin/python3 install.py
echo '按任意键关闭窗口'
read -k 1
