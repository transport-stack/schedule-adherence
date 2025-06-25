#app.py
import requests
from google.transit import gtfs_realtime_pb2
import pytz
import wget
import os
import pandas as pd
from tqdm import tqdm
from datetime import datetime, timedelta, timezone
import pickle
import logging
import json
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect
import re
import csv
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('schedule_adherence.log')
    ]
)
logger = logging.getLogger('schedule_adherence')

# Load environment variables
load_dotenv()

# Check for required environment variables
required_env_vars = [
    'DEPOT_TOOL_URL', 'VEHICLE_AGENCY_URL', 'REALTIME_API_URL'
]

missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
    logger.error("Please set these variables in your .env file")
    sys.exit(1)

# Get timezone from environment or use default
timezone = pytz.timezone(os.getenv("TIMEZONE", "Asia/Kolkata"))
current_time = datetime.now(timezone)
f_name = current_time.strftime("%Y_%m_%d")

# Ensure data directory exists
os.makedirs('route_comp/data', exist_ok=True)

# Create an SQLAlchemy engine
db_file = 'route_comp/data/route_comp_' + f_name + ".db"
engine = create_engine("sqlite:///" + db_file)

# Check if the table already exists in the database
inspector = inspect(engine)
table_exists = inspector.has_table('gps_Vs_sch')

# Load route tree dictionary
tree_dict = {}
tree_dict_file = os.getenv("TREE_DICT_FILE", 'route_comp/tree_dict.pkl')
try:
    with open(tree_dict_file, 'rb') as file:
        tree_dict = pickle.load(file)
    logger.info(f"Successfully loaded tree dictionary from {tree_dict_file}")
except FileNotFoundError:
    logger.error(f"Tree dictionary file not found: {tree_dict_file}")
    logger.error("Please ensure the file exists and the path is correct in your .env file")
    sys.exit(1)
except Exception as e:
    logger.error(f"Error loading tree dictionary: {str(e)}")
    sys.exit(1)

# Get environment variables
DEPOT_TOOL_URL = os.getenv("DEPOT_TOOL_URL")
VEHICLE_AGENCY_URL = os.getenv("VEHICLE_AGENCY_URL")
REALTIME_API_URL = os.getenv("REALTIME_API_URL")
ROUTES_FILE = os.getenv("ROUTES_FILE", 'route_comp/routes.txt')

def apply_nearest_seq_tree(row):
      return nearest_seq_tree(row['route_id'], row['lat'], row['lng'])

def nearest_seq_tree(route_id, v_lat, v_lon):
    tree_info = tree_dict[route_id]
    tree = tree_info['tree']
    stop_ids = tree_info['stop_ids']

    _, idx = tree.query([v_lat, v_lon])
    total_stops = len(tree.data)
    result = float(((idx + 1) / total_stops) * 100)
    result = round(result, 2)
    final_result = 'towards ' + str(stop_ids[-1]['stop_name']) + ',' + str(result) + ',' + str(stop_ids[idx]['stop_name']) + ',' + str(stop_ids[idx]['stop_id'])
    return final_result

def get_vehicle_details(vehicle_list, target_vehicle_id):
    for vehicle in vehicle_list:
        if vehicle["vehicle_id"] == target_vehicle_id:
            return {
                "agency": vehicle["agency"],
                "depot": vehicle["depot"],
                "ac": vehicle["ac"]
            }

