import requests
import pandas as pd
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
        print("Successfully authenticated with Trakt.")
        return token_data['access_token'], client_id
    else:
        print(f"Error authenticating with Trakt: {response.status_code} - {response.text}")
        exit()

# Function to create a new list on Trakt
def create_trakt_list(access_token, client_id):
    list_name = input("Enter the title for the new Trakt list: ").strip()
    list_description = input("Enter the description for the Trakt list: ").strip()
    is_public = input("Should this list be public? (yes/no): ").strip().lower() == 'yes'
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id
    }
    
    # Payload for creating the list
    payload = {
        "name": list_name,
        "description": list_description,
        "privacy": "public" if is_public else "private",
        "display_numbers": False,
        "allow_comments": True
    }
    
    response = requests.post(f"{TRAKT_BASE_URL}/users/me/lists", headers=headers, json=payload)
    
    if response.status_code == 201:
        list_slug = response.json()['ids']['slug']
        print(f"List '{list_name}' created successfully on Trakt.")
        return list_slug
    else:
        print(f"Failed to create list. Response: {response.status_code} - {response.text}")
        exit()

# Function to remove all items from a Trakt list
def remove_all_items_from_trakt_list(list_slug, access_token, client_id):
    trakt_url = f"{TRAKT_BASE_URL}/users/me/lists/{list_slug}/items/remove"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id
    }

    # Retrieve the current list of items from Trakt
    list_items = retrieve_trakt_list(list_slug, access_token, client_id)
    
    if not list_items:
        print(f"List {list_slug} is already empty.")
        return

    # Prepare the payload to remove all items
    payload = {
        "movies": [{"ids": {"tmdb": item['movie']['ids']['tmdb']}} for item in list_items if 'movie' in item],
        "shows": [{"ids": {"tmdb": item['show']['ids']['tmdb']}} for item in list_items if 'show' in item]
    }

    # Ensure the payload is not empty
    if not payload['movies'] and not payload['shows']:
        print(f"No items found in list {list_slug} to remove.")
        return
    
    # Send the request to remove the items
    response = requests.post(trakt_url, headers=headers, json=payload)
    
    if response.status_code == 200:
        print("Successfully removed all items from the list.")
    else:
        print(f"Failed to remove items from the list. Response: {response.status_code} - {response.text}")


# Function to add items to the Trakt list in batch with rank assignment
def add_items_to_trakt_list_with_rank(list_slug, items, access_token, client_id, retries=3):
    trakt_url = f"{TRAKT_BASE_URL}/users/me/lists/{list_slug}/items"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id
    }

    # Prepare the payload for adding items in the exact order with rank
    payload = {
        "movies": [],
        "shows": []
    }
    
    for item in items:
        if item['type'] == 'movie':
            payload['movies'].append({"ids": {"tmdb": item['tmdb_id']}, "rank": item['rank']})
        elif item['type'] == 'show':
            payload['shows'].append({"ids": {"tmdb": item['tmdb_id']}, "rank": item['rank']})

    # Ensure the payload is not empty
    if not payload['movies'] and not payload['shows']:
        print(f"No valid items found to add to list {list_slug}.")
        return None

    attempt = 0

    while attempt < retries:
        response = requests.post(trakt_url, headers=headers, json=payload)

        if response.status_code == 201:
            print(f"Successfully added all items (movies and shows) to the list in the correct order with ranks.")
            return response.status_code
        elif response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 1))
            print(f"Rate limit exceeded (429). Waiting {retry_after} seconds before retrying... (Attempt {attempt+1}/{retries})")
            time.sleep(retry_after)
            attempt += 1
        else:
            print(f"Failed to add items to the list. Response: {response.status_code} - {response.text}")
            return None

    print(f"Failed to add items after {retries} attempts due to rate limits.")
    return None


# Function to retrieve the list from Trakt after adding items
def retrieve_trakt_list(list_slug, access_token, client_id):
    trakt_url = f"{TRAKT_BASE_URL}/users/me/lists/{list_slug}/items"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id
    }

    response = requests.get(trakt_url, headers=headers)
    
    if response.status_code == 200:
        return response.json()  # Return the list items
    else:
        print(f"Failed to retrieve list items from Trakt. Response: {response.status_code} - {response.text}")
        return None

# Function to reorder items in the Trakt list to match the CSV order
def reorder_trakt_list(list_slug, items, access_token, client_id):
    trakt_url = f"{TRAKT_BASE_URL}/users/me/lists/{list_slug}/items/reorder"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id
    }

    # Retrieve the current list of items from Trakt
    list_items = retrieve_trakt_list(list_slug, access_token, client_id)
    
    # Map the item ranks based on the CSV file order
    item_order = []
    for item in items:
        for trakt_item in list_items:
            if 'movie' in trakt_item and trakt_item['movie']['ids']['tmdb'] == item['tmdb_id']:
                item_order.append(trakt_item['id'])
            elif 'show' in trakt_item and trakt_item['show']['ids']['tmdb'] == item['tmdb_id']:
                item_order.append(trakt_item['id'])

        # Prepare the payload for reordering
    payload = {
        "rank": item_order  # Use the order from CSV to rank items
    }

    # Send the reorder request
    response = requests.post(trakt_url, headers=headers, json=payload)
    
    if response.status_code == 200:
        print("Successfully reordered the list to match the CSV order.")
    else:
        print(f"Failed to reorder the list. Response: {response.status_code} - {response.text}")

