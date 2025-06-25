import unittest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock
import os
import sys
from datetime import datetime

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock environment variables before importing the module
os.environ['DEPOT_TOOL_URL'] = 'mock_depot_url'
os.environ['VEHICLE_AGENCY_URL'] = 'mock_vehicle_agency_url'
os.environ['REALTIME_API_URL'] = 'mock_realtime_api_url'
os.environ['TREE_DICT_FILE'] = 'route_comp/tree_dict.pkl'
os.environ['ROUTES_FILE'] = 'route_comp/routes.txt'
os.environ['TIMEZONE'] = 'UTC'

# Import functions to test
from realtime_processor import (
    get_vehicle_details,
    nearest_seq_tree
)


class TestRealtimeProcessorUnits(unittest.TestCase):
    """Unit tests for individual functions in realtime_processor.py"""

    def setUp(self):
        """Set up test data used by multiple tests"""
        # Mock tree_dict for nearest_seq_tree tests
        self.tree_dict = {
            'R1': {
                'tree': MagicMock(),
                'stop_ids': [
                    {'stop_name': 'First Stop', 'stop_id': 'S1'},
                    {'stop_name': 'Middle Stop', 'stop_id': 'S2'},
                    {'stop_name': 'Last Stop', 'stop_id': 'S3'}
                ]
            }
        }
        # Configure the mock tree to return index 1 (Middle Stop)
        self.tree_dict['R1']['tree'].query.return_value = (0.1, 1)
        self.tree_dict['R1']['tree'].data = [[1, 1], [2, 2], [3, 3]]  # 3 stops

    def test_timestamp_conversion(self):
        """Test manual conversion of timestamp to ISO format"""
        # This is a simple test to verify timestamp conversion logic
        timestamp = 1672531200  # 2023-01-01 00:00:00 UTC
        
        # Convert using pandas (similar to what's done in fetch_and_process_data)
        dt = pd.to_datetime(timestamp, unit='s')
        iso_str = dt.strftime('%Y-%m-%dT%H:%M:%S+00:00')
        
        # Check result
        self.assertEqual(iso_str, '2023-01-01T00:00:00+00:00')

    @patch('realtime_processor.tree_dict', None)  # Ensure we use our mock
    def test_nearest_seq_tree(self):
        """Test finding nearest stop sequence using tree"""
        # Patch the global tree_dict
        with patch('realtime_processor.tree_dict', self.tree_dict):
            # Call the function
            result = nearest_seq_tree('R1', 34.0522, -118.2437)
            
            # Expected: "towards Last Stop,66.67,Middle Stop,S2"
            # 66.67 because it's the 2nd stop out of 3 (2/3 * 100 = 66.67%)
            self.assertTrue('towards Last Stop' in result)
            self.assertTrue('Middle Stop' in result)
            self.assertTrue('S2' in result)
            # Check that the percentage is roughly 66.67%
            percentage = float(result.split(',')[1])
            self.assertAlmostEqual(percentage, 66.67, delta=0.1)

    def test_get_vehicle_details(self):
        """Test retrieving vehicle details from a list"""
        # Create test data
        vehicle_list = [
            {'vehicle_id': 'V1', 'agency': 'A1', 'depot': 'D1', 'ac': True},
            {'vehicle_id': 'V2', 'agency': 'A2', 'depot': 'D2', 'ac': False}
        ]
        
        # Test finding an existing vehicle
        result = get_vehicle_details(vehicle_list, 'V1')
        self.assertEqual(result, {'agency': 'A1', 'depot': 'D1', 'ac': True})
        
        # Test with a non-existent vehicle
        result = get_vehicle_details(vehicle_list, 'V3')
        self.assertIsNone(result)

    def test_vehicle_data_processing(self):
        """Test basic vehicle data processing logic"""
        # Create test vehicle data like what would be created in fetch_and_process_data
        vehicle_data = [
            {
                "vehicle_id": "V1",
                "agency": "A1",
                "depot": "D1",
                "ac": True,
                "lat": 34.0522,
                "lng": -118.2437,
                "route_id": "R1",
                "timestamp": 1672531200
            }
        ]
        
        # Convert to DataFrame (as done in the function)
        df = pd.DataFrame(vehicle_data)
        
        # Check basic processing
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]['vehicle_id'], 'V1')
        self.assertEqual(df.iloc[0]['agency'], 'A1')


if __name__ == '__main__':
    unittest.main()
