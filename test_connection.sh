#!/bin/bash

# PostgreSQL Connection Test Script
# Tests various connection parameters to 13.125.10.58:5432

set +e  # Don't exit on error

REMOTE_HOST="13.125.10.58"
REMOTE_PORT="5432"
REMOTE_USER="ciel"
REMOTE_PASSWORD="cielinc!@#"

echo "========================================================"
echo "🔍 PostgreSQL Connection Diagnostics"
echo "========================================================"
echo "Target: ${REMOTE_HOST}:${REMOTE_PORT}"
echo "User: ${REMOTE_USER}"
echo "========================================================"

# Test 1: Basic connectivity
echo "📡 Test 1: Network connectivity"
if timeout 5 nc -zv ${REMOTE_HOST} ${REMOTE_PORT}; then
    echo "✅ Port ${REMOTE_PORT} is accessible"
else
    echo "❌ Port ${REMOTE_PORT} is not accessible"
    exit 1
fi

# Test 2: Try different database names
echo "🗄️  Test 2: Trying different database names"
DATABASES=("postgres" "ciel" "public" "template1" "byeongcheollim")

export PGPASSWORD="${REMOTE_PASSWORD}"
export PGCONNECT_TIMEOUT=10

for db in "${DATABASES[@]}"; do
    echo -n "  Testing database '$db': "
    
    # Capture both stdout and stderr
    result=$(timeout 15 psql -h ${REMOTE_HOST} -p ${REMOTE_PORT} -U ${REMOTE_USER} -d ${db} -c "SELECT current_database(), version();" 2>&1)
    exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        echo "✅ SUCCESS"
        echo "    Database: $db"
        echo "    Version: $(echo "$result" | grep PostgreSQL | head -1)"
        WORKING_DB=$db
        break
    else
        echo "❌ Failed"
        # Show first line of error for debugging
        error_line=$(echo "$result" | head -1)
        if [ ! -z "$error_line" ]; then
            echo "    Error: $error_line"
        fi
    fi
done

# Test 3: If we found a working database, test PostGIS
if [ ! -z "$WORKING_DB" ]; then
    echo "🗺️  Test 3: Testing PostGIS extension"
    
    echo -n "  Checking PostGIS availability: "
    result=$(timeout 10 psql -h ${REMOTE_HOST} -p ${REMOTE_PORT} -U ${REMOTE_USER} -d ${WORKING_DB} -c "CREATE EXTENSION IF NOT EXISTS postgis; SELECT postgis_version();" 2>&1)
    exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        echo "✅ PostGIS available"
        postgis_version=$(echo "$result" | grep -E "^[[:space:]]*[0-9]" | head -1 | tr -d ' ')
        echo "    PostGIS Version: $postgis_version"
    else
        echo "❌ PostGIS not available"
        echo "    Error: $(echo "$result" | head -1)"
    fi
    
    # Test 4: Test table creation permissions
    echo "📊 Test 4: Testing table creation permissions"
    
    echo -n "  Testing CREATE TABLE permission: "
    result=$(timeout 10 psql -h ${REMOTE_HOST} -p ${REMOTE_PORT} -U ${REMOTE_USER} -d ${WORKING_DB} -c "CREATE TABLE IF NOT EXISTS test_table (id INT, name TEXT); DROP TABLE IF EXISTS test_table;" 2>&1)
    exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        echo "✅ Can create/drop tables"
    else
        echo "❌ Cannot create tables"
        echo "    Error: $(echo "$result" | head -1)"
    fi
    
    # Test 5: Test ogr2ogr connection
    echo "🛠️  Test 5: Testing ogr2ogr connection"
    
    echo -n "  Testing ogr2ogr PostgreSQL connection: "
    
    # Create a simple test shapefile info
    if [ -f "[2025-08-14]NODELINKDATA/MOCT_NODE.shp" ]; then
        result=$(timeout 30 ogr2ogr --config PG_LIST_ALL_TABLES YES -f "PostgreSQL" "PG:host=${REMOTE_HOST} port=${REMOTE_PORT} dbname=${WORKING_DB} user=${REMOTE_USER} password=${REMOTE_PASSWORD}" "[2025-08-14]NODELINKDATA/MOCT_NODE.shp" -nln test_connection_node -t_srs EPSG:4326 -s_srs EPSG:5186 -lco GEOMETRY_NAME=geom -sql "SELECT node_id, node_name FROM MOCT_NODE LIMIT 1" --config PG_USE_COPY YES 2>&1)
        exit_code=$?
        
        if [ $exit_code -eq 0 ]; then
            echo "✅ ogr2ogr connection works"
            
            # Count imported records
            count_result=$(timeout 10 psql -h ${REMOTE_HOST} -p ${REMOTE_PORT} -U ${REMOTE_USER} -d ${WORKING_DB} -t -c "SELECT COUNT(*) FROM test_connection_node;" 2>/dev/null)
            if [ ! -z "$count_result" ]; then
                echo "    Imported records: $(echo $count_result | tr -d ' ')"
            fi
            
            # Cleanup
            psql -h ${REMOTE_HOST} -p ${REMOTE_PORT} -U ${REMOTE_USER} -d ${WORKING_DB} -c "DROP TABLE IF EXISTS test_connection_node;" >/dev/null 2>&1
        else
            echo "❌ ogr2ogr connection failed"
            echo "    Error: $(echo "$result" | head -2 | tail -1)"
        fi
    else
        echo "⚠️  MOCT_NODE.shp not found - skipping ogr2ogr test"
    fi
    
    echo "========================================================"
    echo "✅ CONNECTION SUMMARY"
    echo "========================================================"
    echo "Working Database: $WORKING_DB"
    echo "Server: ${REMOTE_HOST}:${REMOTE_PORT}"
    echo "User: ${REMOTE_USER}"
    echo ""
    echo "🚀 Ready to run MOCT import!"
    echo "Update your scripts to use database: $WORKING_DB"
    echo ""
    echo "Run the import with:"
    echo "./import_moct_to_remote.sh"
    echo ""
    
else
    echo "========================================================"
    echo "❌ CONNECTION FAILED"
    echo "========================================================"
    echo "Could not connect to any database."
    echo "Please check:"
    echo "  - Server is running and accessible"
    echo "  - Username and password are correct"
    echo "  - User has permission to connect"
    echo "  - Firewall allows connections"
    echo "========================================================"
fi

unset PGPASSWORD
