import requests
import json
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

# Function to retrieve all ratings (movies, shows, and episodes)
def get_trakt_ratings(access_token, client_id, retries=3):
    trakt_url = f"{TRAKT_BASE_URL}/users/me/ratings"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id
    }

    ratings_items = []
    page = 1
    per_page = 100

    while True:
        attempt = 0
        while attempt < retries:
            response = requests.get(f"{trakt_url}?page={page}&limit={per_page}", headers=headers)

            if response.status_code == 200:
                items = response.json()
                if not items:
                    return ratings_items  # No more items to retrieve
                ratings_items.extend(items)
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
                return []

    return ratings_items

# Function to delete ratings from Trakt
def delete_trakt_ratings(ratings_items, access_token, client_id, retries=3):
    trakt_url = f"{TRAKT_BASE_URL}/sync/ratings/remove"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id
    }

    # Organize ratings by type for deletion
    movies = [{"ids": item['movie']['ids']} for item in ratings_items if item['type'] == 'movie']
    shows = [{"ids": item['show']['ids']} for item in ratings_items if item['type'] == 'show']
    episodes = [{"ids": item['episode']['ids']} for item in ratings_items if item['type'] == 'episode']

    if not movies and not shows and not episodes:
        print("No ratings to delete.")
        return

    payload = {
        "movies": movies,
        "shows": shows,
        "episodes": episodes
    }

    print(f"Deleting {len(movies)} movie ratings, {len(shows)} show ratings, and {len(episodes)} episode ratings...")

    attempt = 0
    while attempt < retries:
        response = requests.post(trakt_url, headers=headers, json=payload)

        if response.status_code == 200:
            print("Successfully deleted all ratings.")
            return
        elif response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 1))
            print(f"Rate limit exceeded (429). Waiting {retry_after} seconds before retrying... (Attempt {attempt+1}/{retries})")
            time.sleep(retry_after)
            attempt += 1
        else:
            print(f"Failed to delete ratings. Response: {response.status_code} - {response.text}")
            return

    print(f"Failed to delete ratings after {retries} attempts due to rate limits.")

# Function to retrieve the user's entire history from Trakt
def get_trakt_history(access_token, client_id, retries=3):
    trakt_url = f"{TRAKT_BASE_URL}/users/me/history"
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
                print(f"Retrieved page {page} of history...")
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

# Function to delete items from Trakt history
def delete_trakt_history(history_items, access_token, client_id, retries=3):
    trakt_url = f"{TRAKT_BASE_URL}/sync/history/remove"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id
    }

    history_ids = [item['id'] for item in history_items]

    if not history_ids:
        print("No history items to delete.")
        return

    payload = {
        "ids": history_ids
    }

    print(f"Deleting {len(history_ids)} history items...")

    attempt = 0
    while attempt < retries:
        response = requests.post(trakt_url, headers=headers, json=payload)

        if response.status_code == 200:
            print("Successfully deleted all history items.")
            return
        elif response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 1))
            print(f"Rate limit exceeded (429). Waiting {retry_after} seconds before retrying... (Attempt {attempt+1}/{retries})")
            time.sleep(retry_after)
            attempt += 1
        else:
            print(f"Failed to delete history. Response: {response.status_code} - {response.text}")
            return

    print(f"Failed to delete history after {retries} attempts due to rate limits.")

# Function to retrieve the watchlist from Trakt
def get_trakt_watchlist(access_token, client_id, retries=3):
    trakt_url = f"{TRAKT_BASE_URL}/sync/watchlist"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id
    }

    watchlist_items = []
    page = 1
    per_page = 100

    while True:
        attempt = 0
        while attempt < retries:
            response = requests.get(f"{trakt_url}?page={page}&limit={per_page}", headers=headers)

            if response.status_code == 200:
                items = response.json()
                if not items:
                    return watchlist_items  # No more items to retrieve
                watchlist_items.extend(items)
                print(f"Retrieved page {page} of watchlist...")
                page += 1
                break
            elif response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 1))
                print(f"Rate limit exceeded (429). Waiting {retry_after} seconds before retrying... (Attempt {attempt+1}/{retries})")
                time.sleep(retry_after)
                attempt += 1
            else:
                print(f"Failed to retrieve watchlist. Response: {response.status_code} - {response.text}")
                return []

    return watchlist_items

