#!/bin/sh
set -eu
while iptables -t nat -D OUTPUT -p tcp --dport 80 -j REDIRECT --to-port 8889 2>/dev/null; do :; done
while iptables -t nat -D OUTPUT -p tcp --dport 80 -m owner --uid-owner 0 -j REDIRECT --to-port 8888 2>/dev/null; do :; done
while iptables -t nat -D OUTPUT -p tcp --dport 80 -j REDIRECT --to-port 8888 2>/dev/null; do :; done
# Redirect only root-owned HTTP (curl). tinyproxy runs as user tinyproxy and must reach upstream directly.
iptables -t nat -A OUTPUT -p tcp --dport 80 -m owner --uid-owner 0 -j REDIRECT --to-port 8888
