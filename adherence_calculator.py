import pandas as pd
import pickle
from math import radians, sin, cos, sqrt, atan2
from datetime import datetime, timedelta
from functools import reduce
from tqdm import tqdm
import sqlite3
import json
import re
import pytz
from itertools import islice
import warnings
import numpy as np
import os
import sys
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('schedule_adherence_trip.log')
    ]
)
logger = logging.getLogger('schedule_adherence_trip')

# Load environment variables
load_dotenv()

# Suppress pandas warnings
warnings.filterwarnings("ignore")


# Load route tree dictionary
tree_dict = {}
tree_dict_file = os.getenv("TREE_DICT_FILE", 'route_comp/tree_dict.pkl')
try:
    with open(tree_dict_file, 'rb') as file:
        tree_dict = pickle.load(file)
        file.close()
    logger.info(f"Successfully loaded tree dictionary from {tree_dict_file}")
except FileNotFoundError:
    logger.error(f"Tree dictionary file not found: {tree_dict_file}")
    logger.error("Please ensure the file exists and the path is correct in your .env file")
    sys.exit(1)
except Exception as e:
    logger.error(f"Error loading tree dictionary: {str(e)}")
    sys.exit(1)

def scheduled_start_end_time():
    """Load and process scheduled start and end times for transit trips.
    
    Returns:
        tuple: A tuple containing (scheduled_timestamp, route_timestamp)
    """
    # Get timezone from environment or use default
    local_tz = pytz.timezone(os.getenv("TIMEZONE", "Asia/Kolkata"))
    formatted_date = datetime.now(local_tz) - timedelta(days=1)
    formatted_date_str = formatted_date.strftime('%Y-%m-%d')

    # Load depot data
    depot_file = f'route_comp/data/depot_{formatted_date_str}.txt'
    try:
        depot_df = pd.read_csv(depot_file)
        logger.info(f"Successfully loaded depot data from {depot_file}")
    except FileNotFoundError:
        logger.error(f"Depot file not found: {depot_file}")
        logger.error("Please ensure the file exists in the correct directory")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error loading depot data: {str(e)}")
        sys.exit(1)
    depot_df.columns = depot_df.columns.str.replace('Plate No.','vehicle_id')
    # depot_df['Route No.'] = depot_df['Route No.'].str.replace(
    #     "CL|_| |P1|P2|P3|P4|P5|P6|P7|P8|P9|P10|P11|P12|P13|P14|P15|P16|P17|P18|P19|P20", "", regex=True)
    pattern = r"CL|_| |P[0-9]+|\."  # Updated regex pattern to include any number after 'P'
    depot_df['Route No.'] = depot_df['Route No.'].str.replace(pattern, "", regex=True)
    depot_df['Route No.'] = depot_df['Route No.'].apply(lambda x: re.sub(r'DN$', 'DOWN', x)).str.upper()
    # depot_df['Duty Allocated'] = pd.to_datetime(depot_df['Duty Allocated'])
    # Filter rows for the specified date
    # desired_date = '2023-12-24'
    # depot_df = depot_df[depot_df['Duty Allocated'].dt.date == pd.to_datetime(desired_date).date()]

    # print(depot_df)
    # print(depot_df.columns)

    desired_date = formatted_date_str

    for index, row in tqdm(depot_df.iterrows(), total=len(depot_df), desc="Convert to ISO Time Format"):
        try:
            trip_start_time = datetime.strptime(f"{desired_date} {row['Trip Start Time']}", '%Y-%m-%d %H:%M:%S').replace(tzinfo=local_tz)
            trip_end_time = datetime.strptime(f"{desired_date} {row['Trip End Time']}", '%Y-%m-%d %H:%M:%S').replace(tzinfo=local_tz)

            # Check if Trip End Time is smaller than Trip Start Time, add one day
            if trip_end_time < trip_start_time:
                trip_end_time += timedelta(days=1)

            # Convert to ISO format
            depot_df.at[index, 'Trip Start Time'] = trip_start_time.strftime('%Y-%m-%dT%H:%M:%S+05:30')
            depot_df.at[index, 'Trip End Time'] = trip_end_time.strftime('%Y-%m-%dT%H:%M:%S+05:30')
        except Exception as e:
            logger.error(f"Error processing row {index}: {str(e)}")
            continue

    depot_df.columns = depot_df.columns.str.replace('Route No.','route_long_name')
    depot_df.columns = depot_df.columns.str.replace('Trip End Time','scheduled_end_timestamp')
    depot_df.columns = depot_df.columns.str.replace('Trip Start Time','scheduled_start_timestamp')

    columns_to_delete = ['Duty ID', 'Trip Number']
    depot_df = depot_df.drop(columns=columns_to_delete)

    #print(depot_df)
    #print(depot_df.columns)

    # Load vehicle data
    vehicle_file = 'route_comp/vehicle_data.json'
    try:
        with open(vehicle_file) as json_file:
            vehicle_data = json.load(json_file)
        logger.info(f"Successfully loaded vehicle data from {vehicle_file}")
    except FileNotFoundError:
        logger.error(f"Vehicle data file not found: {vehicle_file}")
        logger.error("Please ensure the file exists in the correct directory")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing vehicle data JSON: {str(e)}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error loading vehicle data: {str(e)}")
        sys.exit(1)

    vehicle_mapping = {item['vehicle_id']: item['agency'].upper() for item in vehicle_data}

    depot_df['agency_id'] = depot_df['vehicle_id'].map(vehicle_mapping)
    # depot_df.to_csv('depot_df.csv', index=False)
    # print(depot_df)

    # Load routes data
    routes_file = os.getenv("ROUTES_FILE", 'route_comp/routes.txt')
    try:
        routes_df = pd.read_csv(routes_file)
        logger.info(f"Successfully loaded routes data from {routes_file}")
    except FileNotFoundError:
        logger.error(f"Routes file not found: {routes_file}")
        logger.error("Please ensure the file exists and the path is correct in your .env file")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error loading routes data: {str(e)}")
        sys.exit(1)
    depot_df['agency_id'] = depot_df['agency_id'].astype(str)
    merged_df = pd.merge(depot_df, routes_df, how='left', on=['agency_id', 'route_long_name'])

    # dropped_df = merged_df[merged_df['route_id'].isna()]
    merged_df = merged_df.dropna(subset=['route_id'])
    
    if merged_df['route_id'].dtype != 'object':
        merged_df['route_id'] = merged_df['route_id'].astype(int).astype(str)
    
    columns_to_drop = ['route_short_name', 'route_type']
    scheduled_timestamp = merged_df.drop(columns=columns_to_drop)

    route_timestamp = calculate_avg_time_difference(scheduled_timestamp)

    return scheduled_timestamp, route_timestamp

