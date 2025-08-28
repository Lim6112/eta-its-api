import os

# API Configuration
TRAFFIC_API_URL = "https://openapi.its.go.kr:9443/trafficInfo"
TRAFFIC_API_KEY = "c0cfd6df07c34f1e818f1388d1132458"

# Database Configuration
DB_CONFIG = {
    'host': 'localhost',
    'database': 'traffic_db',
    'user': 'postgres',
    'password': 'your_password',
    'port': 5432
}

# Monitoring Configuration
UPDATE_INTERVAL_MINUTES = 30
ROUTE_HISTORY_DAYS = 7

# OSRM Configuration
OSRM_BASE_URL = "http://localhost:5000"
