# Manual MOCT Data Import Guide

## Remote PostgreSQL Server Information
- **Host**: 13.125.10.58
- **Port**: 5432  
- **User**: postgres
- **Password**: cielinc!@#
- **Database**: postgres (or create a specific database)

## Prerequisites Check

### 1. Test Connection
```bash
# Test basic connectivity
nc -zv 13.125.10.58 5432

# Test PostgreSQL connection
PGPASSWORD="cielinc!@#" psql -h 13.125.10.58 -p 5432 -U postgres -d postgres -c "SELECT version();"
```

### 2. Enable PostGIS Extension
```sql
-- Connect to database and run:
CREATE EXTENSION IF NOT EXISTS postgis;
SELECT postgis_version();
```

### 3. Check Available Data Files
```bash
ls -la "[2025-08-14]NODELINKDATA/"
# Should show:
# - MOCT_NODE.shp (32MB) + .dbf (165MB) + .shx + .prj + .cpg
# - MOCT_LINK.shp (275MB) + .dbf (295MB) + .shx + .prj + .cpg
```

## Import Commands

### Step 1: Import MOCT_NODE (Intersection Points)
```bash
PGPASSWORD="cielinc!@#" ogr2ogr -f "PostgreSQL" \
  "PG:host=13.125.10.58 port=5432 dbname=postgres user=postgres password=cielinc!@#" \
  "[2025-08-14]NODELINKDATA/MOCT_NODE.shp" \
  -nln moct_nodes \
  -t_srs EPSG:4326 \
  -s_srs EPSG:5186 \
  -lco GEOMETRY_NAME=geom \
  --config PG_USE_COPY YES \
  -overwrite
```

**Expected Result**: ~1,174,161 node records imported

### Step 2: Import MOCT_LINK (Road Segments)
```bash
PGPASSWORD="cielinc!@#" ogr2ogr -f "PostgreSQL" \
  "PG:host=13.125.10.58 port=5432 dbname=postgres user=postgres password=cielinc!@#" \
  "[2025-08-14]NODELINKDATA/MOCT_LINK.shp" \
  -nln moct_links \
  -t_srs EPSG:4326 \
  -s_srs EPSG:5186 \
  -lco GEOMETRY_NAME=geom \
  --config PG_USE_COPY YES \
  -overwrite
```

**Expected Result**: ~1,549,618 link records imported

### Step 3: Create Indexes (Execute SQL)
```sql
-- Spatial indexes (GIST) for geometry columns
CREATE INDEX IF NOT EXISTS idx_moct_nodes_geom ON moct_nodes USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_moct_links_geom ON moct_links USING GIST (geom);

-- Attribute indexes for common queries
CREATE INDEX IF NOT EXISTS idx_moct_nodes_node_id ON moct_nodes(node_id);
CREATE INDEX IF NOT EXISTS idx_moct_nodes_node_name ON moct_nodes(node_name);
CREATE INDEX IF NOT EXISTS idx_moct_links_link_id ON moct_links(link_id);
CREATE INDEX IF NOT EXISTS idx_moct_links_f_node ON moct_links(f_node);
CREATE INDEX IF NOT EXISTS idx_moct_links_t_node ON moct_links(t_node);
CREATE INDEX IF NOT EXISTS idx_moct_links_road_name ON moct_links(road_name);

-- Update statistics
ANALYZE moct_nodes;
ANALYZE moct_links;
```

## Verification Queries

### Basic Data Check
```sql
-- Record counts
SELECT 'moct_nodes' as table_name, COUNT(*) as records FROM moct_nodes
UNION ALL
SELECT 'moct_links' as table_name, COUNT(*) as records FROM moct_links;

-- Coordinate ranges (should cover South Korea)
SELECT 
    MIN(ST_X(geom)) as min_lng, 
    MAX(ST_X(geom)) as max_lng,
    MIN(ST_Y(geom)) as min_lat, 
    MAX(ST_Y(geom)) as max_lat
FROM moct_nodes;
```

### Location Tests
```sql
-- Find nodes near Seoul City Hall
SELECT 
    node_id, 
    node_name,
    ST_X(geom) as lng, 
    ST_Y(geom) as lat
FROM moct_nodes 
WHERE ST_DWithin(
    geom, 
    ST_SetSRID(ST_MakePoint(126.978, 37.566), 4326)::geography, 
    1000
)
LIMIT 5;

-- Find roads near Gangnam Station
SELECT 
    link_id,
    road_name,
    ST_Length(geom::geography) as length_m
FROM moct_links 
WHERE ST_DWithin(
    geom, 
    ST_SetSRID(ST_MakePoint(127.028, 37.498), 4326)::geography, 
    500
)
LIMIT 5;
```

## Data Schema

### MOCT_NODES Table
- **node_id**: Unique node identifier (String 10)
- **node_type**: Node type (String 3) - 101=intersection
- **node_name**: Korean place name (String 50)
- **geom**: POINT geometry in WGS84 (EPSG:4326)

### MOCT_LINKS Table  
- **link_id**: Unique link identifier (String 10)
- **f_node**: From node ID (String 10)
- **t_node**: To node ID (String 10)
- **road_name**: Korean road name (String 30)
- **road_rank**: Road classification (String 3)
- **max_spd**: Speed limit (Integer)
- **length**: Link length in meters (Real)
- **geom**: LINESTRING geometry in WGS84 (EPSG:4326)

## Troubleshooting

### Connection Issues
- Check firewall: `nc -zv 13.125.10.58 5432`
- Verify credentials: Try connecting with psql first
- Check server logs for authentication errors
- Ensure PostgreSQL accepts remote connections

### Import Issues
- Check ogr2ogr version: `ogr2ogr --version`
- Verify GDAL supports PostgreSQL: `ogrinfo --formats | grep PostgreSQL`
- Check disk space on remote server
- Monitor server memory during large imports

### Performance Issues
- Create indexes AFTER import, not before
- Use `--config PG_USE_COPY YES` for faster imports
- Consider importing during low-usage hours
- Monitor server resources during import

## Expected Import Times
- **MOCT_NODE**: ~10-15 minutes (1.17M records)
- **MOCT_LINK**: ~20-30 minutes (1.55M records) 
- **Index Creation**: ~5-10 minutes
- **Total**: ~45-60 minutes

## File Locations
- Import script: `./import_moct_to_remote.sh`
- SQL indexes: `./moct_remote_indexes.sql`  
- This guide: `./MANUAL_IMPORT_GUIDE.md`

## Success Criteria
✅ Connection established to remote server
✅ PostGIS extension enabled
✅ ~1.17M nodes imported with spatial coordinates
✅ ~1.55M links imported with road geometries  
✅ All spatial and attribute indexes created
✅ Sample spatial queries return accurate results
✅ Coordinate ranges cover all of South Korea
✅ Korean text (road/place names) display correctly

---

**Note**: The automated script `import_moct_to_remote.sh` will do all these steps automatically once the connection issues are resolved.
