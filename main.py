import time
import schedule
import json
from datetime import datetime
from traffic_fetcher import TrafficFetcher
from route_processor import RouteProcessor
from change_monitor import ChangeMonitor
from config import UPDATE_INTERVAL_MINUTES

class TrafficRouteMonitor:
    def __init__(self):
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
        print(f"Updating routes at {datetime.now()}")
        
        for route_id, route_info in self.routes.items():
            # Fetch current traffic data
            bbox = route_info['bbox']
            traffic_data = self.traffic_fetcher.fetch_traffic_data(*bbox)
            
            if traffic_data:
                # Store traffic data
                self.traffic_fetcher.store_traffic_data(traffic_data)
                
                # Get updated route with traffic
                updated_route = self.route_processor.calculate_updated_route(
                    route_info['current_route'], traffic_data
                )
                
                # Get fresh OSRM route (in real implementation, this would use traffic-adjusted speeds)
                current_route = self.route_processor.get_route_from_osrm(
                    route_info['start_coords'], route_info['end_coords']
                )
                
                if current_route:
                    # Store snapshot
                    self.change_monitor.store_route_snapshot(route_id, current_route['routes'][0])
                    
                    # Detect changes
                    changes = self.change_monitor.detect_changes(route_id)
                    
                    if changes:
                        print(f"Route {route_id} changes detected:")
                        for change in changes:
                            print(f"  {change['type']}: {change['old_value']:.2f} -> {change['new_value']:.2f} ({change['percentage_change']:+.1f}%)")
                    
                    # Update stored route
                    self.routes[route_id]['current_route'] = current_route
    
    def start_monitoring(self):
        """Start the monitoring service"""
        print("Starting traffic route monitoring...")
        
        # Schedule updates every 30 minutes
        schedule.every(UPDATE_INTERVAL_MINUTES).minutes.do(self.update_routes)
        
        # Run initial update
        self.update_routes()
        
        # Keep running
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
