-- MOCT Data Indexes and Verification SQL Script
-- Target: Remote PostgreSQL Server (13.125.10.58:5432)
-- Execute after importing MOCT_NODE and MOCT_LINK data

-- =======================================================
-- 1. ENABLE POSTGIS EXTENSION
-- =======================================================
CREATE EXTENSION IF NOT EXISTS postgis;

-- =======================================================
-- 2. CREATE SPATIAL INDEXES (GIST)
-- =======================================================
-- Spatial indexes for geometry columns
CREATE INDEX IF NOT EXISTS idx_moct_nodes_geom ON moct_nodes USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_moct_links_geom ON moct_links USING GIST (geom);

-- =======================================================
-- 3. CREATE ATTRIBUTE INDEXES
-- =======================================================
-- Node table indexes
CREATE INDEX IF NOT EXISTS idx_moct_nodes_node_id ON moct_nodes(node_id);
CREATE INDEX IF NOT EXISTS idx_moct_nodes_node_name ON moct_nodes(node_name);
CREATE INDEX IF NOT EXISTS idx_moct_nodes_node_type ON moct_nodes(node_type);

-- Link table indexes
CREATE INDEX IF NOT EXISTS idx_moct_links_link_id ON moct_links(link_id);
CREATE INDEX IF NOT EXISTS idx_moct_links_f_node ON moct_links(f_node);
CREATE INDEX IF NOT EXISTS idx_moct_links_t_node ON moct_links(t_node);
CREATE INDEX IF NOT EXISTS idx_moct_links_road_name ON moct_links(road_name);
CREATE INDEX IF NOT EXISTS idx_moct_links_road_rank ON moct_links(road_rank);

-- =======================================================
-- 4. UPDATE TABLE STATISTICS
-- =======================================================
ANALYZE moct_nodes;
ANALYZE moct_links;

-- =======================================================
-- 5. DATA VERIFICATION QUERIES
-- =======================================================

-- Check table record counts
SELECT 'moct_nodes' as table_name, COUNT(*) as record_count FROM moct_nodes
UNION ALL
SELECT 'moct_links' as table_name, COUNT(*) as record_count FROM moct_links;

-- Check coordinate ranges (should cover all of South Korea)
SELECT 
    'moct_nodes' as table_name, 
    COUNT(*) as record_count,
    MIN(ST_X(geom)) as min_lng, 
    MAX(ST_X(geom)) as max_lng,
    MIN(ST_Y(geom)) as min_lat, 
    MAX(ST_Y(geom)) as max_lat,
    'POINT' as geom_type
FROM moct_nodes
UNION ALL
SELECT 
    'moct_links' as table_name, 
    COUNT(*) as record_count,
    MIN(ST_X(ST_Envelope(geom))) as min_lng,
    MAX(ST_X(ST_Envelope(geom))) as max_lng,
    MIN(ST_Y(ST_Envelope(geom))) as min_lat,
    MAX(ST_Y(ST_Envelope(geom))) as max_lat,
    'LINESTRING' as geom_type
FROM moct_links;

-- Check SRID (should be 4326 for WGS84)
SELECT 'moct_nodes' as table_name, ST_SRID(geom) as srid FROM moct_nodes LIMIT 1
UNION ALL  
SELECT 'moct_links' as table_name, ST_SRID(geom) as srid FROM moct_links LIMIT 1;

-- =======================================================
-- 6. SAMPLE DATA QUERIES
-- =======================================================

-- Sample nodes with Korean place names
SELECT 
    node_id, 
    node_name, 
    node_type,
    ST_X(geom) as longitude, 
    ST_Y(geom) as latitude 
FROM moct_nodes 
WHERE node_name IS NOT NULL 
  AND LENGTH(node_name) > 0
LIMIT 10;

-- Sample links with road information
SELECT 
    link_id, 
    road_name, 
    f_node, 
    t_node, 
    road_rank,
    ROUND(ST_Length(geom::geography)::numeric, 2) as length_meters
