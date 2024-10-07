import requests
import pandas as pd
import json
from datetime import datetime
import os
import time
import webbrowser

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

    # If not found, ask the user for the Client ID and Client Secret
    client_id = input("Enter your Trakt Client ID: ").strip()
    client_secret = input("Enter your Trakt Client Secret: ").strip()

    # Save them to the json file for future use
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

    # Ask for the PIN code
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

# Function to mark movies and shows as watched on Trakt in a batch request, with retry mechanism
def mark_watched_batch(movies, shows, watched_at, access_token, client_id, retries=3):
    trakt_url = f"{TRAKT_BASE_URL}/sync/history"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id
    }

    # Prepare the payload for batch marking movies and shows
    payload = {
        "movies": [{"ids": {"tmdb": movie_id}, "watched_at": watched_at} for movie_id in movies],
        "shows": [{"ids": {"tmdb": show_id}, "watched_at": watched_at} for show_id in shows]
    }

    attempt = 0
    while attempt < retries:
        response = requests.post(trakt_url, headers=headers, json=payload)

        if response.status_code == 201:
            print("Successfully marked all movies and shows as watched in one request.")
            return True
        elif response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 1))
            print(f"Rate limit exceeded (429). Waiting {retry_after} seconds before retrying... (Attempt {attempt+1}/{retries})")
            time.sleep(retry_after)
            attempt += 1
        else:
            print(f"Failed to mark items as watched. Response: {response.status_code} - {response.text}")
            return False

    print(f"Failed to mark items after {retries} attempts due to rate limits.")
    return False

# Function to mark movies as rated on Trakt
def import_ratings(movies_with_ratings, access_token, client_id):
    trakt_url = f"{TRAKT_BASE_URL}/sync/ratings"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id
    }

    # Prepare the payload for movies ratings
    payload = {
        "movies": [{"ids": {"tmdb": movie_id}, "rating": rating} for movie_id, rating in movies_with_ratings.items()]
    }

    response = requests.post(trakt_url, headers=headers, json=payload)
    
    if response.status_code == 201:
        print("Successfully imported ratings.")
        return True
    else:
        print(f"Failed to import ratings. Response: {response.status_code} - {response.text}")
        return False

# Function to import movies to the user's watchlist
def import_watchlist(movies, shows, access_token, client_id):
    trakt_url = f"{TRAKT_BASE_URL}/sync/watchlist"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id
    }

    # Prepare the payload for watchlist import
    payload = {
        "movies": [{"ids": {"tmdb": movie_id}} for movie_id in movies],
        "shows": [{"ids": {"tmdb": show_id}} for show_id in shows]
    }

    response = requests.post(trakt_url, headers=headers, json=payload)

    if response.status_code == 201:
        print("Successfully imported watchlist.")
        return True
    else:
        print(f"Failed to import watchlist. Response: {response.status_code} - {response.text}")
        return False

# Function to process the CSV file and collect items for the batch request
def process_csv(file_path):
    # Read the CSV file
    data = pd.read_csv(file_path)

    # Collect movies, shows, and ratings
    movies = []
    shows = []
    movies_with_ratings = {}
    letterboxd_urls = {}

    # Loop through each row
    for index, row in data.iterrows():
        tmdb_id = row['TMDB ID']
        media_type = row['Type']
        letterboxd_url = row.get('Letterboxd URL', '')
        letterboxd_urls[tmdb_id] = letterboxd_url

        if media_type == 'movie':
            movies.append(tmdb_id)
            if 'Rating' in row and not pd.isnull(row['Rating']):
                # Store rating if available
                movies_with_ratings[tmdb_id] = int(row['Rating'])
        elif media_type == 'show':
            shows.append(tmdb_id)
    
    return movies, shows, letterboxd_urls, movies_with_ratings

# Function to retrieve watched history from Trakt
def retrieve_trakt_history(access_token, client_id):
    trakt_url = f"{TRAKT_BASE_URL}/sync/history"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id
    }

    all_history = []
    page = 1
    while True:
        response = requests.get(f"{trakt_url}?page={page}&limit=1000", headers=headers)
        if response.status_code != 200:
            print(f"Failed to retrieve watched history from Trakt. Response: {response.status_code} - {response.text}")
            return None

        page_data = response.json()
        if not page_data:
            break  # No more history to fetch
        all_history.extend(page_data)
        page += 1

    return all_history

