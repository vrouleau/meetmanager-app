#!/bin/sh
set -e
# Substitute only ${PORT} — leaves nginx variables ($host, $uri, etc.) untouched
envsubst '${PORT} ${BACKEND_URL}' < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf
exec nginx -g 'daemon off;'
