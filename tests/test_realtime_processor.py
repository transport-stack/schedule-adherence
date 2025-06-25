import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
from google.transit import gtfs_realtime_pb2
import os

# Set environment variables to point to our synthetic data files.
# These patches are applied before the module is imported, which is crucial.
@patch.dict(os.environ, {
    'DEPOT_TOOL_URL': 'mock_depot_url',
    'VEHICLE_AGENCY_URL': 'mock_vehicle_agency_url',
    'REALTIME_API_URL': 'mock_realtime_api_url',
    'TREE_DICT_FILE': 'route_comp/tree_dict.pkl',
    'ROUTES_FILE': 'route_comp/routes.txt',
    'TIMEZONE': 'UTC'
})
@patch('realtime_processor.create_engine')
@patch('realtime_processor.inspect')
class TestRealtimeProcessor(unittest.TestCase):

    @patch('requests.get')
    def test_fetch_and_process_data_with_synthetic_data(self, mock_requests_get, mock_inspector, mock_engine):
        """
        Test successful fetching and processing of real-time data
        using synthetic data files instead of extensive mocks.
        """
        # Importing here ensures the patches are active when the module loads.
        from realtime_processor import fetch_and_process_data

        # --- Mock API response ---
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.header.gtfs_realtime_version = "2.0"
        feed.header.timestamp = 1672531200
        entity = feed.entity.add()
        entity.id = '1'
        entity.vehicle.trip.route_id = 'R1'
        entity.vehicle.vehicle.id = 'V1'
        entity.vehicle.position.latitude = 34.0522
        entity.vehicle.position.longitude = -118.2437
        entity.vehicle.timestamp = 1672531200  # 2023-01-01 00:00:00 UTC

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = feed.SerializeToString()
        mock_requests_get.return_value = mock_response

        # --- Mock Database ---
        mock_conn = MagicMock()
        mock_engine.return_value.connect.return_value = mock_conn
        mock_inspector.return_value.has_table.return_value = False
        # Patch the to_sql method on the DataFrame class within a context
        with patch('pandas.DataFrame.to_sql') as mock_to_sql:
            # --- Call the function ---
            fetch_and_process_data()

            # --- Assertions ---
            # Check that the API was called
            mock_requests_get.assert_called_once_with('mock_realtime_api_url', timeout=30)
            # Check that the data was written to the database
            self.assertTrue(mock_to_sql.called)
            # Check the processed data
            processed_df = mock_to_sql.call_args[0][0]
            self.assertEqual(len(processed_df), 1)
            self.assertEqual(processed_df.iloc[0]['vehicle_id'], 'V1')
            self.assertEqual(processed_df.iloc[0]['agency'], 'A1')
            self.assertTrue(processed_df.iloc[0]['same_as_scheduled'])

if __name__ == '__main__':
    unittest.main()
