from route_processor import RouteProcessor
import json

def create_yeouido_routes():
    """Create sample routes around Yeouido area"""
    processor = RouteProcessor()
    
    # Key locations in Yeouido area
    locations = {
        'yeouido_park': [37.5285, 126.9245],           # 여의도공원
        'national_assembly': [37.5323, 126.9170],      # 국회의사당
        'ifc_mall': [37.5259, 126.9240],               # IFC몰
        'kbs': [37.5263, 126.9292],                    # KBS
        'lotte_hotel': [37.5251, 126.9244],            # 롯데호텔
        'hangang_park': [37.5204, 126.9348],           # 한강공원
        'mapo_bridge': [37.5447, 126.9442],            # 마포대교
        'banpo_bridge': [37.5133, 126.9772]            # 반포대교
    }
    
    # Create route combinations
    routes = []
    
    # Routes within Yeouido
    yeouido_routes = [
        ('yeouido_park', 'national_assembly', 'Park to Assembly'),
        ('ifc_mall', 'kbs', 'IFC to KBS'),
        ('lotte_hotel', 'yeouido_park', 'Hotel to Park'),
        ('national_assembly', 'ifc_mall', 'Assembly to IFC')
    ]
    
    # Routes from Yeouido to other areas
    external_routes = [
        ('yeouido_park', 'hangang_park', 'Yeouido to Hangang Park'),
        ('ifc_mall', 'mapo_bridge', 'IFC to Mapo Bridge'),
        ('national_assembly', 'banpo_bridge', 'Assembly to Banpo Bridge'),
        ('kbs', 'mapo_bridge', 'KBS to Mapo Bridge')
    ]
    
    all_route_configs = yeouido_routes + external_routes
    
    print("Creating OSRM routes around Yeouido...")
    
    for start_key, end_key, description in all_route_configs:
        start_coords = locations[start_key]
        end_coords = locations[end_key]
        
        print(f"Creating route: {description}")
        route_data = processor.get_route_from_osrm(start_coords, end_coords)
        
        if route_data and 'routes' in route_data:
            route_info = route_data['routes'][0]
            bbox = calculate_route_bbox(route_info['geometry'])  # Use actual geometry
            
            routes.append({
                'id': f"{start_key}_to_{end_key}",
                'description': description,
                'start_location': start_key,
                'end_location': end_key,
                'start_coords': start_coords,
                'end_coords': end_coords,
                'duration': route_info['duration'],
                'distance': route_info['distance'],
                'geometry': route_info['geometry'],
                'bbox': bbox
            })
            print(f"  ✓ Duration: {route_info['duration']:.0f}s, Distance: {route_info['distance']:.0f}m")
        else:
            print(f"  ✗ Failed to get route")
    
    return routes

def calculate_route_bbox(route_geometry, buffer=0.005):
    """Calculate bounding box from actual route geometry"""
    coordinates = route_geometry['coordinates']
    
    lngs = [coord[0] for coord in coordinates]
    lats = [coord[1] for coord in coordinates]
    
    return {
        'min_x': min(lngs) - buffer,
        'max_x': max(lngs) + buffer,
        'min_y': min(lats) - buffer,
        'max_y': max(lats) + buffer
    }

def save_routes_to_file(routes, filename='yeouido_routes.json'):
    """Save routes to JSON file"""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(routes, f, indent=2, ensure_ascii=False)
    print(f"Routes saved to {filename}")

def add_routes_to_monitor(routes):
    """Add all routes to the monitoring system"""
    from main import TrafficRouteMonitor
    
    monitor = TrafficRouteMonitor()
    
    for route in routes:
        bbox = route['bbox']
        monitor.add_route(
            route['id'],
            route['start_coords'],
            route['end_coords'],
            bbox=(bbox['min_x'], bbox['max_x'], bbox['min_y'], bbox['max_y'])
        )
    
    print(f"Added {len(routes)} routes to monitoring system")
    return monitor

if __name__ == "__main__":
    # Create routes
    routes = create_yeouido_routes()
    
    # Save to file
    save_routes_to_file(routes)
    
    # Print summary
    print(f"\n=== Route Summary ===")
    print(f"Total routes created: {len(routes)}")
    
    for route in routes:
        print(f"{route['description']}: {route['duration']:.0f}s, {route['distance']:.0f}m")
    
    # Option to start monitoring
    start_monitoring = input("\nStart monitoring these routes? (y/n): ")
    if start_monitoring.lower() == 'y':
        monitor = add_routes_to_monitor(routes)
        print("Starting monitoring...")
        monitor.start_monitoring()
