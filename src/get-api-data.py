#!/usr/local/bin/python3

import re
import sys
import os
import json
import datetime
import requests
# import asyncio
import psycopg2
from psycopg2.extras import Json # import the new JSON method from psycopg2
import sqlalchemy
from dotenv import load_dotenv
from pprint import pprint
import argparse



def getCountries():
    print("generating countries")
    response = requests.get(f"http://v2.api-football.com/countries", headers={'X-RapidAPI-Key': api_key})
    countries = response.json().get("api").get("countries")

    for country in countries:
        try:
            pgcursor.execute("INSERT INTO predictionsbot.countries (country, code, flag) VALUES (%s, %s, %s);", (country.get("country"), country.get("code"), country.get("flag")))
        except (Exception) as e:
            print(f"{e}")
            postgresconnection.rollback()
    print("done\n")


def getLeagues(season):
    if not season:
        print("cannot get leagues; re-run with --season <YYYY>")
        sys.exit(1)

    print(f"generating leagues for season {season}")

    response = requests.get(f"http://v2.api-football.com/leagues", headers={'X-RapidAPI-Key': api_key})
    leagues = response.json().get("api").get("leagues")
    
    parsed_leagues = []
    for league in leagues:
        delete_keys = [key for key in league if key not in ["league_id", "name", "season", "logo", "country", "is_current"]]
        for key in delete_keys: 
            del league[key]
        parsed_leagues.append(league)

    # only get leagues for the current season
    # season '2019' is for calendar years 2019-2020
    delete_seasons = [row for row in parsed_leagues if row.get("is_current") != 1]
    # delete_seasons = [row for row in parsed_leagues if row.get("season") != prev_year]
    for season in delete_seasons:
        parsed_leagues.remove(season)
        

    for league in parsed_leagues:
        try:
            pgcursor.execute("INSERT INTO predictionsbot.leagues (league_id, name, season, logo, country) VALUES (%s, %s, %s, %s, %s);", (league.get("league_id"), league.get("name"), league.get("season"), league.get("logo"), league.get("country")))
        except (Exception) as e:
            print(f"{e}")
            postgresconnection.rollback()
    print("done\n")


def generateTeamIDList(league_id):
    if not league:
        print("No team IDs generated. Pass in a --league <league_id>")
        sys.exit(1)

    print(f"generating team IDs in league {league}")
    response = requests.get(f"http://v2.api-football.com/teams/league/{league_id}", headers={'X-RapidAPI-Key': api_key})
    league_teams = response.json().get("api").get("teams")

    for team in league_teams:
        team_ids_list.append(team.get("team_id"))
    print(team_ids_list)
    print("done\n")


def getTeams(league):
    parsed_teams = []

    if not team_ids_list:
        print("No team IDs generated. Pass in --league <league_id> \nand make sure generateTeamIDList function is called")
        sys.exit(1)

    print(f"generating teams in league {league}")
    for team_id in team_ids_list:
        response = requests.get(f"http://v2.api-football.com/teams/team/{team_id}", headers={'X-RapidAPI-Key': api_key})
        teams = response.json().get("api").get("teams")

        for team in teams:
            delete_keys = [key for key in team if key not in ["team_id", "name", "logo", "country"]]

        for key in delete_keys:
            del team[key]
        parsed_teams.append(team)

    for team in parsed_teams:
        try:
            pgcursor.execute("INSERT INTO predictionsbot.teams (team_id, name, logo, country) VALUES (%s, %s, %s, %s);", (team.get("team_id"), team.get("name"), team.get("logo"), team.get("country")))
        except (Exception) as e:
            print(f"{e}")
            postgresconnection.rollback()
    print("done\n")


def getPlayers(season, full_season, league):
    teams = {}

    if not team_ids_list or not season:
        print("no players generated. make sure generateTeamIDList function is active and --season <YYYY> was passed")
        sys.exit(1)

    print(f"generating players in league {league} for season {full_season}")
    for team_id in team_ids_list:
        response = requests.get(f"http://v2.api-football.com/players/squad/{team_id}/{full_season}", headers={'X-RapidAPI-Key': api_key})
        players = response.json().get("api").get("players")
        teams[team_id] = players
    
    for team, player_array in teams.items():
        for player in player_array:
            delete_keys = [key for key in player if key not in ["player_name", "firstname", "lastname"]]
            for key in delete_keys: 
                del player[key]
    for team, player_array in teams.items():
        for player in player_array:
            try:
                pgcursor.execute("INSERT INTO predictionsbot.players (season, team_id, player_name, firstname, lastname) VALUES (%s, %s, %s, %s, %s);", (season, team, player.get("player_name"), player.get("firstname"), player.get("lastname")))
            except (Exception) as e:    
                print(f"{e}")
                postgresconnection.rollback()
    print("done\n")
        

