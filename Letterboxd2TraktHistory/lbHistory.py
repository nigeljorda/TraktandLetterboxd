import requests
from bs4 import BeautifulSoup
import csv
import math
from concurrent.futures import ThreadPoolExecutor, as_completed

# Define the header for the output CSV files
csv_file = "watched_movies_tmdb.csv"
watchlist_csv_file = "watchlist_tmdb.csv"
csv_header = ["Letterboxd URL", "TMDB ID", "Type"]

# Function to extract movie URLs and (optional) ratings from the ratings page
def extract_ratings(page_url):
    response = requests.get(page_url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    ratings_data = {}
    
    # Get all rated movie containers (list items)
    movie_items = soup.find_all('li', class_='poster-container')
    
    for li in movie_items:
        lazy_load_div = li.find('div', class_='really-lazy-load')
        if lazy_load_div and lazy_load_div.get('data-target-link'):
            movie_url = "https://letterboxd.com" + lazy_load_div['data-target-link']
            rating_tag = li.find('span', class_='rating')
            if rating_tag:
                # Find the class that contains 'rated-' and extract the rating value
                rating_class = next((cls for cls in rating_tag['class'] if 'rated-' in cls), None)
                if rating_class:
                    # Convert rating by stripping 'rated-' and dividing by 2 to map to the 10-point scale
                    letterboxd_rating = float(rating_class.replace('rated-', '')) / 2
                    ratings_data[movie_url] = letterboxd_rating
    
    return ratings_data


# Function to extract movie URLs from the main list page
def extract_movie_urls(page_url):
    response = requests.get(page_url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    movie_data = []
    
    # Get all movie containers (list items)
    movie_items = soup.find_all('li', class_='poster-container')
    
    for li in movie_items:
        lazy_load_div = li.find('div', class_='really-lazy-load')
        
        if lazy_load_div and lazy_load_div.get('data-target-link'):
            movie_url = "https://letterboxd.com" + lazy_load_div['data-target-link']
            movie_data.append(movie_url)
    
    return movie_data

# Function to extract TMDb info from the detailed movie page
def extract_tmdb_info(movie_url):
    response = requests.get(movie_url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find the TMDb button by class and text content
    tmdb_button = soup.find('a', class_='micro-button track-event', string='TMDb')
    
    if tmdb_button:
        tmdb_link = tmdb_button.get('href')
        
        # Extract TMDB ID and type (movie or tv)
        if "/movie/" in tmdb_link:
            tmdb_id = tmdb_link.split("/movie/")[1].strip("/")
            media_type = "movie"
        elif "/tv/" in tmdb_link:
            tmdb_id = tmdb_link.split("/tv/")[1].strip("/")
            media_type = "show"
        else:
            tmdb_id = None
            media_type = None
        
        return movie_url, tmdb_id, media_type
    else:
        return movie_url, None, None

# Function to find the last page number by parsing pagination
def get_last_page(base_url):
    first_page_url = base_url + "/page/1/"
    response = requests.get(first_page_url)
    soup = BeautifulSoup(response.text, 'html.parser')

    # Find pagination container
    pagination = soup.find('div', class_='paginate-pages')
    
    if pagination:
        # Find the last page number by looking for the last link in the pagination
        last_page_link = pagination.find_all('a')[-1].get('href')
        last_page_number = int(last_page_link.split('/page/')[-1].strip('/'))
    else:
        # If no pagination is found, we assume there's only one page
        last_page_number = 1

    return last_page_number

# Function to crawl multiple pages using ThreadPoolExecutor
def crawl_movies(last_page, base_url):
    all_movie_urls = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = []
        for page in range(1, last_page + 1):
            page_url = base_url + f"/page/{page}/"
            futures.append(executor.submit(extract_movie_urls, page_url))
        
        # Progress feedback
        print("- Extracting movies from pages")
        
        # Collect the results as they are completed
        for future in as_completed(futures):
            all_movie_urls.extend(future.result())
    
    return all_movie_urls

# Function to crawl detailed movie pages for TMDb links
def crawl_detailed_movie_pages(movie_urls):
    all_movie_data = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = []
        for movie_url in movie_urls:
            futures.append(executor.submit(extract_tmdb_info, movie_url))
        
        # Progress feedback
        print("- Gathering TMDB Ids")
        
        # Collect the results as they are completed
        for future in as_completed(futures):
            all_movie_data.append(future.result())
    
    return all_movie_data

# Function to save the extracted data to a CSV file
def save_to_csv(movie_data, ratings_data=None, csv_file=csv_file):
    if ratings_data:
        csv_header.append("Rating")
    with open(csv_file, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(csv_header)
        for movie in movie_data:
            row = list(movie)
            if ratings_data and movie[0] in ratings_data:
                # Ensure the rating is a whole number for Trakt (rounded after doubling)
                trakt_rating = math.ceil(ratings_data[movie[0]] * 2)
                row.append(trakt_rating)  # Add the Trakt-compliant rating
            writer.writerow(row)
    
    # Feedback after saving
    print(f"- Movies/shows saved to {csv_file}")

# Function to get the Letterboxd username and validate the input URL
def get_letterboxd_url():
    while True:
        username = input("Enter your Letterboxd username: ").strip()
        base_url = f"https://letterboxd.com/{username}/films"
        
        # Validate the URL by trying to access the first page
        try:
            response = requests.get(base_url)
            if response.status_code == 200:
                return base_url, username
            else:
                print(f"Invalid username or the page doesn't exist. Please try again.")
        except requests.RequestException:
            print("Error accessing the page. Please check your internet connection and try again.")

# Function to crawl the watchlist
def crawl_watchlist(username):
    watchlist_url = f"https://letterboxd.com/{username}/watchlist/"
    last_page = get_last_page(watchlist_url)
    watchlist_movies = crawl_movies(last_page, watchlist_url)  # Reusing the function to scrape watchlist
    return watchlist_movies

# Main function to run the script
if __name__ == "__main__":
    # Get the user's Letterboxd URL and username
    base_url, username = get_letterboxd_url()
    
    # Ask if the user wants to scrape ratings
    scrape_ratings = input("Do you want to scrape ratings? (yes/no): ").strip().lower() == "yes"
    
    # Ask if the user wants to scrape their watchlist
    scrape_watchlist = input("Do you want to scrape your watchlist? (yes/no): ").strip().lower() == "yes"

    # Find the last page number for watched movies
    last_page = get_last_page(base_url)
    
    # Crawl all pages to collect movie URLs
    movie_urls = crawl_movies(last_page, base_url)
    
    # Crawl detailed movie pages to extract TMDb links
    movie_data = crawl_detailed_movie_pages(movie_urls)

    ratings_data = None
    if scrape_ratings:
        # If ratings scraping is selected, scrape from the ratings page
        ratings_url = f"https://letterboxd.com/{username}/films/by/entry-rating/"
        ratings_data = {}
        last_ratings_page = get_last_page(ratings_url)
        for page in range(1, last_ratings_page + 1):
            page_url = ratings_url + f"page/{page}/"
            ratings_data.update(extract_ratings(page_url))
    
    # Optionally crawl the watchlist
    if scrape_watchlist:
        watchlist_urls = crawl_watchlist(username)
        watchlist_data = crawl_detailed_movie_pages(watchlist_urls)
        # Save the watchlist to a separate CSV
        save_to_csv(watchlist_data, csv_file=watchlist_csv_file)

    # Save the watched movies data to CSV
    save_to_csv(movie_data, ratings_data)

    print("Script finished.")
