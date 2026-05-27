/*
	- Run as user: dbadmin
	- Do not forget to change the password: MYPASSWORD
*/
/* USE [ORG_WS]
GO
CREATE SCHEMA [specific_user_name];
GO
GRANT SELECT                            ON SCHEMA::specific_user_name TO [data viewer];
GRANT SELECT, INSERT, UPDATE, DELETE, ALTER, EXECUTE, REFERENCES, VIEW DEFINITION    ON SCHEMA::specific_user_name TO [data editor];
GRANT SELECT, INSERT, UPDATE, DELETE, ALTER, EXECUTE, REFERENCES, VIEW DEFINITION    ON SCHEMA::specific_user_name TO [data creator];
GO

USE [master]
GO
CREATE LOGIN [specific_user_name] WITH PASSWORD=N'MYPASSWORD', DEFAULT_DATABASE=[ORG_WS], DEFAULT_LANGUAGE=[us_english], CHECK_EXPIRATION=OFF, CHECK_POLICY=ON
GO

USE [ORG_WS]
GO
CREATE USER [specific_user_name] FOR LOGIN [specific_user_name] WITH DEFAULT_SCHEMA=[specific_user_name]
GO
USE [ORG_WS]
GO
ALTER ROLE [data creator] ADD MEMBER [specific_user_name]
GO

ALTER AUTHORIZATION ON SCHEMA::specific_user_name TO specific_user_name;
GO


GRANT SELECT, INSERT, UPDATE, DELETE, ALTER, EXECUTE, REFERENCES, VIEW DEFINITION ON SCHEMA::sde TO [data creator];
GO
GRANT SELECT, INSERT, UPDATE, DELETE, ALTER, EXECUTE, REFERENCES, VIEW DEFINITION ON SCHEMA::sde TO [data editor];
GO


GRANT CREATE TABLE TO [data creator];
GRANT CREATE PROCEDURE   TO [data creator];
GRANT CREATE VIEW        TO [data creator];
GO
*/


/*
  CreateDBSchema.sql
  - Improved, idempotent and defensive script to create schema, login and user.
  
  Usage notes:
  - If you run this file directly with sqlcmd you can set variables with -v, e.g.
	sqlcmd -S servername -i CreateDBSchema.sql -v DBName="ORG_WS" SchemaName="general" Password="MySecret"

  Variables:
	$(DBName)      - target database name (default: ORG_WS)
	$(SchemaName)  - schema name (default: general)
	$(UserPassword)    - password for new login
*/

SET NOCOUNT ON;

DECLARE @DBName sysname = N'ORG_DB2';
DECLARE @SchemaName sysname = N'general';
DECLARE @UserPassword nvarchar(256) = N'';

