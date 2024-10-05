import requests
import json
import re
import time
from datetime import datetime
import os
import webbrowser

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

# Function to mark episodes as watched, season by season up to the last watched episode
def mark_episodes_watched(show_id, last_season, last_ep, watched_at, access_token, client_id, retries=5):
    trakt_url = f"{TRAKT_BASE_URL}/sync/history"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id
    }

    payload = {"shows": [{"ids": {"slug": show_id}, "seasons": []}]}

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

    attempt = 0
    while attempt < retries:
        response = requests.post(trakt_url, headers=headers, json=payload)
        
        if response.status_code == 201:
            print(f"Successfully marked up to season {last_season}, episode {last_ep} as watched.")
            return
        elif handle_rate_limit(response):
            continue
        else:
            print(f"Failed to mark episodes for show. Response: {response.status_code} - {response.text}")
            break

    if attempt == retries:
        print(f"Failed after {retries} attempts due to rate limits.")

# Function to extract show slug from the Trakt URL
def extract_show_slug(trakt_url):
    match = re.search(r'trakt\.tv/shows/([^/]+)', trakt_url)
    if match:
        return match.group(1)
    else:
        print(f"Error: Could not extract show slug from URL '{trakt_url}'")
        exit()

# Function to process the input of the last watched episode
def parse_season_episode(season_episode):
    match = re.match(r'S(\d+)E(\d+)', season_episode, re.IGNORECASE)
    if match:
        season_number = int(match.group(1))
        episode_number = int(match.group(2))
        return season_number, episode_number
    else:
        print(f"Error: Invalid season/episode format '{season_episode}'")
        exit()

# Main function to run the script
if __name__ == "__main__":
    # Authenticate with Trakt
    access_token, client_id = authenticate_trakt()

    # Ask the user for the show link and last watched episode
    trakt_show_url = input("Enter the Trakt show link (e.g., https://trakt.tv/shows/the-lord-of-the-rings-the-rings-of-power): ").strip()
    last_watched_episode = input("Enter the last watched episode in the format SxExx (e.g., S2E3): ").strip()

    # Extract show slug from the URL
    show_slug = extract_show_slug(trakt_show_url)

    # Parse the last watched episode input
    last_season, last_episode = parse_season_episode(last_watched_episode)

    # Ask the user if they want to mark watched episodes as 'now' or 'release date'
    print("Do you want to mark episodes watched as 'now' or on the 'release date'?")
    watched_choice = input("Type 'now' or 'release date': ").strip().lower()

    # Handle the watched date
    if watched_choice == 'now':
        watched_at = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    elif watched_choice == 'release date':
        watched_at = "released"  # Trakt will use the release date of the episode or movie
    else:
        print("Invalid choice, defaulting to 'now'.")
        watched_at = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

    # Mark episodes as watched
    mark_episodes_watched(show_slug, last_season, last_episode, watched_at, access_token, client_id)

    print("All episodes up to the given one have been marked as watched.")
