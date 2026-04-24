# Schedule Adherence Module

This module analyzes real-time transit vehicle data to determine schedule adherence—how well vehicles are following their scheduled timetables. It compares actual arrival and departure times with scheduled times to calculate adherence metrics.

## Overview

The Schedule Adherence Module processes real-time GTFS vehicle position data and compares it with scheduled timetables to:

1. Determine if vehicles are running on their assigned routes.
2. Calculate arrival and departure adherence at stops (early, on-time, or late).
3. Track trip completion percentages.
4. Generate detailed adherence reports for transit operators.

## Features

- Real-time monitoring of vehicle positions via GTFS-RT feeds.
- Comparison of actual vs. scheduled route assignments.
- Calculation of schedule adherence at the start and end of trips.
- Trip completion tracking.
- JSON output for easy integration with other systems.

## Requirements

- Python 3.7+
- Dependencies listed in `requirements.txt`

## Setup and Installation

1. **Clone the repository:**

    ```bash
    git clone https://github.com/transport-stack/schedule-adherence.git
    cd schedule-adherence
    ```

2. **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

3. **Create a `.env` file:**

    Create a `.env` file in the root directory by copying the example file:

    ```bash
    cp .env.example .env
    ```

    Update the `.env` file with your specific API endpoints and configuration:

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

4. **Directory Structure:**

    The module requires a `route_comp` directory with the following structure:

    ```
    route_comp/
    ├── data/                    # Directory for storing data files
    ├── routes.txt               # GTFS routes file
    ├── tree_dict.pkl            # Pickle file containing route trees
    └── vehicle_data.json        # Vehicle metadata
    ```

## Data Processing Pipeline

The application runs in two main stages:

1. **Real-time Data Processing (`realtime_processor.py`):**
    - Fetches real-time vehicle positions from the GTFS-RT feed.
    - Downloads and updates vehicle and depot data.
    - Processes the data and stores it in a local SQLite database (`route_comp/data/route_comp_{YYYY_MM_DD}.db`).
    - Generates a JSON file (`route_comp/actualVsScheduled.json`) that compares actual vs. scheduled routes.

2. **Schedule Adherence Calculation (`adherence_calculator.py`):**
    - Reads the processed data from the SQLite database.
    - Calculates schedule adherence metrics, including start/end trip adherence and stop-level adherence.
    - Generates a detailed JSON report (`route_comp/SCHEDULE_ADHERENCE.json`).

## Usage

To run the complete pipeline, execute the scripts in the following order:

1. **Run the real-time processor:**

    ```bash
    python realtime_processor.py
    ```

2. **Run the adherence calculator:**

    ```bash
    python adherence_calculator.py
    ```

## Output

The module generates the following output files:

1. `route_comp/actualVsScheduled.json`: A JSON file containing the comparison of actual vs. scheduled route assignments.
2. `route_comp/SCHEDULE_ADHERENCE.json`: A detailed schedule adherence report for each trip. The format is as follows:

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

## License

[Your License Here]
