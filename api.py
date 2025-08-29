from flask import Flask, request, jsonify
import json
import logging
from datetime import datetime
from main import TrafficRouteMonitor

app = Flask(__name__)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize the traffic monitor
monitor = TrafficRouteMonitor()

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "traffic-route-monitor"
    })

@app.route('/analyze-route', methods=['POST'])
def analyze_route():
    """
    Analyze traffic for a given route
    
    Expected JSON body:
    {
        "route_name": "optional_route_name",
        "route_data": {
            "resultCode": "Ok",
            "result": [
                {
                    "waypoints": [...],
                    "routes": [...]
                }
            ]
        }
    }
    """
    try:
        # Get JSON data from request
        data = request.get_json()
        
        if not data:
            return jsonify({
                "error": "No JSON data provided",
                "status": "error"
            }), 400
        
        # Extract route data and optional name
        route_data = data.get('route_data')
        route_name = data.get('route_name', f"route_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        
        if not route_data:
            return jsonify({
                "error": "route_data is required",
                "status": "error"
            }), 400
        
        # Validate route data structure
        if not _validate_route_data(route_data):
            return jsonify({
                "error": "Invalid route_data structure",
                "status": "error",
                "expected_format": {
                    "resultCode": "Ok",
                    "result": [
                        {
                            "waypoints": [
                                {
                                    "waypointType": "break|last",
                                    "name": "location_name",
                                    "location": {
                                        "longitude": 126.812902,
                                        "latitude": 37.577833
                                    }
                                }
                            ],
                            "routes": [
                                {
                                    "legs": [...],
                                    "geometry": "...",
                                    "duration": 600.3,
                                    "distance": 9703.7
                                }
                            ]
                        }
                    ]
                }
            }), 400
        
        logger.info(f"Analyzing route: {route_name}")
        
        # Analyze the route with traffic data
        result = monitor.check_route_traffic(route_data, route_name)
        
        if result:
            # Extract traffic analysis
            traffic_adjusted = _extract_traffic_adjusted_route(result)
            recommendations = _generate_recommendations(result)
            
            # Return successful analysis
            response = {
                "status": "success",
                "route_name": route_name,
                "timestamp": result['timestamp'],
                "analysis": {
                    "original_route": {
                        "duration_seconds": result['route_data']['duration'],
                        "distance_meters": result['route_data']['distance'],
                        "average_speed_kmh": (result['route_data']['distance']/1000) / (result['route_data']['duration']/3600)
                    },
                    "traffic_data": {
                        "total_segments_in_area": len(result['matched_traffic']) if result['matched_traffic'] else 0,
                        "relevant_segments": traffic_adjusted['traffic_segments'] if traffic_adjusted else 0,
                        "coverage": traffic_adjusted.get('traffic_coverage', 'unknown') if traffic_adjusted else 'no_data',
                        "bbox_used": result['bbox']
                    }
                },
                "traffic_adjusted_route": traffic_adjusted,
                "recommendations": recommendations
            }
            
            # Only include the full original format if specifically requested or if we have good traffic data
            if traffic_adjusted and traffic_adjusted.get('traffic_segments', 0) > 0:
                response["traffic_adjusted_route_original_format"] = _generate_traffic_adjusted_route_original_format(result)
            
            logger.info(f"Successfully analyzed route {route_name}")
            return jsonify(response)
        
        else:
            logger.error(f"Failed to analyze route {route_name}")
            return jsonify({
                "error": "Failed to analyze route traffic",
                "status": "error",
                "route_name": route_name
            }), 500
            
    except Exception as e:
        logger.error(f"Error in analyze_route: {str(e)}")
        return jsonify({
            "error": f"Internal server error: {str(e)}",
            "status": "error"
        }), 500

@app.route('/analyze-route-simple', methods=['POST'])
def analyze_route_simple():
    """
    Simplified route analysis endpoint that returns just the traffic-adjusted route
    
    Expected JSON body:
    {
        "waypoints": [
            {
                "latitude": 37.577833,
                "longitude": 126.812902,
                "name": "Start Location"
            },
            {
                "latitude": 37.538431,
                "longitude": 126.895589,
                "name": "End Location"
            }
        ]
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'waypoints' not in data:
            return jsonify({
                "error": "waypoints array is required",
                "status": "error",
                "expected_format": {
                    "waypoints": [
                        {
                            "latitude": 37.577833,
                            "longitude": 126.812902,
                            "name": "Start Location"
                        },
                        {
                            "latitude": 37.538431,
                            "longitude": 126.895589,
                            "name": "End Location"
                        }
                    ]
                }
            }), 400
        
        waypoints = data['waypoints']
        
        if len(waypoints) < 2:
            return jsonify({
                "error": "At least 2 waypoints are required",
                "status": "error"
            }), 400
        
        # Convert to route data format
        route_data = _convert_waypoints_to_route_data(waypoints)
        route_name = data.get('route_name', f"simple_route_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        
        # Get OSRM route first
        start_coords = [waypoints[0]['latitude'], waypoints[0]['longitude']]
        end_coords = [waypoints[-1]['latitude'], waypoints[-1]['longitude']]
        
        osrm_route = monitor.route_processor.get_route_from_osrm(start_coords, end_coords)
        
        if not osrm_route:
            return jsonify({
                "error": "Could not calculate route between waypoints",
                "status": "error"
            }), 400
        
        # Analyze with traffic
        result = monitor.check_route_traffic(osrm_route, route_name)
        
        if result:
            # Return simplified response
            response = {
                "status": "success",
                "route_name": route_name,
                "original_duration_seconds": result['route_data']['duration'],
                "original_distance_meters": result['route_data']['distance'],
                "traffic_segments_found": len(result['matched_traffic']) if result['matched_traffic'] else 0,
                "traffic_adjusted_route": _extract_traffic_adjusted_route_simple(result),
                "traffic_adjusted_route_original_format": _generate_traffic_adjusted_route_original_format(result)
            }
            
            return jsonify(response)
        
        else:
            return jsonify({
                "error": "Failed to analyze route traffic",
                "status": "error"
            }), 500
            
    except Exception as e:
        logger.error(f"Error in analyze_route_simple: {str(e)}")
        return jsonify({
            "error": f"Internal server error: {str(e)}",
            "status": "error"
        }), 500

def _validate_route_data(route_data):
    """Validate the structure of route data"""
    try:
        if not isinstance(route_data, dict):
            return False
        
        if 'result' not in route_data or not isinstance(route_data['result'], list):
            return False
        
        if len(route_data['result']) == 0:
            return False
        
        result = route_data['result'][0]
        
        # Check for required fields
        required_fields = ['waypoints', 'routes']
        for field in required_fields:
            if field not in result:
                return False
        
        # Check waypoints structure
        waypoints = result['waypoints']
        if not isinstance(waypoints, list) or len(waypoints) < 2:
            return False
        
        for waypoint in waypoints:
            if not isinstance(waypoint, dict):
                return False
            if 'location' not in waypoint:
                return False
            location = waypoint['location']
            if 'latitude' not in location or 'longitude' not in location:
                return False
        
        # Check routes structure
        routes = result['routes']
        if not isinstance(routes, list) or len(routes) == 0:
            return False
        
        route = routes[0]
        if not isinstance(route, dict):
            return False
        
        # Check for basic route fields
        if 'duration' not in route or 'distance' not in route:
            return False
        
        return True
        
    except Exception:
        return False

def _convert_waypoints_to_route_data(waypoints):
    """Convert simple waypoints to route data format"""
    route_waypoints = []
    
    for i, wp in enumerate(waypoints):
        waypoint_type = "break" if i == 0 else "last" if i == len(waypoints) - 1 else "via"
        route_waypoints.append({
            "waypointType": waypoint_type,
            "name": wp.get('name', f"Point {i+1}"),
            "location": {
                "longitude": wp['longitude'],
                "latitude": wp['latitude']
            }
        })
    
    return {
        "resultCode": "Ok",
        "result": [
            {
                "waypoints": route_waypoints,
                "routes": []  # Will be filled by OSRM
            }
        ]
    }

def _extract_traffic_adjusted_route(result):
    """Extract traffic-adjusted route information from analysis result"""
    if not result:
        return None
    
    route_data = result['route_data']
    matched_traffic = result.get('matched_traffic', [])
    
    # Check if we have meaningful traffic data that actually matches the route
    route_specific_traffic = []
    if matched_traffic:
        # Filter for traffic data that's actually relevant to the route
        # This is a simplified check - in a real system you'd want more sophisticated matching
        for match in matched_traffic:
            road_name = match.get('road_name', '').lower()
            # Check if the traffic data road name contains any of the actual route road names
            route_roads = ['금낭화로', '양천로', '노들로', '양평로', '선유로']
            if any(route_road.lower() in road_name or road_name in route_road.lower() for route_road in route_roads):
                route_specific_traffic.append(match)
    
    if not route_specific_traffic:
        # No relevant traffic data found
        return {
            "duration_seconds": route_data['duration'],
            "distance_meters": route_data['distance'],
            "average_speed_kmh": (route_data['distance']/1000) / (route_data['duration']/3600),
            "time_difference_seconds": 0,
            "time_difference_percent": 0,
            "traffic_segments": 0,
            "traffic_coverage": "no_relevant_data",
            "note": "No traffic data found for the specific route roads"
        }
    
    # Calculate traffic-based metrics using only relevant traffic data
    traffic_speeds = [match['current_speed'] for match in route_specific_traffic]
    avg_traffic_speed = sum(traffic_speeds) / len(traffic_speeds)
    
    # Estimate traffic-adjusted duration
    route_distance_km = route_data['distance'] / 1000
    if avg_traffic_speed > 0:
        traffic_duration = (route_distance_km / avg_traffic_speed) * 3600
    else:
        traffic_duration = route_data['duration']
    
    return {
        "duration_seconds": traffic_duration,
        "distance_meters": route_data['distance'],
        "average_speed_kmh": avg_traffic_speed,
        "time_difference_seconds": traffic_duration - route_data['duration'],
        "time_difference_percent": ((traffic_duration - route_data['duration']) / route_data['duration'] * 100) if route_data['duration'] > 0 else 0,
        "traffic_segments": len(route_specific_traffic),
        "total_traffic_segments_in_area": len(matched_traffic),
        "traffic_coverage": "partial" if len(route_specific_traffic) < len(matched_traffic) else "good",
        "speed_range": {
            "min_kmh": min(traffic_speeds),
            "max_kmh": max(traffic_speeds)
        }
    }

def _generate_traffic_adjusted_route_original_format(result):
    """Generate traffic-adjusted route in the original route data format"""
    if not result:
        return None
    
    route_data = result['route_data']
    matched_traffic = result.get('matched_traffic', [])
    
    # Calculate traffic-adjusted duration
    if matched_traffic:
        traffic_speeds = [match['current_speed'] for match in matched_traffic]
        avg_traffic_speed = sum(traffic_speeds) / len(traffic_speeds)
        route_distance_km = route_data['distance'] / 1000
        
        if avg_traffic_speed > 0:
            traffic_duration = (route_distance_km / avg_traffic_speed) * 3600
        else:
            traffic_duration = route_data['duration']
    else:
        traffic_duration = route_data['duration']
    
    # Create traffic-adjusted route structure
    traffic_adjusted_route = {
        "resultCode": "Ok",
        "result": [
            {
                "waypoints": [
                    {
                        "waypointType": "break",
                        "name": "Start Location",
                        "location": {
                            "longitude": 0.0,
                            "latitude": 0.0
                        }
                    },
                    {
                        "waypointType": "last",
                        "name": "End Location", 
                        "location": {
                            "longitude": 0.0,
                            "latitude": 0.0
                        }
                    }
                ],
                "routes": [
                    {
                        "weight_name": "",
                        "weight": 0,
                        "legs": [
                            {
                                "summary": "Traffic-adjusted route",
                                "steps": [],
                                "duration": traffic_duration,
                                "distance": route_data['distance']
                            }
                        ],
                        "geometry": route_data.get('geometry', ''),
                        "duration": traffic_duration,
                        "distance": route_data['distance']
                    }
                ],
                "code": "Ok"
            }
        ]
    }
    
    # Add traffic adjustment metadata
    traffic_adjusted_route["traffic_metadata"] = {
        "original_duration": route_data['duration'],
        "traffic_adjusted_duration": traffic_duration,
        "time_difference_seconds": traffic_duration - route_data['duration'],
        "time_difference_percent": ((traffic_duration - route_data['duration']) / route_data['duration'] * 100) if route_data['duration'] > 0 else 0,
        "traffic_segments_used": len(matched_traffic),
        "average_traffic_speed_kmh": sum([match['current_speed'] for match in matched_traffic]) / len(matched_traffic) if matched_traffic else 0,
        "timestamp": datetime.now().isoformat()
    }
    
    return traffic_adjusted_route

def _extract_traffic_adjusted_route_simple(result):
    """Extract simplified traffic-adjusted route information"""
    traffic_adjusted = _extract_traffic_adjusted_route(result)
    
    if not traffic_adjusted:
        return {
            "duration_seconds": result['route_data']['duration'],
            "time_difference_seconds": 0,
            "traffic_condition": "no_data"
        }
    
    # Determine traffic condition
    time_diff_pct = traffic_adjusted['time_difference_percent']
    if time_diff_pct > 20:
        condition = "heavy_delay"
    elif time_diff_pct > 10:
        condition = "moderate_delay"
    elif time_diff_pct < -10:
        condition = "faster_than_expected"
    else:
        condition = "normal"
    
    return {
        "duration_seconds": traffic_adjusted['duration_seconds'],
        "time_difference_seconds": traffic_adjusted['time_difference_seconds'],
        "time_difference_minutes": traffic_adjusted['time_difference_seconds'] / 60,
        "traffic_condition": condition,
        "average_speed_kmh": traffic_adjusted['average_speed_kmh']
    }

def _generate_recommendations(result):
    """Generate recommendations based on traffic analysis"""
    if not result:
        return ["Unable to analyze traffic for this route"]
    
    recommendations = []
    traffic_adjusted = _extract_traffic_adjusted_route(result)
    
    if not traffic_adjusted:
        return ["No traffic data available for this specific route"]
    
    # Check if we have relevant traffic data
    if traffic_adjusted.get('traffic_coverage') == 'no_relevant_data':
        recommendations.append("No traffic data available for the specific roads on this route")
        recommendations.append("Route uses local roads that may not be monitored by traffic systems")
        recommendations.append("Use original route time estimate")
        return recommendations
    
    time_diff_minutes = traffic_adjusted['time_difference_seconds'] / 60
    traffic_segments = traffic_adjusted['traffic_segments']
    
    if traffic_segments == 0:
        recommendations.append("Limited traffic data available for this route")
        recommendations.append("Use original route time estimate with caution")
    elif time_diff_minutes > 5:
        recommendations.append(f"Expect {time_diff_minutes:.1f} minutes longer than planned due to traffic")
        recommendations.append("Consider departing earlier or finding an alternative route")
    elif time_diff_minutes < -2:
        recommendations.append(f"Traffic is flowing well - you may arrive {abs(time_diff_minutes):.1f} minutes earlier")
    else:
        recommendations.append("Current traffic conditions are close to normal expectations")
    
    if traffic_segments > 0:
        avg_speed = traffic_adjusted['average_speed_kmh']
        if avg_speed < 20:
            recommendations.append("Heavy traffic detected on monitored segments")
        elif avg_speed < 30:
            recommendations.append("Moderate traffic on monitored segments")
        else:
            recommendations.append("Good traffic flow on monitored segments")
        
        # Add coverage information
        total_segments = traffic_adjusted.get('total_traffic_segments_in_area', 0)
        if traffic_segments < total_segments * 0.1:
            recommendations.append(f"Limited coverage: only {traffic_segments} relevant traffic segments found")
    
    return recommendations

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
