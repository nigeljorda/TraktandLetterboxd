import requests
import pandas as pd
import json
from datetime import datetime
import os
import webbrowser
import re
import time
import csv

# Trakt API URL for authorization and syncing
TRAKT_BASE_URL = 'https://api.trakt.tv'

# Function to load or request Trakt Client ID and Secret, storing them in a .json file
def get_client_credentials():
    credentials_file = 'trakt_credentials.json'
    
    if os.path.exists(credentials_file):
        with open(credentials_file, 'r') as f:
            credentials = json.load(f)
            client_id = credentials.get('client_id')
            client_secret = credentials.get('client_secret')
            if client_id and client_secret:
                return client_id, client_secret

    client_id = input("Enter your Trakt Client ID: ").strip()
    client_secret = input("Enter your Trakt Client Secret: ").strip()

    with open(credentials_file, 'w') as f:
        json.dump({'client_id': client_id, 'client_secret': client_secret}, f)

    return client_id, client_secret

# Function to authenticate Trakt using PIN-based flow and open the browser for the user
def authenticate_trakt():
    client_id, client_secret = get_client_credentials()

    # URL for OAuth2 PIN-based authorization
    auth_url = f"https://trakt.tv/oauth/authorize?response_type=code&client_id={client_id}&redirect_uri=urn:ietf:wg:oauth:2.0:oob"
    print(f"Opening browser to authorize Trakt. Please enter the PIN code provided.")
    
    # Open the browser automatically for the user
    webbrowser.open(auth_url)

    pin = input("Enter the PIN code you received from Trakt: ").strip()

    # Prepare the token request payload
    token_payload = {
        "code": pin,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
        "grant_type": "authorization_code"
    }

    # Request the access token
    response = requests.post(f"{TRAKT_BASE_URL}/oauth/token", json=token_payload)
    
    if response.status_code == 200:
        token_data = response.json()
        with open('trakt_token.json', 'w') as f:
            json.dump(token_data, f)
        print("Successfully authenticated with Trakt.")
        return token_data['access_token'], client_id
    else:
        print(f"Error authenticating with Trakt: {response.status_code} - {response.text}")
        exit()

# Function to retry requests on rate limit (429)
def handle_rate_limit(response):
    if response.status_code == 429:
        retry_after = int(response.headers.get('Retry-After', 1))
        print(f"Rate limit exceeded (429). Waiting {retry_after} seconds before retrying...")
        time.sleep(retry_after)
        return True
    return False

# Function to mark shows as watched, season by season up to the last watched episode
def mark_episodes_watched(shows, watched_at, access_token, client_id, retries=5):
    trakt_url = f"{TRAKT_BASE_URL}/sync/history"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id
    }

    attempt = 0
    while attempt < retries:
        for show_id, last_season, last_ep in shows:
            payload = {"shows": [{"ids": {"tmdb": show_id}, "seasons": []}]}

            # Mark all episodes from previous seasons as watched
            for season in range(1, last_season):
                season_payload = {
                    "number": season,
                    "episodes": [{"number": ep, "watched_at": watched_at} for ep in range(1, 100)]  # Assuming 100 episodes max
                }
                payload["shows"][0]["seasons"].append(season_payload)

            # Mark episodes from the last season up to the specified last episode
            season_payload = {
                "number": last_season,
                "episodes": [{"number": ep, "watched_at": watched_at} for ep in range(1, last_ep + 1)]
            }
            payload["shows"][0]["seasons"].append(season_payload)

            response = requests.post(trakt_url, headers=headers, json=payload)
            
            if response.status_code == 201:
                print(f"Successfully marked {show_id} up to season {last_season}, episode {last_ep} as watched.")
            elif handle_rate_limit(response):
                continue
            else:
                print(f"Failed to mark episodes for {show_id}. Response: {response.status_code} - {response.text}")
                break

        if response.status_code != 429:
            return  # Stop retrying if not rate limit error

    if attempt == retries:
        print(f"Failed after {retries} attempts due to rate limits.")


# Function to process shows CSV and skip already watched episodes
def process_shows_csv(file_path):
    data = pd.read_csv(file_path)
    shows = []
    
    for _, row in data.iterrows():
        show_id = row['TMDB ID']
        season_episode = row['Last Watched Episode']
        
        # Extract season and episode using regex
        match = re.match(r'S(\d+)E(\d+)', season_episode)
        if match:
            season_number = int(match.group(1))  # Extract season number
            last_ep = int(match.group(2))        # Extract episode number
            
            shows.append((show_id, season_number, last_ep))
        else:
            print(f"Warning: Could not parse season/episode from '{season_episode}' for show ID {show_id}")
    
    return shows

