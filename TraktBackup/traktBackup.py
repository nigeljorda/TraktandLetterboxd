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

# Function to retrieve detailed show information from Trakt
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

# Function to retrieve a user's personal lists
def get_user_lists(access_token, client_id):
    trakt_url = f"{TRAKT_BASE_URL}/users/me/lists"
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
        print(f"Failed to retrieve personal lists. Response: {response.status_code} - {response.text}")
        return []

# Function to retrieve items from a personal list
def get_list_items(list_slug, access_token, client_id):
    trakt_url = f"{TRAKT_BASE_URL}/users/me/lists/{list_slug}/items"
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
        print(f"Failed to retrieve items for list {list_slug}. Response: {response.status_code} - {response.text}")
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


# Function to create CSV for personal lists
def create_list_csv(list_items, list_name):
    filename = f"lists/{list_name}.csv"
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Title', 'Year', 'TMDB ID', 'Type']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for item in list_items:
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

    print(f"Saved {len(list_items)} items in list: {list_name}")


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

# Function to create CSV for shows with progress, TMDB ID, and ratings
def create_shows_csv(progress, ratings, access_token, client_id, filename):
    has_ratings = any(ratings['shows'].values())
    fieldnames = ['Title', 'Year', 'Seasons Watched', 'Completed', 'Last Watched Episode', 'TMDB ID']
    if has_ratings:
        fieldnames.append('Rating')

    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
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

            row = {
                'Title': title, 
                'Year': year, 
                'Seasons Watched': num_seasons_watched, 
                'Completed': completed,
                'Last Watched Episode': last_watched_episode,
                'TMDB ID': tmdb_id
            }

            if has_ratings:
                row['Rating'] = ratings['shows'].get(tmdb_id, '')

            writer.writerow(row)


# Function to create CSV for movies with history, TMDB ID, and ratings
def create_movies_csv(history, ratings, filename):
    has_ratings = any(ratings['movies'].values())
    fieldnames = ['Title', 'Year', 'TMDB ID']
    if has_ratings:
        fieldnames.append('Rating')
    
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
                if has_ratings:
                    row['Rating'] = ratings['movies'].get(tmdb_id, '')

                writer.writerow(row)


# Main function to run the script
if __name__ == "__main__":
    # Authenticate with Trakt
    access_token, client_id = authenticate_trakt()

    # Ask the user if they want to back up ratings
    backup_ratings = input("Do you want to back up ratings as well? (yes/no): ").strip().lower() == 'yes'
    
    # Ask the user if they want to back up their watchlist
    backup_watchlist = input("Do you want to back up your watchlist? (yes/no): ").strip().lower() == 'yes'
    
    # Ask the user if they want to back up personal lists
    backup_lists = input("Do you want to back up your personal lists? (yes/no): ").strip().lower() == 'yes'

    # Get history for movies, progress for shows, and ratings
    movie_history = get_trakt_history_movies(access_token, client_id)
    show_progress = get_trakt_show_progress(access_token, client_id)

    # Optionally get ratings
    ratings = {'movies': {}, 'shows': {}}
    if backup_ratings:
        ratings = get_trakt_ratings(access_token, client_id)

    # Create CSV files for movies and shows, including ratings if requested
    create_movies_csv(movie_history, ratings, 'trakt_movies_with_ratings.csv')
    create_shows_csv(show_progress, ratings, access_token, client_id, 'trakt_shows_with_ratings.csv')

    # Optionally back up the watchlist
    if backup_watchlist:
        watchlist = get_watchlist(access_token, client_id)
        create_watchlist_csv(watchlist)

    # Optionally back up personal lists
    if backup_lists:
        user_lists = get_user_lists(access_token, client_id)
        for user_list in user_lists:
            list_name = user_list['name']
            list_slug = user_list['ids']['slug']
            list_items = get_list_items(list_slug, access_token, client_id)
            create_list_csv(list_items, list_name)

    print("Backup process completed successfully.")
