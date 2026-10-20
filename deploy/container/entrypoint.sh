#!/bin/sh
# Entropy container entrypoint.
#   serve (default)   initialize the volume if needed, then run the web server
#   init              initialize or migrate the volume only
#   ent ...           the Entropy command line, e.g. `ent user list`
#   anything else     run it (e.g. bash)
set -e

# OpenShift's arbitrary UID has no passwd entry; ssh and git need one.
if ! whoami >/dev/null 2>&1 && [ -w /etc/passwd ]; then
    echo "entropy:x:$(id -u):0:Entropy:${HOME}:/bin/bash" >> /etc/passwd
fi

case "${1:-serve}" in
    serve|init) exec python3 -m lib.install.container "${1:-serve}" ;;
    ent) shift; exec /usr/local/bin/ent "$@" ;;
    *) exec "$@" ;;
esac