BEGIN TRY
	BEGIN TRANSACTION;

	PRINT N'==> Starting CreateDBSchema transaction for database ' + @DBName + ' and schema ' + @SchemaName;

	-- Validate database exists
	IF DB_ID(@DBName) IS NULL
	BEGIN
		DECLARE @throwMsg nvarchar(400) = N'Target database "' + @DBName + N'" not found on this server.';
		THROW 51000, @throwMsg, 1;
	END

	-- Create schema if it doesn't exist (in target database)
	PRINT N'==> Ensuring schema ' + @SchemaName + ' exists in database ' + @DBName;
	DECLARE @createSchemaSql nvarchar(max) = N'USE ' + QUOTENAME(@DBName) + N';' + CHAR(13)+CHAR(10)
		+ N'IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N''' + REPLACE(@SchemaName, '''', '''''') + N''')' + CHAR(13)+CHAR(10)
		+ N'    EXEC(''CREATE SCHEMA ' + QUOTENAME(@SchemaName) + N' AUTHORIZATION sde'');' + CHAR(13)+CHAR(10);
	EXEC sp_executesql @createSchemaSql;

	-- Create server login if not exists (on master)
	PRINT N'==> Checking/creating server login ' + @SchemaName + ' on instance (master)';
	IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = @SchemaName)
	BEGIN
		DECLARE @createLogin nvarchar(max);
		SET @createLogin = N'CREATE LOGIN ' + QUOTENAME(@SchemaName)
			+ N' WITH PASSWORD = N''' + REPLACE(@UserPassword, '''', '''''') + N''''
			+ N', DEFAULT_DATABASE=' + QUOTENAME(@DBName)
			+ N', DEFAULT_LANGUAGE=[us_english], CHECK_EXPIRATION=OFF, CHECK_POLICY=ON';
		EXEC(@createLogin);
	END

	-- Create database user mapped to the login (in target DB)
	PRINT N'==> Ensuring database user ' + @SchemaName + ' exists in database ' + @DBName + ' and is mapped to login ' + @SchemaName;
	DECLARE @createUserSql nvarchar(max) = N'USE ' + QUOTENAME(@DBName) + N';' + CHAR(13)+CHAR(10)
		+ N'IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N''' + REPLACE(@SchemaName, '''', '''''') + N''')' + CHAR(13)+CHAR(10)
		+ N'    CREATE USER ' + QUOTENAME(@SchemaName) + N' FOR LOGIN ' + QUOTENAME(@SchemaName) + N' WITH DEFAULT_SCHEMA=' + QUOTENAME(@SchemaName) + N';' + CHAR(13)+CHAR(10)
		+ N'ELSE' + CHAR(13)+CHAR(10)
		+ N'    ALTER USER ' + QUOTENAME(@SchemaName) + N' WITH DEFAULT_SCHEMA=' + QUOTENAME(@SchemaName) + N';' + CHAR(13)+CHAR(10);
	EXEC sp_executesql @createUserSql;

	-- Ensure schema ownership is set to the new user (only if different)
	PRINT N'==> Checking and updating schema owner for ' + @SchemaName + ' if required';
	DECLARE @alterAuthSql nvarchar(max) = N'USE ' + QUOTENAME(@DBName) + N';' + CHAR(13)+CHAR(10)
		+ N'IF EXISTS (SELECT 1 FROM sys.schemas WHERE name = N''' + REPLACE(@SchemaName, '''', '''''') + N''')' + CHAR(13)+CHAR(10)
		+ N'BEGIN' + CHAR(13)+CHAR(10)
		+ N'    DECLARE @owner_pid int = (SELECT principal_id FROM sys.schemas WHERE name = N''' + REPLACE(@SchemaName, '''', '''''') + N''');' + CHAR(13)+CHAR(10)
		+ N'    DECLARE @user_pid int = (SELECT principal_id FROM sys.database_principals WHERE name = N''' + REPLACE(@SchemaName, '''', '''''') + N''');' + CHAR(13)+CHAR(10)
		+ N'    IF @owner_pid IS NULL OR @owner_pid <> @user_pid' + CHAR(13)+CHAR(10)
		+ N'    BEGIN' + CHAR(13)+CHAR(10)
		+ N'        EXEC(''ALTER AUTHORIZATION ON SCHEMA::' + QUOTENAME(@SchemaName) + N' TO ' + QUOTENAME(@SchemaName) + N''');' + CHAR(13)+CHAR(10)
		+ N'    END' + CHAR(13)+CHAR(10)
		+ N'END' + CHAR(13)+CHAR(10);
	EXEC sp_executesql @alterAuthSql;

	-- Add user to role [data creator]
	PRINT N'==> Adding ' + @SchemaName + ' to database role [data creator] if not already a member';
	DECLARE @addRoleSql nvarchar(max) = N'USE ' + QUOTENAME(@DBName) + N';' + CHAR(13)+CHAR(10)
		+ N'IF NOT EXISTS (SELECT 1 FROM sys.database_principals dp JOIN sys.database_role_members drm ON dp.principal_id = drm.role_principal_id WHERE dp.name = N''data creator'' AND drm.member_principal_id = USER_ID(N''' + REPLACE(@SchemaName, '''', '''''') + N'''))' + CHAR(13)+CHAR(10)
		+ N'    EXEC(''ALTER ROLE [data creator] ADD MEMBER ' + QUOTENAME(@SchemaName) + N''');' + CHAR(13)+CHAR(10);
	EXEC sp_executesql @addRoleSql;

	-- Grant schema-level permissions
	PRINT N'==> Granting schema-level permissions for ' + @SchemaName;
	DECLARE @grantSql nvarchar(max) = N'USE ' + QUOTENAME(@DBName) + N';' + CHAR(13)+CHAR(10)
		+ N'GRANT SELECT ON SCHEMA::' + QUOTENAME(@SchemaName) + N' TO [data viewer];' + CHAR(13)+CHAR(10)
		+ N'GRANT SELECT, INSERT, UPDATE, DELETE, ALTER, EXECUTE, REFERENCES, VIEW DEFINITION ON SCHEMA::' + QUOTENAME(@SchemaName) + N' TO [data editor];' + CHAR(13)+CHAR(10)
		+ N'GRANT SELECT, INSERT, UPDATE, DELETE, ALTER, EXECUTE, REFERENCES, VIEW DEFINITION ON SCHEMA::' + QUOTENAME(@SchemaName) + N' TO [data creator];' + CHAR(13)+CHAR(10);
	EXEC sp_executesql @grantSql;

	-- Grant some sde permissions to data creator/editor as in original script
	PRINT N'==> Granting sde schema permissions to [data creator] and [data editor] (only if missing)';
	-- schema permissions to check
	DECLARE @perm sysname;
	-- data creator
	SET @perm = N'SELECT';
	IF NOT EXISTS (SELECT 1 FROM sys.database_permissions p WHERE p.class = 3 AND p.major_id = SCHEMA_ID(N'sde') AND p.permission_name = @perm AND p.grantee_principal_id = DATABASE_PRINCIPAL_ID(N'data creator'))
		EXEC sp_executesql N'GRANT SELECT ON SCHEMA::sde TO [data creator];';
	SET @perm = N'INSERT';
	IF NOT EXISTS (SELECT 1 FROM sys.database_permissions p WHERE p.class = 3 AND p.major_id = SCHEMA_ID(N'sde') AND p.permission_name = @perm AND p.grantee_principal_id = DATABASE_PRINCIPAL_ID(N'data creator'))
		EXEC sp_executesql N'GRANT INSERT ON SCHEMA::sde TO [data creator];';
	SET @perm = N'UPDATE';
	IF NOT EXISTS (SELECT 1 FROM sys.database_permissions p WHERE p.class = 3 AND p.major_id = SCHEMA_ID(N'sde') AND p.permission_name = @perm AND p.grantee_principal_id = DATABASE_PRINCIPAL_ID(N'data creator'))
		EXEC sp_executesql N'GRANT UPDATE ON SCHEMA::sde TO [data creator];';
	SET @perm = N'DELETE';
	IF NOT EXISTS (SELECT 1 FROM sys.database_permissions p WHERE p.class = 3 AND p.major_id = SCHEMA_ID(N'sde') AND p.permission_name = @perm AND p.grantee_principal_id = DATABASE_PRINCIPAL_ID(N'data creator'))
		EXEC sp_executesql N'GRANT DELETE ON SCHEMA::sde TO [data creator];';
	SET @perm = N'ALTER';
	IF NOT EXISTS (SELECT 1 FROM sys.database_permissions p WHERE p.class = 3 AND p.major_id = SCHEMA_ID(N'sde') AND p.permission_name = @perm AND p.grantee_principal_id = DATABASE_PRINCIPAL_ID(N'data creator'))
		EXEC sp_executesql N'GRANT ALTER ON SCHEMA::sde TO [data creator];';
	SET @perm = N'EXECUTE';
	IF NOT EXISTS (SELECT 1 FROM sys.database_permissions p WHERE p.class = 3 AND p.major_id = SCHEMA_ID(N'sde') AND p.permission_name = @perm AND p.grantee_principal_id = DATABASE_PRINCIPAL_ID(N'data creator'))
		EXEC sp_executesql N'GRANT EXECUTE ON SCHEMA::sde TO [data creator];';
	SET @perm = N'REFERENCES';
	IF NOT EXISTS (SELECT 1 FROM sys.database_permissions p WHERE p.class = 3 AND p.major_id = SCHEMA_ID(N'sde') AND p.permission_name = @perm AND p.grantee_principal_id = DATABASE_PRINCIPAL_ID(N'data creator'))
		EXEC sp_executesql N'GRANT REFERENCES ON SCHEMA::sde TO [data creator];';
	SET @perm = N'VIEW DEFINITION';
	IF NOT EXISTS (SELECT 1 FROM sys.database_permissions p WHERE p.class = 3 AND p.major_id = SCHEMA_ID(N'sde') AND p.permission_name = @perm AND p.grantee_principal_id = DATABASE_PRINCIPAL_ID(N'data creator'))
		EXEC sp_executesql N'GRANT VIEW DEFINITION ON SCHEMA::sde TO [data creator];';

	-- data editor (grant a subset or matching set as appropriate)
	SET @perm = N'SELECT';
	IF NOT EXISTS (SELECT 1 FROM sys.database_permissions p WHERE p.class = 3 AND p.major_id = SCHEMA_ID(N'sde') AND p.permission_name = @perm AND p.grantee_principal_id = DATABASE_PRINCIPAL_ID(N'data editor'))
		EXEC sp_executesql N'GRANT SELECT ON SCHEMA::sde TO [data editor];';
	SET @perm = N'INSERT';
	IF NOT EXISTS (SELECT 1 FROM sys.database_permissions p WHERE p.class = 3 AND p.major_id = SCHEMA_ID(N'sde') AND p.permission_name = @perm AND p.grantee_principal_id = DATABASE_PRINCIPAL_ID(N'data editor'))
		EXEC sp_executesql N'GRANT INSERT ON SCHEMA::sde TO [data editor];';
	SET @perm = N'UPDATE';
	IF NOT EXISTS (SELECT 1 FROM sys.database_permissions p WHERE p.class = 3 AND p.major_id = SCHEMA_ID(N'sde') AND p.permission_name = @perm AND p.grantee_principal_id = DATABASE_PRINCIPAL_ID(N'data editor'))
		EXEC sp_executesql N'GRANT UPDATE ON SCHEMA::sde TO [data editor];';
	SET @perm = N'DELETE';
	IF NOT EXISTS (SELECT 1 FROM sys.database_permissions p WHERE p.class = 3 AND p.major_id = SCHEMA_ID(N'sde') AND p.permission_name = @perm AND p.grantee_principal_id = DATABASE_PRINCIPAL_ID(N'data editor'))
		EXEC sp_executesql N'GRANT DELETE ON SCHEMA::sde TO [data editor];';
	SET @perm = N'ALTER';
	IF NOT EXISTS (SELECT 1 FROM sys.database_permissions p WHERE p.class = 3 AND p.major_id = SCHEMA_ID(N'sde') AND p.permission_name = @perm AND p.grantee_principal_id = DATABASE_PRINCIPAL_ID(N'data editor'))
		EXEC sp_executesql N'GRANT ALTER ON SCHEMA::sde TO [data editor];';
	SET @perm = N'EXECUTE';
	IF NOT EXISTS (SELECT 1 FROM sys.database_permissions p WHERE p.class = 3 AND p.major_id = SCHEMA_ID(N'sde') AND p.permission_name = @perm AND p.grantee_principal_id = DATABASE_PRINCIPAL_ID(N'data editor'))
		EXEC sp_executesql N'GRANT EXECUTE ON SCHEMA::sde TO [data editor];';
	SET @perm = N'REFERENCES';
	IF NOT EXISTS (SELECT 1 FROM sys.database_permissions p WHERE p.class = 3 AND p.major_id = SCHEMA_ID(N'sde') AND p.permission_name = @perm AND p.grantee_principal_id = DATABASE_PRINCIPAL_ID(N'data editor'))
		EXEC sp_executesql N'GRANT REFERENCES ON SCHEMA::sde TO [data editor];';
	SET @perm = N'VIEW DEFINITION';
	IF NOT EXISTS (SELECT 1 FROM sys.database_permissions p WHERE p.class = 3 AND p.major_id = SCHEMA_ID(N'sde') AND p.permission_name = @perm AND p.grantee_principal_id = DATABASE_PRINCIPAL_ID(N'data editor'))
		EXEC sp_executesql N'GRANT VIEW DEFINITION ON SCHEMA::sde TO [data editor];';

	-- Database-level create permissions
	PRINT N'==> Granting database-level create permissions to [data creator] and [data editor] (only if missing)';
	-- for each permission check and grant per role
	IF NOT EXISTS (SELECT 1 FROM sys.database_permissions p WHERE p.class = 0 AND p.permission_name = N'CREATE TABLE' AND p.grantee_principal_id = DATABASE_PRINCIPAL_ID(N'data creator'))
		EXEC sp_executesql N'GRANT CREATE TABLE TO [data creator];';
	IF NOT EXISTS (SELECT 1 FROM sys.database_permissions p WHERE p.class = 0 AND p.permission_name = N'CREATE PROCEDURE' AND p.grantee_principal_id = DATABASE_PRINCIPAL_ID(N'data creator'))
		EXEC sp_executesql N'GRANT CREATE PROCEDURE TO [data creator];';
	IF NOT EXISTS (SELECT 1 FROM sys.database_permissions p WHERE p.class = 0 AND p.permission_name = N'CREATE VIEW' AND p.grantee_principal_id = DATABASE_PRINCIPAL_ID(N'data creator'))
		EXEC sp_executesql N'GRANT CREATE VIEW TO [data creator];';
	IF NOT EXISTS (SELECT 1 FROM sys.database_permissions p WHERE p.class = 0 AND p.permission_name = N'CREATE TABLE' AND p.grantee_principal_id = DATABASE_PRINCIPAL_ID(N'data editor'))
		EXEC sp_executesql N'GRANT CREATE TABLE TO [data editor];';
	IF NOT EXISTS (SELECT 1 FROM sys.database_permissions p WHERE p.class = 0 AND p.permission_name = N'CREATE PROCEDURE' AND p.grantee_principal_id = DATABASE_PRINCIPAL_ID(N'data editor'))
		EXEC sp_executesql N'GRANT CREATE PROCEDURE TO [data editor];';
	IF NOT EXISTS (SELECT 1 FROM sys.database_permissions p WHERE p.class = 0 AND p.permission_name = N'CREATE VIEW' AND p.grantee_principal_id = DATABASE_PRINCIPAL_ID(N'data editor'))
		EXEC sp_executesql N'GRANT CREATE VIEW TO [data editor];';

	COMMIT TRANSACTION;

	PRINT 'Schema and user creation completed successfully.';
	PRINT '';

	PRINT '**** NEXT STEPS: ****';
	PRINT '- Create an ArcGIS connection file using the new schema and credentials. (See CreateSDEFiles.py script)';
	PRINT '- Register the database as a Site Data Store in ArcGIS Server Manager.';
END TRY
BEGIN CATCH
	IF XACT_STATE() <> 0
	BEGIN
		ROLLBACK TRANSACTION;
	END
	DECLARE @ErrMsg nvarchar(4000) = ERROR_MESSAGE();
	DECLARE @ErrNum int = ERROR_NUMBER();
	DECLARE @ErrState int = ERROR_STATE();
	RAISERROR('Error %d (state %d): %s', 16, 1, @ErrNum, @ErrState, @ErrMsg);
END CATCH

GO