# Function to mark movies as watched with retry mechanism
def mark_movies_watched(movies, watched_at, access_token, client_id, retries=5):
    trakt_url = f"{TRAKT_BASE_URL}/sync/history"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id
    }

    payload = {
        "movies": [{"ids": {"tmdb": movie_id}, "watched_at": watched_at} for movie_id in movies]
    }

    attempt = 0
    while attempt < retries:
        response = requests.post(trakt_url, headers=headers, json=payload)
        
        if response.status_code == 201:
            print("Successfully marked movies as watched.")
            return
        elif handle_rate_limit(response):
            continue
        else:
            print(f"Failed to mark movies as watched. Response: {response.status_code} - {response.text}")
            break

    if attempt == retries:
        print(f"Failed after {retries} attempts due to rate limits.")

# Function to process the movies CSV file
def process_movies_csv(file_path):
    data = pd.read_csv(file_path)
    return list(data['TMDB ID'])

# Function to sync ratings to Trakt with retries
def import_ratings(movies, shows, access_token, client_id, retries=3):
    trakt_url = f"{TRAKT_BASE_URL}/sync/ratings"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id
    }

    payload = {
        "movies": [{"ids": {"tmdb": movie_id}, "rating": rating} for movie_id, rating in movies.items() if rating != ''],
        "shows": [{"ids": {"tmdb": show_id}, "rating": rating} for show_id, rating in shows.items() if rating != '']
    }

    if not payload['movies'] and not payload['shows']:
        print("No ratings to import.")
        return

    attempt = 0
    while attempt < retries:
        response = requests.post(trakt_url, headers=headers, json=payload)
        
        if response.status_code == 201:
            print("Successfully imported ratings.")
            return
        elif handle_rate_limit(response):
            continue
        else:
            print(f"Failed to import ratings. Response: {response.status_code} - {response.text}")
            break

    if attempt == retries:
        print(f"Failed after {retries} attempts due to rate limits.")

# Function to create a personal list on Trakt with retry mechanism for rate limits
def create_personal_list(list_name, access_token, client_id, retries=3):
    trakt_url = f"{TRAKT_BASE_URL}/users/me/lists"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id
    }
    payload = {
        "name": list_name,
        "privacy": "private",  # Modify the privacy setting if needed
        "display_numbers": False,
        "allow_comments": True
    }

    attempt = 0
    while attempt < retries:
        response = requests.post(trakt_url, headers=headers, json=payload)
        if response.status_code == 201:
            print(f"Created list: {list_name}")
            return response.json()['ids']['slug']  # Return the slug for the newly created list
        elif response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 1))
            print(f"Rate limit exceeded (429). Waiting {retry_after} seconds before retrying... (Attempt {attempt+1}/{retries})")
            time.sleep(retry_after)
            attempt += 1
        else:
            print(f"Failed to create list {list_name}. Response: {response.status_code} - {response.text}")
            return None
    print(f"Failed to create list {list_name} after {retries} attempts.")
    return None

# Function to add items to a personal list with retry mechanism for rate limits
def add_items_to_list(list_slug, items, access_token, client_id, retries=3):
    trakt_url = f"{TRAKT_BASE_URL}/users/me/lists/{list_slug}/items"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id
    }

    payload = {
        "movies": [{"ids": {"tmdb": item['TMDB ID']}} for item in items if item['Type'] == 'movie'],
        "shows": [{"ids": {"tmdb": item['TMDB ID']}} for item in items if item['Type'] == 'show']
    }

    attempt = 0
    while attempt < retries:
        response = requests.post(trakt_url, headers=headers, json=payload)
        if response.status_code == 201:
            print(f"Successfully added items to list {list_slug}.")
            return True
        elif response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 1))
            print(f"Rate limit exceeded (429). Waiting {retry_after} seconds before retrying... (Attempt {attempt+1}/{retries})")
            time.sleep(retry_after)
            attempt += 1
        else:
            print(f"Failed to add items to list {list_slug}. Response: {response.status_code} - {response.text}")
            return False
    print(f"Failed to add items to list {list_slug} after {retries} attempts.")
    return False


# Function to process and import lists from the 'lists' directory
def import_lists(access_token, client_id):
    lists_dir = "lists"
    if not os.path.exists(lists_dir):
        print(f"No 'lists' directory found.")
        return

    # Iterate through CSV files in the 'lists' directory
    for list_file in os.listdir(lists_dir):
        if list_file.endswith(".csv"):
            list_name = os.path.splitext(list_file)[0]
            list_slug = create_personal_list(list_name, access_token, client_id)
            if list_slug:
                items = []
                with open(os.path.join(lists_dir, list_file), 'r', newline='', encoding='utf-8') as csvfile:
                    reader = csv.DictReader(csvfile)
                    for row in reader:
                        items.append(row)
                add_items_to_list(list_slug, items, access_token, client_id)