def calculate_avg_time_difference(df):   
    # Calculate the time difference in each row
    df['time_difference'] = abs(df.apply(lambda row: calculate_time_difference(row['scheduled_end_timestamp'], row['scheduled_start_timestamp']), axis=1))

    # Group by route_long_name
    grouped = df.groupby('route_long_name')

    # Calculate the average time difference
    average_time_difference = grouped['time_difference'].mean().astype(int)

    # Create a new dataframe
    new_data = pd.DataFrame({'route_long_name': average_time_difference.index, 
                             'max_time_difference': average_time_difference.values})

    return new_data

def calculate_time_difference(actual_timestamp, scheduled_timestamp):

    if not isinstance(actual_timestamp, str) or not isinstance(scheduled_timestamp, str):
        return None
    
    try:
        actual_dt = datetime.strptime(actual_timestamp, '%Y-%m-%dT%H:%M:%S%z')
        scheduled_dt = datetime.strptime(scheduled_timestamp, '%Y-%m-%dT%H:%M:%S%z')
    except ValueError:
        return None
    
    actual_dt = datetime.strptime(actual_timestamp, '%Y-%m-%dT%H:%M:%S%z')
    scheduled_dt = datetime.strptime(scheduled_timestamp, '%Y-%m-%dT%H:%M:%S%z')
    time_difference = (actual_dt - scheduled_dt).total_seconds()
    return int(time_difference)

def adding_schedule_timetable(adherence_df, schedule_df):
    """
    Merges adherence data with schedule data and calculates adherence metrics.
    """
    # Ensure consistent column names for merging
    if 'agency_id' in schedule_df.columns:
        schedule_df = schedule_df.rename(columns={'agency_id': 'agency'})

    # Convert timestamp columns to datetime objects for merging
    for col in ['scheduled_start_timestamp', 'scheduled_end_timestamp']:
        adherence_df[col] = pd.to_datetime(adherence_df[col], errors='coerce', utc=True)
        schedule_df[col] = pd.to_datetime(schedule_df[col], errors='coerce', utc=True)
    
    # Perform the merge
    merged_df = pd.merge(
        schedule_df,
        adherence_df,
        on=['vehicle_id', 'agency', 'route_id', 'scheduled_start_timestamp', 'scheduled_end_timestamp'],
        how='left'
    )

    # Convert more columns to datetime after merge
    merged_df['actual_start_timestamp'] = pd.to_datetime(merged_df['actual_start_timestamp'], errors='coerce', utc=True)
    merged_df['actual_end_timestamp'] = pd.to_datetime(merged_df['actual_end_timestamp'], errors='coerce', utc=True)

    # Calculate adherence for rows where actual timestamps are available
    valid_actuals = merged_df[merged_df['actual_start_timestamp'].notna()].copy()
    
    if not valid_actuals.empty:
        valid_actuals['start_adherence'] = (valid_actuals['actual_start_timestamp'] - valid_actuals['scheduled_start_timestamp']).dt.total_seconds()
        valid_actuals['end_adherence'] = (valid_actuals['actual_end_timestamp'] - valid_actuals['scheduled_end_timestamp']).dt.total_seconds()
        
        # Update the original merged_df with calculated adherence
        merged_df.update(valid_actuals)

    return merged_df

