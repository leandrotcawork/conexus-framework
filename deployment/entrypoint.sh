#!/bin/sh
set -e
# Fix Fly volume permissions — volume mounts as root, app runs as conexus
mkdir -p /data
chown -R conexus:conexus /data
exec gosu conexus "$@"
