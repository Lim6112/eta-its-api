import time
import schedule
import json
import logging
from datetime import datetime
from traffic_fetcher import TrafficFetcher
from route_processor import RouteProcessor
from change_monitor import ChangeMonitor
from config import UPDATE_INTERVAL_MINUTES, DB_CONFIG

def setup_logging():
    """Setup logging to file and console"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(f'traffic_monitor_{datetime.now().strftime("%Y%m%d")}.log'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

class TrafficRouteMonitor:
    def __init__(self):
        self.logger = setup_logging()
        self.traffic_fetcher = TrafficFetcher()
        self.route_processor = RouteProcessor()
        self.change_monitor = ChangeMonitor()
        self.routes = {}  # Store routes to monitor
    
    def add_route(self, route_id, start_coords, end_coords, bbox=None):
        """Add a route to monitor"""
        # Get initial OSRM route
        initial_route = self.route_processor.get_route_from_osrm(start_coords, end_coords)
        
        if initial_route:
            # Calculate bbox from actual route geometry, not just endpoints
            if bbox is None:
                route_geometry = initial_route['routes'][0]['geometry']
                bbox = self.route_processor.calculate_route_bbox(route_geometry)
            
            self.routes[route_id] = {
                'start_coords': start_coords,
                'end_coords': end_coords,
                'bbox': bbox,
                'current_route': initial_route
            }
            
            # Store initial snapshot
            self.change_monitor.store_route_snapshot(route_id, initial_route['routes'][0])
            print(f"Added route {route_id} with bbox: {bbox}")
        else:
            print(f"Failed to get initial route for {route_id}")
    
    def _calculate_bbox(self, start_coords, end_coords):
        """Calculate bounding box for traffic API"""
        min_x = min(start_coords[1], end_coords[1]) - 0.01
        max_x = max(start_coords[1], end_coords[1]) + 0.01
        min_y = min(start_coords[0], end_coords[0]) - 0.01
        max_y = max(start_coords[0], end_coords[0]) + 0.01
        return (min_x, max_x, min_y, max_y)
    
    def update_routes(self):
        """Update all monitored routes with current traffic"""
        print(f"\n{'='*50}")
        print(f"🔄 Updating routes at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*50}")
        
        for route_id, route_info in self.routes.items():
            print(f"\n📍 Processing route: {route_id}")
            
            # Fetch current traffic data
            bbox = route_info['bbox']
            print(f"   Fetching traffic data for bbox: {bbox}")
            traffic_data = self.traffic_fetcher.fetch_traffic_data(*bbox)
            
            if traffic_data:
                print(f"   ✓ Traffic data received")
                # Store traffic data
                self.traffic_fetcher.store_traffic_data(traffic_data)
                
                # Get updated route with traffic
                updated_route = self.route_processor.calculate_updated_route(
                    route_info['current_route'], traffic_data
                )
                
                # Get fresh OSRM route
                current_route = self.route_processor.get_route_from_osrm(
                    route_info['start_coords'], route_info['end_coords']
                )
                
                if current_route:
                    route_data = current_route['routes'][0]
                    print(f"   📊 Current route: {route_data['duration']:.0f}s, {route_data['distance']:.0f}m")
                    
                    # Store snapshot
                    self.change_monitor.store_route_snapshot(route_id, route_data)
                    
                    # Detect changes
                    changes = self.change_monitor.detect_changes(route_id)
                    
                    if changes:
                        print(f"   🚨 CHANGES DETECTED for {route_id}:")
                        for change in changes:
                            direction = "📈" if change['percentage_change'] > 0 else "📉"
                            print(f"      {direction} {change['type']}: {change['old_value']:.2f} → {change['new_value']:.2f} ({change['percentage_change']:+.1f}%)")
                    else:
                        print(f"   ✅ No significant changes detected")
                    
                    # Update stored route
                    self.routes[route_id]['current_route'] = current_route
                else:
                    print(f"   ❌ Failed to get updated route")
            else:
                print(f"   ❌ Failed to fetch traffic data")
        
        print(f"\n{'='*50}")
        print(f"✅ Route update completed at {datetime.now().strftime('%H:%M:%S')}")
        print(f"⏰ Next update in {UPDATE_INTERVAL_MINUTES} minutes")
        print(f"{'='*50}")
    
    def check_route_traffic(self, route_data, route_name="custom_route"):
        """Check traffic for a specific route from route data"""
        print(f"\n🔍 Checking traffic for route: {route_name}")
        
        # Extract waypoints
        start_coords, end_coords = self.route_processor.extract_waypoints_from_route_data(route_data)
        
        if not start_coords or not end_coords:
            print("❌ Could not extract coordinates from route data")
            return None
        
        print(f"📍 Start: {start_coords}")
        print(f"📍 End: {end_coords}")
        
        # Calculate bounding box with larger buffer for short routes
        buffer = 0.01  # Larger buffer for better traffic data coverage
        min_lng = min(start_coords[1], end_coords[1]) - buffer
        max_lng = max(start_coords[1], end_coords[1]) + buffer
        min_lat = min(start_coords[0], end_coords[0]) - buffer
        max_lat = max(start_coords[0], end_coords[0]) + buffer
        
        bbox = (min_lng, max_lng, min_lat, max_lat)
        print(f"🗺️  Bounding box: {bbox}")
        
        # Fetch traffic data
        traffic_data = self.traffic_fetcher.fetch_traffic_data(*bbox)
        
        if traffic_data:
            print(f"✅ Traffic data received")
            
            # Store traffic data
            self.traffic_fetcher.store_traffic_data(traffic_data)
            
            # Get current OSRM route for comparison
            current_route = self.route_processor.get_route_from_osrm(start_coords, end_coords)
            
            if current_route:
                route_info = current_route['routes'][0]
                print(f"📊 Current route info:")
                print(f"   Duration: {route_info['duration']:.1f} seconds")
                print(f"   Distance: {route_info['distance']:.1f} meters")
                
                # Analyze traffic data
                self._analyze_traffic_data(traffic_data, bbox)
                
                return {
                    'route_data': route_info,
                    'traffic_data': traffic_data,
                    'bbox': bbox,
                    'timestamp': datetime.now().isoformat()
                }
            else:
                print("❌ Could not get OSRM route")
        else:
            print("❌ Failed to fetch traffic data")
        
        return None
    
    def _analyze_traffic_data(self, traffic_data, bbox):
        """Analyze and display traffic data"""
        if not traffic_data:
            print("📊 No traffic data to analyze")
            return
        
        print(f"📊 Traffic analysis:")
        print(f"   Raw response keys: {list(traffic_data.keys())}")
        
        # Handle different possible response formats
        data_items = []
        if 'body' in traffic_data and 'items' in traffic_data['body']:
            data_items = traffic_data['body']['items']
        elif 'data' in traffic_data:
            data_items = traffic_data['data']
        elif 'response' in traffic_data:
            data_items = traffic_data['response'].get('data', [])
        elif 'result' in traffic_data:
            data_items = traffic_data['result']
        elif isinstance(traffic_data, list):
            data_items = traffic_data
        
        print(f"   Total data points: {len(data_items)}")
        
        if len(data_items) > 0:
            # Analyze various possible field names for Korean traffic API
            traffic_levels = []
            speeds = []
            congestion_levels = []
            
            for item in data_items:
                # Check for different possible field names
                if 'trafficLevel' in item:
                    traffic_levels.append(item['trafficLevel'])
                elif 'congestion' in item:
                    congestion_levels.append(item['congestion'])
                elif 'level' in item:
                    traffic_levels.append(item['level'])
                
                if 'speed' in item:
                    speeds.append(item['speed'])
                elif 'velocity' in item:
                    speeds.append(item['velocity'])
                elif 'avgSpeed' in item:
                    speeds.append(item['avgSpeed'])
            
            if traffic_levels:
                avg_traffic_level = sum(traffic_levels) / len(traffic_levels)
                print(f"   Average traffic level: {avg_traffic_level:.1f}")
            
            if congestion_levels:
                avg_congestion = sum(congestion_levels) / len(congestion_levels)
                print(f"   Average congestion: {avg_congestion:.1f}")
            
            if speeds:
                avg_speed = sum(speeds) / len(speeds)
                print(f"   Average speed: {avg_speed:.1f} km/h")
            
            # Show sample data with better formatting
            print(f"   Sample traffic points:")
            for i, item in enumerate(data_items[:3]):  # Show first 3 items
                if isinstance(item, dict):
                    # Show key fields only for readability
                    key_fields = {}
                    for key in ['linkId', 'nodeId', 'speed', 'trafficLevel', 'congestion', 'level', 'velocity', 'avgSpeed', 'roadName', 'roadType', 'roadGrade', 'roadType', 'startNodeId', 'endNodeId']:
                        if key in item:
                            key_fields[key] = item[key]
                    print(f"     {i+1}. {key_fields}")
                else:
                    print(f"     {i+1}. {item}")
            
            # Show full structure of first item for debugging
            if data_items and isinstance(data_items[0], dict):
                print(f"   First item structure: {list(data_items[0].keys())}")
        else:
            print("   No detailed traffic data available")
            # Show the full response structure for debugging
            print(f"   Full response structure:")
            if isinstance(traffic_data, dict):
                for key, value in traffic_data.items():
                    if isinstance(value, list):
                        print(f"     {key}: list with {len(value)} items")
                    elif isinstance(value, dict):
                        print(f"     {key}: dict with keys {list(value.keys())}")
                        # Show body content if it exists
                        if key == 'body' and 'totalCount' in value:
                            print(f"       totalCount: {value['totalCount']}")
                            if 'items' in value:
                                print(f"       items: list with {len(value['items'])} items")
                                if len(value['items']) > 0:
                                    print(f"       first item keys: {list(value['items'][0].keys())}")
                    else:
                        print(f"     {key}: {type(value).__name__} = {value}")

    def start_monitoring(self):
        """Start the monitoring service"""
        print(f"\n🚀 Starting traffic route monitoring...")
        print(f"📊 Monitoring {len(self.routes)} routes")
        print(f"⏱️  Update interval: {UPDATE_INTERVAL_MINUTES} minutes")
        print(f"🗄️  Database: {DB_CONFIG['database']}")
        
        # Schedule updates every 30 minutes
        schedule.every(UPDATE_INTERVAL_MINUTES).minutes.do(self.update_routes)
        
        # Run initial update
        print(f"\n🔄 Running initial update...")
        self.update_routes()
        
        # Keep running
        print(f"\n⏳ Waiting for next scheduled update...")
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute

if __name__ == "__main__":
    monitor = TrafficRouteMonitor()
    
    # Your specific route data
    route_data = {
        "resultCode": "Ok",
        "result": [
            {
                "waypoints": [
                    {
                        "waypointType": "break",
                        "name": "금낭화로",
                        "location": {
                            "longitude": 126.812902,
                            "latitude": 37.577833
                        }
                    },
                    {
                        "waypointType": "last",
                        "name": "금낭화로",
                        "location": {
                            "longitude": 126.812899,
                            "latitude": 37.577824
                        }
                    }
                ],
                "routes": [
                    {
                        "weight_name": "",
                        "weight": 0,
                        "legs": [
                            {
                                "summary": "금낭화로",
                                "steps": [
                                    {
                                        "name": "금낭화로",
                                        "mode": "driving",
                                        "maneuver": {
                                            "type": "depart",
                                            "modifier": "left",
                                            "location": {
                                                "longitude": 126.812902,
                                                "latitude": 37.577833
                                            },
                                            "bearing_before": 0,
                                            "bearing_after": 0
                                        },
                                        "intersections": [
                                            {
                                                "out": 0,
                                                "location": {
                                                    "longitude": 126.812902,
                                                    "latitude": 37.577833
                                                },
                                                "indications": [
                                                    "uturn"
                                                ],
                                                "in": None,
                                                "entry": [
                                                    True
                                                ],
                                                "bearings": [
                                                    195
                                                ]
                                            }
                                        ],
                                        "instruction": "left",
                                        "geometry": "mljdFsc_eW@?",
                                        "duration": 0.0,
                                        "distance": 1.0
                                    },
                                    {
                                        "name": "금낭화로",
                                        "mode": "driving",
                                        "maneuver": {
                                            "type": "arrive",
                                            "modifier": None,
                                            "location": {
                                                "longitude": 126.812899,
                                                "latitude": 37.577824
                                            },
                                            "bearing_before": 0,
                                            "bearing_after": 0
                                        },
                                        "intersections": [
                                            {
                                                "out": None,
                                                "location": {
                                                    "longitude": 126.812899,
                                                    "latitude": 37.577824
                                                },
                                                "indications": [
                                                    "uturn"
                                                ],
                                                "in": 0,
                                                "entry": [
                                                    True
                                                ],
                                                "bearings": [
                                                    15
                                                ]
                                            }
                                        ],
                                        "instruction": None,
                                        "geometry": "kljdFsc_eW",
                                        "duration": 0.0,
                                        "distance": 0.0
                                    }
                                ],
                                "duration": 0.0,
                                "distance": 1.0,
                                "annotation": {
                                    "nodes": [
                                        2702609963,
                                        436821289
                                    ],
                                    "duration": [
                                        0
                                    ],
                                    "distance": [
                                        1
                                    ],
                                    "datasource": [
                                        0
                                    ]
                                }
                            }
                        ],
                        "geometry": "mljdFsc_eW@?",
                        "duration": 0.0,
                        "distance": 1.0
                    }
                ],
                "code": "Ok"
            }
        ]
    }
    
    # Check traffic for your specific route
    result = monitor.check_route_traffic(route_data, "금낭화로_route")
    
    if result:
        print(f"\n✅ Traffic check completed successfully!")
        print(f"📄 Results saved to database")
    else:
        print(f"\n❌ Traffic check failed")
    
    # Optionally, you can also add it to continuous monitoring
    # start_coords = [37.577833, 126.812902]  # lat, lng
    # end_coords = [37.577824, 126.812899]
    # monitor.add_route("금낭화로_continuous", start_coords, end_coords)
    # monitor.start_monitoring()
