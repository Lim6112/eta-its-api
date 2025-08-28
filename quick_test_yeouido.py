from yeouido_routes import create_yeouido_routes, add_routes_to_monitor

def test_single_route():
    """Test a single route quickly"""
    from route_processor import RouteProcessor
    
    processor = RouteProcessor()
    
    # Simple route within Yeouido
    start = [37.5285, 126.9245]  # 여의도공원
    end = [37.5323, 126.9170]    # 국회의사당
    
    print("Testing single route: 여의도공원 → 국회의사당")
    route = processor.get_route_from_osrm(start, end)
    
    if route and 'routes' in route:
        r = route['routes'][0]
        print(f"✓ Success: {r['duration']:.0f}s, {r['distance']:.0f}m")
        return True
    else:
        print("✗ Failed")
        return False

def test_traffic_for_yeouido():
    """Test traffic API for Yeouido area"""
    from traffic_fetcher import TrafficFetcher
    
    fetcher = TrafficFetcher()
    
    # Yeouido bounding box
    traffic_data = fetcher.fetch_traffic_data(126.91, 126.94, 37.52, 37.54)
    
    if traffic_data:
        print("✓ Traffic data retrieved for Yeouido")
        return True
    else:
        print("✗ Traffic data failed")
        return False

if __name__ == "__main__":
    print("=== Quick Yeouido Test ===")
    
    # Test basic functionality first
    if test_single_route() and test_traffic_for_yeouido():
        print("\n✓ Basic tests passed. Creating full route set...")
        routes = create_yeouido_routes()
    else:
        print("\n✗ Basic tests failed. Check OSRM and API connections.")
