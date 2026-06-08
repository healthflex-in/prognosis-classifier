#!/usr/bin/env python3
"""
Fetch matches from MongoDB and transform to VALD format for a specific patient.
Replaces the file-based approach with direct MongoDB queries.
"""

import json
import os
from typing import Dict, List, Any, Optional
from pymongo import MongoClient
from pathlib import Path

# Load .env file explicitly
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)


class VALDTransformer:
    """Fetch and transform VALD data from MongoDB matches collection."""
    
    def __init__(self, mongo_uri: str = None, db_name: str = None):
        """
        Initialize MongoDB connection.
        
        Args:
            mongo_uri: MongoDB connection string
            db_name: Database name (default: 'stance-dashboard')
        """
        self.mongo_uri = mongo_uri or os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or "mongodb://localhost:27017/"
        self.db_name = db_name or os.getenv("MONGO_DB", "stance-dashboard")
        self.client = None
        self.db = None
        self.connect()
    
    def connect(self):
        """Connect to MongoDB."""
        try:
            self.client = MongoClient(
                self.mongo_uri,
                tlsAllowInvalidCertificates=True,
                tlsAllowInvalidHostnames=True
            )
            self.db = self.client[self.db_name]
            # Test connection
            self.db.command('ping')
            print(f"✅ Connected to MongoDB: {self.db_name}")
        except Exception as e:
            print(f"❌ MongoDB connection failed: {e}")
            raise
    
    def fetch_matches_for_patient(self, stance_id: str) -> List[Dict[str, Any]]:
        """
        Fetch match records for a specific patient from MongoDB.
        
        Args:
            stance_id: The patient's stance ID
        
        Returns:
            List of match documents
        """
        try:
            collection = self.db['matches']
            
            # Query for matches with this stance ID
            matches = list(collection.find({'stanceId': stance_id}))
            
            print(f"✓ Fetched {len(matches)} match records for stance ID: {stance_id}")
            return matches
        
        except Exception as e:
            print(f"❌ Error fetching matches from MongoDB: {e}")
            return []
    
    def get_vald_data_for_patient(self, stance_id: str) -> List[Dict[str, Any]]:
        """
        Fetch and transform VALD data for a specific patient in one call.
        
        Args:
            stance_id: The patient's stance ID
        
        Returns:
            List of VALD records for this patient
        """
        print(f"\n📂 Fetching VALD data from MongoDB for stance ID: {stance_id}...")
        
        # Fetch matches from MongoDB
        matches = self.fetch_matches_for_patient(stance_id)
        
        if not matches:
            print(f"⚠️  No matches found for stance ID: {stance_id}")
            return []
        
        # Transform to VALD format with 0N filtering
        print(f"🔄 Transforming {len(matches)} matches to VALD format...")
        print(f"🧹 Applying data quality filters (removing 0N force values)...")
        vald_records = self.transform_matches_to_vald(matches)
        
        # Generate summary
        self._generate_summary(vald_records)
        
        return vald_records
    
    def _generate_summary(self, vald_records: List[Dict[str, Any]]):
        """Generate summary statistics of VALD data with session dates."""
        
        print(f"\n📊 VALD Data Summary:")
        print(f"━" * 80)
        
        total_records = len(vald_records)
        active_records = sum(1 for r in vald_records if r.get('is_active'))
        records_with_force_frame = sum(1 for r in vald_records if r['exercises']['forceFrame'])
        records_with_force_deck = sum(1 for r in vald_records if r['exercises']['forceDeck'])
        records_with_dynamo = sum(1 for r in vald_records if r['exercises']['dynamo'])
        
        print(f"Total Records: {total_records}")
        print(f"Active Records: {active_records}")
        print(f"Records with Force Frame Data: {records_with_force_frame}")
        print(f"Records with Force Deck Data: {records_with_force_deck}")
        print(f"Records with Dynamo Data: {records_with_dynamo}")
        
        # Exercise distribution by category with session dates
        exercise_counts = {'forceFrame': {}, 'forceDeck': {}, 'dynamo': {}}
        
        for record in vald_records:
            # Get record date from lastRecordedUtc as fallback when dates are not explicitly given
            record_date = None
            if 'last_recorded_utc' in record:
                utc_value = record['last_recorded_utc']
                if isinstance(utc_value, str):
                    record_date = utc_value[:10]  # Extract YYYY-MM-DD
                elif hasattr(utc_value, 'strftime'):  # datetime object
                    record_date = utc_value.strftime('%Y-%m-%d')
                else:
                    # Try to convert to string and extract
                    record_date = str(utc_value)[:10]
            
            for category in ['forceFrame', 'forceDeck', 'dynamo']:
                for exercise_key, exercise_data in record['exercises'][category].items():
                    if exercise_key not in exercise_counts[category]:
                        exercise_counts[category][exercise_key] = {'count': 0, 'dates': set()}
                    
                    exercise_counts[category][exercise_key]['count'] += 1
                    
                    # Extract session dates
                    data = exercise_data.get('data', {})
                    dates = self._extract_session_dates_from_exercise(data)
                    
                    # If no dates found explicitly in the data, use lastRecordedUtc as fallback
                    if not dates and record_date:
                        dates = {record_date}
                    
                    exercise_counts[category][exercise_key]['dates'].update(dates)
        
        # Print distribution for each category
        for category in ['forceFrame', 'forceDeck', 'dynamo']:
            if exercise_counts[category]:
                print(f"\n{category} Exercise Distribution:")
                for exercise, info in sorted(exercise_counts[category].items(), key=lambda x: x[1]['count'], reverse=True):
                    dates_list = sorted(list(info['dates']))
                    dates_str = ", ".join(dates_list) if dates_list else "No dates found"
                    print(f"  - {exercise}: {info['count']} records")
                    print(f"    Sessions: {dates_str}")
        
        print(f"━" * 80)
    
    def _extract_session_dates_from_exercise(self, data: Dict) -> set:
        """Extract session dates from exercise data."""
        dates = set()
        
        if not isinstance(data, dict):
            return dates
        
        # Look for sessionDates key
        if 'sessionDates' in data and isinstance(data['sessionDates'], list):
            for date_str in data['sessionDates']:
                date_part = date_str[:10] if len(date_str) >= 10 else date_str
                dates.add(date_part)
        
        # Look for x_axis_entities in graph data (recursive search)
        def extract_dates_recursive(obj):
            found_dates = []
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key == 'x_axis_entities' and isinstance(value, list):
                        # Only extract valid date strings (YYYY-MM-DD format or ISO format)
                        for item in value:
                            if isinstance(item, str):
                                # Check if it looks like a date (starts with YYYY-MM-DD or YYYY-MM-DDTHH:MM)
                                if len(item) >= 10 and item[4] == '-' and item[7] == '-':
                                    found_dates.append(item)
                    else:
                        found_dates.extend(extract_dates_recursive(value))
            elif isinstance(obj, list):
                for item in obj:
                    found_dates.extend(extract_dates_recursive(item))
            return found_dates
        
        x_axis_dates = extract_dates_recursive(data)
        for date_str in x_axis_dates:
            date_part = date_str[:10] if len(date_str) >= 10 else date_str
            dates.add(date_part)
        
        return dates
    
    def _has_zero_force_values(self, data: Dict) -> bool:
        """
        Check if exercise data contains 0N force values.
        
        ALL 0N values should be filtered out from agent processing, regardless of whether
        they are recording errors or legitimate measurements.
        
        Args:
            data: Exercise data dictionary
        
        Returns:
            True if data contains any 0N force values, False otherwise
        """
        if not isinstance(data, dict):
            return False
        
        # Check all possible force value locations
        def check_for_zeros_recursive(obj):
            """Recursively check for any 0N values in the data structure"""
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key in ['y_axis_entities', 'y_axis_entity_left', 'y_axis_entity_right']:
                        if isinstance(value, list):
                            if any(v in [0, 0.0, "0"] for v in value if v is not None):
                                return True
                        elif value in [0, 0.0, "0"]:
                            return True
                    elif check_for_zeros_recursive(value):
                        return True
            elif isinstance(obj, list):
                for item in obj:
                    if check_for_zeros_recursive(item):
                        return True
            elif obj in [0, 0.0, "0"]:
                return True
            return False
        
        # Check common force value fields
        force_fields = [
            'maxOuterLeftForce',
            'maxOuterRightForce',
            'avgOuterLeftForce',
            'avgOuterRightForce',
            'maxInnerLeftForce',
            'maxInnerRightForce',
            'avgInnerLeftForce',
            'avgInnerRightForce',
            'maxForce',
            'avgForce',
            'peakForce'
        ]
        
        # Check individual force fields
        for field in force_fields:
            if field in data and data[field] in [0, 0.0, "0"]:
                return True
        
        # Check recursively for any 0N values in nested structures
        return check_for_zeros_recursive(data)
    
    def _filter_zero_force_sessions(self, exercise_data: Dict) -> tuple[Dict, list]:
        """
        Filter out 0N values based on data structure:
        - For bilateral single-session data: exclude entire exercise if either side is 0N
        - For time-series data: exclude only specific dates with 0N values
        - For individual metrics: set 0N values to None but preserve structure
        
        Args:
            exercise_data: Exercise data dictionary
        
        Returns:
            Tuple of (filtered_data, excluded_dates)
            - filtered_data: Exercise data with 0N values filtered appropriately
            - excluded_dates: List of specific 0N value identifiers found
        """
        if not isinstance(exercise_data, dict):
            return exercise_data if exercise_data is not None else {}, []
        
        excluded_dates = []
        filtered_data = exercise_data.copy()
        
        # Check if this exercise has ANY 0N values
        if not self._has_zero_force_values(exercise_data):
            return exercise_data, []  # No 0N values, return as-is
        
        # Check for bilateral single-session data at the root level
        # This handles cases like: maxOuterLeftForce: 0, maxOuterRightForce: 191.25
        force_fields = [
            'maxOuterLeftForce', 'maxOuterRightForce', 'avgOuterLeftForce', 'avgOuterRightForce',
            'maxInnerLeftForce', 'maxInnerRightForce', 'avgInnerLeftForce', 'avgInnerRightForce'
        ]
        
        # Check if this is a bilateral comparison at root level
        has_left_right_forces = any(field.endswith('LeftForce') for field in force_fields if field in filtered_data) and \
                               any(field.endswith('RightForce') for field in force_fields if field in filtered_data)
        
        if has_left_right_forces:
            # This is bilateral single-session data - check if BOTH sides are 0N for the same metric type
            # Only exclude entire exercise if both left and right are 0N for ALL metric types
            all_metrics_zero = True
            zero_details = []
            
            # Group by metric type (outer vs inner, max vs avg)
            metric_types = ['maxOuter', 'avgOuter', 'maxInner', 'avgInner']
            
            for metric_type in metric_types:
                left_field = f"{metric_type}LeftForce"
                right_field = f"{metric_type}RightForce"
                
                if left_field in filtered_data and right_field in filtered_data:
                    left_val = filtered_data[left_field]
                    right_val = filtered_data[right_field]
                    
                    # If both sides are 0N for this metric type, exclude this metric
                    if left_val in [0, 0.0, "0"] and right_val in [0, 0.0, "0"]:
                        zero_details.append(f"{metric_type}: left={left_val}N, right={right_val}N")
                        # Set both to None to exclude this metric
                        filtered_data[left_field] = None
                        filtered_data[right_field] = None
                    elif left_val in [0, 0.0, "0"] or right_val in [0, 0.0, "0"]:
                        # Only one side is 0N - exclude the entire metric pair for this type
                        if left_val in [0, 0.0, "0"]:
                            zero_details.append(f"{metric_type}: left={left_val}N (excluding metric pair)")
                        if right_val in [0, 0.0, "0"]:
                            zero_details.append(f"{metric_type}: right={right_val}N (excluding metric pair)")
                        # Set both to None to exclude this entire metric type
                        filtered_data[left_field] = None
                        filtered_data[right_field] = None
                    else:
                        # At least one metric type has valid data on both sides
                        all_metrics_zero = False
            
            if zero_details:
                if all_metrics_zero:
                    print(f"        🔍 All bilateral metrics have 0N values: {', '.join(zero_details)} - excluding entire exercise")
                    excluded_dates.extend(zero_details)
                    return {}, excluded_dates  # Return empty dict to exclude entire exercise
                else:
                    print(f"        🔍 Some bilateral metrics have 0N values: {', '.join(zero_details)} - excluding only those metrics")
                    excluded_dates.extend(zero_details)
        
        # Handle summary section with individual force values
        if 'summary' in filtered_data and isinstance(filtered_data['summary'], dict):
            summary = filtered_data['summary']
            summary_zero_details = []
            
            # Check individual force fields in summary
            summary_force_fields = [
                'inner_left_max_force', 'inner_right_max_force', 
                'outer_left_max_force', 'outer_right_max_force',
                'inner_left_avg_force', 'inner_right_avg_force',
                'outer_left_avg_force', 'outer_right_avg_force'
            ]
            
            fields_to_remove = []
            for field in summary_force_fields:
                if field in summary and summary[field] in [0, 0.0, "0"]:
                    summary_zero_details.append(f"summary.{field}={summary[field]}N")
                    fields_to_remove.append(field)
            
            # Remove the 0N fields completely
            for field in fields_to_remove:
                del summary[field]
            
            if summary_zero_details:
                print(f"        🔍 Found 0N in summary fields: {', '.join(summary_zero_details)} - removing fields")
                excluded_dates.extend(summary_zero_details)
        
        # Handle individual graph objects that might have 0N values
        graph_fields = [
            'outerLeftMaxForceGraph', 'outerRightMaxForceGraph',
            'outerLeftAvgForceGraph', 'outerRightAvgForceGraph', 
            'innerLeftMaxForceGraph', 'innerRightMaxForceGraph'
        ]
        
        for graph_field in graph_fields:
            if graph_field in filtered_data and isinstance(filtered_data[graph_field], dict):
                graph_data = filtered_data[graph_field]
                if 'x_axis_entity' in graph_data and graph_data['x_axis_entity'] in [0, 0.0, "0"]:
                    excluded_dates.append(f"{graph_field}.x_axis_entity={graph_data['x_axis_entity']}N")
                    # Remove the entire graph object instead of setting to None
                    del filtered_data[graph_field]
                    print(f"        🔍 Found 0N in {graph_field} - removing entire graph object")
        
        # Handle graph data structures with bilateral time-series data
        for key, value in filtered_data.items():
            if isinstance(value, dict):
                # Handle bilateral time-series data (y_axis_entity_left and y_axis_entity_right arrays)
                if 'y_axis_entity_left' in value and 'y_axis_entity_right' in value:
                    left_values = value['y_axis_entity_left']
                    right_values = value['y_axis_entity_right']
                    x_entities = value.get('x_axis_entities', [])
                    
                    if (isinstance(left_values, list) and isinstance(right_values, list) and 
                        isinstance(x_entities, list) and len(left_values) == len(right_values) == len(x_entities)):
                        
                        # Time-series bilateral data - exclude specific sessions where either side is 0N
                        valid_indices = []
                        for i in range(len(left_values)):
                            left_val = left_values[i]
                            right_val = right_values[i]
                            
                            # If either side is 0N, exclude this entire session/date
                            if left_val in [0, 0.0, "0", None] or right_val in [0, 0.0, "0", None]:
                                date_identifier = x_entities[i] if i < len(x_entities) else f"session_{i}"
                                if left_val in [0, 0.0, "0", None]:
                                    excluded_dates.append(f"{key}.{date_identifier}.left={left_val}N")
                                if right_val in [0, 0.0, "0", None]:
                                    excluded_dates.append(f"{key}.{date_identifier}.right={right_val}N")
                                print(f"        🔍 Found 0N in bilateral time-series {key} at {date_identifier}: left={left_val}N, right={right_val}N - excluding this session")
                            else:
                                valid_indices.append(i)
                        
                        # Update arrays with only valid sessions
                        if valid_indices:
                            filtered_data[key]['y_axis_entity_left'] = [left_values[i] for i in valid_indices]
                            filtered_data[key]['y_axis_entity_right'] = [right_values[i] for i in valid_indices]
                            filtered_data[key]['x_axis_entities'] = [x_entities[i] for i in valid_indices]
                            print(f"        ✅ Kept {len(valid_indices)} valid sessions out of {len(left_values)} total sessions")
                        else:
                            # All sessions had 0N values, clear the arrays
                            filtered_data[key]['y_axis_entity_left'] = []
                            filtered_data[key]['y_axis_entity_right'] = []
                            filtered_data[key]['x_axis_entities'] = []
                            print(f"        ⚠️  All sessions in {key} had 0N values - cleared entire dataset")
                
                # Handle single y_axis_entities array (could be bilateral single-session or time-series)
                elif 'y_axis_entities' in value:
                    y_values = value['y_axis_entities']
                    x_entities = value.get('x_axis_entities', [])
                    
                    if isinstance(y_values, list) and isinstance(x_entities, list) and len(y_values) == len(x_entities):
                        # Determine if this is bilateral single-session or time-series data
                        is_bilateral_single_session = (
                            len(x_entities) == 2 and 
                            set(str(x).lower() for x in x_entities) == {'left', 'right'}
                        )
                        
                        if is_bilateral_single_session:
                            # Single session bilateral comparison - if either side is 0N, exclude entire exercise
                            has_zero = any(v in [0, 0.0, "0", None] for v in y_values)
                            if has_zero:
                                zero_sides = []
                                for i, y_val in enumerate(y_values):
                                    if y_val in [0, 0.0, "0", None]:
                                        side = x_entities[i]
                                        zero_sides.append(f"{side}={y_val}N")
                                
                                excluded_dates.extend([f"{key}.{side}" for side in zero_sides])
                                print(f"        🔍 Found 0N in bilateral single-session {key}: {', '.join(zero_sides)} - excluding entire exercise")
                                return {}, excluded_dates  # Return empty dict to exclude entire exercise
                        
                        else:
                            # Time-series data - remove only specific dates with 0N values
                            valid_indices = []
                            for i, y_val in enumerate(y_values):
                                if y_val not in [0, 0.0, "0", None]:
                                    valid_indices.append(i)
                                else:
                                    identifier = x_entities[i] if i < len(x_entities) else f"index_{i}"
                                    excluded_dates.append(f"{key}.{identifier}={y_val}N")
                            
                            # Update arrays with only valid values
                            if valid_indices:
                                filtered_data[key]['y_axis_entities'] = [y_values[i] for i in valid_indices]
                                filtered_data[key]['x_axis_entities'] = [x_entities[i] for i in valid_indices]
                                print(f"        🔍 Found 0N in time-series {key} - kept {len(valid_indices)} valid sessions")
                            else:
                                # All values were 0N, clear the arrays
                                filtered_data[key]['y_axis_entities'] = []
                                filtered_data[key]['x_axis_entities'] = []
                                print(f"        🔍 All values in {key} were 0N - cleared entire dataset")
        
        # For non-bilateral data, filter individual force fields - set 0N values to None
        for field in ['maxForce', 'avgForce', 'peakForce']:
            if field in filtered_data and filtered_data[field] in [0, 0.0, "0"]:
                excluded_dates.append(f"{field}={filtered_data[field]}N")
                filtered_data[field] = None
        
        # Check if we have any valid data remaining
        has_valid_data = False
        
        # Check if any force fields have valid values (not 0)
        for field in force_fields + ['maxForce', 'avgForce', 'peakForce']:
            if field in filtered_data and filtered_data[field] not in [0, 0.0, "0", None]:
                has_valid_data = True
                break
        
        # Check summary section for valid values
        if not has_valid_data and 'summary' in filtered_data and isinstance(filtered_data['summary'], dict):
            summary = filtered_data['summary']
            for field, value in summary.items():
                if value not in [0, 0.0, "0", None] and isinstance(value, (int, float)):
                    has_valid_data = True
                    break
        
        # Check graph data for valid values
        if not has_valid_data:
            for graph_field in graph_fields:
                if graph_field in filtered_data and isinstance(filtered_data[graph_field], dict):
                    graph_data = filtered_data[graph_field]
                    if 'x_axis_entity' in graph_data and graph_data['x_axis_entity'] not in [0, 0.0, "0", None]:
                        has_valid_data = True
                        break
        
        # Check if any other graph data has valid values
        if not has_valid_data:
            for key, value in filtered_data.items():
                if isinstance(value, dict) and 'y_axis_entities' in value:
                    if value['y_axis_entities']:  # Non-empty array
                        has_valid_data = True
                        break
        
        # Check for any other numeric fields that might be valid (for exercises like squat assessment)
        if not has_valid_data:
            for key, value in filtered_data.items():
                if isinstance(value, (int, float)) and value not in [0, 0.0, "0", None]:
                    has_valid_data = True
                    break
                elif isinstance(value, dict):
                    # Recursively check nested objects for valid numeric values
                    def has_valid_numeric_data(obj):
                        if isinstance(obj, dict):
                            for k, v in obj.items():
                                if isinstance(v, (int, float)) and v not in [0, 0.0, "0", None]:
                                    return True
                                elif isinstance(v, dict) and has_valid_numeric_data(v):
                                    return True
                        return False
                    
                    if has_valid_numeric_data(value):
                        has_valid_data = True
                        break
        
        if not has_valid_data:
            print(f"        ⚠️  No valid data remaining after filtering - excluding entire exercise")
            return {}, excluded_dates
        
        return filtered_data, excluded_dates
        
    
    def transform_matches_to_vald(self, matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Transform matches JSON into VALD input format.
        Filters out metrics with 0N force values (data recording errors).
        
        Args:
            matches: List of match documents from MongoDB
        
        Returns:
            List of VALD records with extracted force frame data (0N sessions excluded)
        """
        
        print(f"\n🔍 VALD DATA QUALITY CHECK")
        print(f"━" * 80)
        print(f"Checking for 0N force values (data recording errors)...")
        
        vald_records = []
        total_excluded_metrics = 0
        total_exercises_checked = 0
        
        for match in matches:
            # Extract basic info
            stance_id = match.get('stanceId')
            full_name = match.get('stanceFullName', 'Unknown')
            vald_ids = match.get('associatedValdId', [])
            vald_id = vald_ids[0] if vald_ids else None
            
            # Extract VALD data root from savedResponse
            saved_response = match.get('savedResponse', {}) or {}
            data_root = saved_response.get('data')
            if not isinstance(data_root, dict):
                # Fallback: some integrations may put forceFrame/forceDeck directly under savedResponse
                data_root = saved_response
            data = data_root or {}
            
            # Create VALD record
            vald_record = {
                '_id': match.get('_id'),
                'user_id': stance_id,
                'name': full_name,
                'vald_id': vald_id,
                'date_of_birth': match.get('dateOfBirth'),
                'sex': match.get('sex'),
                'last_recorded_utc': match.get('lastRecordedUtc'),
                'is_active': match.get('isActive'),
                'created_at': match.get('createdAt'),
                'updated_at': match.get('updatedAt'),
                'exercises': {
                    'forceFrame': {},
                    'forceDeck': {},
                    'dynamo': {}
                },
                'data_quality': {
                    'excluded_sessions': []  # Track excluded sessions
                }
            }
            
            # Process force frame exercises (from either data.forceFrame or savedResponse.forceFrame)
            force_frame_data = data.get('forceFrame') or saved_response.get('forceFrame') or {}
            if force_frame_data:
                print(f"  📊 Checking ForceFrame exercises for {full_name}...")
                for exercise_key, exercise_data in force_frame_data.items():
                    # Skip non-exercise keys
                    if exercise_key in ['dynamo', 'forceDeck']:
                        continue
                    
                    total_exercises_checked += 1
                    print(f"    🔍 Checking {exercise_key}...")
                    
                    # Filter out 0N force value sessions
                    if exercise_data is None:
                        continue
                    
                    filtered_data, excluded_dates = self._filter_zero_force_sessions(exercise_data)
                    
                    if excluded_dates:
                        total_excluded_metrics += len(excluded_dates)
                        print(f"      ❌ FOUND 0N VALUES: {len(excluded_dates)} metrics with 0N force values")
                        print(f"      📅 Excluded metrics: {', '.join(excluded_dates)}")
                        print(f"      🧹 Filtering out these metrics from analysis")
                        vald_record['data_quality']['excluded_sessions'].extend([
                            {
                                'exercise': exercise_key,
                                'category': 'forceFrame',
                                'dates': excluded_dates,
                                'reason': '0N force values (data recording error)'
                            }
                        ])
                    else:
                        print(f"      ✅ No 0N values detected - data is clean")
                    
                    # Exercise data is directly in the exercise object (not wrapped in 'data' key)
                    exercise_record = {
                        'exercise_name': exercise_key,
                        'data': filtered_data  # Store the filtered metrics
                    }
                    
                    vald_record['exercises']['forceFrame'][exercise_key] = exercise_record
            
            # Process forceDeck exercises (from either data.forceDeck or savedResponse.forceDeck)
            force_deck_data = data.get('forceDeck') or saved_response.get('forceDeck') or {}
            if force_deck_data:
                print(f"  📊 Checking ForceDeck exercises for {full_name}...")
                for exercise_key, exercise_data in force_deck_data.items():
                    total_exercises_checked += 1
                    print(f"    🔍 Checking {exercise_key}...")
                    
                    # Filter out 0N force value sessions
                    if exercise_data is None:
                        print(f"      ⚠️  Exercise data is None - skipping")
                        continue
                    
                    try:
                        filtered_data, excluded_dates = self._filter_zero_force_sessions(exercise_data)
                    except Exception as e:
                        print(f"      ❌ Error filtering exercise {exercise_key}: {e}")
                        print(f"      📊 Exercise data type: {type(exercise_data)}")
                        print(f"      📊 Exercise data: {exercise_data}")
                        continue
                    
                    if excluded_dates:
                        total_excluded_metrics += len(excluded_dates)
                        print(f"      ❌ FOUND 0N VALUES: {len(excluded_dates)} metrics with 0N force values")
                        print(f"      📅 Excluded metrics: {', '.join(excluded_dates)}")
                        print(f"      🧹 Filtering out these metrics from analysis")
                        vald_record['data_quality']['excluded_sessions'].extend([
                            {
                                'exercise': exercise_key,
                                'category': 'forceDeck',
                                'dates': excluded_dates,
                                'reason': '0N force values (data recording error)'
                            }
                        ])
                    else:
                        print(f"      ✅ No 0N values detected - data is clean")
                    
                    exercise_record = {
                        'exercise_name': exercise_key,
                        'data': filtered_data
                    }
                    vald_record['exercises']['forceDeck'][exercise_key] = exercise_record
            
            # Process dynamo exercises (from either data.dynamo or savedResponse.dynamo)
            dynamo_data = data.get('dynamo') or saved_response.get('dynamo') or {}
            if dynamo_data:
                print(f"  📊 Checking Dynamo exercises for {full_name}...")
                for exercise_key, exercise_data in dynamo_data.items():
                    total_exercises_checked += 1
                    print(f"    🔍 Checking {exercise_key}...")
                    
                    # Filter out 0N force value sessions
                    if exercise_data is None:
                        continue
                    
                    filtered_data, excluded_dates = self._filter_zero_force_sessions(exercise_data)
                    
                    if excluded_dates:
                        total_excluded_metrics += len(excluded_dates)
                        print(f"      ❌ FOUND 0N VALUES: {len(excluded_dates)} metrics with 0N force values")
                        print(f"      📅 Excluded metrics: {', '.join(excluded_dates)}")
                        print(f"      🧹 Filtering out these metrics from analysis")
                        vald_record['data_quality']['excluded_sessions'].extend([
                            {
                                'exercise': exercise_key,
                                'category': 'dynamo',
                                'dates': excluded_dates,
                                'reason': '0N force values (data recording error)'
                            }
                        ])
                    else:
                        print(f"      ✅ No 0N values detected - data is clean")
                    
                    exercise_record = {
                        'exercise_name': exercise_key,
                        'data': filtered_data
                    }
                    vald_record['exercises']['dynamo'][exercise_key] = exercise_record
            
            vald_records.append(vald_record)
        
        # Print summary of data quality check
        print(f"━" * 80)
        print(f"📊 VALD DATA QUALITY SUMMARY:")
        print(f"  Total exercises checked: {total_exercises_checked}")
        print(f"  Metrics with 0N values found: {total_excluded_metrics}")
        
        if total_excluded_metrics > 0:
            print(f"  ⚠️  Data recording errors detected and filtered out:")
            for record in vald_records:
                if record['data_quality']['excluded_sessions']:
                    print(f"\n    Patient: {record['name']} ({record['user_id']})")
                    for exclusion in record['data_quality']['excluded_sessions']:
                        dates_str = ", ".join(exclusion['dates'])
                        print(f"      - {exclusion['exercise']} ({exclusion['category']}): {dates_str}")
            print(f"  ✅ Clean data will be used for analysis")
        else:
            print(f"  ✅ All VALD data is clean - no 0N values detected")
        
        print(f"━" * 80)
        
        return vald_records
    
    def close(self):
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            print("✅ MongoDB connection closed")


# Example usage
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python fetch_and_transform_vald.py <stance_id>")
        sys.exit(1)
    
    stance_id = sys.argv[1]
    
    transformer = VALDTransformer()
    vald_data = transformer.get_vald_data_for_patient(stance_id)
    
    if vald_data:
        print(f"\n✨ Successfully fetched and transformed VALD data for {stance_id}")
        print(f"📊 Total VALD records: {len(vald_data)}")
    else:
        print(f"❌ No VALD data found for {stance_id}")
    
    transformer.close()
