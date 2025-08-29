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
    
    def _match_traffic_geographically(self, traffic_data, bbox):
        """Simple geographic matching without database - matches traffic data within bounding box"""
        matched_data = []
        
        # Extract traffic items from API response
        traffic_items = []
        if 'body' in traffic_data and 'items' in traffic_data['body']:
            traffic_items = traffic_data['body']['items']
        elif 'data' in traffic_data:
            traffic_items = traffic_data['data']
        
        if not traffic_items:
            return matched_data
        
        min_lng, max_lng, min_lat, max_lat = bbox
        
        # For each traffic item, check if it's within our bounding box
        for item in traffic_items:
            link_id = item.get('linkId')
            if not link_id:
                continue
            
            # Since we don't have coordinates from database, we'll include all items
            # that are returned by the API (they should already be filtered by bbox)
            matched_data.append({
                'link_id': link_id,
                'current_speed': float(item.get('speed', 0)),
                'travel_time': float(item.get('travelTime', 0)),
                'road_name': item.get('roadName', ''),
                'created_date': item.get('createdDate', ''),
                'api_data': item
            })
        
        return matched_data
    
    def _format_timestamp(self, timestamp_str):
        """Format Korean traffic API timestamp"""
        try:
            if len(timestamp_str) == 14:  # YYYYMMDDHHMMSS
                year = timestamp_str[:4]
                month = timestamp_str[4:6]
                day = timestamp_str[6:8]
                hour = timestamp_str[8:10]
                minute = timestamp_str[10:12]
                second = timestamp_str[12:14]
                return f"{year}-{month}-{day} {hour}:{minute}:{second}"
        except:
            pass
        return timestamp_str
    
    def _analyze_route_path_matching(self, matches):
        """Analyze how well traffic data matches the actual route path"""
        print(f"\n🔍 Route Path Matching Analysis:")
        
        # Group by road names
        road_groups = {}
        for match in matches:
            road_name = match['road_name']
            if road_name not in road_groups:
                road_groups[road_name] = []
            road_groups[road_name].append(match)
        
        print(f"   📊 Traffic data covers {len(road_groups)} different roads in bounding box")
        
        # Identify actual route roads from the route data
        actual_route_roads = ['금낭화로', '양천로', '노들로', '양평로24길', '양평로22사길', '양평로22길', '선유로55길', '선유로53길']
        
        # Find matches for actual route roads
        route_matches = {}
        other_matches = {}
        
        for road_name, segments in road_groups.items():
            is_route_road = False
            for route_road in actual_route_roads:
                if route_road in road_name or road_name in route_road:
                    if route_road not in route_matches:
                        route_matches[route_road] = []
                    route_matches[route_road].extend(segments)
                    is_route_road = True
                    break
            
            if not is_route_road:
                other_matches[road_name] = segments
        
        # Show route road coverage
        print(f"\n   🎯 ACTUAL ROUTE ROAD COVERAGE:")
        total_route_segments = 0
        for route_road in actual_route_roads:
            if route_road in route_matches:
                segments = route_matches[route_road]
                avg_speed = sum(s['current_speed'] for s in segments) / len(segments)
                total_route_segments += len(segments)
                print(f"     ✅ {route_road}: {len(segments)} segments, avg {avg_speed:.1f} km/h")
            else:
                print(f"     ❌ {route_road}: No traffic data found")
        
        print(f"\n   📈 Route Coverage Summary:")
        print(f"     • Route roads with traffic data: {len(route_matches)}/{len(actual_route_roads)}")
        print(f"     • Total route segments: {total_route_segments}")
        print(f"     • Other roads in area: {len(other_matches)} ({sum(len(s) for s in other_matches.values())} segments)")
        
        # Show top non-route roads (major highways/arterials in the area)
        print(f"\n   🛣️  Major roads in area (not on route):")
        sorted_others = sorted(other_matches.items(), key=lambda x: len(x[1]), reverse=True)[:5]
        for road_name, segments in sorted_others:
            avg_speed = sum(s['current_speed'] for s in segments) / len(segments)
            print(f"     • {road_name}: {len(segments)} segments, avg {avg_speed:.1f} km/h")
        
        # Calculate route-specific metrics
        if route_matches:
            all_route_segments = []
            for segments in route_matches.values():
                all_route_segments.extend(segments)
            
            route_speeds = [s['current_speed'] for s in all_route_segments]
            route_avg_speed = sum(route_speeds) / len(route_speeds)
            
            print(f"\n   🚗 Route-Specific Traffic Analysis:")
            print(f"     • Average speed on route roads: {route_avg_speed:.1f} km/h")
            print(f"     • Route road speed range: {min(route_speeds):.1f} - {max(route_speeds):.1f} km/h")
            print(f"     • Route coverage: {(total_route_segments/len(matches)*100):.1f}% of traffic data")
    
    def _analyze_route_geometry_coverage(self, route_info, matches):
        """Analyze how well traffic data covers the actual route geometry"""
        print(f"\n🗺️  Route Geometry Coverage Analysis:")
        
        # Extract route steps and their names
        if 'legs' in route_info:
            route_steps = []
            for leg in route_info['legs']:
                if 'steps' in leg:
                    for step in leg['steps']:
                        step_name = step.get('name', 'unnamed')
                        step_distance = step.get('distance', 0)
                        step_duration = step.get('duration', 0)
                        route_steps.append({
                            'name': step_name,
                            'distance': step_distance,
                            'duration': step_duration
                        })
            
            print(f"   📍 Route consists of {len(route_steps)} segments:")
            total_distance = 0
            covered_distance = 0
            
            for i, step in enumerate(route_steps):
                total_distance += step['distance']
                
                # Check if this step has traffic data
                has_traffic = False
                matching_segments = []
                
                for match in matches:
                    if step['name'] and step['name'] in match['road_name']:
                        has_traffic = True
                        matching_segments.append(match)
                
                if has_traffic:
                    covered_distance += step['distance']
                    avg_speed = sum(m['current_speed'] for m in matching_segments) / len(matching_segments)
                    status = f"✅ {len(matching_segments)} traffic segments, avg {avg_speed:.1f} km/h"
                else:
                    status = "❌ No traffic data"
                
                print(f"     {i+1}. {step['name']} ({step['distance']:.0f}m) - {status}")
            
            coverage_pct = (covered_distance / total_distance * 100) if total_distance > 0 else 0
            print(f"\n   📊 Coverage Summary:")
            print(f"     • Total route distance: {total_distance:.0f} meters")
            print(f"     • Distance with traffic data: {covered_distance:.0f} meters")
            print(f"     • Coverage percentage: {coverage_pct:.1f}%")
            
            if coverage_pct < 50:
                print(f"     ⚠️  Low coverage - route may use local roads not monitored by traffic system")
            elif coverage_pct < 80:
                print(f"     🟡 Moderate coverage - some route segments have traffic data")
            else:
                print(f"     ✅ Good coverage - most route segments have traffic data")
    
    def _show_detailed_match_info(self, match):
        """Show detailed information about a matched traffic segment"""
        print(f"\n📋 Detailed info for matched segment:")
        print(f"   🆔 Link ID: {match['link_id']}")
        print(f"   🛣️  Road Name: {match['road_name']}")
        print(f"   🚗 Current Speed: {match['current_speed']:.1f} km/h")
        print(f"   ⏱️  Travel Time: {match['travel_time']:.1f} seconds")
        print(f"   📅 Created: {match['created_date']}")
        
        # Show full API data structure
        if 'api_data' in match:
            api_data = match['api_data']
            print(f"   📊 Full API data:")
            for key, value in api_data.items():
                print(f"      {key}: {value}")
        
        # Analyze traffic conditions
        speed = match['current_speed']
        if speed >= 50:
            condition = "🟢 Good flow"
        elif speed >= 30:
            condition = "🟡 Moderate traffic"
        elif speed >= 15:
            condition = "🟠 Heavy traffic"
        else:
            condition = "🔴 Congested"
        
        print(f"   💡 Analysis:")
        print(f"      - Traffic Condition: {condition}")
        print(f"      - This segment is part of {match['road_name']} (증산로)")
        print(f"      - Speed of {match['current_speed']} km/h vs typical urban speed ~50 km/h")
        print(f"      - Link connects nodes {api_data.get('startNodeId', 'N/A')} → {api_data.get('endNodeId', 'N/A')}")
        print(f"      - Data freshness: {self._format_timestamp(match['created_date'])}")
        print(f"      - Geographic matching used (database spatial matching failed)")
    
    def _compare_route_vs_traffic_speeds(self, route_info, traffic_matches):
        """Compare route's expected speed vs actual traffic speeds"""
        print(f"\n🚗 Route Speed vs Traffic Speed Analysis:")
        
        # Calculate route's implied average speed
        route_duration_hours = route_info['duration'] / 3600  # Convert seconds to hours
        route_distance_km = route_info['distance'] / 1000     # Convert meters to km
        route_avg_speed = route_distance_km / route_duration_hours if route_duration_hours > 0 else 0
        
        print(f"   📊 Route Performance:")
        print(f"     • Total distance: {route_distance_km:.2f} km")
        print(f"     • Total duration: {route_info['duration']:.0f} seconds ({route_duration_hours*60:.1f} minutes)")
        print(f"     • Route average speed: {route_avg_speed:.1f} km/h")
        
        if not traffic_matches:
            print(f"   ❌ No traffic data available for comparison")
            return
        
        # Calculate traffic-based speeds
        traffic_speeds = [match['current_speed'] for match in traffic_matches]
        traffic_avg_speed = sum(traffic_speeds) / len(traffic_speeds)
        traffic_min_speed = min(traffic_speeds)
        traffic_max_speed = max(traffic_speeds)
        
        print(f"\n   🚦 Current Traffic Conditions:")
        print(f"     • Traffic segments analyzed: {len(traffic_matches)}")
        print(f"     • Traffic average speed: {traffic_avg_speed:.1f} km/h")
        print(f"     • Traffic speed range: {traffic_min_speed:.1f} - {traffic_max_speed:.1f} km/h")
        
        # Speed comparison analysis
        speed_difference = traffic_avg_speed - route_avg_speed
        speed_difference_pct = (speed_difference / route_avg_speed * 100) if route_avg_speed > 0 else 0
        
        print(f"\n   ⚖️  Speed Comparison:")
        print(f"     • Speed difference: {speed_difference:+.1f} km/h ({speed_difference_pct:+.1f}%)")
        
        if speed_difference_pct > 10:
            print(f"     ✅ Traffic is flowing FASTER than route estimate")
            print(f"        → Current conditions are better than expected")
            print(f"        → Actual travel time may be shorter")
        elif speed_difference_pct < -10:
            print(f"     🚨 Traffic is flowing SLOWER than route estimate")
            print(f"        → Current conditions are worse than expected")
            print(f"        → Actual travel time may be longer")
        else:
            print(f"     ✅ Traffic speed matches route estimate closely")
            print(f"        → Current conditions align with route planning")
        
        # Estimate actual travel time based on traffic
        if traffic_avg_speed > 0:
            traffic_based_duration = (route_distance_km / traffic_avg_speed) * 3600  # Convert to seconds
            time_difference = traffic_based_duration - route_info['duration']
            time_difference_minutes = time_difference / 60
            
            print(f"\n   ⏱️  Travel Time Impact:")
            print(f"     • Route estimated time: {route_info['duration']:.0f} seconds ({route_info['duration']/60:.1f} minutes)")
            print(f"     • Traffic-based estimate: {traffic_based_duration:.0f} seconds ({traffic_based_duration/60:.1f} minutes)")
            print(f"     • Time difference: {time_difference:+.0f} seconds ({time_difference_minutes:+.1f} minutes)")
            
            if time_difference_minutes > 2:
                print(f"     ⚠️  Expect {time_difference_minutes:.1f} minutes LONGER than planned")
            elif time_difference_minutes < -2:
                print(f"     ✅ Expect {abs(time_difference_minutes):.1f} minutes SHORTER than planned")
            else:
                print(f"     ✅ Travel time should be close to route estimate")
        
        # Analyze speed distribution
        print(f"\n   📈 Traffic Speed Distribution:")
        
        # Categorize speeds
        fast_segments = [s for s in traffic_speeds if s >= 50]
        moderate_segments = [s for s in traffic_speeds if 30 <= s < 50]
        slow_segments = [s for s in traffic_speeds if 15 <= s < 30]
        congested_segments = [s for s in traffic_speeds if s < 15]
        
        total_segments = len(traffic_speeds)
        print(f"     • Fast flow (≥50 km/h): {len(fast_segments)} segments ({len(fast_segments)/total_segments*100:.1f}%)")
        print(f"     • Moderate flow (30-49 km/h): {len(moderate_segments)} segments ({len(moderate_segments)/total_segments*100:.1f}%)")
        print(f"     • Slow flow (15-29 km/h): {len(slow_segments)} segments ({len(slow_segments)/total_segments*100:.1f}%)")
        print(f"     • Congested (<15 km/h): {len(congested_segments)} segments ({len(congested_segments)/total_segments*100:.1f}%)")
        
        # Overall traffic assessment
        if len(congested_segments) > total_segments * 0.3:
            assessment = "🔴 HEAVY CONGESTION"
        elif len(slow_segments) + len(congested_segments) > total_segments * 0.5:
            assessment = "🟠 MODERATE CONGESTION"
        elif len(fast_segments) > total_segments * 0.6:
            assessment = "🟢 GOOD FLOW"
        else:
            assessment = "🟡 MIXED CONDITIONS"
        
        print(f"\n   🎯 Overall Traffic Assessment: {assessment}")
        
        # Identify problem areas
        if congested_segments or slow_segments:
            print(f"\n   ⚠️  Potential Bottlenecks:")
            problem_roads = {}
            for match in traffic_matches:
                if match['current_speed'] < 30:
                    road = match['road_name']
                    if road not in problem_roads:
                        problem_roads[road] = []
                    problem_roads[road].append(match['current_speed'])
            
            for road, speeds in problem_roads.items():
                avg_speed = sum(speeds) / len(speeds)
                print(f"     • {road}: {len(speeds)} slow segments, avg {avg_speed:.1f} km/h")
    
    def _print_traffic_adjusted_route(self, route_info, traffic_matches):
        """Print the route adjusted with current traffic data for comparison"""
        print(f"\n📋 TRAFFIC-ADJUSTED ROUTE COMPARISON:")
        print(f"{'='*60}")
        
        # Original route information
        print(f"\n🔵 ORIGINAL ROUTE (OSRM Estimate):")
        print(f"   📏 Total Distance: {route_info['distance']:.0f} meters ({route_info['distance']/1000:.2f} km)")
        print(f"   ⏱️  Total Duration: {route_info['duration']:.0f} seconds ({route_info['duration']/60:.1f} minutes)")
        print(f"   🚗 Average Speed: {(route_info['distance']/1000)/(route_info['duration']/3600):.1f} km/h")
        
        # Extract route steps for detailed comparison
        route_steps = []
        if 'legs' in route_info and len(route_info['legs']) > 0:
            print(f"\n   📍 Route Steps:")
            total_original_time = 0
            for i, leg in enumerate(route_info['legs']):
                if 'steps' in leg:
                    for j, step in enumerate(leg['steps']):
                        step_name = step.get('name', 'unnamed')
                        step_distance = step.get('distance', 0)
                        step_duration = step.get('duration', 0)
                        step_speed = (step_distance/1000)/(step_duration/3600) if step_duration > 0 else 0
                        total_original_time += step_duration
                        
                        route_steps.append({
                            'name': step_name,
                            'distance': step_distance,
                            'duration': step_duration,
                            'speed': step_speed
                        })
                        
                        print(f"     {j+1}. {step_name}")
                        print(f"        Distance: {step_distance:.0f}m, Duration: {step_duration:.1f}s, Speed: {step_speed:.1f} km/h")
        
        # Traffic-adjusted route information
        print(f"\n🔴 TRAFFIC-ADJUSTED ROUTE (Current Conditions):")
        
        if not traffic_matches:
            print(f"   ❌ No traffic data available - cannot adjust route")
            return
        
        # Group traffic data by road names that match route steps
        route_road_traffic = {}
        other_traffic = []
        
        # Define the actual route roads
        actual_route_roads = ['금낭화로', '양천로', '노들로', '양평로24길', '양평로22사길', '양평로22길', '선유로55길', '선유로53길']
        
        for match in traffic_matches:
            road_name = match['road_name']
            is_route_road = False
            
            for route_road in actual_route_roads:
                if route_road in road_name or road_name in route_road:
                    if route_road not in route_road_traffic:
                        route_road_traffic[route_road] = []
                    route_road_traffic[route_road].append(match)
                    is_route_road = True
                    break
            
            if not is_route_road:
                other_traffic.append(match)
        
        # Calculate traffic-adjusted metrics for each route segment
        print(f"   📍 Traffic-Adjusted Route Steps:")
        total_traffic_time = 0
        total_traffic_distance = 0
        
        # Match route steps with traffic data more accurately
        step_traffic_mapping = {}
        
        # First, try to match route steps with traffic data
        for step in route_steps:
            step_name = step['name']
            matched_traffic = []
            
            # Find traffic segments that match this step
            for match in traffic_matches:
                road_name = match['road_name']
                # Check if this traffic segment belongs to the current route step
                if (step_name and step_name in road_name) or (road_name and road_name in step_name):
                    matched_traffic.append(match)
            
            if matched_traffic:
                step_traffic_mapping[step_name] = matched_traffic
        
        # Now display each route step with its traffic-adjusted information
        for i, step in enumerate(route_steps):
            step_name = step['name']
            step_distance = step['distance']
            step_duration = step['duration']
            step_speed = step['speed']
            
            if step_name in step_traffic_mapping:
                segments = step_traffic_mapping[step_name]
                avg_traffic_speed = sum(s['current_speed'] for s in segments) / len(segments)
                segment_count = len(segments)
                
                # Calculate time based on traffic speed and actual step distance
                traffic_time = (step_distance/1000) / avg_traffic_speed * 3600 if avg_traffic_speed > 0 else step_duration
                
                total_traffic_time += traffic_time
                
                # Compare with original step duration
                time_difference = traffic_time - step_duration
                time_diff_pct = (time_difference / step_duration * 100) if step_duration > 0 else 0
                
                status_icon = "🟢" if time_diff_pct < -10 else "🟡" if abs(time_diff_pct) <= 10 else "🔴"
                
                print(f"     {i+1}. {step_name} {status_icon}")
                print(f"        Original: {step_distance:.0f}m, {step_duration:.1f}s, {step_speed:.1f} km/h")
                print(f"        Traffic: {avg_traffic_speed:.1f} km/h ({segment_count} segments)")
                print(f"        Updated: {step_distance:.0f}m, {traffic_time:.1f}s, {avg_traffic_speed:.1f} km/h")
                print(f"        Time Impact: {time_difference:+.1f}s ({time_diff_pct:+.1f}%)")
            else:
                # No traffic data for this step
                total_traffic_time += step_duration
                
                print(f"     {i+1}. {step_name} ❌")
                print(f"        Original: {step_distance:.0f}m, {step_duration:.1f}s, {step_speed:.1f} km/h")
                print(f"        Traffic: No data available")
                print(f"        Updated: {step_distance:.0f}m, {step_duration:.1f}s, {step_speed:.1f} km/h (unchanged)")
                print(f"        Time Impact: +0.0s (0.0%)")
        
        # Also show the aggregated route road analysis for comparison
        print(f"\n   🗺️  Route Road Summary (Aggregated):")
        for i, route_road in enumerate(actual_route_roads):
            if route_road in route_road_traffic:
                segments = route_road_traffic[route_road]
                avg_traffic_speed = sum(s['current_speed'] for s in segments) / len(segments)
                segment_count = len(segments)
                
                # Estimate distance for this road segment (simplified)
                estimated_distance = route_info['distance'] / len(actual_route_roads)  # Rough approximation
                
                # Calculate time based on traffic speed
                traffic_time = (estimated_distance/1000) / avg_traffic_speed * 3600 if avg_traffic_speed > 0 else 0
                
                # Compare with original
                original_time = route_info['duration'] / len(actual_route_roads)  # Rough approximation
                time_difference = traffic_time - original_time
                time_diff_pct = (time_difference / original_time * 100) if original_time > 0 else 0
                
                status_icon = "🟢" if time_diff_pct < -10 else "🟡" if abs(time_diff_pct) <= 10 else "🔴"
                
                print(f"     {i+1}. {route_road} {status_icon}")
                print(f"        Traffic Speed: {avg_traffic_speed:.1f} km/h ({segment_count} segments)")
                print(f"        Estimated Time: {traffic_time:.1f}s (vs {original_time:.1f}s original)")
                print(f"        Time Impact: {time_difference:+.1f}s ({time_diff_pct:+.1f}%)")
            else:
                print(f"     {i+1}. {route_road} ❌")
                print(f"        No traffic data available")
                print(f"        Using original estimate")
        
        # Overall comparison
        print(f"\n   📊 OVERALL COMPARISON:")
        print(f"     Original Total Time: {route_info['duration']:.0f} seconds ({route_info['duration']/60:.1f} minutes)")
        print(f"     Traffic-Adjusted Time: {total_traffic_time:.0f} seconds ({total_traffic_time/60:.1f} minutes)")
        
        time_difference = total_traffic_time - route_info['duration']
        time_diff_pct = (time_difference / route_info['duration'] * 100) if route_info['duration'] > 0 else 0
        
        print(f"     Time Difference: {time_difference:+.0f} seconds ({time_diff_pct:+.1f}%)")
        
        if time_difference > 120:  # More than 2 minutes
            print(f"     🔴 SIGNIFICANT DELAY: Expect {time_difference/60:.1f} minutes longer")
        elif time_difference > 60:  # More than 1 minute
            print(f"     🟡 MODERATE DELAY: Expect {time_difference/60:.1f} minutes longer")
        elif time_difference < -60:  # More than 1 minute faster
            print(f"     🟢 FASTER ROUTE: Expect {abs(time_difference)/60:.1f} minutes shorter")
        else:
            print(f"     🟢 SIMILAR TIME: Close to original estimate")
        
        # Print JSON format for easy comparison/export
        print(f"\n📄 TRAFFIC-ADJUSTED ROUTE DATA (JSON):")
        print(f"{'='*60}")
        
        traffic_adjusted_route = {
            "route_name": "금낭화로_route_traffic_adjusted",
            "timestamp": datetime.now().isoformat(),
            "original_route": {
                "distance_m": route_info['distance'],
                "duration_s": route_info['duration'],
                "average_speed_kmh": (route_info['distance']/1000)/(route_info['duration']/3600)
            },
            "traffic_adjusted": {
                "estimated_duration_s": total_traffic_time,
                "time_difference_s": time_difference,
                "time_difference_pct": time_diff_pct,
                "traffic_segments_used": len([r for r in route_road_traffic.values() if r])
            },
            "route_segments": []
        }
        
        # Add detailed segment information
        for i, route_road in enumerate(actual_route_roads):
            segment_info = {
                "segment_name": route_road,
                "order": i + 1,
                "has_traffic_data": route_road in route_road_traffic
            }
            
            if route_road in route_road_traffic:
                segments = route_road_traffic[route_road]
                segment_info.update({
                    "traffic_segments_count": len(segments),
                    "average_speed_kmh": sum(s['current_speed'] for s in segments) / len(segments),
                    "speed_range": {
                        "min_kmh": min(s['current_speed'] for s in segments),
                        "max_kmh": max(s['current_speed'] for s in segments)
                    },
                    "traffic_condition": self._assess_traffic_condition(sum(s['current_speed'] for s in segments) / len(segments))
                })
            
            traffic_adjusted_route["route_segments"].append(segment_info)
        
        # Print formatted JSON
        print(json.dumps(traffic_adjusted_route, indent=2, ensure_ascii=False))
        
        print(f"\n{'='*60}")
        print(f"💡 Use this data to:")
        print(f"   • Compare with your original route planning")
        print(f"   • Adjust departure time if significant delays expected")
        print(f"   • Consider alternative routes if traffic is heavy")
        print(f"   • Monitor specific road segments that show congestion")
    
    def _assess_traffic_condition(self, speed_kmh):
        """Assess traffic condition based on speed"""
        if speed_kmh >= 50:
            return "good_flow"
        elif speed_kmh >= 30:
            return "moderate_traffic"
        elif speed_kmh >= 15:
            return "heavy_traffic"
        else:
            return "congested"
    
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
                
                # Match traffic to route path
                route_geometry = route_info.get('geometry', '')
                matched_traffic = self.route_processor.match_traffic_to_route(
                    route_geometry, traffic_data, buffer_distance=100
                )
                
                # Also try simple geographic matching without database
                geographic_matches = self._match_traffic_geographically(traffic_data, bbox)
                
                if matched_traffic:
                    print(f"🛣️  Route-specific traffic analysis (Database matching):")
                    print(f"   Matched {len(matched_traffic)} road segments to route")
                    
                    # Calculate route-specific metrics
                    total_length = sum(link['length_m'] for link in matched_traffic if 'length_m' in link)
                    if len(matched_traffic) > 0:
                        avg_speed_on_route = sum(link['current_speed'] for link in matched_traffic) / len(matched_traffic)
                        print(f"   Total matched road length: {total_length:.0f} meters")
                        print(f"   Average speed on route: {avg_speed_on_route:.1f} km/h")
                        
                        # Show closest traffic segments
                        print(f"   Closest traffic segments:")
                        for i, link in enumerate(matched_traffic[:5]):
                            distance_str = f" (distance: {link['distance_to_route_m']:.0f}m)" if 'distance_to_route_m' in link else ""
                            print(f"     {i+1}. {link['road_name']} - {link['current_speed']:.0f} km/h{distance_str}")
                elif geographic_matches:
                    print(f"🛣️  Geographic traffic analysis (No database required):")
                    print(f"   Found {len(geographic_matches)} traffic segments in route area")
                    
                    # Calculate metrics from geographic matches
                    avg_speed = sum(link['current_speed'] for link in geographic_matches) / len(geographic_matches)
                    print(f"   Average speed in area: {avg_speed:.1f} km/h")
                    
                    # Show sample traffic segments
                    print(f"   Sample traffic segments in route area:")
                    for i, link in enumerate(geographic_matches[:5]):
                        print(f"     {i+1}. {link['road_name']} - {link['current_speed']:.0f} km/h (Link: {link['link_id']})")
                    
                    # Show route path analysis
                    self._analyze_route_path_matching(geographic_matches)
                    
                    # Show route geometry analysis
                    self._analyze_route_geometry_coverage(route_info, geographic_matches)
                    
                    # Compare route speed vs traffic speed
                    self._compare_route_vs_traffic_speeds(route_info, geographic_matches)
                    
                    # Print traffic-adjusted route for comparison
                    self._print_traffic_adjusted_route(route_info, geographic_matches)
                    
                    # Show detailed info for first match
                    if geographic_matches:
                        self._show_detailed_match_info(geographic_matches[0])
                    
                    matched_traffic = geographic_matches  # Use geographic matches as fallback
                else:
                    print(f"🛣️  No traffic data matched to route - this could mean:")
                    print(f"   - The route links are not in the traffic database")
                    print(f"   - The link IDs don't match between OSRM and traffic API")
                    print(f"   - The database table structure is different than expected")
                
                return {
                    'route_data': route_info,
                    'traffic_data': traffic_data,
                    'matched_traffic': matched_traffic,
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
                    try:
                        traffic_levels.append(float(item['trafficLevel']))
                    except (ValueError, TypeError):
                        pass
                elif 'congestion' in item:
                    try:
                        congestion_levels.append(float(item['congestion']))
                    except (ValueError, TypeError):
                        pass
                elif 'level' in item:
                    try:
                        traffic_levels.append(float(item['level']))
                    except (ValueError, TypeError):
                        pass
                
                if 'speed' in item:
                    try:
                        speeds.append(float(item['speed']))
                    except (ValueError, TypeError):
                        pass
                elif 'velocity' in item:
                    try:
                        speeds.append(float(item['velocity']))
                    except (ValueError, TypeError):
                        pass
                elif 'avgSpeed' in item:
                    try:
                        speeds.append(float(item['avgSpeed']))
                    except (ValueError, TypeError):
                        pass
            
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
                        "name": "선유로53길",
                        "location": {
                            "longitude": 126.895589,
                            "latitude": 37.538431
                        }
                    }
                ],
                "routes": [
                    {
                        "weight_name": "",
                        "weight": 0,
                        "legs": [
                            {
                                "summary": "양천로, 노들로",
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
                                                    196
                                                ]
                                            }
                                        ],
                                        "instruction": "left",
                                        "geometry": "mljdFsc_eWnD~@vCv@tAx@tAp@VH~@PbBLX@v@FJ@dADZ@",
                                        "duration": 39.9,
                                        "distance": 511.0
                                    },
                                    {
                                        "name": "양천로",
                                        "mode": "driving",
                                        "maneuver": {
                                            "type": "turn",
                                            "modifier": "left",
                                            "location": {
                                                "longitude": 126.811448,
                                                "latitude": 37.573428
                                            },
                                            "bearing_before": 0,
                                            "bearing_after": 0
                                        },
                                        "instruction": "left",
                                        "geometry": "}pidFqz~dWE_AG{BF{@@aG@u@HiGBiE?S@O?c@@sA@iCByG@iE?CDcGN{DPoDDc@VoKDeB^sNZoNJmFB{@PwDLgAJa@^iAn@kAdFgK|@qB|DoJZq@bAyBb@aAp@}ABKRg@^w@h@iAZs@|@kBnBoEL[f@gAt@gBZs@FMnCoGhAiCh@oADIr@cBpAyCLYjCcGpCuGNYrB}EnDcJ`@eAJW^w@~AiDHQlBgEHOn@{ATi@N[bDaH^{@~@yBDKP_@v@kBxCqHN_@N]pBoEZo@bB}BlA_BLQ@AdAyAZq@f@gA^iAJ[L_@@G`@mAdBmER_@R_@nAgBf@k@dDwDHInB_Cd@m@pA_Cv@_BRa@Ne@RcAhAmGPaATuAf@qCh@_FXqAFYDQRw@Ze@r@}@|EqF",
                                        "duration": 391.1,
                                        "distance": 6980.5
                                    },
                                    {
                                        "name": "",
                                        "mode": "driving",
                                        "maneuver": {
                                            "type": "turn",
                                            "modifier": "right",
                                            "location": {
                                                "longitude": 126.880236,
                                                "latitude": 37.547234
                                            },
                                            "bearing_before": 0,
                                            "bearing_after": 0
                                        },
                                        "instruction": "right",
                                        "geometry": "emddFohleWT@PDPLLRBZA\\Mx@INMLWBOEMISYWs@",
                                        "duration": 23.2,
                                        "distance": 192.0
                                    },
                                    {
                                        "name": "노들로",
                                        "mode": "driving",
                                        "maneuver": {
                                            "type": "new name",
                                            "modifier": "straight",
                                            "location": {
                                                "longitude": 126.879749,
                                                "latitude": 37.547535
                                            },
                                            "bearing_before": 0,
                                            "bearing_after": 0
                                        },
                                        "instruction": "straight",
                                        "geometry": "coddFmeleWUiA[qBUeBI_AAU?[BiADk@Fy@Ls@Li@Zw@zB{FxCeHd@uAbBeEhBsExBsF|@yBjAuC`BoDfByDhDmHXo@",
                                        "duration": 85.1,
                                        "distance": 1534.5
                                    },
                                    {
                                        "name": "양평로24길",
                                        "mode": "driving",
                                        "maneuver": {
                                            "type": "turn",
                                            "modifier": "right",
                                            "location": {
                                                "longitude": 126.894753,
                                                "latitude": 37.541688
                                            },
                                            "bearing_before": 0,
                                            "bearing_after": 0
                                        },
                                        "instruction": "right",
                                        "geometry": "qjcdFecoeWRA",
                                        "duration": 1.7,
                                        "distance": 11.5
                                    },
                                    {
                                        "name": "양평로22사길",
                                        "mode": "driving",
                                        "maneuver": {
                                            "type": "fork",
                                            "modifier": "slight left",
                                            "location": {
                                                "longitude": 126.894756,
                                                "latitude": 37.541585
                                            },
                                            "bearing_before": 0,
                                            "bearing_after": 0
                                        },
                                        "instruction": "slight left",
                                        "geometry": "}icdFgcoeW`@Gr@WNQFOtAyCHIFE",
                                        "duration": 15.4,
                                        "distance": 165.1
                                    },
                                    {
                                        "name": "양평로22길",
                                        "mode": "driving",
                                        "maneuver": {
                                            "type": "turn",
                                            "modifier": "right",
                                            "location": {
                                                "longitude": 126.895942,
                                                "latitude": 37.540522
                                            },
                                            "bearing_before": 0,
                                            "bearing_after": 0
                                        },
                                        "instruction": "right",
                                        "geometry": "gccdFsjoeWtA`AfAt@hAz@",
                                        "duration": 19.2,
                                        "distance": 151.6
                                    },
                                    {
                                        "name": "선유로55길",
                                        "mode": "driving",
                                        "maneuver": {
                                            "type": "turn",
                                            "modifier": "left",
                                            "location": {
                                                "longitude": 126.895038,
                                                "latitude": 37.539363
                                            },
                                            "bearing_before": 0,
                                            "bearing_after": 0
                                        },
                                        "instruction": "left",
                                        "geometry": "_|bdF_eoeWp@gBd@mA",
                                        "duration": 15.6,
                                        "distance": 94.8
                                    },
                                    {
                                        "name": "선유로53길",
                                        "mode": "driving",
                                        "maneuver": {
                                            "type": "turn",
                                            "modifier": "right",
                                            "location": {
                                                "longitude": 126.895953,
                                                "latitude": 37.538916
                                            },
                                            "bearing_before": 0,
                                            "bearing_after": 0
                                        },
                                        "instruction": "right",
                                        "geometry": "gybdFujoeW`BfA",
                                        "duration": 9.1,
                                        "distance": 62.8
                                    },
                                    {
                                        "name": "선유로53길",
                                        "mode": "driving",
                                        "maneuver": {
                                            "type": "arrive",
                                            "modifier": "right",
                                            "location": {
                                                "longitude": 126.895589,
                                                "latitude": 37.538431
                                            },
                                            "bearing_before": 0,
                                            "bearing_after": 0
                                        },
                                        "instruction": "right",
                                        "geometry": "evbdFmhoeW",
                                        "duration": 0.0,
                                        "distance": 0.0
                                    }
                                ],
                                "duration": 600.3,
                                "distance": 9703.7
                            }
                        ],
                        "geometry": "mljdFsc_eWnD~@vCv@tAx@tAp@VH~@PbBLX@v@FJ@dADZ@E_AG{BF{@@aG@u@HiGBiE?S@O?c@@sA@iCByG@iE?CDcGN{DPoDDc@VoKDeB^sNZoNJmFB{@PwDLgAJa@^iAn@kAdFgK|@qB|DoJZq@bAyBb@aAp@}ABKRg@^w@h@iAZs@|@kBnBoEL[f@gAt@gBZs@FMnCoGhAiCh@oADIr@cBpAyCLYjCcGpCuGNYrB}EnDcJ`@eAJW^w@~AiDHQlBgEHOn@{ATi@N[bDaH^{@~@yBDKP_@v@kBxCqHN_@N]pBoEZo@bB}BlA_BLQ@AdAyAZq@f@gA^iAJ[L_@@G`@mAdBmER_@R_@nAgBf@k@dDwDHInB_Cd@m@pA_Cv@_BRa@Ne@RcAhAmGPaATuAf@qCh@_FXqAFYDQRw@Ze@r@}@|EqFT@PDPLLRBZA\\Mx@INMLWBOEMISYWs@UiA[qBUeBI_AAU?[BiADk@Fy@Ls@Li@Zw@zB{FxCeHd@uAbBeEhBsExBsF|@yBjAuC`BoDfByDhDmHXo@RA`@Gr@WNQFOtAyCHIFEtA`AfAt@hAz@p@gBd@mA`BfA",
                        "duration": 600.3,
                        "distance": 9703.7
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