def add_to_csv(vehicle_id):
    # Function to add vehicle ID to a CSV file
    with open('not_available_vehicle_ids.csv', 'a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([vehicle_id])

def fetch_and_process_data():
    """Fetch real-time vehicle data and process it to calculate schedule adherence.
    
    Returns:
        str: JSON string containing processed data
    """
    vehicle_data = []

    # Load vehicle agency data
    file_name = "route_comp/vehicle_data.json"
    try:
        if os.path.exists(file_name):
            with open(file_name, "r") as json_file:
                vehicle_agency_data = json.load(json_file)
                logger.info(f"Loaded vehicle data from {file_name}")
        else:
            vehicle_agency_data = []
            logger.warning(f"Vehicle data file {file_name} not found")
    except Exception as e:
        logger.error(f"Error loading vehicle data: {str(e)}")
        vehicle_agency_data = []

    # Fetch real-time vehicle positions
    try:
        logger.info(f"Fetching real-time data from {REALTIME_API_URL}")
        response = requests.get(REALTIME_API_URL, timeout=30)

        if response.status_code == 200:
            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(response.content)
            logger.info(f"Successfully fetched real-time data with {len(feed.entity)} entities")

            for entity in feed.entity:
                if entity.HasField("vehicle"):
                    vehicle_id = entity.vehicle.vehicle.id
                    details = get_vehicle_details(vehicle_agency_data, vehicle_id)

                    if details is None:
                        logger.warning(f"Vehicle details not found for vehicle ID: {vehicle_id}")
                        add_to_csv(vehicle_id)
                    else:
                        vehicle_data.append({
                            "vehicle_id": entity.vehicle.vehicle.id,
                            "agency": details["agency"],
                            "depot": details["depot"],
                            "ac": details["ac"],
                            "lat": entity.vehicle.position.latitude,
                            "lng": entity.vehicle.position.longitude,
                            "route_id": entity.vehicle.trip.route_id,
                            "timestamp": entity.vehicle.timestamp,
                        })
        else:
            logger.error(f"Error: Unable to fetch data. Status Code: {response.status_code}")
            return
    except requests.exceptions.RequestException as e:
        logger.error(f"Error making request to REALTIME_API_URL: {str(e)}")
        return
    except Exception as e:
        logger.error(f"Unexpected error processing real-time data: {str(e)}")
        return
    
    df = pd.DataFrame(vehicle_data)
    df = df.drop_duplicates(subset=['lat', 'lng','vehicle_id','route_id','timestamp'])
    df['route_id'] = df['route_id'].astype(str)
    
    routes_data = pd.read_csv('route_comp/routes.txt',usecols=['route_id', 'route_long_name','agency_id'])
    routes_data['route_id'] = routes_data['route_id'].astype(str)
    merged_df = pd.merge(df, routes_data, on='route_id', how='left')

    df = merged_df
    df['nearest_sequence'] = float('nan')

    tqdm.pandas(desc="Calculating Nearest Sequence")
    df['nearest_sequence'] = df.progress_apply(apply_nearest_seq_tree, axis=1)
    df.columns = df.columns.str.replace('route_long_name','actual_route_short_name')
    df['actual_route_short_name'] = df['actual_route_short_name'].astype(str)
    df['nearest_sequence'] = df['nearest_sequence'].astype(str)
    df['actual_route_long_name'] = df['actual_route_short_name'] + ' ' + df['nearest_sequence']
    df['ist_timestamp'] = pd.to_datetime(df['timestamp'], unit='s') + timedelta(hours=5, minutes=30)
    df['bucket'] = df['ist_timestamp'].dt.floor('5min').dt.strftime('%Y-%m-%dT%H:%M:%S+05:30')
    df[['actual_route_long_name', 'trip_completion', 'closest_stop_name','closest_stop_id']] = df['actual_route_long_name'].str.split(',', n=3, expand=True)
    # print(df.columns)
    df.columns = df.columns.str.replace('route_id','actual_route_id')
    df['ist_timestamp'] = df['ist_timestamp'].dt.strftime('%Y-%m-%dT%H:%M:%S+05:30')
    df.columns = df.columns.str.replace('ist_timestamp','closest_stop_time')
    df['trip_completion'] = df['trip_completion'].astype(float)
    pivot_df = df 
    columns_to_drop = ['lat', 'lng', 'timestamp','nearest_sequence']
    df = df.drop(columns=columns_to_drop)

    final_df = df
    # filename = f'gps_data.csv'
    # final_df.to_csv(filename)
    
    depot_df = pd.read_csv('route_comp/depot_tool_duty_master.txt')
    depot_df.columns = depot_df.columns.str.replace('Plate No.','vehicle_id')
    pattern = r"CL|_| |P[0-9]+|\."  # Updated regex pattern to include any number after 'P'
    depot_df['Route No.'] = depot_df['Route No.'].str.replace(pattern, "", regex=True)
    depot_df['Route No.'] = depot_df['Route No.'].apply(lambda x: re.sub(r'DN$', 'DOWN', x)).str.upper()
    # print(depot_df['Route No.'])
    current_date = datetime.now().strftime('%Y-%m-%d')

    ist = pytz.timezone('Asia/Kolkata')

    for index, row in tqdm(depot_df.iterrows(), total=len(depot_df), desc="Convert to ISO Time Format"):
        trip_start_time = datetime.strptime(f"{current_date} {row['Trip Start Time']}", '%Y-%m-%d %H:%M:%S').replace(tzinfo=ist)
        trip_end_time = datetime.strptime(f"{current_date} {row['Trip End Time']}", '%Y-%m-%d %H:%M:%S').replace(tzinfo=ist)

        # Check if Trip End Time is smaller than Trip Start Time, add one day
        if trip_end_time < trip_start_time:
            trip_end_time += timedelta(days=1)

        # Convert to ISO format
        depot_df.at[index, 'Trip Start Time'] = trip_start_time.isoformat()
        depot_df.at[index, 'Trip End Time'] = trip_end_time.isoformat()

    current_time = datetime.now(ist)

    # Filter rows based on current time
    depot_df = depot_df[(depot_df['Trip Start Time'] <= current_time.isoformat()) & (current_time.isoformat() <= depot_df['Trip End Time'])]

    # If there are rows where current time is not in between "Trip Start Time" and "Trip End Time", drop those rows
    depot_df.dropna(inplace=True)

    # print(depot_df['Trip End Time'],depot_df['Trip Start Time'])

    final_df['scheduled_route_short_name'] = ''
    final_df['scheduled_route_id'] = ''

    # Convert 'vehicle_id' to categorical if it's not already
    final_df['vehicle_id'] = final_df['vehicle_id'].astype('category')
    depot_df['vehicle_id'] = depot_df['vehicle_id'].astype('category')

    # Set 'vehicle_id' as the index for both DataFrames
    final_df.set_index('vehicle_id', inplace=True)
    depot_df.set_index('vehicle_id', inplace=True)
    
    def fill_actual_route(row):
        vehicle_id = row.name  # Access the index (vehicle_id) directly
        trip_start_time = row['Trip Start Time']
        trip_end_time = row['Trip End Time']
        route_no = row['Route No.']
        route_id = None
        final_df_row_agency = pivot_df.loc[pivot_df['vehicle_id'] == vehicle_id]

        # Filter rows in final_df for the specific vehicle_id and time range
        mask = (final_df.index == vehicle_id) & (final_df['bucket'] >= trip_start_time) & (final_df['bucket'] <= trip_end_time)

        if not final_df_row_agency.empty:
            agency = final_df_row_agency['agency'].values[0]
            routes_data_route_id = routes_data.loc[(routes_data['agency_id'].str.lower() == agency.lower()) & (routes_data['route_long_name'] == route_no)]
            if not routes_data_route_id.empty:
                route_id = routes_data_route_id['route_id'].values[0]
        
        # Fill the 'actual_route' column in the filtered rows
        final_df.loc[mask, 'scheduled_route_short_name'] = route_no
        final_df.loc[mask, 'scheduled_route_id'] = route_id

    # Use apply function to apply the fill_actual_route function to each row of depot_df
    tqdm.pandas(desc="Processing Vehicles")
    depot_df.progress_apply(fill_actual_route, axis=1)

    final_df.reset_index(inplace=True)
    final_df.columns = final_df.columns.str.replace('bucket','timestamp')
    columns_to_drop = ['agency_id']
    final_df = final_df.drop(columns=columns_to_drop)
    final_df['scheduled_route_id'] = pd.to_numeric(final_df['scheduled_route_id'], errors='coerce')
    final_df['actual_route_id'] = pd.to_numeric(final_df['actual_route_id'], errors='coerce')

    final_df['scheduled_route_id'].fillna(0, inplace=True)
    final_df['actual_route_id'].fillna(0, inplace=True)
    
    final_df['scheduled_route_id'] = final_df['scheduled_route_id'].astype(int)
    final_df['actual_route_id'] = final_df['actual_route_id'].astype(int)

    final_df['same_as_scheduled'] = final_df['scheduled_route_id'] == final_df['actual_route_id']
    final_df['Trip_Number'] = 1

    if not table_exists:
        final_df.to_sql('gps_Vs_sch', con=engine, index=False)
    else:
        # Append the data to the existing table

        # 1. Query the last updated records from the database
        query = """
            SELECT g.vehicle_id, g.actual_route_short_name, g.Trip_Number
            FROM gps_Vs_sch AS g
            JOIN (
                SELECT vehicle_id, MAX(timestamp) AS max_timestamp
                FROM gps_Vs_sch
                GROUP BY vehicle_id
            ) AS max_time
            ON g.vehicle_id = max_time.vehicle_id AND g.timestamp = max_time.max_timestamp
        """

        # Execute the query and fetch the results into a DataFrame
        unique_records = pd.read_sql_query(query, con=engine)

        db_trips = {}
        for _, row in unique_records.iterrows():
            vehicle_id = row['vehicle_id']
            actual_route_short_name = row['actual_route_short_name']
            trip_number = row['Trip_Number']
            db_trips[vehicle_id] = (actual_route_short_name, trip_number)
        
        with tqdm(total=len(final_df), desc="Adding Trip Number") as pbar:

            for index, row in final_df.iterrows():
                vehicle_id = row['vehicle_id']
                actual_route_short_name = row['actual_route_short_name']
                
                if vehicle_id in db_trips:
                    db_actual_route_short_name, db_trip_number = db_trips[vehicle_id]
                    if actual_route_short_name != db_actual_route_short_name:
                        db_trip_number += 1   
                        final_df.at[index, 'Trip_Number'] = db_trip_number
                    else:
                        final_df.at[index, 'Trip_Number'] = db_trip_number
                # Update tqdm progress bar
                pbar.update(1)
        
        final_df.to_sql('gps_Vs_sch', con=engine, index=False, if_exists='append')
    
    engine.dispose()
    # filename = f'gps_sch_data.csv'
    # final_df.to_csv(filename)
    
    actual_columns = ['vehicle_id', 'agency', 'depot', 'ac', 'actual_route_id','actual_route_short_name','actual_route_long_name','trip_completion','closest_stop_name','closest_stop_time','closest_stop_id','timestamp','same_as_scheduled','scheduled_route_short_name']
    actual_df = final_df[actual_columns]
    actual_df.loc[:, 'type'] = 'actual'

    # Rename columns
    actual_mapping = {
        'actual_route_id': 'route_id',
        'actual_route_short_name': 'route_short_name',
        'actual_route_long_name': 'route_long_name',
    }

    actual_df = actual_df.rename(columns=actual_mapping)
    actual_json_data = actual_df.to_json(orient='records')

    scheduled_columns = ['vehicle_id', 'agency', 'depot', 'ac', 'scheduled_route_id','scheduled_route_short_name','timestamp']
    scheduled_df = final_df[scheduled_columns]
    scheduled_df.loc[:, 'type'] = 'scheduled'

    # Rename columns
    scheduled_mapping = {
        'scheduled_route_id': 'route_id',
        'scheduled_route_short_name': 'route_short_name',
    }

    scheduled_df = scheduled_df.rename(columns=scheduled_mapping)
    scheduled_json_data = scheduled_df.to_json(orient='records')
    
    actual_data = json.loads(actual_json_data)
    scheduled_data = json.loads(scheduled_json_data)

    # Concatenate lists
    actual_data.extend(scheduled_data)

    final_json_data = json.dumps(actual_data, indent=2)

    return final_json_data

def run_app():
    """
    Main function to run the schedule adherence application.
    
    This function:
    1. Downloads the latest depot tool duty master data
    2. Updates vehicle data if needed
    3. Processes real-time data to calculate schedule adherence
    4. Saves results to JSON files
    """
    try:
        # Ensure route_comp directory exists
        os.makedirs("route_comp", exist_ok=True)
        
        # Download depot tool duty master data
        logger.info(f"Downloading depot tool duty master from {DEPOT_TOOL_URL}")
        try:
            if os.path.exists("route_comp/depot_tool_duty_master.txt"):
                os.remove("route_comp/depot_tool_duty_master.txt")
            wget.download(DEPOT_TOOL_URL, "route_comp/depot_tool_duty_master.txt")
            logger.info("Successfully downloaded depot tool duty master")
        except Exception as e:
            logger.error(f"Error downloading depot tool duty master: {str(e)}")
            return

        # Check and update vehicle data if needed
        file_name = "route_comp/vehicle_data.json"
        try:
            if os.path.exists(file_name):
                # Get the modification time of the file
                modification_time = os.path.getmtime(file_name)
                modification_datetime = datetime.fromtimestamp(modification_time)
                
                # Check if the file is older than 24 hours
                if datetime.now() - modification_datetime > timedelta(hours=24):
                    logger.info(f"Vehicle data file is older than 24 hours. Downloading a new version.")
                    response = requests.get(VEHICLE_AGENCY_URL, timeout=30)
                    data = response.json()
                    with open(file_name, "w") as json_file:
                        json.dump(data, json_file, indent=2)
                else:
                    logger.info(f"Vehicle data file is up to date. No need to download.")
            else:
                logger.info(f"Vehicle data file does not exist. Downloading...")
                response = requests.get(VEHICLE_AGENCY_URL, timeout=30)
                data = response.json()
                with open(file_name, "w") as json_file:
                    json.dump(data, json_file, indent=2)
        except requests.exceptions.RequestException as e:
            logger.error(f"Error downloading vehicle data: {str(e)}")
        except Exception as e:
            logger.error(f"Error processing vehicle data: {str(e)}")

        # Process data and generate schedule adherence metrics
        json_data = fetch_and_process_data()
        if json_data:
            json_filename = 'route_comp/actualVsScheduled.json'
            try:
                with open(json_filename, 'w') as json_file:
                    json_file.write(json_data)
                logger.info(f"Successfully saved data to {json_filename}")
            except Exception as e:
                logger.error(f"Error saving JSON data: {str(e)}")
        else:
            logger.warning("No data to save")

        # Log completion time
        current_time = datetime.now(timezone)
        formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S %z")
        logger.info(f"Execution completed at {formatted_time}")
        
        try:
            with open("log.txt", "a") as log_file:
                log_file.write(f"{formatted_time}\n")
        except Exception as e:
            logger.error(f"Error writing to log file: {str(e)}")
            
    except Exception as e:
        logger.error(f"Unexpected error in run_app: {str(e)}")
        raise

if __name__ == "__main__":
    run_app()