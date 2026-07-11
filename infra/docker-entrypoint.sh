#!/bin/sh
set -eu

if [ "$(id -u)" = "0" ]; then
  chown paperlight:paperlight /data
  install -d -o paperlight -g paperlight /data/objects
  exec gosu paperlight "$@"
fi

exec "$@"
