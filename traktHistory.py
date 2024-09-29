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
            return
        elif response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 1))
            print(f"Rate limit exceeded (429). Waiting {retry_after} seconds before retrying... (Attempt {attempt+1}/{retries})")
            time.sleep(retry_after)
            attempt += 1
        else:
            print(f"Failed to mark items as watched. Response: {response.status_code} - {response.text}")
            return

    print(f"Failed to mark items after {retries} attempts due to rate limits.")

# Function to process the CSV file and collect items for the batch request
def process_csv(file_path, watched_at, access_token, client_id):
    # Read the CSV file
    data = pd.read_csv(file_path)

    # Collect movies and shows
    movies = []
    shows = []

    # Loop through each row
    for index, row in data.iterrows():
        tmdb_id = row['TMDB ID']
        media_type = row['Type']

        if media_type == 'movie':
            movies.append(tmdb_id)
        elif media_type == 'show':
            shows.append(tmdb_id)
    
    # Mark all items as watched in a batch request
    mark_watched_batch(movies, shows, watched_at, access_token, client_id)

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

    # Use the .csv from the previous Letterboxd script
    csv_file_path = 'watched_movies_tmdb.csv'

    # Process the CSV and mark movies/shows as watched in one request
    process_csv(csv_file_path, watched_at, access_token, client_id)

    print("All movies and shows have been processed.")
