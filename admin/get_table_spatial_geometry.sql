-- Find SRID for every table with a geometry/geography column
DECLARE @sql NVARCHAR(MAX) = N'';

SELECT @sql = @sql + 
    'SELECT ' + 
    QUOTENAME(s.name + '.' + t.name, '''') + ' AS table_name, ' +
    QUOTENAME(c.name, '''') + ' AS geom_column, ' +
    QUOTENAME(ty.name, '''') + ' AS geom_type, ' +
    '(SELECT TOP 1 ' + QUOTENAME(c.name) + '.STSrid FROM ' + 
    QUOTENAME(s.name) + '.' + QUOTENAME(t.name) + 
    ' WHERE ' + QUOTENAME(c.name) + ' IS NOT NULL) AS srid ' +
    'UNION ALL '
FROM sys.columns c
JOIN sys.types ty ON c.user_type_id = ty.user_type_id
JOIN sys.tables t ON c.object_id = t.object_id
JOIN sys.schemas s ON t.schema_id = s.schema_id
WHERE ty.name IN ('geometry', 'geography');

-- Trim trailing UNION ALL
SET @sql = LEFT(@sql, LEN(@sql) - 10);

-- Add human-readable SRID name via CASE lookup
SET @sql = 'SELECT x.table_name, x.geom_column, x.geom_type, x.srid, ' +
           'CASE x.srid ' +
           '  WHEN 4326 THEN ''WGS 84'' ' +
           '  WHEN 3857 THEN ''WGS 84 Web Mercator'' ' +
           '  WHEN 102100 THEN ''WGS 84 / Pseudo-Mercator (Esri)'' ' +
           '  WHEN 4269 THEN ''NAD83'' ' +
           '  WHEN 4267 THEN ''NAD27'' ' +
           '  WHEN 32601 THEN ''WGS 84 / UTM zone 1N'' ' +
           '  WHEN 2193 THEN ''NZGD2000 / NZTM'' ' +
           '  WHEN 0 THEN ''No SRID set'' ' +
           '  ELSE ''SRID '' + CAST(x.srid AS VARCHAR) + '' (lookup not defined)'' ' +
           'END AS spatial_ref ' +
           'FROM (' + @sql + ') x ' +
           'WHERE x.srid is not null ' +
           ' AND x.table_name NOT LIKE ''%.GDB_%'' ' +
           ' AND x.table_name NOT LIKE ''%.a%'' ' +
           ' AND x.table_name NOT LIKE ''%.MANAGE%'' ' +
           'ORDER BY x.table_name;';

EXEC sp_executesql @sql;
