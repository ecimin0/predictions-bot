#!/usr/local/bin/python3

import re
import sys
import os
import json
import datetime
import requests
# import asyncio
import psycopg2
# import the new JSON method from psycopg2
from psycopg2.extras import Json
import sqlalchemy
from dotenv import load_dotenv
from pprint import pprint
import argparse

load_dotenv()

api_key = os.environ.get("API_KEY", None)

# Command line arguments #
parser = argparse.ArgumentParser(description="<short summary of script functionality>")
parser.add_argument('--long-option', '-l', metavar='<sample argument>', type=str, help="<notes about sample argument>")
parser.add_argument('--dryrun', '--dry-run', '-d', action='store_true', help='<notes; store_true defaults to False if the option is omitted')
option = parser.parse_args()


### aws postgres stuff
aws_dbuser = "postgres"
aws_dbpass = "2d9t728EAIRhtAcHW3Bw"
aws_dbhost = "predictions-bot-database.cdv2z684ki93.us-east-2.rds.amazonaws.com"
aws_db_ip = "3.15.92.33"
aws_dbname = "predictions-bot-data"

### API stuff ###
#### league IDs 2019-2020 ####
# UEFA CL: 530
# UEFA EL: 514
# PL: 524
# FA Cup: 1063
# League Cup: 957

#### team IDs ####
# arsenal: 42

# team_id = "42"
# pl2019202teams = ["40", "71", "48", "50", "35", "62", "44", "41", "52", "45", "46", "39", "38", "51", "47", "66", "34", "42", "33", "49"]
season = "2019"
pl_league_id = "524"
current_year = datetime.datetime.now().year
prev_year = datetime.datetime.now().year - 1
# print(prev_year)


def getCountries():
    response = requests.get(f"http://v2.api-football.com/countries", headers={'X-RapidAPI-Key': api_key})
    countries = response.json().get("api").get("countries")

    for country in countries:
        try:
            pgcursor.execute("INSERT INTO predictionsbot.countries (country, code, flag) VALUES (%s, %s, %s);", (country.get("country"), country.get("code"), country.get("flag")))
        except (Exception) as e:
            print(f"{e}")
            postgresconnection.rollback()


def getLeagues():
    response = requests.get(f"http://v2.api-football.com/leagues", headers={'X-RapidAPI-Key': api_key})
    leagues = response.json().get("api").get("leagues")
    
    parsed_leagues = []
    for league in leagues:
        delete_keys = [key for key in league if key not in ["league_id", "name", "season", "logo", "country"]]
        for key in delete_keys: 
            del league[key]
        parsed_leagues.append(league)

    # only get leagues for the current season
    # season '2019' is for calendar years 2019-2020
    delete_seasons = [row for row in parsed_leagues if row.get("season") != prev_year]
    for season in delete_seasons:
        parsed_leagues.remove(season)
        
    for league in parsed_leagues:
        try:
            pgcursor.execute("INSERT INTO predictionsbot.leagues (league_id, name, season, logo, country) VALUES (%s, %s, %s, %s, %s);", (league.get("league_id"), league.get("name"), league.get("season"), league.get("logo"), league.get("country")))
        except (Exception) as e:
            print(f"{e}")
            postgresconnection.rollback()


def getTeamsInLeague(league_id):
    response = requests.get(f"http://v2.api-football.com/teams/league/{league_id}", headers={'X-RapidAPI-Key': api_key})
    league_teams = response.json().get("api").get("teams")

    parsed_team_ids = []

    for team in league_teams:
        parsed_team_ids.append(team.get("team_id"))
    
    final_teams = []
    for team_id in parsed_team_ids:
        team_details = requests.get(f"http://v2.api-football.com/teams/team/{team_id}", headers={'X-RapidAPI-Key': api_key})
        team = team_details.json().get("api").get("teams")
        final_teams.append(team)
        # print(team)
    
        for team in final_teams:
            delete_keys = [key for key in team if key not in ["team_id", "name", "logo", "country"]]
            for key in delete_keys:
                team.remove(team)
            final_teams.append(team)
        # print(delete_keys)

    

# def getTeamDetails(team_id):
    # response = requests.get(f"http://v2.api-football.com/teams/team/{team_id}", headers={'X-RapidAPI-Key': api_key})
    # teams = response.json().get("api").get("teams")

    # for team in teams:

    # return response.json()
    # pprint(f"{team}")
        

def getPlayers(team_id, season):
    response = requests.get(f"http://v2.api-football.com/players/squad/{team_id}/{season}", headers={'X-RapidAPI-Key': api_key})
    players = response.json().get("api").get("players")
    parsed_players = []

    for player in players:
        delete_keys = [key for key in player if key not in ["player_name", "firstname", "lastname"]]
        for key in delete_keys: 
            del player[key]
        parsed_players.append(player)

    for player in parsed_players:
        try:
            pgcursor.execute("INSERT INTO predictionsbot.players (season, team_id, player_name, firstname, lastname) VALUES (%s, %s, %s, %s, %s);", (season, team_id, player.get("player_name"), player.get("firstname"), player.get("lastname")))
        except (Exception) as e:    
            print(f"{e}")
            postgresconnection.rollback()


def getFixtures(team_id, league_id):
    response = requests.get(f"http://v2.api-football.com/fixtures/team/{team_id}/{league_id}", headers={'X-RapidAPI-Key': api_key})
    return response.json()


def getTables(team_id, league_id):
    response = requests.get(f"http://v2.api-football.com/leagueTable/{league_id}", headers={'X-RapidAPI-Key': api_key})
    return response.json()


try:
    with psycopg2.connect("postgres://{0}:{1}@{2}:5432/{3}".format(aws_dbuser, aws_dbpass, aws_dbhost, aws_dbname)) as postgresconnection:
        postgresconnection.autocommit = True
        print("Connected to postgres")
        pgcursor = postgresconnection.cursor()
    
    
        # getCountries()
        # getLeagues()
        getTeamsInLeague(524)
        
except Exception as e:
    print(f"{e}")

# players_json = getPlayers(team_id, season)
# pprint(players_json)
