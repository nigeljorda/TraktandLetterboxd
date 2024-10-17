import pandas as pd
import requests
import json
import os
import time
import webbrowser
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed

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

# Function to retrieve the user's ratings for movies and shows from Trakt
def get_trakt_ratings(access_token, client_id, retries=3):
    trakt_url = f"{TRAKT_BASE_URL}/users/me/ratings"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id
    }

    ratings = {'movies': {}, 'shows': {}}
    page = 1
    per_page = 100

    while True:
        attempt = 0
        while attempt < retries:
            response = requests.get(f"{trakt_url}?page={page}&limit={per_page}", headers=headers)

            if response.status_code == 200:
                items = response.json()
                if not items:
                    return ratings  # No more items to retrieve

                # Separate ratings for movies and shows
                for item in items:
                    if 'movie' in item:
                        movie = item['movie']
                        tmdb_id = movie.get('ids', {}).get('tmdb', None)
                        if tmdb_id:
                            ratings['movies'][tmdb_id] = item.get('rating', None)
                    elif 'show' in item:
                        show = item['show']
                        tmdb_id = show.get('ids', {}).get('tmdb', None)
                        if tmdb_id:
                            ratings['shows'][tmdb_id] = item.get('rating', None)

                print(f"Retrieved page {page} of ratings...")
                page += 1
                break
            elif response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 1))
                print(f"Rate limit exceeded (429). Waiting {retry_after} seconds before retrying... (Attempt {attempt+1}/{retries})")
                time.sleep(retry_after)
                attempt += 1
            else:
                print(f"Failed to retrieve ratings. Response: {response.status_code} - {response.text}")
                return ratings

    return ratings

# Function to retrieve the user's entire movie history from Trakt
def get_trakt_history_movies(access_token, client_id, retries=3):
    trakt_url = f"{TRAKT_BASE_URL}/users/me/history/movies"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id
    }

    history_items = []
    page = 1
    per_page = 100

    while True:
        attempt = 0
        while attempt < retries:
            response = requests.get(f"{trakt_url}?page={page}&limit={per_page}", headers=headers)

            if response.status_code == 200:
                items = response.json()
                if not items:
                    return history_items  # No more items to retrieve
                history_items.extend(items)
                print(f"Retrieved page {page} of movie history...")
                page += 1
                break
            elif response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 1))
                print(f"Rate limit exceeded (429). Waiting {retry_after} seconds before retrying... (Attempt {attempt+1}/{retries})")
                time.sleep(retry_after)
                attempt += 1
            else:
                print(f"Failed to retrieve history. Response: {response.status_code} - {response.text}")
                return []

    return history_items

# Function to retrieve the user's watched show progress from Trakt
def get_trakt_show_progress(access_token, client_id, retries=3):
    trakt_url = f"{TRAKT_BASE_URL}/users/me/watched/shows"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id
    }

    progress_items = []
    page = 1
    per_page = 100

    while True:
        attempt = 0
        while attempt < retries:
            response = requests.get(f"{trakt_url}?page={page}&limit={per_page}", headers=headers)

            if response.status_code == 200:
                items = response.json()

                # Get total page count from headers
                total_pages = int(response.headers.get('X-Pagination-Page-Count', 1))

                if not items:
                    return progress_items  # No more items to retrieve
                
                progress_items.extend(items)
                print(f"Retrieved page {page} of {total_pages} for show progress...")

                # Stop if we reach the last page
                if page >= total_pages:
                    return progress_items

                page += 1
                break
            elif response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 1))
                print(f"Rate limit exceeded (429). Waiting {retry_after} seconds before retrying... (Attempt {attempt+1}/{retries})")
                time.sleep(retry_after)
                attempt += 1
            else:
                print(f"Failed to retrieve progress. Response: {response.status_code} - {response.text}")
                return []

    return progress_items

