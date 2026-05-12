#!/bin/sh
set -e
# Substitute only ${PORT} — leaves nginx variables ($host, $uri, etc.) untouched
envsubst '${PORT} ${BACKEND_HOST}' < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf
exec nginx -g 'daemon off;'
