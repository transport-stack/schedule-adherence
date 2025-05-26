# Schedule Adherence Module

This module analyzes real-time transit vehicle data to determine schedule adherence - how well vehicles are following their scheduled timetables. It compares actual arrival and departure times with scheduled times to calculate adherence metrics.

## Overview

The Schedule Adherence Module processes real-time GTFS vehicle position data and compares it with scheduled timetables to:

1. Determine if vehicles are running on their assigned routes
2. Calculate arrival and departure adherence at stops (early, on-time, or late)
3. Track trip completion percentages
4. Generate detailed adherence reports for transit operators

## Features

- Real-time monitoring of vehicle positions via GTFS-RT feeds
- Comparison of actual vs. scheduled route assignments
- Calculation of schedule adherence at the start and end of trips
- Trip completion tracking
- JSON output for easy integration with other systems

## Requirements

- Python 3.7+
- Dependencies listed in `requirements.txt`

## Installation

1. Clone this repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Create a `.env` file based on the provided `.env.example` with your API endpoints and configuration

## Configuration

The module uses environment variables for configuration. Create a `.env` file with the following variables:

```
# API Endpoints
DEPOT_TOOL_URL=https://api.example.com/depot_tool_duty_master
VEHICLE_AGENCY_URL=https://api.example.com/vehicle_agency_data
REALTIME_API_URL=https://api.example.com/realtime_gtfs_feed

# File Paths
ROUTES_FILE=route_comp/routes.txt
TREE_DICT_FILE=route_comp/tree_dict.pkl

# Timezone Settings
TIMEZONE=Asia/Kolkata
```

## Directory Structure

The module requires a `route_comp` directory with the following structure:

```
route_comp/
├── data/                    # Directory for storing data files
├── routes.txt               # GTFS routes file
├── tree_dict.pkl            # Pickle file containing route trees
└── vehicle_data.json        # Vehicle metadata
```

## Usage

Run the schedule adherence module:

```
python realtime_processor.py
```

This will:
1. Fetch real-time vehicle positions
2. Compare with scheduled timetables
3. Calculate adherence metrics
4. Generate output files in the `route_comp` directory

## Output

The module generates the following output files:

1. `route_comp/actualVsScheduled.json` - JSON file containing actual vs. scheduled route assignments
2. `route_comp/SCHEDULE_ADHERENCE.json` - Detailed schedule adherence metrics for each trip

### Output Format

The `SCHEDULE_ADHERENCE.json` file contains an array of trip records with the following structure:

```json
{
  "vehicle": {
    "id": "VEHICLE_ID",
    "is_ac": true/false,
    "fuel_type": "electric/cng",
    "depot": {
      "name": "DEPOT_NAME",
      "agency": "AGENCY_NAME"
    }
  },
  "trip_completion": 100.0,
  "pb_trip_id": "TRIP_ID",
  "route_id": "ROUTE_ID",
  "route_short_name": "ROUTE_SHORT_NAME",
  "route_long_name": "ROUTE_LONG_NAME",
  "actual": {
    "start_timestamp": "YYYY-MM-DDThh:mm:ss+05:30",
    "end_timestamp": "YYYY-MM-DDThh:mm:ss+05:30"
  },
  "scheduled": {
    "start_timestamp": "YYYY-MM-DDThh:mm:ss+05:30",
    "end_timestamp": "YYYY-MM-DDThh:mm:ss+05:30"
  },
  "start_adherence_in_seconds": 120,
  "end_adherence_in_seconds": 180,
  "stops": [
    {
      "id": "STOP_ID",
      "name": "STOP_NAME",
      "actual_arrival": "YYYY-MM-DDThh:mm:ss+05:30",
      "scheduled_arrival": "YYYY-MM-DDThh:mm:ss+05:30",
      "actual_departure": "YYYY-MM-DDThh:mm:ss+05:30",
      "scheduled_departure": "YYYY-MM-DDThh:mm:ss+05:30",
      "arrival_adherence_in_seconds": 120,
      "departure_adherence_in_seconds": 120
    }
  ]
}
```

## Algorithm

The schedule adherence algorithm works as follows:

1. Fetch real-time vehicle positions from GTFS-RT feed
2. Match vehicles to their scheduled assignments
3. Track vehicle progress along routes using stop sequences
4. Determine actual arrival and departure times at stops
5. Compare with scheduled times to calculate adherence
6. Generate adherence metrics and reports

## License

[Your License Here]
