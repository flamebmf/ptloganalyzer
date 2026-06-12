-- Local admin user with fixed password for management
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'pgadmin') THEN
    CREATE ROLE pgadmin WITH LOGIN SUPERUSER PASSWORD 'ptlog_admin_2024';
  END IF;
END
$$;
