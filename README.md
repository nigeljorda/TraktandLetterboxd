# traktscripts

## Scripts to make your life easier on Trakt.tv and Letterboxd.com

This repository provides various Python scripts to interact with Letterboxd and Trakt.tv to manage your watched movie and show data. Below is an overview of what each script does and how you can use them.

## Scripts

### Trakt

- **traktHistory**: Import watched movies from Letterboxd into Trakt. **First use Lbhistory to get your watched movies from Letterboxd**
- **traktList**: Import a Letterboxd list into Trakt. **First use lbList to get your movies from a custom list**
- **traktDeleter**: Delete all watched entries on your Trakt account.
- **traktBackup**: Backup all your watched data from your Trakt account.
- **traktImporter**: Import a previously backed-up Trakt data file into your Trakt account. **Only works with backups done by traktBackup.py**
- **trakt2Letterboxd**: Convert Traktbackup .csv files to a .csv file that can be imported on Letterboxd. **First use traktBackup.py to convert your Trakt backup to work with Letterboxd import**
- **traktMarker**: Mark every episode as watched until a specific episode.

### Letterboxd
- **lbhHistory**: Export your watched movies from Letterboxd.
- **lbList**: Export a Letterboxd list into a `.csv` format.
- **letterboxdCompare**: Compare what User 1 has watched but User 2 hasn't watched.

## Installation

Trakt.tv API Setup

To use the scripts that interact with Trakt.tv, you will need to set up an API application on Trakt.tv to obtain a Client ID and Client Secret.

Steps to Set Up Trakt.tv API:
Go to Trakt.tv Applications.
Click on Create New Application.
Fill in the necessary details such as:
Application Name: Give your app a name (e.g., "Movie Manager").
Redirect URI: If you don't have a specific URI, use urn:ietf:wg:oauth:2.0:oob.
Click Save.
After creation, you will be provided with a Client ID and a Client Secret.
You need to include this Client ID and Client Secret in the scripts that interact with Trakt.tv. These values are necessary for authentication when interacting with Trakt's API.

Before using any of the scripts, make sure to install the required dependencies by running the following command:

```bash
pip3 install beautifulsoup4 pandas requests