# Function to retrieve the user's watchlist
def get_watchlist(access_token, client_id):
    trakt_url = f"{TRAKT_BASE_URL}/sync/watchlist"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id
    }

    response = requests.get(trakt_url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to retrieve watchlist. Response: {response.status_code} - {response.text}")
        return []

# Function to create CSV for the watchlist
def create_watchlist_csv(watchlist, filename='watchlist.csv'):
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Title', 'Year', 'TMDB ID', 'Type']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for item in watchlist:
            if 'movie' in item:
                movie = item['movie']
                title = movie.get('title', 'Unknown Title')
                year = movie.get('year', 'Unknown Year')
                tmdb_id = movie.get('ids', {}).get('tmdb', 'Unknown TMDB ID')
                writer.writerow({'Title': title, 'Year': year, 'TMDB ID': tmdb_id, 'Type': 'movie'})
            elif 'show' in item:
                show = item['show']
                title = show.get('title', 'Unknown Title')
                year = show.get('year', 'Unknown Year')
                tmdb_id = show.get('ids', {}).get('tmdb', 'Unknown TMDB ID')
                writer.writerow({'Title': title, 'Year': year, 'TMDB ID': tmdb_id, 'Type': 'show'})

    print(f"Saved {len(watchlist)} items in the watchlist.")


# Function to create CSV for movies with history, TMDB ID, and rating10 (Trakt ratings doubled)
def create_movies_csv(history, ratings, filename='trakt_movies.csv'):
    has_ratings = any(ratings['movies'].values())
    fieldnames = ['Title', 'Year', 'TMDB ID', 'rating10']  # Change to 'rating10'

    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for item in history:
            if 'movie' in item:
                movie = item['movie']
                title = movie.get('title', 'Unknown Title')
                year = movie.get('year', 'Unknown Year')
                tmdb_id = movie.get('ids', {}).get('tmdb', 'Unknown TMDB ID')
                
                row = {'Title': title, 'Year': year, 'TMDB ID': tmdb_id}
                
                # Double the rating to fit Letterboxd's 10-point scale
                if has_ratings and tmdb_id in ratings['movies']:
                    row['rating10'] = ratings['movies'].get(tmdb_id, 0) * 2
                else:
                    row['rating10'] = ''

                writer.writerow(row)

# Function to create CSV for shows with progress, TMDB ID, and rating10 (Trakt ratings doubled)
def create_shows_csv(progress, ratings, access_token, client_id, filename='trakt_shows.csv'):
    has_ratings = any(ratings['shows'].values())
    fieldnames = ['Title', 'Year', 'TMDB ID', 'rating10']  # Change to 'rating10'

    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for item in progress:
            show = item['show']
            title = show.get('title', 'Unknown Title')
            year = show.get('year', 'Unknown Year')
            tmdb_id = show.get('ids', {}).get('tmdb', 'Unknown TMDB ID')

            row = {'Title': title, 'Year': year, 'TMDB ID': tmdb_id}

            # Double the rating to fit Letterboxd's 10-point scale
            if has_ratings and tmdb_id in ratings['shows']:
                row['rating10'] = ratings['shows'].get(tmdb_id, 0) * 2
            else:
                row['rating10'] = ''

            writer.writerow(row)


# Function to merge movies and shows into a Letterboxd importable CSV
def merge_trakt_files(movies_file_path, shows_file_path, output_file_path):
    # Check if the necessary files exist
    if not os.path.exists(movies_file_path) or not os.path.exists(shows_file_path):
        print("Error: Required files are missing!")
        return

    # Load the CSV files
    movies_df = pd.read_csv(movies_file_path)
    shows_df = pd.read_csv(shows_file_path)

    # Ensure proper renaming of the TMDB ID column to tmdbID
    if 'TMDB ID' in movies_df.columns:
        movies_df.rename(columns={'TMDB ID': 'tmdbID'}, inplace=True)
    if 'TMDB ID' in shows_df.columns:
        shows_df.rename(columns={'TMDB ID': 'tmdbID'}, inplace=True)

    # Check if 'rating10' column exists, if not, add an empty 'rating10' column
    if 'rating10' not in movies_df.columns:
        movies_df['rating10'] = ""
    if 'rating10' not in shows_df.columns:
        shows_df['rating10'] = ""

    # Ensure tmdbID column exists before proceeding
    if 'tmdbID' not in movies_df.columns or 'tmdbID' not in shows_df.columns:
        print("Error: tmdbID column is missing in one or both files.")
        return

    # Select relevant columns from movies
    movies_df = movies_df[['Title', 'Year', 'tmdbID', 'rating10']].copy()

    # Select relevant columns from shows
    shows_df = shows_df[['Title', 'Year', 'tmdbID', 'rating10']].copy()

    # Merge the two dataframes
    merged_df = pd.concat([movies_df[['Title', 'Year', 'tmdbID', 'rating10']],
                           shows_df[['Title', 'Year', 'tmdbID', 'rating10']]],
                          ignore_index=True)

    # Export to CSV in the Letterboxd format
    merged_df.to_csv(output_file_path, index=False, encoding='utf-8')
    print(f"CSV file successfully created: {output_file_path}")

    # Remove old CSV files
    os.remove(movies_file_path)
    os.remove(shows_file_path)

    # Provide a message for the user to import the files
    print(f"You can now import {output_file_path} to Letterboxd at https://letterboxd.com/import/")
    print(f"You can import your watchlist at https://letterboxd.com/watchlist/")



if __name__ == "__main__":
    # Authenticate with Trakt
    access_token, client_id = authenticate_trakt()

    # Ask the user if they want to back up ratings
    backup_ratings = input("Do you want to back up ratings as well? (yes/no): ").strip().lower() == 'yes'
    
    # Ask the user if they want to back up their watchlist
    backup_watchlist = input("Do you want to back up your watchlist? (yes/no): ").strip().lower() == 'yes'

    # Get history for movies, progress for shows, and ratings
    movie_history = get_trakt_history_movies(access_token, client_id)
    show_progress = get_trakt_show_progress(access_token, client_id)

    # Optionally get ratings
    ratings = {'movies': {}, 'shows': {}}
    if backup_ratings:
        ratings = get_trakt_ratings(access_token, client_id)

    # Create CSV files for movies and shows, including doubled ratings if requested
    create_movies_csv(movie_history, ratings, 'trakt_movies.csv')
    create_shows_csv(show_progress, ratings, access_token, client_id, 'trakt_shows.csv')

    # Optionally back up the watchlist
    if backup_watchlist:
        watchlist = get_watchlist(access_token, client_id)
        create_watchlist_csv(watchlist)

    # Merge the CSVs and create a Letterboxd importable file
    merge_trakt_files('trakt_movies.csv', 'trakt_shows.csv', 'ImporttoLetterboxd.csv')
