import pandas as pd
import requests
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

def is_available_on_letterboxd(tmdb_id):
    """Check if a movie/show with the given TMDb ID exists on Letterboxd."""
    url = f"https://letterboxd.com/tmdb/{tmdb_id}"
    try:
        response = requests.get(url, timeout=5)
        if "Film not found" in response.text:
            return False, tmdb_id
        return True, tmdb_id
    except requests.RequestException:
        return False, tmdb_id

def check_availability_concurrently(df, max_workers=10):
    """Check availability concurrently for each movie/show in the dataframe."""
    available_list = []
    not_found_list = []
    
    # Use ThreadPoolExecutor for concurrent processing
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(is_available_on_letterboxd, row['tmdbID']): row for _, row in df.iterrows()}
        
        for future in as_completed(futures):
            row = futures[future]
            try:
                available, tmdb_id = future.result()
                if available:
                    available_list.append(row)
                else:
                    not_found_list.append(row)
            except Exception as exc:
                print(f"An error occurred: {exc}")

    # Convert the lists back to dataframes
    available_df = pd.DataFrame(available_list)
    not_found_df = pd.DataFrame(not_found_list)
    
    return available_df, not_found_df

def merge_trakt_files(movies_file_path, shows_file_path, output_file_path, check_availability=False, max_workers=10):
    # Check if the necessary files exist
    if not os.path.exists(movies_file_path) or not os.path.exists(shows_file_path):
        print("Error: Required files are missing!")
        print(f"Please make sure {movies_file_path} and {shows_file_path} are present.")
        print("You need to use traktbackup.py to generate these files.")
        return

    # Load the CSV files
    movies_df = pd.read_csv(movies_file_path)
    shows_df = pd.read_csv(shows_file_path)

    # Select relevant columns from movies
    movies_df = movies_df[['Title', 'Year', 'TMDB ID', 'Rating']].copy()

    # Select relevant columns from shows and map ratings to 1-10 scale for Letterboxd
    shows_df = shows_df[['Title', 'Year', 'TMDB ID', 'Rating']].copy()

    # Rename columns to Letterboxd format
    movies_df.rename(columns={'TMDB ID': 'tmdbID'}, inplace=True)
    shows_df.rename(columns={'TMDB ID': 'tmdbID'}, inplace=True)

    # Ensure ratings are integers only when they are present (leaving NaNs/empty as they are)
    movies_df['Rating10'] = movies_df['Rating'].apply(lambda x: int(x) if pd.notna(x) else "")
    shows_df['Rating10'] = shows_df['Rating'].apply(lambda x: int(x) if pd.notna(x) else "")

    # Merge the two dataframes
    merged_df = pd.concat([movies_df[['Title', 'Year', 'tmdbID', 'Rating10']],
                           shows_df[['Title', 'Year', 'tmdbID', 'Rating10']]],
                          ignore_index=True)

    if check_availability:
        # Check availability of each item on Letterboxd using concurrent threads
        available_df, not_found_df = check_availability_concurrently(merged_df, max_workers=max_workers)
        
        # Save the items not found on Letterboxd to a separate CSV file
        if not not_found_df.empty:
            not_found_file = 'notfoundonletterboxd.csv'
            not_found_df.to_csv(not_found_file, index=False, encoding='utf-8')
            print(f"Some items were not found on Letterboxd: {len(not_found_df)} items.")
            print(f"See {not_found_file} for details.")
        
        # Use only available items for the final CSV
        merged_df = available_df

    # Export to CSV in the Letterboxd format
    merged_df.to_csv(output_file_path, index=False, encoding='utf-8')
    print(f"CSV file successfully created: {output_file_path}")

# Example usage
if __name__ == "__main__":
    # Input file paths
    movies_file = 'trakt_movies_with_ratings.csv'  # Update with actual file path
    shows_file = 'trakt_shows_with_ratings.csv'  # Update with actual file path
    output_file = 'letterboxd_import_ready.csv'  # Update with desired output file path

    # Check if the required files exist
    if not os.path.exists(movies_file) or not os.path.exists(shows_file):
        print(f"Error: Please ensure that {movies_file} and {shows_file} are available.")
        print("Use traktbackup.py to generate these files.")
    else:
        # Ask user if they want to check availability on Letterboxd
        check = input("Do you want to check if each movie/show is available on Letterboxd? (yes/no): ").strip().lower()
        check_availability = check == "yes"

        # Call the function with user choice
        merge_trakt_files(movies_file, shows_file, output_file, check_availability)
