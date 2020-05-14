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
parser = argparse.ArgumentParser(description="Populate database with football API data for a given season", formatter_class=argparse.RawTextHelpFormatter, add_help=False)
parser.add_argument('-h ', '--help', action='help', help="show this help message and exit\n\n")
parser.add_argument('--season', help="SEASON is a string in YYYY format\n'2003' identifies the 2003-2004 season\n\n")
parser.add_argument('--league', help="LEAGUE is a league_id from the API\n'524' identifies the the English Premier League 2019-2020\n\n")
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

team_ids_list = []

season = option.season
league = option.league

season_YYYY = int(season) + 1
full_season = f"{season}-{season_YYYY}"

current_year = datetime.datetime.now().year
prev_year = current_year - 1
next_year = current_year + 1 


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


def generateTeamIDList(league_id):
    response = requests.get(f"http://v2.api-football.com/teams/league/{league_id}", headers={'X-RapidAPI-Key': api_key})
    league_teams = response.json().get("api").get("teams")

    for team in league_teams:
        team_ids_list.append(team.get("team_id"))
    
    print(team_ids_list)


def getTeamsInLeague():
    # parsed_teams = []
    final_teams = []
    for team_id in team_ids_list:
        response = requests.get(f"http://v2.api-football.com/teams/team/{team_id}", headers={'X-RapidAPI-Key': api_key})
        teams = response.json().get("api").get("teams")[0]
        # parsed_teams.append(team)

    for team in teams:
        delete_keys = [key for key in team if key not in ["team_id", "name", "logo", "country"]]

        for key in delete_keys:
            del team[key]
        final_teams.append(team)
        
    for team in final_teams:
        try:
            pgcursor.execute("INSERT INTO predictionsbot.teams (team_id, name, logo, country) VALUES (%s, %s, %s, %s);", (team.get("team_id"), team.get("name"), team.get("logo"), team.get("country")))
        except (Exception) as e:
            print(f"{e}")
            postgresconnection.rollback()

        
# def getPlayers():
#     players_on_teams = []
#     final_players = []
#     for team_id in team_ids_list:
#         response = requests.get(f"http://v2.api-football.com/players/squad/{team_id}/{full_season}", headers={'X-RapidAPI-Key': api_key})
#         players = response.json().get("api").get("players")
#         players_on_teams.append(players)
        
#     for team in players_on_teams:
#         for player in team:
#             delete_keys = [key for key in player if key not in ["player_name", "firstname", "lastname"]]
#             for key in delete_keys: 
#                 del player[key]
#             final_players.append(player)
    
#     # print(final_players)

#     for player in final_players:
#         try:
#             pgcursor.execute("INSERT INTO predictionsbot.players (season, team_id, player_name, firstname, lastname) VALUES (%s, %s, %s, %s, %s);", (full_season, team_id, player.get("player_name"), player.get("firstname"), player.get("lastname")))
#         except (Exception) as e:    
#             print(f"{e}")
#             postgresconnection.rollback()


def getPlayers():
    all_players = []
    final_players = []
    teams = {}
    for team_id in team_ids_list:
        response = requests.get(f"http://v2.api-football.com/players/squad/{team_id}/{full_season}", headers={'X-RapidAPI-Key': api_key})
        players = response.json().get("api").get("players")
        teams[team_id] = players
        # all_players.append(players)
    # for player in all_players:
    for team, player_array in teams.items():
        for player in player_array:
            delete_keys = [key for key in player if key not in ["player_name", "firstname", "lastname"]]
            for key in delete_keys: 
                del player[key]
    for team, player_array in teams.items():
        # print(f"TEAMID: {team}")
        # print("Players: ")
        # pprint(player_array)
        for player in player_array:
            try:
                pgcursor.execute("INSERT INTO predictionsbot.players (season, team_id, player_name, firstname, lastname) VALUES (%s, %s, %s, %s, %s);", (season, team, player.get("player_name"), player.get("firstname"), player.get("lastname")))
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
    
    
        generateTeamIDList(league)
        # getCountries()
        # getLeagues()
        # getTeamsInLeague()
        getPlayers()
        
except Exception as e:
    print(f"{e}")


# pprint(players_json)
