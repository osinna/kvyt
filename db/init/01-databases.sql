-- Creates one Postgres user per service and one database per service.
-- Each service user has access only to its own database.

CREATE USER identity_user WITH PASSWORD 'identity_pass';
CREATE USER catalog_user  WITH PASSWORD 'catalog_pass';
CREATE USER booking_user  WITH PASSWORD 'booking_pass';

CREATE DATABASE identity OWNER identity_user;
CREATE DATABASE catalog  OWNER catalog_user;
CREATE DATABASE booking  OWNER booking_user;

REVOKE ALL ON DATABASE identity FROM PUBLIC;
REVOKE ALL ON DATABASE catalog  FROM PUBLIC;
REVOKE ALL ON DATABASE booking  FROM PUBLIC;

GRANT CONNECT ON DATABASE identity TO identity_user;
GRANT CONNECT ON DATABASE catalog  TO catalog_user;
GRANT CONNECT ON DATABASE booking  TO booking_user;
