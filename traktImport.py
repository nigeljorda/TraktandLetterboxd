import requests
import pandas as pd
import json
from datetime import datetime
import os
import webbrowser
import re
import time

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
        watched_at = "released"  # Trakt will use the release date of the episode or movie
    else:
        print("Invalid choice, defaulting to 'now'.")
        watched_at = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

        # Process the CSV files for movies and shows
    movies_csv = 'trakt_movies_with_ratings.csv'
    shows_csv = 'trakt_shows_with_ratings.csv'

    # Process the movies and shows
    movies = process_movies_csv(movies_csv)
    shows = process_shows_csv(shows_csv)

    # Mark movies and shows as watched
    if movies:
        mark_movies_watched(movies, watched_at, access_token, client_id)
    else:
        print("No new movies to mark as watched.")

    if shows:
        mark_episodes_watched(shows, watched_at, access_token, client_id)
    else:
        print("No new shows to mark as watched.")

    # Import ratings for both movies and shows
    movies_with_ratings = pd.read_csv(movies_csv).set_index('TMDB ID')['Rating'].dropna().to_dict()
    shows_with_ratings = pd.read_csv(shows_csv).set_index('TMDB ID')['Rating'].dropna().to_dict()

    if movies_with_ratings or shows_with_ratings:
        import_ratings(movies_with_ratings, shows_with_ratings, access_token, client_id)
    else:
        print("No new ratings to import.")

    print("All movies, shows, and ratings have been processed.")