# Function to compare the items in the CSV with those in the Trakt list
def compare_trakt_and_csv(csv_items, trakt_items, letterboxd_urls):
    # Extract the TMDb IDs from the Trakt list items
    trakt_ids = []
    for item in trakt_items:
        if 'movie' in item:
            trakt_ids.append(item['movie']['ids']['tmdb'])
        elif 'show' in item:
            trakt_ids.append(item['show']['ids']['tmdb'])

    # Compare the CSV items with the Trakt list
    missing_items = []
    for item in csv_items:
        if item['tmdb_id'] not in trakt_ids:
            missing_items.append(item['tmdb_id'])
    
    # Report missing items
    if missing_items:
        print("\nThe following items were not added to the Trakt list:")
        for tmdb_id in missing_items:
            print(f"TMDb ID: {tmdb_id}, Letterboxd URL: {letterboxd_urls.get(tmdb_id, 'No URL found')}")
        print("\nYou may need to add these items manually, as they do not exist on Trakt.")
    else:
        print("All items were successfully added to the Trakt list.")

# Function to process the CSV file and collect items with their rank
def process_csv_with_rank(file_path):
    data = pd.read_csv(file_path)

    # Collect items with their rank
    items = []
    letterboxd_urls = {}  # Map TMDB ID to Letterboxd URL

    for index, row in data.iterrows():
        tmdb_id = row['TMDB ID']
        media_type = row['Type']
        rank = index + 1  # Assign rank based on CSV order (starting from 1)
        letterboxd_url = row['Letterboxd URL']
        letterboxd_urls[tmdb_id] = letterboxd_url

        items.append({
            'tmdb_id': tmdb_id,
            'type': media_type,
            'rank': rank
        })
    
    return items, letterboxd_urls

# Main function to run the script with the new feature
if __name__ == "__main__":
    # Ask the user if they want to create a new list or update an existing one
    action = input("Would you like to (1) create a new list or (2) update an existing list? Enter 1 or 2: ").strip()

    # Authenticate with Trakt
    access_token, client_id = authenticate_trakt()

    # Process the CSV to get the list of items with their ranks and corresponding Letterboxd URLs
    csv_file_path = 'list.csv'  # Path to the uploaded CSV
    items, letterboxd_urls = process_csv_with_rank(csv_file_path)

    if action == '1':
        # Create a new list on Trakt
        list_slug = create_trakt_list(access_token, client_id)

        # Add the items with their ranks to the Trakt list
        add_status = add_items_to_trakt_list_with_rank(list_slug, items, access_token, client_id)

        # If items were added, retrieve the list from Trakt and reorder the items based on the CSV
        if add_status == 201:
            print("Waiting 5 seconds for Trakt to update the list...")
            time.sleep(5)  # Wait for a few seconds to allow Trakt to update the list
            reorder_trakt_list(list_slug, items, access_token, client_id)
            
            # Retrieve the final list of items after reordering
            trakt_items = retrieve_trakt_list(list_slug, access_token, client_id)
            
            # Compare the CSV items with the final Trakt list
            compare_trakt_and_csv(items, trakt_items, letterboxd_urls)
    
    elif action == '2':
        # Ask the user for the Trakt list URL and extract the slug
        trakt_list_url = input("Enter the Trakt list URL to update: ").strip()
        list_slug = trakt_list_url.split('/')[-1].split('?')[0]  # Extract the list slug without query parameters

        # Remove all items from the existing Trakt list
        remove_all_items_from_trakt_list(list_slug, access_token, client_id)

        # Add the items with their ranks to the Trakt list
        add_status = add_items_to_trakt_list_with_rank(list_slug, items, access_token, client_id)

        # If items were added, retrieve the list from Trakt and reorder the items based on the CSV
        if add_status == 201:
            print("Waiting 5 seconds for Trakt to update the list...")
            time.sleep(5)  # Wait for a few seconds to allow Trakt to update the list
            reorder_trakt_list(list_slug, items, access_token, client_id)

            # Retrieve the final list of items after reordering
            trakt_items = retrieve_trakt_list(list_slug, access_token, client_id)

            # Compare the CSV items with the final Trakt list
            compare_trakt_and_csv(items, trakt_items, letterboxd_urls)

    print("All items have been processed and ordered correctly.")