# Function to remove items from Trakt watchlist (including seasons)
def delete_trakt_watchlist(watchlist_items, access_token, client_id, retries=3):
    trakt_url = f"{TRAKT_BASE_URL}/sync/watchlist/remove"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id
    }

    movies = [{"ids": item['movie']['ids']} for item in watchlist_items if item['type'] == 'movie']
    shows = [{"ids": item['show']['ids']} for item in watchlist_items if item['type'] == 'show']
    episodes = [{"ids": item['episode']['ids']} for item in watchlist_items if item['type'] == 'episode']
    seasons = [{"ids": item['season']['ids']} for item in watchlist_items if item['type'] == 'season']

    if not movies and not shows and not episodes and not seasons:
        print("No watchlist items to delete.")
        return

    payload = {
        "movies": movies,
        "shows": shows,
        "episodes": episodes,
        "seasons": seasons
    }

    print(f"Deleting {len(movies)} movie watchlist items, {len(shows)} show watchlist items, {len(episodes)} episode watchlist items, and {len(seasons)} season watchlist items...")

    attempt = 0
    while attempt < retries:
        response = requests.post(trakt_url, headers=headers, json=payload)

        if response.status_code == 200:
            print("Successfully deleted all watchlist items.")
            return
        elif response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 1))
            print(f"Rate limit exceeded (429). Waiting {retry_after} seconds before retrying... (Attempt {attempt+1}/{retries})")
            time.sleep(retry_after)
            attempt += 1
        else:
            print(f"Failed to delete watchlist. Response: {response.status_code} - {response.text}")
            return

    print(f"Failed to delete watchlist after {retries} attempts due to rate limits.")


# Function to delete all personal lists from Trakt with retry mechanism
def delete_all_trakt_lists(access_token, client_id, retries=3):
    # First, get all the user's lists
    trakt_url = f"{TRAKT_BASE_URL}/users/me/lists"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id
    }

    attempt = 0
    while attempt < retries:
        response = requests.get(trakt_url, headers=headers)

        if response.status_code == 200:
            lists = response.json()
            if not lists:
                print("No lists to delete.")
                return

            # Loop through each list and delete
            for trakt_list in lists:
                list_id = trakt_list['ids']['slug']
                delete_url = f"{TRAKT_BASE_URL}/users/me/lists/{list_id}"

                # Retry loop for deleting a list
                list_attempt = 0
                while list_attempt < retries:
                    delete_response = requests.delete(delete_url, headers=headers)

                    if delete_response.status_code == 204:
                        print(f"Successfully deleted list: {trakt_list['name']}")
                        break
                    elif delete_response.status_code == 429:
                        retry_after = int(delete_response.headers.get('Retry-After', 1))
                        print(f"Rate limit exceeded (429) for list {trakt_list['name']}. Waiting {retry_after} seconds before retrying... (Attempt {list_attempt+1}/{retries})")
                        time.sleep(retry_after)
                        list_attempt += 1
                    else:
                        print(f"Failed to delete list {trakt_list['name']}. Response: {delete_response.status_code} - {delete_response.text}")
                        break

            return
        elif response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 1))
            print(f"Rate limit exceeded (429). Waiting {retry_after} seconds before retrying... (Attempt {attempt+1}/{retries})")
            time.sleep(retry_after)
            attempt += 1
        else:
            print(f"Failed to retrieve lists. Response: {response.status_code} - {response.text}")
            return

    print(f"Failed to retrieve or delete lists after {retries} attempts due to rate limits.")


# Main function to run the script
if __name__ == "__main__":
    # Authenticate with Trakt
    access_token, client_id = authenticate_trakt()

    # Ask the user if they want to delete ratings
    delete_ratings_choice = input("Do you want to delete all ratings? Type 'yes' to confirm or 'no' to skip: ").strip().lower()
    
    if delete_ratings_choice == 'yes':
        # Process and delete the user's ratings
        print("Starting ratings deletion process...")
        ratings = get_trakt_ratings(access_token, client_id)
        if ratings:
            delete_trakt_ratings(ratings, access_token, client_id)
        else:
            print("No ratings found to delete.")
    else:
        print("Skipping ratings deletion.")

    # Ask the user if they want to delete history
    delete_history_choice = input("Do you want to delete all history? Type 'yes' to confirm or 'no' to skip: ").strip().lower()
    
    if delete_history_choice == 'yes':
        # Process and delete the user's history
        print("Starting history deletion process...")
        history = get_trakt_history(access_token, client_id)
        if history:
            delete_trakt_history(history, access_token, client_id)
        else:
            print("No history found to delete.")
    else:
        print("Skipping history deletion.")

    # Ask the user if they want to remove everything from watchlist
    delete_watchlist_choice = input("Do you want to remove all items from your watchlist? Type 'yes' to confirm or 'no' to skip: ").strip().lower()

    if delete_watchlist_choice == 'yes':
        # Process and delete the user's watchlist items
        print("Starting watchlist deletion process...")
        watchlist_items = get_trakt_watchlist(access_token, client_id)
        if watchlist_items:
            delete_trakt_watchlist(watchlist_items, access_token, client_id)
        else:
            print("No watchlist items found to delete.")
    else:
        print("Skipping watchlist deletion.")

    # Ask the user if they want to delete all lists
    delete_lists_choice = input("Do you want to delete all your personal lists? Type 'yes' to confirm or 'no' to skip: ").strip().lower()

    if delete_lists_choice == 'yes':
        # Process and delete all personal lists
        print("Starting lists deletion process...")
        delete_all_trakt_lists(access_token, client_id)
    else:
        print("Skipping lists deletion.")

    print("Process completed.")