# Function to import items from the watchlist.csv to the user's Trakt watchlist
def import_watchlist(access_token, client_id):
    watchlist_file = "watchlist.csv"
    if not os.path.exists(watchlist_file):
        print(f"No 'watchlist.csv' file found.")
        return

    items = []
    with open(watchlist_file, 'r', newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            items.append(row)

    trakt_url = f"{TRAKT_BASE_URL}/sync/watchlist"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id
    }

    payload = {
        "movies": [{"ids": {"tmdb": item['TMDB ID']}} for item in items if item['Type'] == 'movie'],
        "shows": [{"ids": {"tmdb": item['TMDB ID']}} for item in items if item['Type'] == 'show']
    }

    response = requests.post(trakt_url, headers=headers, json=payload)
    if response.status_code == 201:
        print(f"Successfully imported {len(items)} items to the watchlist.")
    else:
        print(f"Failed to import items to the watchlist. Response: {response.status_code} - {response.text}")

# Function to import watched history (already existing, just ensure it's called when needed)
def import_watched_history(access_token, client_id):
    trakt_url = f"{TRAKT_BASE_URL}/sync/history"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id
    }

    # Example of fetching watched history (for illustration)
    response = requests.get(trakt_url, headers=headers)
    if response.status_code == 200:
        history = response.json()
        print(f"Successfully imported watched history with {len(history)} items.")
    else:
        print(f"Failed to import watched history. Response: {response.status_code} - {response.text}")



if __name__ == "__main__":
    # Authenticate with Trakt
    access_token, client_id = authenticate_trakt()

    # Ask if the user wants to import watched history
    print("Do you want to import your watched history?")
    import_watched_history_choice = input("Type 'yes' or 'no': ").strip().lower()

    # Import watched history if user agrees
    if import_watched_history_choice == 'yes':
        import_watched_history(access_token, client_id)

        # Ask the user to choose the watched date option (only after asking about history import)
        print("Do you want to mark everything watched as 'now' or on the 'release date'?")
        watched_choice = input("Type 'now' or 'release date': ").strip().lower()

        # Handle the watched date
        if watched_choice == 'now':
            watched_at = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        elif watched_choice == 'release date':
            watched_at = "released"  # Trakt will use the release date of the episode or movie
        else:
            print("Invalid choice, defaulting to 'now'.")
            watched_at = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

        # Process the CSV files for movies and shows only if the user chooses to import watched history
        movies_csv = 'trakt_movies_with_ratings.csv'
        shows_csv = 'trakt_shows_with_ratings.csv'

        # Process the movies and shows
        movies = process_movies_csv(movies_csv)
        shows = process_shows_csv(shows_csv)

        # Mark movies as watched
        if movies:
            mark_movies_watched(movies, watched_at, access_token, client_id)
        else:
            print("No new movies to mark as watched.")

        # Mark shows/episodes as watched
        if shows:
            mark_episodes_watched(shows, watched_at, access_token, client_id)
        else:
            print("No new shows to mark as watched.")

    # Import ratings for both movies and shows, independent of watched history
    movies_csv = 'trakt_movies_with_ratings.csv'
    shows_csv = 'trakt_shows_with_ratings.csv'

    movies_df = pd.read_csv(movies_csv)
    shows_df = pd.read_csv(shows_csv)

    if 'Rating' in movies_df.columns:
        movies_with_ratings = movies_df.set_index('TMDB ID')['Rating'].dropna().to_dict()
    else:
        movies_with_ratings = {}

    if 'Rating' in shows_df.columns:
        shows_with_ratings = shows_df.set_index('TMDB ID')['Rating'].dropna().to_dict()
    else:
        shows_with_ratings = {}

    if movies_with_ratings or shows_with_ratings:
        import_ratings(movies_with_ratings, shows_with_ratings, access_token, client_id)
    else:
        print("No ratings to import.")

    # Ask if the user wants to import the watchlist
    print("Do you want to import your watchlist from watchlist.csv?")
    import_watchlist_choice = input("Type 'yes' or 'no': ").strip().lower()

    # Ask if the user wants to import personal lists from the 'lists' directory
    print("Do you want to import your personal lists from the 'lists' directory?")
    import_lists_choice = input("Type 'yes' or 'no': ").strip().lower()

    # Import watchlist if user agrees
    if import_watchlist_choice == 'yes':
        import_watchlist(access_token, client_id)

    # Import personal lists if user agrees
    if import_lists_choice == 'yes':
        import_lists(access_token, client_id)

    print("All movies, shows, ratings, watched history, and lists have been processed.")
