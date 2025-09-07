# docker/postgres/init.sql
-- Initialize the sermon processor database

-- Create extensions if available
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create database user if not exists
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'sermon_user') THEN
    CREATE ROLE sermon_user LOGIN PASSWORD 'sermon_default_pass';
  END IF;
END
$$;

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE sermon_processor TO sermon_user;
GRANT ALL ON SCHEMA public TO sermon_user;