def convert_to_json(row):
    """
    Convert a DataFrame row to a JSON object with a specific structure.
    """
    json_output = {
        'vehicle': {
            'id': row.get('vehicle_id'),
            'ac': row.get('ac'),
            'fuel': row.get('fuel'),
            'depot': row.get('depot'),
            'agency': row.get('agency')
        },
        'trip_progress': {
            'completion_percentage': row.get('completion'),
            'id': row.get('pb_trip_id')
        },
        'route': {
            'id': row.get('route_id'),
            'short_name': row.get('route_short_name'),
            'long_name': row.get('route_long_name')
        },
        'timestamps': {
            'actual_start': row.get('actual_start_timestamp'),
            'actual_end': row.get('actual_end_timestamp'),
            'scheduled_start': row.get('scheduled_start_timestamp'),
            'scheduled_end': row.get('scheduled_end_timestamp')
        },
        'start_adherence_in_seconds': row.get('start_adherence'),
        'end_adherence_in_seconds': row.get('end_adherence'),
        'stops': []
    }

    stops_data = []
    seen_stop_ids = set()

    # Use .get() to avoid KeyErrors if a column is missing
    # Stop from main columns
    stop_id = row.get('stop_id')
    if pd.notna(stop_id) and stop_id not in seen_stop_ids:
        stops_data.append({
            "id": stop_id,
            "name": row.get('stop_name'),
            "actual_arrival": row.get('actual_arrival'),
            "scheduled_arrival": row.get('scheduled_arrival'),
            "actual_departure": row.get('actual_departure'),
            "scheduled_departure": row.get('scheduled_departure'),
            "arrival_adherence_in_seconds": row.get('arrival_adherence'),
            "departure_adherence_in_seconds": row.get('departure_adherence')
        })
        seen_stop_ids.add(stop_id)

    # Stop from 'first_stop' columns
    first_stop_id = row.get('first_stop_id')
    if pd.notna(first_stop_id) and first_stop_id not in seen_stop_ids:
        stops_data.append({
            "id": first_stop_id,
            "name": row.get('first_stop_name'),
            "actual_arrival": None,
            "scheduled_arrival": None,
            "actual_departure": None,
            "scheduled_departure": None,
            "arrival_adherence_in_seconds": None,
            "departure_adherence_in_seconds": None
        })
        seen_stop_ids.add(first_stop_id)

    # Stop from 'last_stop' columns
    last_stop_id = row.get('last_stop_id')
    if pd.notna(last_stop_id) and last_stop_id not in seen_stop_ids:
        stops_data.append({
            "id": last_stop_id,
            "name": row.get('last_stop_name'),
            "actual_arrival": None,
            "scheduled_arrival": None,
            "actual_departure": None,
            "scheduled_departure": None,
            "arrival_adherence_in_seconds": None,
            "departure_adherence_in_seconds": None
        })
        seen_stop_ids.add(last_stop_id)

    json_output['stops'] = stops_data
    return json_output

def split_dataframe(trips, max_time_difference):
    splits = []
    grouped_trips = trips.groupby('Trip_Number')

    for _, group in grouped_trips:

        current_split = [group.iloc[0]]

        for i in range(1, len(group)):
            prev_completion = current_split[-1]['trip_completion']
            current_completion = group.iloc[i]['trip_completion']

            prev_timestamp = current_split[-1]['timestamp']
            current_timestamp = group.iloc[i]['timestamp']

            time_difference = (current_timestamp - prev_timestamp).total_seconds()

            if current_completion >= prev_completion and time_difference <= max_time_difference:
                current_split.append(group.iloc[i])
            else:
                current_split_df = pd.DataFrame(current_split)
                current_split_df.drop_duplicates(subset='trip_completion', inplace=True)
                if len(current_split_df) >= 3:
                    splits.append(current_split_df)
                current_split = [group.iloc[i]]
        
        current_split_df = pd.DataFrame(current_split)
        current_split_df.drop_duplicates(subset='trip_completion', inplace=True)
        if len(current_split_df) >= 3:
            splits.append(current_split_df)
    
    return splits

def speedCal(route_id,closest_Stop_id_One,closest_Stop_id_Two,closest_timestamp_One,closest_timestamp_Two):
    tree_info = tree_dict[route_id]
    tree = tree_info['tree']
    stops = tree_info['stop_ids']

    index_of_stop_One = None
    index_of_stop_Two = None

    for i, stop in enumerate(stops):
        if stop['stop_id'] == closest_Stop_id_One:
            index_of_stop_One = i
        if stop['stop_id'] == closest_Stop_id_Two:
            index_of_stop_Two = i
        # If both indexes are found, exit the loop
        if index_of_stop_One is not None and index_of_stop_Two is not None:
            break

    # print(f'route_id: {route_id}')
    # print(f'index_of_stop_One: {index_of_stop_One}')
    # print(f'index_of_stop_Two: {index_of_stop_Two}')

    coordinate_One = tree.data[index_of_stop_One]
    coordinate_Two = tree.data[index_of_stop_Two]

    distance = haversine_distance(coordinate_One, coordinate_Two)

    timestamp_One = datetime.fromisoformat(closest_timestamp_One[:-6])
    timestamp_Two = datetime.fromisoformat(closest_timestamp_Two[:-6])
    # print(coordinate_One,coordinate_Two)
    # print(timestamp_One,timestamp_Two)
    time_difference = abs(timestamp_Two - timestamp_One).total_seconds() / 3600
    # print(time_difference)
    # print(f'coordinate_One: {coordinate_One}')
    # print(f'coordinate_Two: {coordinate_Two}')
    # print(f'distance: {distance}')
    # print(f'time_difference: {time_difference}')
    if time_difference < 1:
        return 14
    speed = round(distance / time_difference, 2)

    return speed

