import psycopg2
import json
from datetime import datetime, timedelta
from config import DB_CONFIG

class ChangeMonitor:
    def __init__(self):
        self.setup_database()
    
    def setup_database(self):
        """Create tables for route monitoring"""
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS route_snapshots (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP,
                route_id VARCHAR(255),
                route_data JSONB,
                duration_seconds INTEGER,
                distance_meters REAL,
                avg_speed REAL
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS route_changes (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP,
                route_id VARCHAR(255),
                change_type VARCHAR(100),
                old_value REAL,
                new_value REAL,
                percentage_change REAL
            )
        """)
        
        conn.commit()
        cur.close()
        conn.close()
    
    def store_route_snapshot(self, route_id, route_data):
        """Store current route state"""
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        # Extract key metrics
        duration = route_data.get('duration', 0)
        distance = route_data.get('distance', 0)
        avg_speed = distance / duration if duration > 0 else 0
        
        cur.execute("""
            INSERT INTO route_snapshots 
            (timestamp, route_id, route_data, duration_seconds, distance_meters, avg_speed)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (datetime.now(), route_id, json.dumps(route_data), duration, distance, avg_speed))
        
        conn.commit()
        cur.close()
        conn.close()
    
    def detect_changes(self, route_id):
        """Detect changes in route compared to previous snapshot"""
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        # Get last two snapshots
        cur.execute("""
            SELECT duration_seconds, distance_meters, avg_speed, timestamp
            FROM route_snapshots 
            WHERE route_id = %s 
            ORDER BY timestamp DESC 
            LIMIT 2
        """, (route_id,))
        
        results = cur.fetchall()
        
        if len(results) < 2:
            cur.close()
            conn.close()
            return []
        
        current = results[0]
        previous = results[1]
        changes = []
        
        # Check duration change
        if abs(current[0] - previous[0]) > 30:  # 30 second threshold
            pct_change = ((current[0] - previous[0]) / previous[0]) * 100
            changes.append({
                'type': 'duration',
                'old_value': previous[0],
                'new_value': current[0],
                'percentage_change': pct_change
            })
        
        # Check speed change
        if abs(current[2] - previous[2]) > 2:  # 2 km/h threshold
            pct_change = ((current[2] - previous[2]) / previous[2]) * 100
            changes.append({
                'type': 'avg_speed',
                'old_value': previous[2],
                'new_value': current[2],
                'percentage_change': pct_change
            })
        
        # Store detected changes
        for change in changes:
            cur.execute("""
                INSERT INTO route_changes 
                (timestamp, route_id, change_type, old_value, new_value, percentage_change)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (datetime.now(), route_id, change['type'], 
                  change['old_value'], change['new_value'], change['percentage_change']))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return changes
