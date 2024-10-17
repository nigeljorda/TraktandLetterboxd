import csv
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from concurrent.futures import ThreadPoolExecutor, as_completed
import math

# Prompt the user for the Letterboxd list URL and the number of movies to scrape
list_url = input("Enter the Letterboxd list URL: ")
num_movies = int(input("Enter the number of movies to scrape: "))

# Assuming 72 movies per page
movies_per_page = 72

# Calculate how many pages are required to scrape the specified number of movies
num_pages = math.ceil(num_movies / movies_per_page)

# Set up Selenium to run in headless mode (in the background)
chrome_options = Options()
chrome_options.add_argument("--headless")  # Run in headless mode
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")

# Initialize the headless browser driver
driver = webdriver.Chrome(options=chrome_options)

# Function to extract TMDb info from the detailed movie page
def extract_tmdb_info(movie_url):
    try:
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
        else:
            tmdb_id = None
            media_type = None
        
        return movie_url, tmdb_id, media_type
    except Exception as e:
        return movie_url, None, None

# Open the Letterboxd list URL
driver.get(list_url)

# Wait for the page to load
driver.implicitly_wait(10)

# List to hold all movie URLs in the correct order with their position
movies_with_positions = []

# Scrape movie URLs and their positions from each page
for page_num in range(1, num_pages + 1):
    driver.get(f"{list_url}page/{page_num}/")
    
    # Find all movies on the page using a generalized XPath
    movie_elements = driver.find_elements(By.XPATH, '//ul/li/div[@data-film-link]')
    
    # Extract the data-film-link attribute and the position for each movie
    for idx, movie_element in enumerate(movie_elements):
        movie_url = 'https://letterboxd.com' + movie_element.get_attribute('data-film-link')
        movie_position = (page_num - 1) * len(movie_elements) + (idx + 1)
        movies_with_positions.append((movie_url, movie_position))
        
        # Stop scraping when we've reached the desired number of movies
        if len(movies_with_positions) >= num_movies:
            break

    # Stop if we have already gathered enough movies
    if len(movies_with_positions) >= num_movies:
        break

# Close the browser after fetching the URLs
driver.quit()

# List to hold all movies with their TMDb data
movies_with_tmdb = []

# Use ThreadPoolExecutor for concurrent scraping of TMDb data
with ThreadPoolExecutor(max_workers=10) as executor:
    # Start scraping TMDb data concurrently
    future_to_movie = {executor.submit(extract_tmdb_info, url): (url, position) for url, position in movies_with_positions}
    
    for future in as_completed(future_to_movie):
        movie_url, tmdb_id, media_type = future.result()
        url, position = future_to_movie[future]
        movies_with_tmdb.append({
            'position': position,
            'letterboxd_url': url,
            'tmdb_id': tmdb_id,
            'media_type': media_type
        })

# Sort movies based on their original position
movies_with_tmdb.sort(key=lambda x: x['position'])

# CSV header and file writing
csv_header = ["Position", "Letterboxd URL", "TMDB ID", "Type"]

with open('list.csv', mode='w', newline='') as file:
    writer = csv.DictWriter(file, fieldnames=csv_header)
    writer.writeheader()
    
    # Write each movie's data to the CSV file
    for movie in movies_with_tmdb:
        writer.writerow({
            "Position": movie['position'],
            "Letterboxd URL": movie['letterboxd_url'],
            "TMDB ID": movie['tmdb_id'],
            "Type": movie['media_type']
        })

print(f"Data saved to list.csv with {len(movies_with_tmdb)} movies.")
