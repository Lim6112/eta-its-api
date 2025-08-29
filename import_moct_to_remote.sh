#!/bin/bash

# MOCT Data Import Script for Remote PostgreSQL Server
# Target: 13.125.10.58:5432, user: postgres, password: cielinc!@#

set -e  # Exit on any error

# Configuration
REMOTE_HOST="13.125.10.58"
REMOTE_PORT="5432"
REMOTE_USER="postgres"
REMOTE_PASSWORD="cielinc!@#"
REMOTE_DB="postgres"  # Change this if needed

# Data paths
DATA_DIR="[2025-08-14]NODELINKDATA"
MOCT_NODE_SHP="${DATA_DIR}/MOCT_NODE.shp"
MOCT_LINK_SHP="${DATA_DIR}/MOCT_LINK.shp"

# Connection string for PostgreSQL
export PGPASSWORD="${REMOTE_PASSWORD}"
PSQL_CMD="psql -h ${REMOTE_HOST} -p ${REMOTE_PORT} -U ${REMOTE_USER} -d ${REMOTE_DB}"

# Connection string for ogr2ogr  
PG_CONNECTION="PG:host=${REMOTE_HOST} port=${REMOTE_PORT} dbname=${REMOTE_DB} user=${REMOTE_USER} password=${REMOTE_PASSWORD}"

echo "========================================================"
echo "🚀 MOCT Data Import to Remote PostgreSQL Server"
echo "========================================================"
echo "Target: ${REMOTE_HOST}:${REMOTE_PORT}"
echo "Database: ${REMOTE_DB}"
echo "User: ${REMOTE_USER}"
echo "========================================================"

# Step 1: Test connection
echo "📡 Step 1: Testing connection..."
if ! timeout 10 $PSQL_CMD -c "SELECT version();" > /dev/null 2>&1; then
    echo "❌ Connection failed. Please check:"
    echo "   - Server is accessible: nc -zv ${REMOTE_HOST} ${REMOTE_PORT}"
    echo "   - Username/password are correct"
    echo "   - Database exists"
    echo "   - Firewall/network allows connection"
    exit 1
fi
echo "✅ Connection successful!"

# Step 2: Check PostGIS extension
echo "📊 Step 2: Checking PostGIS extension..."
$PSQL_CMD -c "CREATE EXTENSION IF NOT EXISTS postgis;" || {
    echo "❌ Failed to create PostGIS extension. Make sure PostGIS is available."
    exit 1
}
echo "✅ PostGIS extension ready!"

# Step 3: Check if data files exist
echo "📁 Step 3: Checking data files..."
if [ ! -f "$MOCT_NODE_SHP" ]; then
    echo "❌ MOCT_NODE.shp not found: $MOCT_NODE_SHP"
    exit 1
fi
if [ ! -f "$MOCT_LINK_SHP" ]; then
    echo "❌ MOCT_LINK.shp not found: $MOCT_LINK_SHP"
    exit 1
fi
echo "✅ Data files found!"

# Step 4: Drop existing tables if they exist (optional - comment out if you want to keep existing data)
echo "🗑️  Step 4: Cleaning up existing tables..."
$PSQL_CMD -c "DROP TABLE IF EXISTS moct_nodes CASCADE;" || true
$PSQL_CMD -c "DROP TABLE IF EXISTS moct_links CASCADE;" || true
echo "✅ Cleanup completed!"

# Step 5: Import MOCT_NODE (intersection points)
echo "📍 Step 5: Importing MOCT_NODE data..."
echo "   Source: $MOCT_NODE_SHP"
echo "   Target table: moct_nodes"

ogr2ogr -f "PostgreSQL" "${PG_CONNECTION}" \
    "${MOCT_NODE_SHP}" \
    -nln moct_nodes \
    -t_srs EPSG:4326 \
    -s_srs EPSG:5186 \
    -lco GEOMETRY_NAME=geom \
    --config PG_USE_COPY YES \
    -overwrite

if [ $? -eq 0 ]; then
    echo "✅ MOCT_NODE import completed!"
    # Get count
    NODE_COUNT=$($PSQL_CMD -t -c "SELECT COUNT(*) FROM moct_nodes;")
    echo "   📊 Imported records: $(echo $NODE_COUNT | tr -d ' ')"
