from main import TrafficRouteMonitor
from traffic_fetcher import TrafficFetcher
from route_processor import RouteProcessor
from change_monitor import ChangeMonitor
import time

def test_traffic_api():
    """Test traffic API connection"""
    print("Testing Traffic API...")
    fetcher = TrafficFetcher()
    
    # Test with Yeouido coordinates
    traffic_data = fetcher.fetch_traffic_data(126.9, 126.95, 37.52, 37.54)
    
    if traffic_data:
        print("✓ Traffic API working")
        print(f"  Response keys: {list(traffic_data.keys())}")
        return True
    else:
        print("✗ Traffic API failed")
        return False

def test_osrm_connection():
    """Test OSRM connection"""
    print("Testing OSRM connection...")
    processor = RouteProcessor()
    
    # Test route in Seoul
    start = [37.525, 126.925]
    end = [37.535, 126.935]
    
    route = processor.get_route_from_osrm(start, end)
    
    if route and 'routes' in route:
        print("✓ OSRM working")
        print(f"  Route duration: {route['routes'][0]['duration']} seconds")
        return True
    else:
        print("✗ OSRM failed")
        return False

def test_database_connection():
    """Test database connection"""
    print("Testing Database connection...")
    try:
        monitor = ChangeMonitor()
        print("✓ Database connection working")
        return True
    except Exception as e:
        print(f"✗ Database failed: {e}")
        return False

def test_full_workflow():
    """Test complete workflow"""
    print("Testing full workflow...")
    
    monitor = TrafficRouteMonitor()
    
    # Add test route
    start_coords = [37.525, 126.925]
    end_coords = [37.535, 126.935]
    
    monitor.add_route("test_route", start_coords, end_coords)
    
    if "test_route" in monitor.routes:
        print("✓ Route added successfully")
        
        # Test single update
        monitor.update_routes()
        print("✓ Route update completed")
        return True
    else:
        print("✗ Route addition failed")
        return False

def run_all_tests():
    """Run all tests"""
    print("=== Traffic Route Monitor Tests ===\n")
    
    tests = [
        test_database_connection,
        test_traffic_api,
        test_osrm_connection,
        test_full_workflow
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"✗ Test failed with exception: {e}")
            results.append(False)
        print()
    
    print("=== Test Summary ===")
    print(f"Passed: {sum(results)}/{len(results)}")
    
    if all(results):
        print("🎉 All tests passed! System ready for monitoring.")
    else:
        print("⚠️  Some tests failed. Check configuration.")

if __name__ == "__main__":
    run_all_tests()
