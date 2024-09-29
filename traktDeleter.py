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

# Function to retrieve the user's entire history from Trakt using "me" instead of username
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

# Function to delete items from Trakt history using the 429 retry mechanism
def delete_trakt_history(history_ids, access_token, client_id, retries=3):
    trakt_url = f"{TRAKT_BASE_URL}/sync/history/remove"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id
    }

    payload = {
        "ids": history_ids
    }

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

# Function to process the retrieved history and prepare it for deletion
def process_and_delete_history(access_token, client_id):
    # Retrieve the entire history
    history = get_trakt_history(access_token, client_id)

    if not history:
        print("No history found or unable to retrieve history.")
        return

    # Extract the IDs of all history items
    history_ids = [item['id'] for item in history]

    # Confirm with the user before deleting
    print(f"\nYou are about to delete {len(history_ids)} items from your Trakt history.")
    confirmation = input("Type 'yes' to confirm: ").strip().lower()

    if confirmation == 'yes':
        # Delete the history
        delete_trakt_history(history_ids, access_token, client_id)
    else:
        print("Deletion cancelled.")

# Main function to run the script
if __name__ == "__main__":
    # Authenticate with Trakt
    access_token, client_id = authenticate_trakt()

    # Process and delete the user's history
    process_and_delete_history(access_token, client_id)
