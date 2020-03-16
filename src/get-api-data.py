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

team_id = "42"
season = "2019-2020"
leagueid = "524"


# execute("INSERT INTO players (season, team_id, player_name, firstname, lastname) VALUE (%s, %s, %s, %s, %s)", (season, team_id, player_name, firstname, lastname))

def getPlayers(team_id, season):
    response = requests.get(f"http://v2.api-football.com/players/squad/{team_id}/{season}", headers={'X-RapidAPI-Key': api_key})
    # return response.json()
    players = response.json().get("api").get("players")
    parsed_players = []

    for player in players:
        delete_keys = [key for key in player if key not in ["player_name", "firstname", "lastname"]]
        for key in delete_keys: 
            del player[key]
        # print(player)
        parsed_players.append(player)
    # print(parsed_players[0])

    for player in parsed_players:
        try:
            pgcursor.execute("INSERT INTO predictionsbot.players (season, team_id, player_name, firstname, lastname) VALUES (%s, %s, %s, %s, %s);", (season, team_id, player.get("player_name"), player.get("firstname"), player.get("lastname")))
        except Exception as e:
            print(f"{e}")

    # return players


def getTeam(team_id):
    response = requests.get(f"http://v2.api-football.com/teams/team/{team_id}", headers={'X-RapidAPI-Key': api_key})
    return response.json()



def getFixtures(team_id, leagueid):
    response = requests.get(f"http://v2.api-football.com/fixtures/team/{team_id}/{leagueid}", headers={'X-RapidAPI-Key': api_key})
    return response.json()



def getTables(team_id, leagueid):
    response = requests.get(f"http://v2.api-football.com/leagueTable/{leagueid}", headers={'X-RapidAPI-Key': api_key})
    return response.json()


# def dbInsert(json):
#     # create a nested list of the records' values
#     values = [list(x.values()) for x in players]

#     # get the column names
#     columns = [list(x.keys()) for x in record_list][0]

#     # value string for the SQL string
#     values_str = ""

#     # enumerate over the records' values
#     for i, record in enumerate(values):

#         # declare empty list for values
#         val_list = []
    
#         # append each value to a new list of values
#         for v, val in enumerate(record):
#             if type(val) == str:
#                 val = str(Json(val)).replace('"', '')
#             val_list += [ str(val) ]

#         # put parenthesis around each record string
#         values_str += "(" + ', '.join( val_list ) + "),\n"

#     # remove the last comma and end SQL with a semicolon
#     values_str = values_str[:-2] + ";"

#     # concatenate the SQL string
#     table_name = "json_data"
#     sql_string = "INSERT INTO %s (%s)\nVALUES %s" % (table_name, ', '.join(columns), values_str)






try:
    postgresconnection = psycopg2.connect("postgres://{0}:{1}@{2}:5432/{3}".format(aws_dbuser, aws_dbpass, aws_dbhost, aws_dbname))
    print("Connected to postgres")
    pgcursor = postgresconnection.cursor()
    getPlayers(team_id, season)
except Exception as e:
    print(f"{e}")

# players_json = getPlayers(team_id, season)
# pprint(players_json)

