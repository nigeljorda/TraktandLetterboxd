import requests
import json
import os
import time
import webbrowser
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

# Function to retrieve show details from Trakt API (to get episode counts)
def get_show_details(trakt_slug, access_token, client_id):
    trakt_url = f"{TRAKT_BASE_URL}/shows/{trakt_slug}/seasons?extended=episodes"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id
    }
    response = requests.get(trakt_url, headers=headers)
    if response.status_code == 200:
        return response.json()  # Return detailed season/episode data
    else:
        print(f"Error retrieving show details for {trakt_slug}: {response.status_code} - {response.text}")
        return []

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

# Function to create CSV for shows with progress and TMDB ID (removing Watch Date)
def create_shows_csv(progress, access_token, client_id, filename):
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Title', 'Year', 'Seasons Watched', 'Completed', 'Last Watched Episode', 'TMDB ID']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for item in progress:
            show = item['show']
            title = show.get('title', 'Unknown Title')
            year = show.get('year', 'Unknown Year')
            trakt_slug = show.get('ids', {}).get('slug', None)
            tmdb_id = show.get('ids', {}).get('tmdb', 'Unknown TMDB ID')

            # Get the number of seasons watched
            seasons_watched = item.get('seasons', [])
            num_seasons_watched = len(seasons_watched)

            # Get detailed show info to verify completion
            show_details = get_show_details(trakt_slug, access_token, client_id)
            if show_details:
                last_show_season = show_details[-1].get('number', None)  # Latest season number
                last_show_episode = show_details[-1].get('episodes', [])[-1].get('number', None)  # Latest episode number
            else:
                last_show_season, last_show_episode = None, None

            last_watched_episode = ''
            if seasons_watched:
                last_season = seasons_watched[-1]  # Last season watched
                last_episode = last_season.get('episodes', [])[-1] if last_season.get('episodes') else {}
                season_number = last_season.get('number', 'N/A')
                episode_number = last_episode.get('number', 'N/A')
                last_watched_episode = f"S{season_number}E{episode_number}"

            # Determine if the show is completed
            completed = 'Yes' if season_number == last_show_season and episode_number == last_show_episode else 'No'

            writer.writerow({
                'Title': title, 
                'Year': year, 
                'Seasons Watched': num_seasons_watched, 
                'Completed': completed,
                'Last Watched Episode': last_watched_episode,
                'TMDB ID': tmdb_id
            })

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

def create_movies_csv(history, filename):
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Title', 'Year', 'TMDB ID']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for item in history:
            if 'movie' in item:
                movie = item['movie']
                title = movie.get('title', 'Unknown Title')
                year = movie.get('year', 'Unknown Year')
                tmdb_id = movie.get('ids', {}).get('tmdb', 'Unknown TMDB ID')
                writer.writerow({'Title': title, 'Year': year, 'TMDB ID': tmdb_id})

# Main function to run the script
if __name__ == "__main__":
    # Authenticate with Trakt
    access_token, client_id = authenticate_trakt()

    # Get history for movies and progress for shows
    movie_history = get_trakt_history_movies(access_token, client_id)
    show_progress = get_trakt_show_progress(access_token, client_id)

    # Create CSV files
    create_movies_csv(movie_history, 'trakt_movies.csv')
    create_shows_csv(show_progress, access_token, client_id, 'trakt_shows.csv')

    print("CSV files created successfully.")
