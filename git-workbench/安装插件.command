#!/bin/zsh
cd -- "${0:A:h}/.."
/usr/bin/python3 plugin-manager/server.py --action git install
