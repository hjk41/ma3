#!/bin/sh
# Broken: redirects to wrong port (8889 instead of tinyproxy 8888)
iptables -t nat -A OUTPUT -p tcp --dport 80 -j REDIRECT --to-port 8889