# Function to compare the CSV and Trakt history
def compare_csv_and_history(csv_movies, csv_shows, trakt_history, letterboxd_urls):
    # Extract the TMDb IDs from the Trakt history
    trakt_movie_ids = []
    trakt_show_ids = []

    for item in trakt_history:
        if 'movie' in item:
            trakt_movie_ids.append(item['movie']['ids']['tmdb'])
        elif 'show' in item:
            trakt_show_ids.append(item['show']['ids']['tmdb'])

    # Compare CSV movies with Trakt movie history
    missing_movies = [movie for movie in csv_movies if movie not in trakt_movie_ids]

    # Compare CSV shows with Trakt show history
    missing_shows = [show for show in csv_shows if show not in trakt_show_ids]

        # Report missing items
    if missing_movies or missing_shows:
        print("\nThe following items were not marked as watched on Trakt:")
        for tmdb_id in missing_movies:
            print(f"Missing Movie - TMDb ID: {tmdb_id}, Letterboxd URL: {letterboxd_urls.get(tmdb_id, 'N/A')}")
        for tmdb_id in missing_shows:
            print(f"Missing Show - TMDb ID: {tmdb_id}, Letterboxd URL: {letterboxd_urls.get(tmdb_id, 'N/A')}")
    else:
        print("All items were successfully marked as watched on Trakt.")

# Main function to run the script
if __name__ == "__main__":
    # Authenticate with Trakt
    access_token, client_id = authenticate_trakt()

    # Ask the user to choose the watched date option
    print("Do you want to mark everything watched as 'now' or on the 'release date'?")
    watched_choice = input("Type 'now' or 'release date': ").strip().lower()

    # Handle the watched date
    if watched_choice == 'now':
        watched_at = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    elif watched_choice == 'release date':
        watched_at = "released"  # Trakt will use the release date of the movie/show
    else:
        print("Invalid choice, defaulting to 'now'.")
        watched_at = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

    # Ask if the user wants to import ratings
    print("Do you want to import ratings as well?")
    import_ratings_choice = input("Type 'yes' or 'no': ").strip().lower()

    # Ask if the user wants to import their watchlist
    print("Do you want to import your watchlist as well?")
    import_watchlist_choice = input("Type 'yes' or 'no': ").strip().lower()

    # Use the .csv file with TMDB IDs and ratings
    csv_file_path = 'watched_movies_tmdb.csv'  # Make sure this path is correct
    movies, shows, letterboxd_urls, movies_with_ratings = process_csv(csv_file_path)

    # Mark movies/shows as watched
    if mark_watched_batch(movies, shows, watched_at, access_token, client_id):
        print("Waiting 5 seconds for Trakt to update the history...")
        time.sleep(5)  # Wait for a few seconds to allow Trakt to update the history

        # Retrieve watched history from Trakt
        trakt_history = retrieve_trakt_history(access_token, client_id)

        if trakt_history:
            # Compare CSV items with Trakt history
            compare_csv_and_history(movies, shows, trakt_history, letterboxd_urls)

    # If the user chose to import ratings
    if import_ratings_choice == 'yes' and movies_with_ratings:
        # Import the ratings using the Trakt API
        if import_ratings(movies_with_ratings, access_token, client_id):
            print("Ratings have been successfully imported to Trakt.")
        else:
            print("There was an issue importing the ratings.")
    else:
        print("Skipping ratings import.")
    
    # If the user chose to import their watchlist
    if import_watchlist_choice == 'yes':
        watchlist_csv_path = 'watchlist_tmdb.csv'  # Path to the watchlist CSV file
        watchlist_movies, watchlist_shows, _, _ = process_csv(watchlist_csv_path)
        if import_watchlist(watchlist_movies, watchlist_shows, access_token, client_id):
            print("Watchlist has been successfully imported to Trakt.")
        else:
            print("There was an issue importing the watchlist.")
    else:
        print("Skipping watchlist import.")

    print("All items have been processed.")
