CREATE OR ALTER PROCEDURE [sde].[ORG_GrantPermissions]
AS
BEGIN
    DECLARE @TableName NVARCHAR(256);
    DECLARE @PrincipalName NVARCHAR(128);
    DECLARE @MissingGrant NVARCHAR(MAX);
    DECLARE @Sql NVARCHAR(MAX);
    DECLARE @PermissionList NVARCHAR(MAX);

    BEGIN TRY
        BEGIN TRANSACTION;

        -- Cursor to loop through all relevant tables
        DECLARE table_cursor CURSOR FOR
        SELECT /* o.name AS TableName, dp.name AS PrincipalName, 
               CASE dp.name
                   WHEN 'data editor' THEN 'DELETE, EXECUTE, INSERT, SELECT, UPDATE'
                   WHEN 'data creator' THEN 'DELETE, EXECUTE, INSERT, SELECT, UPDATE'
                   WHEN 'data viewer' THEN 'SELECT'
               END AS PermissionList */
    'GRANT ' + 
    CASE dp.name
        WHEN 'data editor' THEN 'DELETE, INSERT, SELECT, UPDATE'
        WHEN 'data creator' THEN 'DELETE, INSERT, SELECT, UPDATE'
        WHEN 'data viewer' THEN 'SELECT'
    END + 
    ' ON OBJECT::[' + s.name + '].[' + o.name + '] TO [' + dp.name + '];' AS MissingGrant
        FROM sys.objects o
        INNER JOIN sys.schemas s ON o.schema_id = s.schema_id
        CROSS JOIN (SELECT name, principal_id FROM sys.database_principals 
                    WHERE name IN ('data viewer', 'data creator', 'data editor')) dp
        WHERE o.type = 'U' -- User tables only
        AND o.name NOT LIKE 'SDE_%' 
        AND o.name NOT LIKE 'i_%' 
        AND o.name NOT LIKE 'a_%' 
        AND o.name NOT LIKE 'D_%' 
        AND o.name NOT LIKE 'GDB_%' 
        AND o.name NOT LIKE 'sys%'
        AND NOT EXISTS (
            SELECT 1
            FROM sys.database_permissions p
            WHERE p.major_id = o.object_id
            AND p.grantee_principal_id = dp.principal_id
        )
        ORDER BY o.name;

        -- Open the cursor
        OPEN table_cursor;
        
        -- Fetch the first row
        FETCH NEXT FROM table_cursor INTO @MissingGrant; -- @TableName, @PrincipalName, @PermissionList;

        -- Loop through all tables
        WHILE @@FETCH_STATUS = 0
        BEGIN
            -- SET @Sql = 'GRANT ' + @PermissionList + ' ON OBJECT::[' + @TableName + '] TO [' + @PrincipalName + '];';
            SET @Sql = @MissingGrant;
            EXEC sp_executesql @Sql;

            -- Fetch the next row
            FETCH NEXT FROM table_cursor INTO @MissingGrant; --  @TableName, @PrincipalName, @PermissionList;
        END

        -- Close and deallocate the cursor
        CLOSE table_cursor;
        DEALLOCATE table_cursor;

        -- Commit the transaction if everything is successful
        IF XACT_STATE() = 1
        BEGIN
            COMMIT TRANSACTION;
        END
    END TRY
    BEGIN CATCH
		-- Rollback the transaction if there was an error
		IF XACT_STATE() <> 0
		BEGIN
			ROLLBACK TRANSACTION;
		END
        -- If the cursor is open, close and deallocate it
        IF CURSOR_STATUS('global', 'table_cursor') >= 0
        BEGIN
            CLOSE table_cursor;
            DEALLOCATE table_cursor;
        END
		DECLARE @ErrorMessage NVARCHAR(4000), @ErrorSeverity INT, @ErrorState INT, @ErrorProcedure NVARCHAR(200);
		SELECT 
			@ErrorSeverity = ERROR_SEVERITY(),
			@ErrorState = ERROR_STATE(),
			@ErrorProcedure = ISNULL(ERROR_PROCEDURE(), 'N/A'),
			@ErrorMessage = SUBSTRING('Error in Procedure ''' + @ErrorProcedure + ''' Line ' + CAST(ERROR_LINE() AS NVARCHAR(10)) + ': ' + ERROR_MESSAGE() + ' ****** ' + @sql, 0, 4000);
		RAISERROR (@ErrorMessage, @ErrorSeverity, @ErrorState);
    END CATCH
END;