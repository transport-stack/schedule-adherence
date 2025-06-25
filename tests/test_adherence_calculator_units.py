import unittest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock
import os
import sys
from datetime import datetime

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import functions to test
from adherence_calculator import (
    process_duplicates,
    adding_schedule_timetable,
    convert_to_json
)


class TestAdherenceCalculatorUnits(unittest.TestCase):
    """Unit tests for individual functions in adherence_calculator.py"""

    def test_process_duplicates(self):
        """Test processing of duplicate records"""
        # Create test data with duplicates - include all required columns
        test_df = pd.DataFrame({
            'vehicle_id': ['V1', 'V1', 'V2'],
            'agency': ['A1', 'A1', 'A2'],
            'route_id': ['R1', 'R1', 'R2'],
            'scheduled_start_timestamp': ['2023-01-01 00:00:00', '2023-01-01 00:00:00', '2023-01-01 00:10:00'],
            'scheduled_end_timestamp': ['2023-01-01 01:00:00', '2023-01-01 01:00:00', '2023-01-01 01:10:00'],
            'stops_count': [5, 10, 7]  # Second V1 record has more stops
        })
        
        # Call the function
        result = process_duplicates(test_df)
        
        # Check result
        self.assertEqual(len(result), 2)  # Should have 2 unique vehicle/route combinations
        # V1/R1 should have the record with more stops
        v1_row = result[result['vehicle_id'] == 'V1'].iloc[0]
        self.assertEqual(v1_row['stops_count'], 10)  # Should keep the record with more stops

    def test_adding_schedule_timetable(self):
        """Test merging adherence data with scheduled timetable"""
        # Create test adherence data
        adherence_df = pd.DataFrame({
            'vehicle_id': ['V1', 'V2'],
            'route_id': ['R1', 'R2'],
            'agency': ['A1', 'A2'],
            'actual_start_timestamp': ['2023-01-01 00:05:00', '2023-01-01 00:15:00'],
            'actual_end_timestamp': ['2023-01-01 00:55:00', '2023-01-01 01:05:00'],
            'scheduled_start_timestamp': ['2023-01-01 00:00:00', '2023-01-01 00:10:00'],
            'scheduled_end_timestamp': ['2023-01-01 00:50:00', '2023-01-01 01:00:00']
        })
        
        # Create test scheduled timestamp data - include agency_id
        scheduled_df = pd.DataFrame({
            'vehicle_id': ['V1', 'V2', 'V3'],
            'route_id': ['R1', 'R2', 'R3'],
            'agency': ['A1', 'A2', 'A3'],
            'agency_id': ['A1', 'A2', 'A3'],  # Add agency_id column
            'scheduled_start_timestamp': ['2023-01-01 00:00:00', '2023-01-01 00:10:00', '2023-01-01 00:20:00'],
            'scheduled_end_timestamp': ['2023-01-01 00:50:00', '2023-01-01 01:00:00', '2023-01-01 01:10:00']
        })
        
        # Convert timestamp strings to datetime objects
        for df in [adherence_df, scheduled_df]:
            for col in df.columns:
                if 'timestamp' in col:
                    df[col] = pd.to_datetime(df[col])
        
        # Mock the tree_dict global variable which is used in adding_schedule_timetable
        with patch('adherence_calculator.tree_dict', {}):
            # Call the function
            result = adding_schedule_timetable(adherence_df, scheduled_df)
        
            # Check result
            self.assertEqual(len(result), 3)  # Should include all scheduled records
            
            # Check that the result contains the expected vehicles
            self.assertTrue('V1' in result['vehicle_id'].values)
            self.assertTrue('V2' in result['vehicle_id'].values)
            self.assertTrue('V3' in result['vehicle_id'].values)
            
            # Check V3 has NaN for actual timestamps (no matching adherence data)
            v3_row = result[result['vehicle_id'] == 'V3'].iloc[0]
            self.assertTrue(pd.isna(v3_row['actual_start_timestamp']))
            self.assertTrue(pd.isna(v3_row['actual_end_timestamp']))

    def test_convert_to_json(self):
        """Test conversion of DataFrame row to JSON format"""
        # Create a dictionary with all required columns that would be in a row
        test_row = {
            'vehicle_id': 'V1',
            'route_id': 'R1',
            'agency': 'A1',
            'depot': 'D1',
            'ac': True,
            'fuel': 'diesel',
            'actual_start_timestamp': '2023-01-01T00:05:00+05:30',
            'actual_end_timestamp': '2023-01-01T00:55:00+05:30',
            'scheduled_start_timestamp': '2023-01-01T00:00:00+05:30',
            'scheduled_end_timestamp': '2023-01-01T00:50:00+05:30',
            'start_adherence': 300,  # 5 minutes in seconds
            'end_adherence': 300,
            'first_stop_id': 'S1',
            'first_stop_name': 'Stop A',
            'last_stop_id': 'S2',
            'last_stop_name': 'Stop B'
        }
        
        # Call the function with a single row
        result = convert_to_json(test_row)
        
        # Check result structure
        self.assertTrue(isinstance(result, dict))
        
        # Check the structure of the result
        self.assertEqual(result['vehicle']['id'], 'V1')
        self.assertEqual(result['vehicle']['agency'], 'A1')
        self.assertEqual(result['vehicle']['depot'], 'D1')
        self.assertEqual(result['route']['id'], 'R1')
        self.assertEqual(result['start_adherence_in_seconds'], 300)
        self.assertEqual(result['end_adherence_in_seconds'], 300)
        
        # Check timestamps
        self.assertEqual(result['timestamps']['actual_start'], '2023-01-01T00:05:00+05:30')
        self.assertEqual(result['timestamps']['scheduled_start'], '2023-01-01T00:00:00+05:30')
        
        # Check stops are included
        self.assertTrue('stops' in result)
        self.assertTrue(isinstance(result['stops'], list))
        
        # Verify stops contain first and last stop
        stop_ids = [stop['id'] for stop in result['stops']]
        self.assertTrue('S1' in stop_ids)
        self.assertTrue('S2' in stop_ids)


if __name__ == '__main__':
    unittest.main()
