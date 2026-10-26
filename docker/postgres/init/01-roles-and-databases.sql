-- Runs once, when the Postgres data volume is empty (docker-entrypoint-initdb.d).
-- In production run it manually as a superuser:
--   UNICODE_OWNER_PASSWORD=... UNICODE_DAEMON_PASSWORD=... UNICODE_PANEL_PASSWORD=... \
--   psql -v ON_ERROR_STOP=1 -U postgres -f 01-roles-and-databases.sql

\getenv owner_password UNICODE_OWNER_PASSWORD
\getenv daemon_password UNICODE_DAEMON_PASSWORD
\getenv panel_password UNICODE_PANEL_PASSWORD

-- Owner of the databases; runs migrations. Never used by the running application.
CREATE ROLE unicode_owner LOGIN PASSWORD :'owner_password';
-- Used only by unicode-daemon (read/write, privileges granted by migrations).
CREATE ROLE unicode_daemon LOGIN PASSWORD :'daemon_password';
-- Used only by the teacher web panel (read-only, privileges granted by migrations).
CREATE ROLE unicode_panel LOGIN PASSWORD :'panel_password';

CREATE DATABASE unicode OWNER unicode_owner;
CREATE DATABASE unicode_test OWNER unicode_owner;

REVOKE ALL ON DATABASE unicode FROM PUBLIC;
REVOKE ALL ON DATABASE unicode_test FROM PUBLIC;
GRANT CONNECT ON DATABASE unicode TO unicode_daemon, unicode_panel;
GRANT CONNECT ON DATABASE unicode_test TO unicode_daemon, unicode_panel;
