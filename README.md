# traktscripts

# Movie and Show Data Management Scripts

This repository provides various Python scripts to interact with Letterboxd and Trakt.tv to manage your watched movie and show data. Below is an overview of what each script does and how you can use them.

## Scripts

- **Lbhistory**: Export your watched movies from Letterboxd.
- **Trakthistory**: Import watched movies from Letterboxd into Trakt.
- **Lblist**: Export a Letterboxd list into a `.csv` format.
- **Traktlist**: Import a Letterboxd list into Trakt.
- **Traktdeleter**: Delete all watched entries on your Trakt account.
- **Traktbackup**: Backup all your watched data from your Trakt account.
- **Traktimporter**: Import a previously backed-up Trakt data file into your Trakt account.

## Installation

Before using any of the scripts, make sure to install the required dependencies by running the following command:

```bash
pip install beautifulsoup4 pandas requests

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
