#!/usr/local/bin/python3

import re
import sys
import os
import json
import datetime
import requests
import asyncio
import asyncpg
import sqlalchemy
from dotenv import load_dotenv
from pprint import pprint

load_dotenv()

api_key = os.environ.get("API_KEY", None)

### postgres stuff ###
dbuser = "postgres"
dbpass = "postgres"
dbhost = "localhost"
dbname = "database"

### API stuff ###

#### league IDs ####
# UEFA CL: 530
# UEFA EL: 514
# PL: 524

#### team IDs ####
# arsenal: 42

def getSquad(teamid, season):
    response = requests.get(f"http://v2.api-football.com/players/squad/{teamid}/{season}", headers={'X-RapidAPI-Key': api_key})
    return response.json()

def getTeam(teamid):
    response = requests.get(f"http://v2.api-football.com/teams/team/{teamid}", headers={'X-RapidAPI-Key': api_key})
    return response.json()

def getFixtures(teamid, leagueid):
    response = requests.get(f"http://v2.api-football.com/fixtures/team/{teamid}/{leagueid}", headers={'X-RapidAPI-Key': api_key})
    return response.json()
 
def getTables(teamid, leagueid):
    response = requests.get(f"http://v2.api-football.com/leagueTable/{leagueid}", headers={'X-RapidAPI-Key': api_key})
    return response.json()


# try:
#     postgresconnection = asyncpg.connect("postgres://{0}:{1}@{2}:5432/{3}".format(dbuser, dbpass, dbhost, dbname))
#     cursor = postgresconnection.cursor()
#     print("Connected to postgres")
# except Exception as e:
#     print(f"{e}")

pprint(getSquad("42","2019-2020"))