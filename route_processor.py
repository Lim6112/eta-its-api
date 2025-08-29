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
    
    def match_traffic_to_route(self, route_geometry, traffic_data, buffer_distance=50):
        """Match traffic data to specific route path using spatial analysis"""
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        matched_data = []
        
        # Extract traffic items from API response
        traffic_items = []
        if 'body' in traffic_data and 'items' in traffic_data['body']:
            traffic_items = traffic_data['body']['items']
        elif 'data' in traffic_data:
            traffic_items = traffic_data['data']
        
        if not traffic_items:
            print("No traffic items found in API response")
            cur.close()
            conn.close()
            return matched_data
        
        # Create route line geometry from coordinates
        if isinstance(route_geometry, str):
            # If it's an encoded polyline, decode it first
            route_coords = self._decode_polyline_simple(route_geometry)
        else:
            route_coords = route_geometry.get('coordinates', [])
        
        if not route_coords:
            print("No route coordinates available")
            cur.close()
            conn.close()
            return matched_data
        
        # Convert route coordinates to PostGIS LineString
        route_wkt = self._coords_to_linestring_wkt(route_coords)
        
        for item in traffic_items:
            link_id = item.get('linkId')
            if not link_id:
                continue
                
            try:
                # Find links that intersect with route buffer
                # Try different possible table names
                table_queries = [
                    "SELECT link_id, ST_X(ST_StartPoint(geom)) as start_lng, ST_Y(ST_StartPoint(geom)) as start_lat, ST_X(ST_EndPoint(geom)) as end_lng, ST_Y(ST_EndPoint(geom)) as end_lat, ST_Length(geom::geography) as length_m, ST_Distance(geom::geography, ST_GeomFromText(%s, 4326)::geography) as distance_to_route FROM moct_link WHERE link_id = %s AND ST_DWithin(geom::geography, ST_GeomFromText(%s, 4326)::geography, %s)",
                    "SELECT linkid as link_id, ST_X(ST_StartPoint(geom)) as start_lng, ST_Y(ST_StartPoint(geom)) as start_lat, ST_X(ST_EndPoint(geom)) as end_lng, ST_Y(ST_EndPoint(geom)) as end_lat, ST_Length(geom::geography) as length_m, ST_Distance(geom::geography, ST_GeomFromText(%s, 4326)::geography) as distance_to_route FROM moct_link_table WHERE linkid = %s AND ST_DWithin(geom::geography, ST_GeomFromText(%s, 4326)::geography, %s)",
                    "SELECT link_id, ST_X(ST_StartPoint(geom)) as start_lng, ST_Y(ST_StartPoint(geom)) as start_lat, ST_X(ST_EndPoint(geom)) as end_lng, ST_Y(ST_EndPoint(geom)) as end_lat, ST_Length(geom::geography) as length_m, ST_Distance(geom::geography, ST_GeomFromText(%s, 4326)::geography) as distance_to_route FROM links WHERE link_id = %s AND ST_DWithin(geom::geography, ST_GeomFromText(%s, 4326)::geography, %s)"
                ]
                
                result = None
                for query in table_queries:
                    try:
                        cur.execute(query, (route_wkt, link_id, route_wkt, buffer_distance))
                        result = cur.fetchone()
                        if result:
                            break
                    except psycopg2.Error:
                        continue
                
                if result:
                    matched_data.append({
                        'link_id': link_id,
                        'start_lng': result[1],
                        'start_lat': result[2],
                        'end_lng': result[3],
                        'end_lat': result[4],
                        'length_m': result[5],
                        'distance_to_route_m': result[6],
                        'current_speed': float(item.get('speed', 0)),
                        'travel_time': float(item.get('travelTime', 0)),
                        'road_name': item.get('roadName', ''),
                        'created_date': item.get('createdDate', ''),
                        'api_data': item
                    })
            except Exception as e:
                print(f"Error matching link {link_id}: {e}")
                continue
        
        cur.close()
        conn.close()
        
        # Sort by distance to route (closest first)
        matched_data.sort(key=lambda x: x['distance_to_route_m'])
        
        print(f"Database matching: {len(matched_data)} traffic links to route")
        return matched_data
    
    def _coords_to_linestring_wkt(self, coords):
        """Convert coordinate array to WKT LineString format"""
        if not coords or len(coords) < 2:
            return None
        
        coord_pairs = []
        for coord in coords:
            if len(coord) >= 2:
                coord_pairs.append(f"{coord[0]} {coord[1]}")
        
        if len(coord_pairs) < 2:
            return None
            
        return f"LINESTRING({', '.join(coord_pairs)})"
    
    def _decode_polyline_simple(self, encoded_polyline):
        """Simple polyline decoder - you may want to use a proper library like polyline"""
        # For now, return empty array - implement proper decoding if needed
        # You can use: pip install polyline
        # import polyline
        # return polyline.decode(encoded_polyline)
        return []
    
    def match_traffic_to_network(self, traffic_data):
        """Match traffic data to node/link network (legacy method)"""
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        matched_data = []
        
        # Extract traffic items from API response
        traffic_items = []
        if 'body' in traffic_data and 'items' in traffic_data['body']:
            traffic_items = traffic_data['body']['items']
        elif 'data' in traffic_data:
            traffic_items = traffic_data['data']
        
        for item in traffic_items:
            link_id = item.get('linkId')
            if link_id:
                try:
                    # Get actual coordinates from your network data
                    # Try different possible table names
                    table_queries = [
                        "SELECT ST_X(ST_StartPoint(geom)) as start_lng, ST_Y(ST_StartPoint(geom)) as start_lat, ST_X(ST_EndPoint(geom)) as end_lng, ST_Y(ST_EndPoint(geom)) as end_lat FROM moct_link WHERE link_id = %s",
                        "SELECT ST_X(ST_StartPoint(geom)) as start_lng, ST_Y(ST_StartPoint(geom)) as start_lat, ST_X(ST_EndPoint(geom)) as end_lng, ST_Y(ST_EndPoint(geom)) as end_lat FROM moct_link_table WHERE linkid = %s",
                        "SELECT ST_X(ST_StartPoint(geom)) as start_lng, ST_Y(ST_StartPoint(geom)) as start_lat, ST_X(ST_EndPoint(geom)) as end_lng, ST_Y(ST_EndPoint(geom)) as end_lat FROM links WHERE link_id = %s"
                    ]
                    
                    result = None
                    for query in table_queries:
                        try:
                            cur.execute(query, (link_id,))
                            result = cur.fetchone()
                            if result:
                                break
                        except psycopg2.Error:
                            continue
                    
                    if result:
                        matched_data.append({
                            'link_id': link_id,
                            'start_lng': result[0],
                            'start_lat': result[1],
                            'end_lng': result[2],
                            'end_lat': result[3],
                            'current_speed': float(item.get('speed', 0)),
                            'travel_time': float(item.get('travelTime', 0)),
                            'road_name': item.get('roadName', ''),
                            'api_data': item
                        })
                except Exception as e:
                    print(f"Error processing link {link_id}: {e}")
                    continue
        
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
    
    def calculate_bbox_from_route_data(self, route_data, buffer=0.005):
        """Calculate bounding box from complete route data structure"""
        if 'result' in route_data and len(route_data['result']) > 0:
            routes = route_data['result'][0]['routes']
            if len(routes) > 0:
                geometry = routes[0]['geometry']
                return self.calculate_route_bbox({'coordinates': self._decode_polyline(geometry)}, buffer)
        return None
    
    def _decode_polyline(self, encoded_polyline):
        """Decode polyline geometry to coordinates"""
        # This is a simplified decoder - you might want to use a proper polyline library
        # For now, extract coordinates from waypoints as fallback
        return []
    
    def extract_waypoints_from_route_data(self, route_data):
        """Extract start and end coordinates from route data"""
        if 'result' in route_data and len(route_data['result']) > 0:
            waypoints = route_data['result'][0]['waypoints']
            if len(waypoints) >= 2:
                start = waypoints[0]['location']
                end = waypoints[-1]['location']
                return ([start['latitude'], start['longitude']], 
                       [end['latitude'], end['longitude']])
        return None, None
    
    def calculate_updated_route(self, original_route, traffic_data):
        """Calculate route with updated traffic speeds"""
        # Get route geometry from original route
        route_geometry = original_route['routes'][0].get('geometry', '')
        
        # Match traffic to the specific route path
        matched_traffic = self.match_traffic_to_route(route_geometry, traffic_data)
        
        # Calculate route performance metrics
        if matched_traffic:
            total_segments = len(matched_traffic)
            avg_speed = sum(link['current_speed'] for link in matched_traffic) / total_segments
            total_length = sum(link.get('length_m', 0) for link in matched_traffic)
            
            # Estimate travel time based on matched traffic
            estimated_time = 0
            for link in matched_traffic:
                if link['current_speed'] > 0:
                    estimated_time += (link.get('length_m', 0) / 1000) / link['current_speed'] * 3600
            
            return {
                'original_route': original_route,
                'matched_traffic': matched_traffic,
                'route_metrics': {
                    'matched_segments': total_segments,
                    'avg_speed_kmh': avg_speed,
                    'total_length_m': total_length,
                    'estimated_time_s': estimated_time
                },
                'timestamp': datetime.now().isoformat()
            }
        else:
            return {
                'original_route': original_route,
                'matched_traffic': [],
                'route_metrics': None,
                'timestamp': datetime.now().isoformat()
            }
