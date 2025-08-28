import psycopg2
import requests
import json
from datetime import datetime
from config import DB_CONFIG, OSRM_BASE_URL

class RouteProcessor:
    def __init__(self):
        self.osrm_url = OSRM_BASE_URL
        
    def get_route_from_osrm(self, start_coords, end_coords):
        """Get route from OSRM"""
        url = f"{self.osrm_url}/route/v1/driving/{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}"
        params = {
            'overview': 'full',
            'geometries': 'geojson',
            'annotations': 'true'
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error getting OSRM route: {e}")
            return None
    
    def match_traffic_to_network(self, traffic_data):
        """Match traffic data to node/link network"""
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        matched_data = []
        
        # Assuming traffic_data contains link/node IDs
        for item in traffic_data.get('data', []):
            if 'linkId' in item:
                # Get actual coordinates from your network data
                cur.execute("""
                    SELECT ST_X(geom) as lng, ST_Y(geom) as lat, speed_limit
                    FROM moct_link 
                    WHERE link_id = %s
                """, (item['linkId'],))
                
                result = cur.fetchone()
                if result:
                    matched_data.append({
                        'link_id': item['linkId'],
                        'lng': result[0],
                        'lat': result[1],
                        'speed_limit': result[2],
                        'current_speed': item.get('speed', 0),
                        'traffic_level': item.get('trafficLevel', 0)
                    })
        
        cur.close()
        conn.close()
        return matched_data
    
    def calculate_route_bbox(self, route_geometry, buffer=0.005):
        """Calculate proper bounding box from route geometry"""
        coordinates = route_geometry['coordinates']
        
        # Extract all lat/lng points from route
        lngs = [coord[0] for coord in coordinates]
        lats = [coord[1] for coord in coordinates]
        
        # Find actual bounds of the route
        min_lng = min(lngs) - buffer
        max_lng = max(lngs) + buffer
        min_lat = min(lats) - buffer
        max_lat = max(lats) + buffer
        
        return (min_lng, max_lng, min_lat, max_lat)
    
    def calculate_updated_route(self, original_route, traffic_data):
        """Calculate route with updated traffic speeds"""
        # This would integrate traffic speeds into OSRM calculation
        # For now, return modified route data
        matched_traffic = self.match_traffic_to_network(traffic_data)
        
        return {
            'original_route': original_route,
            'traffic_data': matched_traffic,
            'timestamp': datetime.now().isoformat()
        }
