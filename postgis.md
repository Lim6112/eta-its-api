# PostGIS Chat Summary

## Topic: PostGIS Spatial Queries and Coordinate Systems

### 1. Nearest Neighbor Query
**Question:** How to find nearest record from coordinates 37.4931662546, 126.541883041

**Solution:**
```sql
-- Find nearest record using PostGIS
SELECT *,
       ST_Distance(
           geom_column, 
           ST_SetSRID(ST_MakePoint(126.541883041, 37.4931662546), 4326)
       ) AS distance_meters
FROM your_table_name
ORDER BY geom_column <-> ST_SetSRID(ST_MakePoint(126.541883041, 37.4931662546), 4326)
LIMIT 1;
```

**Key Points:**
- Use `<->` operator for efficient nearest neighbor search
- Coordinates are in longitude, latitude order
- SRID 4326 = WGS84 coordinate system
- Requires spatial index for performance

### 2. Required Columns for PostGIS
**Question:** What column is needed for PostGIS SQL to work?

**Answer:** Geometry or Geography column

**Setup:**
```sql
-- Enable PostGIS
CREATE EXTENSION IF NOT EXISTS postgis;

-- Add geometry column
ALTER TABLE your_table_name 
ADD COLUMN geom GEOMETRY(POINT, 4326);

-- Create spatial index
CREATE INDEX idx_your_table_geom ON your_table_name USING GIST (geom);

-- Populate from lat/lng columns
UPDATE your_table_name 
SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326);
```

### 3. Geometry Data Examples
**Question:** Show example data geom

**Examples:**
- **WKT Format:** `POINT(126.541883041 37.4931662546)`
- **EWKT Format:** `SRID=4326;POINT(126.541883041 37.4931662546)`
- **Sample Seoul locations:**
  - Gangnam Station: `POINT(127.0276 37.4979)`
  - Seoul Station: `POINT(126.9700 37.5547)`
  - Myeongdong: `POINT(126.9850 37.5638)`

**Viewing data:**
```sql
-- As human-readable text
SELECT ST_AsText(geom) FROM locations;

-- As coordinates
SELECT ST_X(geom) as longitude, ST_Y(geom) as latitude FROM locations;
```

### 4. Coordinate System Conversion
**Question:** How to convert from EPSG:5186 to WGS84

**Solution:**
```sql
-- Convert Korean projected coordinates to WGS84
SELECT ST_Transform(geom_5186, 4326) as geom_wgs84
FROM your_table_name;

-- Update existing table
ALTER TABLE your_table_name 
ADD COLUMN geom_wgs84 GEOMETRY(POINT, 4326);

UPDATE your_table_name 
SET geom_wgs84 = ST_Transform(geom_5186, 4326);
```

**Key Points:**
- EPSG:5186 = Korea 2000 / Central Belt 2010 (projected, meters)
- EPSG:4326 = WGS84 (geographic, degrees)
- `ST_Transform()` handles the mathematical conversion
- Korean coordinates convert to ~126-129° longitude, 33-38° latitude

## Quick Reference

### Essential Functions:
- `ST_MakePoint(lng, lat)` - Create point from coordinates
- `ST_SetSRID(geom, srid)` - Set spatial reference system
- `ST_Transform(geom, target_srid)` - Convert coordinate systems
- `ST_Distance(geom1, geom2)` - Calculate distance
- `ST_DWithin(geom1, geom2, distance)` - Within distance check
- `ST_AsText(geom)` - Convert to human-readable text
- `ST_X(geom)`, `ST_Y(geom)` - Extract coordinates

### Common SRIDs:
- 4326 = WGS84 (GPS coordinates)
- 5186 = Korea 2000 / Central Belt 2010
- 3857 = Web Mercator

### Performance Tips:
- Always create spatial indexes: `CREATE INDEX ... USING GIST (geom)`
- Use `<->` operator for nearest neighbor queries
- Consider geometry vs geography based on use case