def haversine_distance(coord1, coord2):
    R = 6371.0
    lat1, lon1 = radians(coord1[0]), radians(coord1[1])
    lat2, lon2 = radians(coord2[0]), radians(coord2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    distance = R * c
    return distance

def distanceCal(route_id,closest_Stop_id_One):
    tree_info = tree_dict[route_id]
    tree = tree_info['tree']
    stops = tree_info['stop_ids']

    index_of_stop_One = None
    for i, stop in enumerate(stops):
        if stop['stop_id'] == closest_Stop_id_One:
            index_of_stop_One = i
            break

    first_stop_id = stops[0]['stop_id']
    first_stop_name = stops[0]['stop_name']

    # coordinate_One = tree.data[0]
    # coordinate_Two = tree.data[index_of_stop_One]
    coordinates = tree.data[0:index_of_stop_One + 1]
    # print(coordinates)
    # print(coordinate_One,coordinate_Two)
    # distance = haversine_distance(coordinate_One, coordinate_Two)
    # Assuming each element in tree.data is a NumPy array or a list
    distances = [haversine_distance(coordinates[i], coordinates[i + 1]) for i in range(len(coordinates) - 1)]
    # print(distances)
    total_distance = reduce(lambda x, y: x + y, distances, 0)

    return round(total_distance, 2) , first_stop_id , first_stop_name

def isLastStop(route_id,closest_Stop_id_last):
    tree_info = tree_dict[route_id]
    stop_ids = tree_info['stop_ids']
    if stop_ids[-1]['stop_id'] == closest_Stop_id_last:
        last_stop_id = stop_ids[-1]['stop_id']
        last_stop_name = stop_ids[-1]['stop_name']
        return True,last_stop_id,last_stop_name
    else:
        return False,None,None

def isFirstStop(route_id,closest_Stop_id_1st):
    tree_info = tree_dict[route_id]
    stop_ids = tree_info['stop_ids']
    if stop_ids[0]['stop_id'] == closest_Stop_id_1st:
        first_stop_id = stop_ids[0]['stop_id']
        first_stop_name = stop_ids[0]['stop_name']
        return True,first_stop_id,first_stop_name
    else:
        return False,None,None

def lastdistanceCal(route_id,closest_Stop_id_One):
    tree_info = tree_dict[route_id]
    tree = tree_info['tree']
    stops = tree_info['stop_ids']

    index_of_stop_One = None
    for i, stop in enumerate(stops):
        if stop['stop_id'] == closest_Stop_id_One:
            index_of_stop_One = i
            break
    last_stop_id = stops[-1]['stop_id']
    last_stop_name = stops[-1]['stop_name']

    coordinates = tree.data[index_of_stop_One:]
    # print(coordinates)
    # print(len(coordinates))
    distances = [haversine_distance(coordinates[i], coordinates[i + 1]) for i in range(len(coordinates) - 1)]
    # print(distances)
    total_distance = reduce(lambda x, y: x + y, distances, 0)

    return round(total_distance, 2) , last_stop_id , last_stop_name

def find_closest_scheduled_time(scheduled_times, vehicle_id, route_id, agency, actual_start_time, actual_end_time):
    # Filter scheduled times for the given vehicle_id and route_id
    filtered_schedule = scheduled_times[(scheduled_times['agency_id'].str.lower() == agency.lower()) & (scheduled_times['vehicle_id'] == vehicle_id) & (scheduled_times['route_id'] == route_id)]
    # print(filtered_schedule)
    if filtered_schedule.empty:
        return None, None
    # Convert actual_start_time to datetime and set the time zone
    actual_start_time = pd.to_datetime(actual_start_time)
    actual_end_time = pd.to_datetime(actual_end_time)
    filtered_schedule['scheduled_start_timestamp'] = pd.to_datetime(filtered_schedule['scheduled_start_timestamp'])
    filtered_schedule['scheduled_end_timestamp'] = pd.to_datetime(filtered_schedule['scheduled_end_timestamp'])
    # Calculate the absolute time difference between actual start time and each scheduled start time
    time_diff = filtered_schedule['scheduled_start_timestamp'].apply(lambda x: abs(x - actual_start_time))

    # Find the index of the minimum time difference
    closest_start_time_idx = time_diff.idxmin()

    timezone_offset = actual_start_time.strftime("%z")
    timezone_offset_with_colon = f"{timezone_offset[:-2]}:{timezone_offset[-2:]}"

    # Use the index to retrieve the corresponding scheduled start time and end time
    closest_start_time = filtered_schedule.loc[closest_start_time_idx, 'scheduled_start_timestamp']
    closest_end_time = filtered_schedule.loc[closest_start_time_idx, 'scheduled_end_timestamp']

    # Return the closest scheduled start time and end time
    closest_start_time_formatted = closest_start_time.strftime("%Y-%m-%dT%H:%M:%S") + timezone_offset_with_colon
    # closest_start_time_formatted = closest_start_time.strftime('%Y-%m-%dT%H:%M:%S%z')
    closest_end_time_formatted = closest_end_time.strftime("%Y-%m-%dT%H:%M:%S") + timezone_offset_with_colon
    # closest_end_time_formatted = closest_end_time.strftime('%Y-%m-%dT%H:%M:%S%z')
    return closest_start_time_formatted, closest_end_time_formatted

def process_trip_completions(trip_comp, route_id):
    actaul_start_timestamp, actaul_end_timestamp = None, None
    first_stop_id, last_stop_id = None, None
    first_stop_name, last_stop_name = None, None
    completion = False 
    first_flag, last_flag = False, False

    # Process start time
    if len(trip_comp) >= 1:
        if trip_comp['trip_completion'].shape[0]>=2:
            closest_Stop_id_1st = trip_comp['closest_stop_id'].iloc[0]
            flag,first_stop_id,first_stop_name = isFirstStop(route_id,closest_Stop_id_1st)
            if flag:
                first_flag = True
                actaul_start_timestamp = trip_comp['closest_stop_time'].iloc[0]
            else:
                if trip_comp['trip_completion'].iloc[0] <= 10:
                    closest_Stop_id_One = trip_comp['closest_stop_id'].iloc[0]
                    closest_Stop_id_Two = trip_comp['closest_stop_id'].iloc[1]
                    closest_timestamp_One = trip_comp['closest_stop_time'].iloc[0]
                    closest_timestamp_Two = trip_comp['closest_stop_time'].iloc[1]
                    speed = speedCal(route_id,closest_Stop_id_One,closest_Stop_id_Two,closest_timestamp_One,closest_timestamp_Two)
                    if speed < 20 :
                        speed = 20
                    distance,first_stop_id,first_stop_name = distanceCal(route_id,closest_Stop_id_One)
                    time_hours = distance / speed

                    timestamp_One = datetime.fromisoformat(closest_timestamp_One)
                    new_timestamp = timestamp_One - timedelta(hours=time_hours)
                    timezone_offset = new_timestamp.strftime("%z")
                    # Insert the colon in the timezone offset
                    timezone_offset_with_colon = f"{timezone_offset[:-2]}:{timezone_offset[-2:]}"
                    new_timestamp_str = new_timestamp.strftime("%Y-%m-%dT%H:%M:%S") + timezone_offset_with_colon

                    # print(closest_timestamp_One,new_timestamp_str)
                    actaul_start_timestamp = new_timestamp_str
                    first_flag = True
                else:
                    first_stop_id = trip_comp['closest_stop_id'].iloc[0]
                    first_stop_name = trip_comp['closest_stop_name'].iloc[0]
                    actaul_start_timestamp = trip_comp['closest_stop_time'].iloc[0]

        # elif trip_comp['trip_completion'].shape[0]==1:
        #     closest_Stop_id_1st = trip_comp['closest_stop_id'].iloc[0]
        #     flag,first_stop_id,first_stop_name = isFirstStop(route_id,closest_Stop_id_1st)
        #     if flag:
        #         actaul_start_timestamp = trip_comp['closest_stop_time'].iloc[0]
        #     else:
        #         closest_Stop_id_One = trip_comp['closest_stop_id'].iloc[0]
        #         closest_timestamp_One = trip_comp['closest_stop_time'].iloc[0]
        #         speed = 14
        #         distance,first_stop_id,first_stop_name = distanceCal(route_id,closest_Stop_id_One)
        #         time_hours = distance / speed
        #         timestamp_One = datetime.fromisoformat(closest_timestamp_One)
        #         new_timestamp = timestamp_One - timedelta(hours=time_hours)
        #         timezone_offset = new_timestamp.strftime("%z")
        #         timezone_offset_with_colon = f"{timezone_offset[:-2]}:{timezone_offset[-2:]}"
        #         new_timestamp_str = new_timestamp.strftime("%Y-%m-%dT%H:%M:%S") + timezone_offset_with_colon
        #         actaul_start_timestamp = new_timestamp_str

    if trip_comp['trip_completion'].shape[0]>=2:
        closest_Stop_id_last = trip_comp['closest_stop_id'].iloc[-1]
        flag,last_stop_id,last_stop_name = isLastStop(route_id,closest_Stop_id_last)
        if flag:
            last_flag = True
            actaul_end_timestamp = trip_comp['closest_stop_time'].iloc[-1]
        else:
            if trip_comp['trip_completion'].iloc[-1] >= 90:
                last_flag = True
                closest_Stop_id_One = trip_comp['closest_stop_id'].iloc[-1]
                closest_Stop_id_Two = trip_comp['closest_stop_id'].iloc[-2]
                closest_timestamp_One = trip_comp['closest_stop_time'].iloc[-1]
                closest_timestamp_Two = trip_comp['closest_stop_time'].iloc[-2]
                # trip_comp.to_csv('trip_comp.csv', index=False)
                # print(f'vehicle_id: {vehicle_id}')
                speed = speedCal(route_id,closest_Stop_id_One,closest_Stop_id_Two,closest_timestamp_One,closest_timestamp_Two)
                if speed < 20 :
                    speed = 20
                distance,last_stop_id,last_stop_name = lastdistanceCal(route_id,closest_Stop_id_One)
                time_hours = distance / speed

                timestamp_One = datetime.fromisoformat(closest_timestamp_One)
                new_timestamp = timestamp_One + timedelta(hours=time_hours)
                timezone_offset = new_timestamp.strftime("%z")
                # Insert the colon in the timezone offset
                timezone_offset_with_colon = f"{timezone_offset[:-2]}:{timezone_offset[-2:]}"
                new_timestamp_str = new_timestamp.strftime("%Y-%m-%dT%H:%M:%S") + timezone_offset_with_colon

                # print(closest_timestamp_One,new_timestamp_str)
                actaul_end_timestamp = new_timestamp_str
            else:
                last_stop_id = trip_comp['closest_stop_id'].iloc[-1]
                last_stop_name = trip_comp['closest_stop_name'].iloc[-1]
                actaul_end_timestamp = trip_comp['closest_stop_time'].iloc[-1]

    # elif trip_comp['trip_completion'].shape[0]==1:
    #     closest_Stop_id_last = trip_comp['closest_stop_id'].iloc[-1]
    #     flag,last_stop_id,last_stop_name = isLastStop(route_id,closest_Stop_id_last)
    #     if flag:
    #         actaul_end_timestamp = trip_comp['closest_stop_time'].iloc[-1]
    #     else:
    #         closest_Stop_id_One = trip_comp['closest_stop_id'].iloc[-1]
    #         closest_timestamp_One = trip_comp['closest_stop_time'].iloc[-1]
    #         speed = 14
    #         distance,last_stop_id,last_stop_name = lastdistanceCal(route_id,closest_Stop_id_One)
    #         time_hours = distance / speed
    #         timestamp_One = datetime.fromisoformat(closest_timestamp_One)
    #         new_timestamp = timestamp_One + timedelta(hours=time_hours)
    #         timezone_offset = new_timestamp.strftime("%z")
    #         timezone_offset_with_colon = f"{timezone_offset[:-2]}:{timezone_offset[-2:]}"
    #         new_timestamp_str = new_timestamp.strftime("%Y-%m-%dT%H:%M:%S") + timezone_offset_with_colon
    #         actaul_end_timestamp = new_timestamp_str

    if first_flag and last_flag:
        completion = True

    return actaul_start_timestamp, actaul_end_timestamp, first_stop_id, first_stop_name, last_stop_id, last_stop_name, completion



def process_vehicle(vehicle_routes_dict, actual_sch_data,SCHEDULE_ADHERENCE,scheduled_timestamp,route_timestamp):

    scheduled_times_dict = {vehicle_id: scheduled_timestamp[scheduled_timestamp['vehicle_id'] == vehicle_id]
                            for vehicle_id in vehicle_routes_dict.keys()}
    for vehicle_id, route_ids in tqdm(vehicle_routes_dict.items(), desc="Processing vehicles"):
        scheduled_times = scheduled_times_dict[vehicle_id]

        if not scheduled_times.empty:
            for route_id in route_ids:
                trip_compl = actual_sch_data[(actual_sch_data['vehicle_id'] == vehicle_id) & (actual_sch_data['actual_route_id'] == route_id)].sort_values(by='timestamp')
                # trip_compl = trip_compl.sort_values(by='timestamp')
                route_long_name = trip_compl.loc[trip_compl['actual_route_id'] == route_id, 'actual_route_short_name'].iloc[0]
                max_time_difference = route_timestamp.loc[route_timestamp['route_long_name'] == route_long_name, 'max_time_difference'].iloc[0] if not route_timestamp.loc[route_timestamp['route_long_name'] == route_long_name].empty else 3600
                # max_time_difference = 3600  # 1 hour in seconds
                split_dataframes = split_dataframe(trip_compl, max_time_difference)

                for i, trip_comp in enumerate(split_dataframes):
                    # print(f"Split {i + 1}:\n{split_df}\n")
                    stops_count = len(trip_comp)
                    actaul_start_timestamp, actaul_end_timestamp, first_stop_id, first_stop_name, last_stop_id, last_stop_name, completion = process_trip_completions(trip_comp, route_id)

                    agency = trip_comp['agency'].iloc[0]

                    scheduled_start_timestamp, scheduled_end_timestamp = find_closest_scheduled_time(scheduled_times, vehicle_id, route_id, agency, actaul_start_timestamp, actaul_end_timestamp)

                    if (
                        actaul_start_timestamp is not None and
                        actaul_end_timestamp is not None and
                        scheduled_start_timestamp is not None and
                        scheduled_end_timestamp is not None and
                        actaul_start_timestamp < actaul_end_timestamp and
                        scheduled_start_timestamp < scheduled_end_timestamp
                    ):

                        new_data = {'vehicle_id': vehicle_id,
                                    'agency': trip_comp['agency'].iloc[0],
                                    'depot': trip_comp['depot'].iloc[0],
                                    'ac': trip_comp['ac'].iloc[0],
                                    'pb_trip_id': str(vehicle_id) + '_' + str(route_id) + '_' + str(i),
                                    'route_id': route_id,
                                    'route_short_name': trip_comp['actual_route_short_name'].iloc[0],
                                    'route_long_name': trip_comp['actual_route_long_name'].iloc[0],
                                    'stops_count':stops_count,
                                    'actual_start_timestamp': actaul_start_timestamp,
                                    'actual_end_timestamp': actaul_end_timestamp,
                                    'scheduled_start_timestamp': scheduled_start_timestamp,
                                    'scheduled_end_timestamp': scheduled_end_timestamp,
                                    'first_stop_id': first_stop_id,
                                    'first_stop_name': first_stop_name,
                                    'last_stop_id': last_stop_id,
                                    'last_stop_name': last_stop_name,
                                    'completion':completion,
                                    }
                        if not is_record_duplicate(SCHEDULE_ADHERENCE, new_data):
                            SCHEDULE_ADHERENCE = pd.concat([SCHEDULE_ADHERENCE, pd.DataFrame([new_data])], ignore_index=True)
                        else:
                            print("Data is already in the SCHEDULE_ADHERENCE. Skipping addition.")

    return SCHEDULE_ADHERENCE

def is_record_duplicate(data_frame, new_record):
    # Extract relevant fields for duplicate checking
    check_fields = ['vehicle_id', 'route_id', 'actual_start_timestamp', 'actual_end_timestamp']

    # Using a more appropriate method to compare dictionary values with DataFrame columns
    conditions = [data_frame[field] == new_record[field] for field in check_fields]
    combined_condition = conditions[0]
    for condition in conditions[1:]:
        combined_condition &= condition

    return not data_frame[combined_condition].empty

def process_duplicates(df):
    # Check for duplicates in scheduled_start_timestamp and scheduled_end_timestamp
    duplicates = df[df.duplicated(subset=['vehicle_id','agency','route_id','scheduled_start_timestamp', 'scheduled_end_timestamp'], keep=False)]

    # If there are duplicates, keep the row with the maximum stops_count
    if not duplicates.empty:
        max_stops_row = duplicates[duplicates['stops_count'] == duplicates['stops_count'].max()]
        # Drop duplicates except the one with the maximum stops_count
        df.drop_duplicates(subset=['vehicle_id','agency','route_id','scheduled_start_timestamp', 'scheduled_end_timestamp'], keep=False, inplace=True)
        df = pd.concat([df, max_stops_row])

    return df


def adding_schedule_timetable(SCHEDULE_ADHERENCE_final, scheduled_timestamp):
    # Convert columns to datetime
    SCHEDULE_ADHERENCE_final['actual_start_timestamp'] = pd.to_datetime(SCHEDULE_ADHERENCE_final['actual_start_timestamp'])
    SCHEDULE_ADHERENCE_final['scheduled_start_timestamp'] = pd.to_datetime(SCHEDULE_ADHERENCE_final['scheduled_start_timestamp'])

    # Sort values for correct time difference calculation
    adherence = SCHEDULE_ADHERENCE_final.copy()
    adherence.sort_values(['vehicle_id', 'agency', 'route_id', 'scheduled_start_timestamp', 'actual_start_timestamp'], inplace=True)

    # Vectorized calculation of adherence and time differences
    adherence['start_adherence'] = (adherence['actual_start_timestamp'] - adherence['scheduled_start_timestamp']).dt.total_seconds()
    adherence['end_adherence'] = (adherence['actual_end_timestamp'] - adherence['scheduled_end_timestamp']).dt.total_seconds()
    time_difference = adherence.groupby(['vehicle_id', 'agency', 'route_id', 'scheduled_start_timestamp'])['actual_start_timestamp'].diff().dt.total_seconds()

    # Filter out records that are too close together (potential duplicates)
    SCHEDULE_ADHERENCE_final = adherence[~((time_difference >= 0) & (time_difference <= 1800))].copy()

    # Convert datetime columns to string with timezone for merging
    SCHEDULE_ADHERENCE_final['actual_start_timestamp'] = SCHEDULE_ADHERENCE_final['actual_start_timestamp'].dt.strftime("%Y-%m-%dT%H:%M:%S") + "+05:30"
    SCHEDULE_ADHERENCE_final['scheduled_start_timestamp'] = SCHEDULE_ADHERENCE_final['scheduled_start_timestamp'].dt.strftime("%Y-%m-%dT%H:%M:%S") + "+05:30"
    SCHEDULE_ADHERENCE_final['scheduled_end_timestamp'] = SCHEDULE_ADHERENCE_final['scheduled_end_timestamp'].dt.strftime("%Y-%m-%dT%H:%M:%S") + "+05:30"

    # Lowercase 'agency' column and convert timestamps in scheduled_timestamp for merging
    scheduled_timestamp['agency'] = scheduled_timestamp['agency_id'].str.lower()
    scheduled_timestamp['scheduled_start_timestamp'] = scheduled_timestamp['scheduled_start_timestamp'].dt.strftime("%Y-%m-%dT%H:%M:%S") + "+05:30"
    scheduled_timestamp['scheduled_end_timestamp'] = scheduled_timestamp['scheduled_end_timestamp'].dt.strftime("%Y-%m-%dT%H:%M:%S") + "+05:30"

    # Merge dataframes using a right join to keep all scheduled timestamps and match with adherence data
    final_dataframe = pd.merge(SCHEDULE_ADHERENCE_final, scheduled_timestamp,
                               how='right',
                               on=['vehicle_id', 'route_id', 'scheduled_start_timestamp', 'scheduled_end_timestamp', 'agency'])

    # Find and save duplicate rows
    subset_cols = ['vehicle_id', 'agency', 'route_id', 'scheduled_start_timestamp', 'scheduled_end_timestamp']
    # duplicate_rows = final_dataframe[final_dataframe.duplicated(subset=subset_cols, keep=False)]
    # duplicate_rows.to_csv('duplicate_rows.csv', index=False)

    # Drop duplicates from final_dataframe
    final_dataframe = final_dataframe.drop_duplicates(subset=subset_cols, keep='first')

    # Save final dataframe
    # final_dataframe.to_csv('final_dataframe.csv', index=False)
    
    return final_dataframe

def run_trip_start_end_time():
    """Main function to process trip start and end times and generate schedule adherence metrics.
    """
    try:
        # Ensure data directory exists
        os.makedirs('route_comp/data', exist_ok=True)
        
        # Get timezone from environment or use default
        local_tz = pytz.timezone(os.getenv("TIMEZONE", "Asia/Kolkata"))
        formatted_date = datetime.now(local_tz) - timedelta(days=1)
        formatted_date_str = formatted_date.strftime('%Y_%m_%d')
        
        # Connect to the database
        db_file = f'route_comp/data/route_comp_{formatted_date_str}.db'
        try:
            conn = sqlite3.connect(db_file)
            logger.info(f"Connected to database: {db_file}")
        except sqlite3.Error as e:
            logger.error(f"Error connecting to database: {str(e)}")
            sys.exit(1)

        # Calculate time range for query
        current_day_start = datetime.now(local_tz).replace(hour=1, minute=0, second=0, microsecond=0)
        twenty_four_hours_ago = current_day_start - timedelta(hours=24)
        
        # Format timestamps as strings
        twenty_four_hours_ago_str = twenty_four_hours_ago.strftime("%Y-%m-%dT%H:%M:%S%z")
        current_day_start_str = current_day_start.strftime("%Y-%m-%dT%H:%M:%S%z")
        
        # Build and execute the SQL query
        query = f"SELECT * FROM gps_Vs_sch WHERE timestamp >= '{twenty_four_hours_ago_str}' AND timestamp <= '{current_day_start_str}'"
        logger.info("Executing query to fetch GPS vs schedule data")

        try:
            actual_sch_data = pd.read_sql_query(query, conn)
            conn.close()
            logger.info(f"Successfully fetched {len(actual_sch_data)} records from database")
        except sqlite3.Error as e:
            logger.error(f"Error executing SQL query: {str(e)}")
            conn.close()
            sys.exit(1)

        actual_sch_data['closest_stop_id'] = actual_sch_data['closest_stop_id'].astype(str)
        actual_sch_data['actual_route_id'] = actual_sch_data['actual_route_id'].astype(str)
        actual_sch_data['timestamp'] = pd.to_datetime(actual_sch_data['timestamp'], utc=True).dt.tz_convert('Asia/Kolkata')
        scheduled_timestamp, route_timestamp = scheduled_start_end_time()

        SCHEDULE_ADHERENCE = pd.DataFrame(columns=['vehicle_id', 'agency', 'depot', 'ac', 'pb_trip_id', 'route_id', 'route_short_name', 'route_long_name','stops_count','actual_start_timestamp', 'actual_end_timestamp', 'scheduled_start_timestamp', 'scheduled_end_timestamp', 'first_stop_id', 'first_stop_name', 'last_stop_id', 'last_stop_name', 'completion'])


        vehicle_routes_dict = {}
        # vehicle_routes_dict = {'DL1PC9916': {'5476', '5010', '5007', '5473'}}
        for _, row in tqdm(actual_sch_data.iterrows(), total=len(actual_sch_data), desc="Processing vehicle_routes_dict"):
            vehicle_id = row['vehicle_id']
            actual_route_id = row['actual_route_id']
            vehicle_routes_dict.setdefault(vehicle_id, set()).add(actual_route_id)

        # num_items_to_process = 200
        # limited_vehicle_routes_dict = dict(islice(vehicle_routes_dict.items(), num_items_to_process))
        # SCHEDULE_ADHERENCE = process_vehicle(limited_vehicle_routes_dict, actual_sch_data,SCHEDULE_ADHERENCE,scheduled_timestamp)
        SCHEDULE_ADHERENCE = process_vehicle(vehicle_routes_dict, actual_sch_data,SCHEDULE_ADHERENCE,scheduled_timestamp,route_timestamp)

        # SCHEDULE_ADHERENCE.to_csv('SCHEDULE_ADHERENCE_pre_final.csv', index=False)

        pre_final_result_SCHEDULE_ADHERENCE = pd.DataFrame()

        for vehicle_id, route_ids in tqdm(vehicle_routes_dict.items(), desc="Final Output"):
            for route_id in route_ids:
                filtered_df = SCHEDULE_ADHERENCE[(SCHEDULE_ADHERENCE['vehicle_id'] == vehicle_id) & (SCHEDULE_ADHERENCE['route_id'] == route_id)]
                result_df = process_duplicates(filtered_df)
                pre_final_result_SCHEDULE_ADHERENCE = pd.concat([pre_final_result_SCHEDULE_ADHERENCE, result_df], ignore_index=True)

        # pre_final_result_SCHEDULE_ADHERENCE.to_csv('SCHEDULE_ADHERENCE_final.csv',index=False)

        SCHEDULE_ADHERENCE_final = pre_final_result_SCHEDULE_ADHERENCE

        SCHEDULE_ADHERENCE_final = adding_schedule_timetable(SCHEDULE_ADHERENCE_final, scheduled_timestamp)
        SCHEDULE_ADHERENCE_final = SCHEDULE_ADHERENCE_final.where(pd.notnull(SCHEDULE_ADHERENCE_final), None)
        # Apply the conversion function to each row of the DataFrame with tqdm
        json_data_list = []
        for _, row in tqdm(SCHEDULE_ADHERENCE_final.iterrows(), total=len(SCHEDULE_ADHERENCE_final)):
            json_data_list.append(convert_to_json(row))

        # Save the JSON data to a file
        output_file = 'route_comp/SCHEDULE_ADHERENCE.json'
        try:
            with open(output_file, 'w') as json_file:
                json.dump(json_data_list, json_file, indent=4)
            logger.info(f"Successfully saved schedule adherence data to {output_file}")
        except Exception as e:
            logger.error(f"Error saving JSON data: {str(e)}")
            
    except Exception as e:
        logger.error(f"Unexpected error in run_trip_start_end_time: {str(e)}")
        raise


if __name__ == "__main__":
    run_trip_start_end_time()
    warnings.resetwarnings()