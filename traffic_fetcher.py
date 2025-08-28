import requests
import json
import time
from datetime import datetime
import psycopg2
from config import TRAFFIC_API_URL, TRAFFIC_API_KEY, DB_CONFIG

class TrafficFetcher:
    def __init__(self):
        self.api_url = TRAFFIC_API_URL
        self.api_key = TRAFFIC_API_KEY
        
    def fetch_traffic_data(self, min_x, max_x, min_y, max_y):
        """Fetch traffic data for given bounding box"""
        params = {
            'apiKey': self.api_key,
            'type': 'all',
            'getType': 'json',
            'minX': min_x,
            'maxX': max_x,
            'minY': min_y,
            'maxY': max_y
        }
        
        try:
            response = requests.get(self.api_url, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching traffic data: {e}")
            return None
    
    def store_traffic_data(self, traffic_data):
        """Store traffic data in PostgreSQL with timestamp"""
        if not traffic_data:
            return
            
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        timestamp = datetime.now()
        
        # Create table if not exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS traffic_history (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP,
                traffic_data JSONB,
                processed BOOLEAN DEFAULT FALSE
            )
        """)
        
        cur.execute(
            "INSERT INTO traffic_history (timestamp, traffic_data) VALUES (%s, %s)",
            (timestamp, json.dumps(traffic_data))
        )
        
        conn.commit()
        cur.close()
        conn.close()
