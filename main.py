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
    
    # Example: Add a route in Seoul (Yeouido area)
    # Replace with your actual coordinates
    start_coords = [37.525, 126.925]  # lat, lng
    end_coords = [37.535, 126.935]
    
    monitor.add_route("yeouido_route", start_coords, end_coords)
    
    # Start monitoring
    monitor.start_monitoring()
