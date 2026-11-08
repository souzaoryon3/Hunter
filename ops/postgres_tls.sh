#!/bin/sh
set -eu
cp /run/tls/server.key /var/lib/postgresql/server.key
cp /run/tls/server.crt /var/lib/postgresql/server.crt
chown postgres:postgres /var/lib/postgresql/server.key /var/lib/postgresql/server.crt
chmod 600 /var/lib/postgresql/server.key
exec docker-entrypoint.sh postgres -c ssl=on -c ssl_cert_file=/var/lib/postgresql/server.crt -c ssl_key_file=/var/lib/postgresql/server.key -c hba_file=/opt/hunter/pg_hba.conf
