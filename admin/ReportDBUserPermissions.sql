/*
  ReportDBUserPermissions.sql
  - Report the current permissions of a database user (or role) in a SQL Server
    enterprise geodatabase: role memberships, permissions granted DIRECTLY to the
    principal, permissions INHERITED from its database roles, and (optionally) the
    NET EFFECTIVE permissions after inheritance and any DENYs.

  Why both direct and inherited: in this geodatabase, users like [cacao] get most of
  their rights from a role (e.g. [data creator]), not from direct grants - section 4
  is where those show up. See CreateDBSchema.sql / the migration plan for the model.

  Usage (SSMS):
    1. Change the USE line below to the target database.
    2. Set @principal to the user or role to inspect.
    3. Execute. You get one result set per section.

  Usage (sqlcmd / SQLCMD mode, optional):
    To parameterize from the command line, replace the @principal literal below with
    N'$(Principal)' and run in SQLCMD mode:
      sqlcmd -S <server> -d <DBName> -v Principal="cacao" -i ReportDBUserPermissions.sql
    (As written, the script uses the plain literal so it runs unchanged in normal SSMS.)

  Notes:
    - Section 5 (effective permissions) impersonates the principal via EXECUTE AS and
      requires IMPERSONATE on that user (a db_owner / the schema-creating login has it).
    - Permission classes reported: DATABASE (class 0), OBJECT_OR_COLUMN (1), SCHEMA (3).
*/

-- >>> EDIT: target database <<<
USE [NBS_WS];
GO

SET NOCOUNT ON;

-- >>> EDIT: principal and options <<<
DECLARE @principal    sysname = N'cacao';   -- user or role to inspect
DECLARE @schema       sysname = N'cacao';   -- schema to test in the optional effective-permissions section (5)
DECLARE @runEffective bit     = 1;          -- set 0 to skip section 5 (EXECUTE AS / IMPERSONATE)

IF DATABASE_PRINCIPAL_ID(@principal) IS NULL
BEGIN
    RAISERROR('Principal "%s" does not exist in database "%s".', 16, 1, @principal, DB_NAME());
    RETURN;
END

/* ============================================================
   1) Principal info.
   ============================================================ */
SELECT
    dp.name              AS principal_name,
    dp.type_desc         AS principal_type,
    dp.authentication_type_desc,
    dp.default_schema_name,
    dp.create_date
FROM sys.database_principals dp
WHERE dp.name = @principal;

/* ============================================================
   2) Database role memberships (recursive - catches nested roles).
   ============================================================ */
WITH membership AS (
    SELECT drm.member_principal_id, drm.role_principal_id
    FROM sys.database_role_members drm
    WHERE drm.member_principal_id = DATABASE_PRINCIPAL_ID(@principal)
    UNION ALL
    SELECT drm.member_principal_id, drm.role_principal_id
    FROM sys.database_role_members drm
    JOIN membership m ON drm.member_principal_id = m.role_principal_id
)
SELECT DISTINCT USER_NAME(m.role_principal_id) AS member_of_role
FROM membership m
ORDER BY member_of_role;

/* ============================================================
   3) Permissions granted DIRECTLY to the principal (all scopes).
   ============================================================ */
SELECT
    @principal                                   AS granted_to,
    perm.state_desc                              AS grant_state,   -- GRANT / DENY / GRANT_WITH_GRANT
    perm.permission_name,
    perm.class_desc,                                               -- DATABASE / SCHEMA / OBJECT_OR_COLUMN / ...
    CASE perm.class
        WHEN 0 THEN DB_NAME()
        WHEN 1 THEN QUOTENAME(SCHEMA_NAME(o.schema_id)) + N'.' + QUOTENAME(o.name)
                    + CASE WHEN perm.minor_id <> 0 THEN N'.' + COL_NAME(perm.major_id, perm.minor_id) ELSE N'' END
        WHEN 3 THEN N'SCHEMA::' + QUOTENAME(SCHEMA_NAME(perm.major_id))
        ELSE N'(class ' + CAST(perm.class AS varchar(10)) + N', major_id ' + CAST(perm.major_id AS varchar(10)) + N')'
    END                                          AS securable,
    CASE WHEN perm.class = 1 THEN o.type_desc END AS object_type
FROM sys.database_permissions perm
LEFT JOIN sys.objects o ON perm.class = 1 AND perm.major_id = o.object_id
WHERE perm.grantee_principal_id = DATABASE_PRINCIPAL_ID(@principal)
ORDER BY grant_state, perm.class_desc, securable, perm.permission_name;

/* ============================================================
   4) Permissions INHERITED via the principal's database roles.
   ============================================================ */
WITH membership AS (
    SELECT drm.role_principal_id
    FROM sys.database_role_members drm
    WHERE drm.member_principal_id = DATABASE_PRINCIPAL_ID(@principal)
    UNION ALL
    SELECT drm.role_principal_id
    FROM sys.database_role_members drm
    JOIN membership m ON drm.member_principal_id = m.role_principal_id
)
SELECT
    USER_NAME(perm.grantee_principal_id)         AS granted_to_role,
    perm.state_desc                              AS grant_state,
    perm.permission_name,
    perm.class_desc,
    CASE perm.class
        WHEN 0 THEN DB_NAME()
        WHEN 1 THEN QUOTENAME(SCHEMA_NAME(o.schema_id)) + N'.' + QUOTENAME(o.name)
                    + CASE WHEN perm.minor_id <> 0 THEN N'.' + COL_NAME(perm.major_id, perm.minor_id) ELSE N'' END
        WHEN 3 THEN N'SCHEMA::' + QUOTENAME(SCHEMA_NAME(perm.major_id))
        ELSE N'(class ' + CAST(perm.class AS varchar(10)) + N', major_id ' + CAST(perm.major_id AS varchar(10)) + N')'
    END                                          AS securable,
    CASE WHEN perm.class = 1 THEN o.type_desc END AS object_type
FROM sys.database_permissions perm
LEFT JOIN sys.objects o ON perm.class = 1 AND perm.major_id = o.object_id
WHERE perm.grantee_principal_id IN (SELECT role_principal_id FROM membership)
ORDER BY granted_to_role, grant_state, perm.class_desc, securable, perm.permission_name;

/* ============================================================
   5) NET EFFECTIVE permissions (after inheritance + DENYs), via EXECUTE AS.
      Requires IMPERSONATE on @principal. Set @runEffective = 0 to skip.
   ============================================================ */
IF @runEffective = 1
BEGIN
    DECLARE @sql nvarchar(max) =
        N'EXECUTE AS USER = ' + QUOTENAME(@principal, '''') + N';' + CHAR(13) +
        N'SELECT ''DATABASE'' AS scope, permission_name, state_desc' + CHAR(13) +
        N'  FROM sys.fn_my_permissions(NULL, ''DATABASE'') ORDER BY permission_name;' + CHAR(13) +
        N'SELECT ''SCHEMA::' + REPLACE(@schema, '''', '''''') + N''' AS scope, permission_name, state_desc' + CHAR(13) +
        N'  FROM sys.fn_my_permissions(' + QUOTENAME(@schema, '''') + N', ''SCHEMA'') ORDER BY permission_name;' + CHAR(13) +
        N'REVERT;';
    EXEC sys.sp_executesql @sql;
END
GO