FROM moct_links 
WHERE road_name IS NOT NULL 
  AND LENGTH(road_name) > 0
LIMIT 10;

-- =======================================================
-- 7. LOCATION-SPECIFIC TESTS
-- =======================================================

-- Find nodes near Seoul City Hall (약 126.978, 37.566)
SELECT 
    node_id, 
    node_name,
    ST_X(geom) as lng, 
    ST_Y(geom) as lat,
    ROUND(ST_Distance(geom, ST_SetSRID(ST_MakePoint(126.978, 37.566), 4326)::geography)::numeric, 0) as distance_m
FROM moct_nodes 
WHERE ST_DWithin(
    geom, 
    ST_SetSRID(ST_MakePoint(126.978, 37.566), 4326)::geography, 
    1000  -- 1km radius
)
ORDER BY distance_m
LIMIT 5;

-- Find roads near Gangnam Station (약 127.028, 37.498)
SELECT 
    link_id,
    road_name,
    f_node,
    t_node,
    ROUND(ST_Length(geom::geography)::numeric, 2) as length_m,
    ROUND(ST_Distance(
        ST_Centroid(geom), 
        ST_SetSRID(ST_MakePoint(127.028, 37.498), 4326)
    )::geography::numeric, 0) as distance_to_station_m
FROM moct_links 
WHERE ST_DWithin(
    geom, 
    ST_SetSRID(ST_MakePoint(127.028, 37.498), 4326)::geography, 
    500  -- 500m radius
)
ORDER BY distance_to_station_m
LIMIT 5;

-- =======================================================
-- 8. PERFORMANCE TESTS
-- =======================================================

-- Test spatial index performance
EXPLAIN (ANALYZE, BUFFERS) 
SELECT COUNT(*) 
FROM moct_nodes 
WHERE ST_DWithin(
    geom, 
    ST_SetSRID(ST_MakePoint(126.9, 37.5), 4326)::geography, 
    1000
);

-- Test join performance between nodes and links
EXPLAIN (ANALYZE, BUFFERS)
SELECT 
    l.link_id,
    l.road_name,
    fn.node_name as from_location,
    tn.node_name as to_location
FROM moct_links l
JOIN moct_nodes fn ON l.f_node = fn.node_id
JOIN moct_nodes tn ON l.t_node = tn.node_id
WHERE l.road_name LIKE '%강남%'
LIMIT 5;

-- =======================================================
-- 9. INDEX VERIFICATION
-- =======================================================

-- Check all indexes created
SELECT 
    schemaname, 
    tablename, 
    indexname, 
    indexdef
FROM pg_indexes 
WHERE tablename IN ('moct_nodes', 'moct_links')
ORDER BY tablename, indexname;

-- Check table sizes
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables 
WHERE tablename IN ('moct_nodes', 'moct_links');

-- =======================================================
-- 10. NETWORK CONNECTIVITY TEST
-- =======================================================

-- Find connected road segments (roads that share nodes)
SELECT 
    l1.link_id as link1,
    l1.road_name as road1,
    l2.link_id as link2, 
    l2.road_name as road2,
    l1.t_node as shared_node
FROM moct_links l1
JOIN moct_links l2 ON l1.t_node = l2.f_node
WHERE l1.link_id != l2.link_id
  AND l1.road_name IS NOT NULL
  AND l2.road_name IS NOT NULL
LIMIT 5;

-- =======================================================
-- SUCCESS MESSAGE
-- =======================================================
SELECT 
    '🎉 MOCT Data Import Verification Completed!' as status,
    (SELECT COUNT(*) FROM moct_nodes) as nodes_imported,
    (SELECT COUNT(*) FROM moct_links) as links_imported,
    (SELECT COUNT(*) FROM pg_indexes WHERE tablename IN ('moct_nodes', 'moct_links')) as indexes_created;