def getFixtures(league_id):
    parsed_fixtures = []
    
    if not league:
        print("No team IDs generated. Pass in a --league <league_id>")
        sys.exit(1)

    print(f"generating fixtures in league {league}")
    response = requests.get(f"http://v2.api-football.com/fixtures/league/{league_id}", headers={'X-RapidAPI-Key': api_key})
    fixtures = response.json().get("api").get("fixtures")

    for match in fixtures:
        home = match.get("homeTeam").get("team_id")
        away = match.get("awayTeam").get("team_id")

        delete_keys = [key for key in match if key not in ["fixture_id", "league_id", "event_date", "goalsHomeTeam", "goalsAwayTeam"]]
    
        for key in delete_keys:
            del match[key]
        
        match["home"] = home
        match["away"] = away

        parsed_fixtures.append(match)
    
    for fixture in parsed_fixtures:
        # todo make this update fixtures if it exists
        # fixture_exists = pgcursor.execute("SELECT * FROM predictionsbot.fixtures WHERE fixture_id = $1", fixture.get("fixture_id"))
        try:
            # if fixture_exists:
                # pgcursor.execute("UPDATE predictionsbot.fixtures SET (home, away, fixture_id, league_id, event_date, goals_home, goals_away) WHERE fixture_id = $1 VALUES (%s, %s, %s, %s, %s, %s, %s);", (fixture.get('home'), fixture.get('away'), fixture.get('fixture_id'), league_id, fixture.get('event_date'), fixture.get('goalsHomeTeam'), fixture.get('goalsAwayTeam')))
            # else: 
            pgcursor.execute("INSERT INTO predictionsbot.fixtures (home, away, fixture_id, league_id, event_date, goals_home, goals_away) VALUES (%s, %s, %s, %s, %s, %s, %s);", (fixture.get('home'), fixture.get('away'), fixture.get('fixture_id'), league_id, fixture.get('event_date'), fixture.get('goalsHomeTeam'), fixture.get('goalsAwayTeam'))) 
        except (Exception) as e:    
            print(f"{e}")
            postgresconnection.rollback()
    print("done\n")


def getStandings(league_id):
    parsed_standings = []

    if not league:
        print("No team IDs generated. Pass in a --league <league_id>")
        sys.exit(1)

    print(f"generating standings in league {league}")
    response = requests.get(f"http://v2.api-football.com/leagueTable/{league_id}", headers={'X-RapidAPI-Key': api_key})
    standings = response.json().get("api").get("standings")
    
    for rank in standings[0]:
        played = rank.get("all").get("matchsPlayed")
        win = rank.get("all").get("win")
        draw = rank.get("all").get("draw")
        lose = rank.get("all").get("lose")
        gf = rank.get("all").get("goalsFor")
        ga = rank.get("all").get("goalsAgainst")

        delete_keys = [key for key in rank if key not in ["rank", "team_id", "teamName", "goalsDiff", "points"]]
        
        for key in delete_keys:
            del rank[key]

        rank["played"] = played
        rank["win"] = win
        rank["draw"] = draw
        rank["loss"] = lose
        rank["goals_for"] = gf
        rank["goals_against"] = ga
        parsed_standings.append(rank)

    for team in parsed_standings:
        try:
            pgcursor.execute("INSERT INTO predictionsbot.standings (rank, points, team, played, win, draw, loss, goals_for, goals_against, goal_diff, team_id, league_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);", (team.get('rank'), team.get('points'), team.get('teamName'), team.get('played'), team.get('win'), team.get('draw'), team.get('loss'), team.get('goals_for'), team.get('goals_against'), team.get('goalsDiff'), team.get('team_id'), league_id))
        except (Exception) as e:    
            print(f"{e}")
            postgresconnection.rollback()
    print("done\n")


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
aws_dbpass = os.environ.get("AWS_DBPASS", None)
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


if option.season:
    season_YYYY = int(season) + 1
    full_season = f"{season}-{season_YYYY}"

current_year = datetime.datetime.now().year
prev_year = current_year - 1
next_year = current_year + 1 


try:
    with psycopg2.connect("postgres://{0}:{1}@{2}:5432/{3}".format(aws_dbuser, aws_dbpass, aws_dbhost, aws_dbname)) as postgresconnection:
        postgresconnection.autocommit = True
        pgcursor = postgresconnection.cursor()
        print("connected to postgres\n")
    
        generateTeamIDList(league)

        # getCountries()

        # getLeagues(season)
        
        getTeams(league)
    
        # getPlayers(season, full_season, league)
    
        # getFixtures(league)
    
        # getStandings(league)

except Exception as e:
    print(f"{e}")

# todo cron this script for getFixtures()
# todo make args for function calls