else
    echo "❌ MOCT_NODE import failed!"
    exit 1
fi

# Step 6: Import MOCT_LINK (road segments)  
echo "🛣️  Step 6: Importing MOCT_LINK data..."
echo "   Source: $MOCT_LINK_SHP"
echo "   Target table: moct_links"

ogr2ogr -f "PostgreSQL" "${PG_CONNECTION}" \
    "${MOCT_LINK_SHP}" \
    -nln moct_links \
    -t_srs EPSG:4326 \
    -s_srs EPSG:5186 \
    -lco GEOMETRY_NAME=geom \
    --config PG_USE_COPY YES \
    -overwrite

if [ $? -eq 0 ]; then
    echo "✅ MOCT_LINK import completed!"
    # Get count
    LINK_COUNT=$($PSQL_CMD -t -c "SELECT COUNT(*) FROM moct_links;")
    echo "   📊 Imported records: $(echo $LINK_COUNT | tr -d ' ')"
else
    echo "❌ MOCT_LINK import failed!"
    exit 1
fi

# Step 7: Create indexes for performance
echo "🔍 Step 7: Creating spatial indexes..."

$PSQL_CMD << 'EOF'
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

-- Update table statistics
ANALYZE moct_nodes;
ANALYZE moct_links;
EOF

echo "✅ Indexes created and statistics updated!"

# Step 8: Data verification
echo "🔬 Step 8: Data verification..."

echo "Running verification queries..."
$PSQL_CMD << 'EOF'
-- Table information
SELECT 
    'moct_nodes' as table_name, 
    COUNT(*) as record_count,
    MIN(ST_X(geom)) as min_lng, 
    MAX(ST_X(geom)) as max_lng,
    MIN(ST_Y(geom)) as min_lat, 
    MAX(ST_Y(geom)) as max_lat
FROM moct_nodes
UNION ALL
SELECT 
    'moct_links' as table_name, 
    COUNT(*) as record_count,
    MIN(ST_X(ST_StartPoint(geom))) as min_lng,
    MAX(ST_X(ST_EndPoint(geom))) as max_lng,
    MIN(ST_Y(ST_StartPoint(geom))) as min_lat,
    MAX(ST_Y(ST_EndPoint(geom))) as max_lat
FROM moct_links;
EOF

echo "✅ Data verification completed!"

# Step 9: Sample queries
echo "📋 Step 9: Running sample queries..."

echo "Sample node data:"
$PSQL_CMD -c "SELECT node_id, node_name, ST_X(geom) as lng, ST_Y(geom) as lat FROM moct_nodes WHERE node_name LIKE '%강남%' LIMIT 3;"

echo "Sample link data:"
$PSQL_CMD -c "SELECT link_id, road_name, f_node, t_node, ST_Length(geom::geography) as length_m FROM moct_links WHERE road_name LIKE '%강남%' LIMIT 3;"

echo "========================================================"
echo "🎉 MOCT DATA IMPORT COMPLETED SUCCESSFULLY!"
echo "========================================================"
echo "Database: ${REMOTE_HOST}:${REMOTE_PORT}/${REMOTE_DB}"
echo ""
echo "📊 Import Summary:"
NODE_COUNT=$($PSQL_CMD -t -c "SELECT COUNT(*) FROM moct_nodes;" | tr -d ' ')
LINK_COUNT=$($PSQL_CMD -t -c "SELECT COUNT(*) FROM moct_links;" | tr -d ' ')
echo "   • MOCT Nodes: $NODE_COUNT records"
echo "   • MOCT Links: $LINK_COUNT records"
echo ""
echo "🔍 Available indexes:"
$PSQL_CMD -c "SELECT schemaname, tablename, indexname FROM pg_indexes WHERE tablename IN ('moct_nodes', 'moct_links');"
echo ""
echo "💡 You can now use these tables for:"
echo "   • Spatial queries with ST_DWithin, ST_Intersects"
echo "   • Route finding and network analysis"
echo "   • Traffic data matching by link_id"
echo "   • Korean address/location lookups"
echo ""
echo "📚 Example queries are available in postgresql_standard_node_link_import.md"
echo "========================================================"

# Unset password
unset PGPASSWORD
