#!/usr/local/bin/python3

import aiohttp
import discord
import re
import sys
import os
import json
import logging 
import asyncio
import asyncpg
import pytz
import argparse
import random
import string
import structlog

from tabulate import tabulate
from pythonjsonlogger import jsonlogger
from discord.ext import commands, tasks
from discord.ext.commands import CommandNotFound, CommandInvokeError
from datetime import timedelta, datetime
from dotenv import load_dotenv

# bot token, API key, other stuff 
load_dotenv()

def createLogger(level):
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(jsonlogger.JsonFormatter(fmt='%(asctime)s %(levelname)s %(name)s %(message)s'))
    asyncio_logger = logging.getLogger('asyncio')
    asyncio_logger.setLevel(os.environ.get("ASYNCIO_LOGLEVEL", "INFO"))
    asyncio_logger.addHandler(handler)
    discord_logger = logging.getLogger('discord')
    discord_logger.setLevel(os.environ.get("DISCORD_LOGLEVEL", "INFO"))
    discord_logger.addHandler(handler)

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    logger = structlog.getLogger("predictions-bot")
    handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(handler)
    logger.setLevel(level)
    return logger

logger = createLogger(os.environ.get("LOGLEVEL", "INFO"))

#todo make script accept stuff like nicknames as a config file
# initialize db on "first launch" by adding initial team name as nickname to teams table, by league of main team (42 == arsenal == premier league == 2790)
# todo ask team, country, league, setup config in database?
# todo config in db/vs file 

# 2020-2021 season league IDs
league_dict = {
    "premier_league": 2790,
    "champions_league": 2771,
    "europa_league": 2777,
    "fa_cup": 2791,
    "league_cup": 2781
}

status_lookup = {
    "TBD": False,
    "NS": False,
    "1H": False,
    "HT": False,
    "2H": False,
    "ET": False,
    "P": False,
    "FT": True,
    "AET": True,
    "PEN": True,
    "BT": False,
    "SUSP": False,
    "INT": False,
    "PST": False,
    "CANC": False,
    "ABD": False,
    "AWD": True,
    "WO": True
}

# TBD : Time To Be Defined
# NS : Not Started
# 1H : First Half, Kick Off
# HT : Halftime
# 2H : Second Half, 2nd Half Started
# ET : Extra Time
# P : Penalty In Progress
# FT : Match Finished
# AET : Match Finished After Extra Time
# PEN : Match Finished After Penalty
# BT : Break Time (in Extra Time)
# SUSP : Match Suspended
# INT : Match Interrupted
# PST : Match Postponed
# CANC : Match Cancelled
# ABD : Match Abandoned
# AWD : Technical Loss
# WO : WalkOver

utc = pytz.timezone("UTC")

testing_mode = os.environ.get("TESTING", False)
if testing_mode:
    channel = 'test-predictions-bot'
    logger.info("Starting in testing mode", channel=channel)
else:
    channel = 'prediction-league'
    logger.info("Starting in production mode", channel=channel)

admin_ids = [
    260908554758782977, 
    249231078303203329
]

aws_dbuser = "postgres"
aws_dbpass = os.environ.get("AWS_DBPASS", None)
aws_dbhost = "predictions-bot-database.cdv2z684ki93.us-east-2.rds.amazonaws.com"
aws_db_ip = "3.15.92.33"

api_key = os.environ.get("API_KEY", None)

if testing_mode:
    aws_dbname = "predictions-bot-data-test"
else:
    aws_dbname = "predictions-bot-data"

# API team id to use as 'main' team
main_team = 42 # arsenal
main_league = 2790

time_format = "%m/%d/%Y, %H:%M:%S %Z"

match_select = f"home, away, fixture_id, league_id, event_date, goals_home, goals_away, new_date, (SELECT name FROM predictionsbot.teams t WHERE t.team_id = f.home) AS home_name, (SELECT name FROM predictionsbot.teams t WHERE t.team_id = f.away) AS away_name, (SELECT name FROM predictionsbot.leagues t WHERE t.league_id = f.league_id) as league_name, CASE WHEN away = 42 THEN home ELSE away END as opponent, (SELECT name FROM predictionsbot.teams t WHERE t.team_id = (CASE WHEN f.away = 42 THEN f.home ELSE f.away END)) as opponent_name, CASE WHEN away = {main_team} THEN 'away' ELSE 'home' END as home_or_away, scorable"

token = os.environ.get("TOKEN", None)
if not token:
    logger.error("Missing Discord bot token! Set TOKEN env value.")
    sys.exit(1)

last_run = {}

# bot only responds to commands prepended with {prefix}
prefix = "+"

# cleaner output of help function(s)
help_function = commands.DefaultHelpCommand(no_category="Available Commands", indent=4, dm_help=True)
bot = commands.Bot(prefix, help_command=help_function)
bot.remove_command('help')

class PleaseTellMeAboutIt(Exception):
    pass

class IsNotAdmin(commands.CheckFailure):
    pass

class RateLimit(commands.CheckFailure):
    pass    

async def getPlayerId(dbconn, userInput):
    player = await dbconn.fetchrow("SELECT player_id FROM predictionsbot.players WHERE $1 = ANY(nicknames) AND team_id = $2;", userInput.lower(), main_team)
    if not player:
        raise Exception(f"no player named {userInput}")
    return player.get("player_id")

async def getTeamId(dbconn, userInput):
    player = await dbconn.fetchrow("SELECT team_id FROM predictionsbot.teams WHERE $1 = ANY(nicknames);", userInput.lower())
    if not player:
        raise Exception(f"no team named {userInput}")
    return player.get("team_id")

def randomAlphanumericString(length):
    letters_and_digits = string.ascii_letters + string.digits
    result_str = ''.join((random.choice(letters_and_digits) for i in range(length)))
    return result_str

def rateLimit(seconds, name):
    async def predicate(ctx):
        global last_run
        if name not in last_run:
            last_run[name] = datetime.utcnow()
            return True
        else:
            seconds_since_last_run = (datetime.utcnow() - last_run[name]).total_seconds()
            if seconds_since_last_run > seconds:
                last_run[name] = datetime.utcnow()
                return True
            else:
                raise RateLimit(f"+{name} command is under a rate limit. May run again in {seconds - seconds_since_last_run:.0f} seconds.")
    return commands.check(predicate)

async def isAdmin(ctx):
    if ctx.message.author.id in admin_ids:
        return True
    else:
        raise IsNotAdmin(f"User {ctx.message.author.name} is not an admin and cannot use this function.")

async def getUserTimezone(dbconn, user):
    user_tz = await dbconn.fetchrow(f"SELECT tz FROM predictionsbot.users WHERE user_id = $1;", user)
    tz = pytz.timezone(user_tz.get("tz", "UTC"))
    return tz 
    
def prepareTimestamp(timestamp, tz, str=True):
    dt = utc.localize(timestamp)
    dt = timestamp.astimezone(tz)
    if str:
        return dt.strftime(time_format)
    else:
        return dt

# use something like these functions to get data from db
## bot.pg_conn.fetch("<sql>")

# nextMatches returns array of fixtures (even for one)
async def nextMatches(dbconn, count=1):
    matches = await dbconn.fetch(f"SELECT {match_select} FROM predictionsbot.fixtures f WHERE event_date > now() AND (home = {main_team} OR away = {main_team}) ORDER BY event_date LIMIT $1;", count)
    return matches

# nextMatch returns record (no array)
async def nextMatch(dbconn):
    match = await dbconn.fetchrow(f"SELECT {match_select} FROM predictionsbot.fixtures f WHERE event_date > now() AND (home = {main_team} OR away = {main_team}) ORDER BY event_date LIMIT 1;")
    return match

# array of completed fixtures records
async def completedMatches(dbconn, count=1, offset=0):
    matches = await dbconn.fetch(f"SELECT {match_select} FROM predictionsbot.fixtures f WHERE event_date + interval '2 hour' < now() AND (home = {main_team} OR away = {main_team}) ORDER BY event_date DESC LIMIT $1 OFFSET $2;", count, offset)
    return matches

async def formatMatch(dbconn, match, user):
    tz = await getUserTimezone(dbconn, user)
    match_time = prepareTimestamp(match.get('event_date'), tz)

    time_until_match = (match.get('event_date') - datetime.now()).total_seconds()

    return f"{match.get('league_name')}\n{match.get('home_name')} vs {match.get('away_name')}\n{match_time}\n*match starts in {time_until_match // 86400:.0f} days, {time_until_match // 3600 %24:.0f} hours, and {time_until_match // 60 %60:.0f} minutes*\n\n" 

async def connectToDB():
    try:
        bot.pg_conn = await asyncpg.create_pool(user=aws_dbuser, password=aws_dbpass, database=aws_dbname, host=aws_db_ip)
        logger.info("Connected to postgres")
        bot.pg_conn_ready = True
    except Exception:
        logger.exception("Error connecting to db")
        sys.exit(1)

async def getAdminDiscordId():
    try:
        bot.admin_id = await bot.fetch_user("249231078303203329")
        if not testing_mode:
            await bot.admin_id.send(f"found admin ID {bot.admin_id}")
    except Exception as e:
        logger.error(f"{e}")

async def getUserPredictions(dbconn, user_id):
    '''
    Return the last 10 predictions by user
    '''
    predictions = await dbconn.fetch("SELECT * FROM predictionsbot.predictions WHERE user_id = $1 ORDER BY timestamp DESC LIMIT 10;", user_id)
    return predictions

async def getMatch(dbconn, fixture_id):
    match = await dbconn.fetchrow(f"SELECT {match_select} FROM predictionsbot.fixtures f WHERE fixture_id = $1;", fixture_id)
    return match

async def getRandomTeam(dbconn):
    team = await dbconn.fetchrow("SELECT * FROM predictionsbot.teams WHERE team_id != 42 ORDER BY random() LIMIT 1;")
    return team.get("name")

async def checkUserExists(dbconn, user_id, ctx):
    user = await dbconn.fetch("SELECT * FROM predictionsbot.users WHERE user_id = $1", user_id)

    if not user:
        async with bot.pg_conn.acquire() as connection:
            async with connection.transaction():
                try:
                    await connection.execute("INSERT INTO predictionsbot.users (user_id, tz) VALUES ($1, $2);", user_id, "UTC")
                except Exception as e:
                    await bot.admin_id.send(f"Error inserting user {user_id} into database:\n{e}")
                    logger.error(f"Error inserting user {user_id} into database: {e}")
        # return False
        # await ctx.send(f"{ctx.message.author.mention}\n\nHello, this is the Arsenal Discord Predictions League\n\nType `+rules` to see the rules for the league\n\nEnter `+help` for a help message")
    else:
        return True

# Convert an integer into its ordinal representation::
# https://stackoverflow.com/questions/9647202/ordinal-numbers-replacement
def makeOrdinal(n):
    n = int(n)
    suffix = ['th', 'st', 'nd', 'rd', 'th'][min(n % 10, 4)]
    if 11 <= (n % 100) <= 13:
        suffix = 'th'
    return str(n) + suffix

# on_ready = when bot is connected to server
@bot.event
async def on_ready(): 
    await connectToDB()
    await getAdminDiscordId()
    logger.info(f'connected to {channel} within {[ guild.name for guild in bot.guilds ]} as {bot.user}')
    # print(f'connected to {[ guild.name for guild in bot.guilds ]} as {bot.user}')

# print events and debug messsages from users in terminal, doesn't do anything on Discord
@bot.event
async def on_message(message):
    # if the bot sends messages to itself don't return anything
    if message.author == bot.user:
        return
    if type(message.channel) == discord.DMChannel:
        await message.channel.send("Don't talk to me here.")
        return
    if message.channel.name == channel:
        logger.info("Received message", channel=message.channel.name, author=message.author.name, author_id=message.author.id, content=message.content)
        # logger.info(f"{message.channel.name} | {message.author} | {message.author.id} | {message.content}")
        await bot.process_commands(message)

# @bot.command(hidden=True)
# @commands.check(isAdmin)
# async def calculatePredictionScores(ctx):
@tasks.loop(minutes=5)
async def calculatePredictionScores():
    await checkBotReady()
    scorable_fixtures = {}
    try:
        async with bot.pg_conn.acquire() as connection:
            async with connection.transaction():
                await connection.set_type_codec(
                    'json',
                    encoder=json.dumps,
                    decoder=json.loads,
                    schema='pg_catalog'
                )
                unscored_predictions = await connection.fetch("SELECT * FROM predictionsbot.predictions WHERE prediction_score is null")
                unscored_fixtures = await connection.fetch("SELECT DISTINCT fixture_id FROM predictionsbot.predictions WHERE prediction_score is null")
    except Exception:
        logger.exception("encountered error while selecting predictions from database")
        raise PleaseTellMeAboutIt("encountered error while selecting predictions from database")
        
    for fixture in unscored_fixtures:
        fixture_status = await bot.pg_conn.fetchrow(f"SELECT {match_select} FROM predictionsbot.fixtures f WHERE fixture_id = $1", fixture.get("fixture_id"))
        if fixture_status.get("scorable"):
            winner = "home"
            if fixture_status.get("goals_away") > fixture_status.get("goals_home"):
                winner = "away"
            elif fixture_status.get("goals_away") == fixture_status.get("goals_home"):
                winner = "draw"
            scorable_fixtures[fixture.get("fixture_id")] = {"goals_home": fixture_status.get("goals_home"), "goals_away": fixture_status.get("goals_away"), "winner": winner, "home_or_away": fixture_status.get("home_or_away")}

    for fix in scorable_fixtures:
        try:       
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://v2.api-football.com/fixtures/id/{fix}", headers={'X-RapidAPI-Key': api_key}, timeout=20) as resp:
                    fixture_response = await resp.json()
            fixture_info = fixture_response['api']['fixtures'][0]
            goals = [event for event in fixture_info.get("events") if event.get("type") == "Goal" and event.get("teamName") == "Arsenal"]
            scorable_fixtures[fix]["goals"] = sorted(goals, key=lambda k: k['elapsed'])
            scorable_fixtures[fix]["fgs"] = scorable_fixtures[fix]["goals"][0].get("player_id")
        except Exception:
            logger.exception("error retrieving scorable fixture", fixture=fix)
            raise PleaseTellMeAboutIt(f"error retrieving scorable fixture: {fix}")

    for prediction in unscored_predictions:
        if prediction.get("fixture_id") in scorable_fixtures:
            match_results = scorable_fixtures[prediction.get("fixture_id")]
            prediction_score = 0
            winner = "home"
            if prediction.get("away_goals") > prediction.get("home_goals"):
                winner = "away"
            elif prediction.get("away_goals") == prediction.get("home_goals"):
                winner = "draw"
            
            # 2 points – correct result (W/D/L)
            if winner == match_results["winner"]:
                prediction_score += 2
            
            # 2 points – correct number of Arsenal goals
            # 1 point – correct number of goals conceded
            if match_results["home_or_away"] == "home":
                opponent_predicted_goals = prediction.get("away_goals")
                arsenal_predicted_goals = prediction.get("home_goals")
                opponent_actual_goals = match_results.get("goals_away")
                arsenal_actual_goals = match_results.get("goals_home")
            elif match_results["home_or_away"] == "away":
                opponent_predicted_goals = prediction.get("home_goals")
                arsenal_predicted_goals = prediction.get("away_goals")
                opponent_actual_goals = match_results.get("goals_home")
                arsenal_actual_goals = match_results.get("goals_away")

            if arsenal_predicted_goals == arsenal_actual_goals:
                prediction_score += 2
            if opponent_predicted_goals == opponent_actual_goals:
                prediction_score += 1

            for idx,player in enumerate(prediction.get("scorers")):
                prediction.get("scorers")[idx]["player_id"] = await getPlayerId(bot.pg_conn, player.get("name"))

            # 1 point – each correct scorer
            actual_goal_scorers = {}
            for goal in match_results.get("goals"):
                if goal.get("player_id") not in actual_goal_scorers:
                    actual_goal_scorers[goal.get("player_id")] = 1
                else:
                    actual_goal_scorers[goal.get("player_id")] += 1
        
            predicted_scorers = {v.get("player_id"):v.get("num_goals") for v in prediction.get("scorers")}
            absolutely_correct = True
            
            # No points for scorers if your prediction's goals exceed the actual goals by 4+
            # No points for any part of the prediction related to scorers or fgs if predicted goals > actual goals + 4
            if arsenal_predicted_goals < arsenal_actual_goals + 4:
                for actual_scorer, count in actual_goal_scorers.items():
                    if actual_scorer in predicted_scorers:
                        if count == predicted_scorers.get(actual_scorer):
                            prediction_score += count
                        elif count < predicted_scorers.get(actual_scorer):
                            prediction_score += count
                            absolutely_correct = False
                        else:
                            prediction_score += predicted_scorers.get(actual_scorer)
                            absolutely_correct = False

                actual_scorers_set = set(actual_goal_scorers.keys())
                predicted_scorers_set = set(predicted_scorers.keys())
                if predicted_scorers_set.symmetric_difference(actual_scorers_set):
                    absolutely_correct = False

                # 1 point – correct FGS (first goal scorer, only Arsenal)
                predicted_fgs = None
                for player in prediction.get("scorers"):
                    if player.get("fgs"):
                        predicted_fgs = player.get("player_id")
                if predicted_fgs == match_results.get("fgs"):
                    prediction_score += 1

                # 2 points bonus – all scorers correct
                if absolutely_correct:
                    predicted_score += 2

            logger.info("calculated prediction", prediction_id=prediction.get("prediction_id"), user_id=prediction.get("user_id"), prediction_string=prediction.get("prediction_string"), prediction_score=prediction_score)
            try:
                async with bot.pg_conn.acquire() as connection:
                    async with connection.transaction():
                        await connection.execute("UPDATE predictionsbot.predictions SET prediction_score = $1 WHERE prediction_id = $2", prediction_score, prediction.get("prediction_id"))
            except Exception:
                logger.exception("")
                raise PleaseTellMeAboutIt(f"Could not insert an prediction")


#todo way to list players and team nicknames (by league)
# add league id field to teams table
## get player ids and team ids

# todo first move get-api-data.py functionality into predictions-bot.py
# todo be able to turn on and off scheduled tasks and updater functions

@bot.command()
async def help(ctx):
    '''
    This help message
    '''
    output = []
    adminOutput = []
    tabulate.PRESERVE_WHITESPACE = True
    for com, value in bot.all_commands.items():
        if not value.hidden:
            output.append(["\t", com, value.help])
        elif value.hidden:
            adminOutput.append(["\t", com, value.help])

    output = tabulate(output, tablefmt="plain")
    adminOutput = tabulate(adminOutput, tablefmt="plain")
    
    user = bot.get_user(ctx.author.id)

    if ctx.author.id in admin_ids:
        await user.send(f"```Available Commands:\n{output}```\n```Available Administrative Commands:\n{adminOutput}```")
    else:
        await user.send(f"```Available Commands:\n{output}```")

# need these to bulk add nicknames with the bot
# @bot.command(hidden=True)
# @commands.check(isAdmin)
# async def updateNicknames(ctx):
#     '''
#     Add player nickname to database
#     '''
#     for k,v in player_nicknames.items():
#         async with bot.pg_conn.acquire() as connection:
#             async with connection.transaction():
#                 await connection.execute("UPDATE predictionsbot.players SET nicknames = '{{ {0} }}' WHERE player_id = $1".format(", ".join(v)), k)

# @bot.command(hidden=True)
# @commands.check(isAdmin)
# async def updateTeamNickNames(ctx):
#     '''
#     Add team nickname to database
#     '''
#     for k,v in team_nicknames.items():
#         async with bot.pg_conn.acquire() as connection:
#             async with connection.transaction():
#                 await connection.execute("UPDATE predictionsbot.teams SET nicknames = '{{ {0} }}' WHERE team_id = $1".format(", ".join(v)), k)

@bot.command(hidden=True)
@commands.check(isAdmin)
async def addNickname(ctx, nicknameType:str, id:int, nickname:str):
    '''
    Add a nickname to database | +addNickname (player|team) <id> <nickname string>
    '''
    if nicknameType == "team":
        async with bot.pg_conn.acquire() as connection:
            async with connection.transaction():
                await connection.execute("UPDATE predictionsbot.teams SET nicknames = array_append(nicknames, $1) WHERE team_id = $2", nickname, id)
    elif nicknameType == "player":
        async with bot.pg_conn.acquire() as connection:
            async with connection.transaction():
                await connection.execute("UPDATE predictionsbot.players SET nicknames = array_append(nicknames, $1) WHERE player_id = $2", nickname, id)
    else:
        await ctx.send("Can only update nicknames for `player` and `team`.")

@bot.command(hidden=True)
@commands.check(isAdmin)
async def removeNickname(ctx, nicknameType:str, id:int, nickname:str):
    '''
    Remove a nickname from database | +removeNickname (player|team) <id> <nickname string>
    '''
    if nicknameType == "team":
        async with bot.pg_conn.acquire() as connection:
            async with connection.transaction():
                await connection.execute("UPDATE predictionsbot.teams SET nicknames = array_remove(nicknames, $1) WHERE team_id = $2", nickname, id)
    elif nicknameType == "player":
        async with bot.pg_conn.acquire() as connection:
            async with connection.transaction():
                await connection.execute("UPDATE predictionsbot.players SET nicknames = array_remove(nicknames, $1) WHERE player_id = $2", nickname, id)
    else:
        await ctx.send("Can only update nicknames for `player` and `team`.")

@bot.command(hidden=True)
@commands.check(isAdmin)
async def listPlayers(ctx):
    '''
    list nicknames in database
    '''
    # if nicknameType == "team":
        # pass
        # async with bot.pg_conn.acquire() as connection:
        #     async with connection.transaction():
        #         await connection.execute("UPDATE predictionsbot.teams SET nicknames = array_remove(nicknames, $1) WHERE team_id = $2", nickname, id)
    # elif nicknameType == "player":
    if True:
        ids = await bot.pg_conn.fetch("SELECT player_id, player_name, nicknames FROM predictionsbot.players WHERE team_id = $1", main_team)
        output = []
        for player in ids:
            output.append([player.get("player_id"), player.get("player_name")])
        # print(output)
        await ctx.send(f"{ctx.message.author.mention}\n\n{tabulate(output)}")
    else:
        await ctx.send(f"{ctx.message.author.mention}\n\nCan only view nicknames/id for `player` and `team`.")


rules_set = """**Predict our next match against {0}**

**Prediction League Rules:**

2 points – correct result (W/D/L)
2 points – correct number of Arsenal goals
1 point – correct number of goals conceded
1 point – each correct scorer
1 point – correct FGS (first goal scorer, only Arsenal)
2 points bonus – all scorers correct

- Players you predict to score multiple goals should be entered as "player x2" or "player 2x"

- No points for scorers if your prediction's goals exceed the actual goals by 4+

**Remember, we are only counting Arsenal goal scorers**
    - Do not predict opposition goal scorers
    - Do not predict opposition FGS

**Example:**
`{1}`
"""

@bot.command()
async def rules(ctx):
    # these 3 quote blocks in all of the commands are returned when user enters +help
    '''
    Display Prediction League Rules
    '''
    predict_example = "+predict 3-0 auba 2x fgs, laca"
    next_match = await nextMatch(bot.pg_conn)
    opponent = next_match.get('opponent_name')

    rules_set_filled = rules_set.format(opponent, predict_example)
    await ctx.send(f"{ctx.message.author.mention}\n\n{rules_set_filled}")

@bot.command()
async def predict(ctx):
    '''
    Make a new prediction
    '''
    log = logger.bind(content=ctx.message.content, author=ctx.message.author.name)

    #checkUserExists inserts the user_id if not present
    try:
        await checkUserExists(bot.pg_conn, ctx.message.author.id, ctx)
        current_match = await nextMatch(bot.pg_conn)
        user_tz = await getUserTimezone(bot.pg_conn, ctx.message.author.id)
    except Exception:
        log.exception("Error initializing user, match, or user tz")
        raise PleaseTellMeAboutIt("Error initializing user, match, or user tz")

    time_limit_offset = {
        league_dict["europa_league"]: 1.5
    }
    # if europa league then timedelta(hours=1.5)
    # else timedelta(hours=1)
    time_offset = 1
    if current_match.get("league_id") in time_limit_offset:
        time_offset = time_limit_offset[current_match.get("league_id")]

    time_limit = current_match.get("event_date") - timedelta(hours=time_offset)
    time_limit_str = prepareTimestamp(time_limit, user_tz)
    time_limit = prepareTimestamp(time_limit, user_tz, str=False)

    fixture_id = current_match.get('fixture_id')

    opponent = current_match.get('opponent_name')

    if utc.localize(datetime.utcnow()) > time_limit:
        team = await getRandomTeam(bot.pg_conn)
        await ctx.send(f"{ctx.message.author.mention}\n\nError: prediction time too close to match start time. Go support {team} instead.")
        return

    temp_msg = ctx.message.content
    if len(temp_msg.split()) < 2:
        await ctx.send(f"{ctx.message.author.mention}\n\nIt looks like you didn't actually predict anything!\nTry something like `+predict 3-2 auba fgs, laca`")
        return 

    goals_regex = r"((\d) ?[:-] ?(\d))"
    # player_regex = r"[A-Za-z]{1,18}[,]? ?(\d[xX]|[xX]\d)?"

    try:
        prediction_string = temp_msg
        temp_msg = temp_msg.replace("+predict ", "")

        goals_match = re.search(goals_regex, temp_msg)
    
        temp_msg = re.sub(goals_regex, "", temp_msg)

        scorers = temp_msg.strip().split(",")

        scorers = [player.strip() for player in scorers]

        scorer_properties = []

        player_scores = {}
        
        for player in scorers:
            if not player:
                continue

            fgs = False
            num_goals = 1

            if re.search("[fF][gG][sS]", player):
                fgs = True
                player = re.sub("[fF][gG][sS]", "", player)

            goals_scored = re.search(r'[xX]?(\d)[xX]?', player)
            if goals_scored:
                player = re.sub(r'[xX]?(\d)[xX]?', "", player)
                num_goals = int(goals_scored.group(1))

            fgs_str = ""
            if fgs:
                fgs_str = "fgs"

            try:
                player_id = await getPlayerId(bot.pg_conn, player.strip())
                player_real_name = await bot.pg_conn.fetchrow("SELECT player_name FROM predictionsbot.players WHERE player_id = $1;", player_id)
                real_name = player_real_name.get("player_name")
            except Exception as e:
                await ctx.send(f"{ctx.message.author.mention}\n\nPlease try again, {e}")
                return 

            if player_id not in player_scores:
                player_scores[player_id] = {"name": player.strip(), "fgs": fgs, "num_goals": num_goals, "fgs_string": fgs_str, "real_name": real_name}
            else:
                player_scores[player_id]["num_goals"] += num_goals
                if not player_scores[player_id]["fgs"] and fgs:
                    player_scores[player_id]["fgs"] = True
                    player_scores[player_id]["fgs_string"] = "fgs"

        log.debug(player_scores)

        scorer_properties = [player for player in player_scores.values()]
        if len([player for player in player_scores.values() if player.get("fgs")]) > 1:
            await ctx.send(f"{ctx.message.author.mention}\n\nWhy are you the way that you are?\nTwo players cannot be first goal scorer. Predict again.")
            return

    except Exception as e:
        log.exception(f"{e}")
        await ctx.send(f"There was an error parsing this prediction:\n{e}")
        return
    
    if not goals_match:
        await ctx.send(f"{ctx.message.author.mention}\n\nDid not provide a match score in your prediction.\n`{ctx.message.content}`")
        return
    else:        
        # football home teams listed first
        home_goals = int(goals_match.group(2))
        # football away teams listed second
        away_goals = int(goals_match.group(3))

    if current_match.get("home_or_away") == "home":
        arsenal_goals = home_goals
    else:
        arsenal_goals = away_goals

    predicted_goal_count = 0
    for scorer in scorer_properties:
        predicted_goal_count += scorer.get("num_goals")

    if predicted_goal_count > arsenal_goals:
        await ctx.send(f"{ctx.message.author.mention}\n\nIt looks like you have predicted Arsenal to score {arsenal_goals}, but have included too many goal scorers:\nPrediction: `{prediction_string}`\nNumber of scorers predicted: {predicted_goal_count} | Predicted goals scored: {arsenal_goals}")
        return

    try:
        prediction_id =  randomAlphanumericString(16)
        successful_or_updated = "successful"

        # print(f"{prediction_id}, {ctx.message.author.id}, {prediction_string}")
        # use similar syntax as next lines for any insert/update to the db
        # also include the magic json stuff for things accessing the predictions table
        async with bot.pg_conn.acquire() as connection:
            async with connection.transaction():
                await connection.set_type_codec(
                    'json',
                    encoder=json.dumps,
                    decoder=json.loads,
                    schema='pg_catalog'
                )
                try:
                    prev_prediction = await connection.fetchrow("SELECT * FROM predictionsbot.predictions WHERE user_id = $1 AND fixture_id = $2", ctx.message.author.id, fixture_id)
                    if prev_prediction:
                        successful_or_updated = "updated"
                        await connection.execute(f"UPDATE predictionsbot.predictions SET prediction_string = $1, home_goals = $2, away_goals = $3, scorers = $4::json, timestamp = now() WHERE user_id = $5 AND fixture_id = $6", prediction_string, home_goals, away_goals, scorer_properties, ctx.message.author.id, fixture_id)
                    else:
                        await connection.execute("INSERT INTO predictionsbot.predictions (prediction_id, user_id, prediction_string, fixture_id, home_goals, away_goals, scorers) VALUES ($1, $2, $3, $4, $5, $6, $7);", prediction_id, ctx.message.author.id, prediction_string, fixture_id, home_goals, away_goals, scorer_properties)
                except Exception as e:
                    log.exception("Error adding prediction")
                    await ctx.send(f"{ctx.message.author.mention}\n\nThere was an error adding your prediction, please try again later.")
                    return

        goal_scorers_array = [f'{scorer.get("real_name")}: {scorer.get("num_goals")} {scorer.get("fgs_string")}' for scorer in scorer_properties]
        goal_scorers = "\n".join(goal_scorers_array)
        
        output = f"""{ctx.message.author.mention}\n\n**Prediction against {opponent} {successful_or_updated}.**\n\nYou have until {time_limit_str} to edit your prediction.\n\n`{ctx.message.content}`"""
        output += f"""\n\n**Score**\n{current_match.get('home_name')} {home_goals} - {away_goals} {current_match.get('away_name')}\n\n"""
        if goal_scorers:
            output += f"""**Goal Scorers**\n{goal_scorers}"""
        await ctx.send(output)

    except (Exception) as e:
        log.exception(f"There was an error loading this prediction into the database: {e}")
        await bot.admin_id.send(f"There was an error loading this prediction into the databse:\n{e}")
        return

@bot.command()
async def predictions(ctx):
    '''
    Show your past predictions
    '''
    await checkUserExists(bot.pg_conn, ctx.message.author.id, ctx)
    predictions = await getUserPredictions(bot.pg_conn, ctx.message.author.id)
    if not predictions:
        await ctx.send(f"{ctx.message.author.mention}\n\nIt looks like you have no predictions! Get started by typing `+predict`")
        return

    embed = discord.Embed(title=f"Predictions for {ctx.message.author.display_name}")

    # output = f"{ctx.message.author.mention}\n"

    total = 0
    for prediction in predictions:
        if prediction.get("prediction_score"):
            total += prediction.get("prediction_score")
        match = await getMatch(bot.pg_conn, prediction.get("fixture_id"))
        embed.add_field(name=f'{match.get("event_date").strftime("%m/%d/%Y")} {match.get("home_name")} vs {match.get("away_name")}', value=f'Score: {prediction.get("prediction_score")} | `{prediction.get("prediction_string")}`\n\n', inline=False)
        # output += f'`{match.get("event_date").strftime("%m/%d/%Y")} {match.get("home_name")} vs {match.get("away_name")}` | `{prediction.get("prediction_string")}` | Score: `{prediction.get("prediction_score")}`\n'
    embed.description=f"Current total league score: **{total}**"
    await ctx.send(f"{ctx.message.author.mention}\n\n",embed=embed)

@bot.command()
@rateLimit(60, "leaderboard")
async def leaderboard(ctx):
    '''
    Show leaderboard
    '''
    log = logger.bind(content=ctx.message.content, author=ctx.message.author.name)
    embed_colors = [0x9C824A, 0x023474, 0xEF0107, 0xDB0007]
    embed_color = random.choice(embed_colors)
    embed = discord.Embed(title="Arsenal Prediction League Leaderboard", description="\u200b", color=embed_color)
    embed.set_thumbnail(url="https://media.api-sports.io/football/teams/42.png")

    # if need to change the way the tied users are displayed change "RANK()" to "DENSE_RANK()"
    try:
        leaderboard = await bot.pg_conn.fetch(f"SELECT DENSE_RANK() OVER(ORDER BY SUM(prediction_score) DESC) as rank, SUM(prediction_score) as score, user_id FROM predictionsbot.predictions WHERE prediction_score IS NOT NULL GROUP BY user_id ORDER BY SUM(prediction_score) DESC")
    except Exception:
        log.error("Failed to retrieve predictions leaderboard from database")

    prediction_dictionary = {}
    # embed_dictionary = {}
    for prediction in leaderboard:
        if prediction.get("rank") not in prediction_dictionary:
            # embed_dictionary[prediction.get("rank")] = discord.Embed(title=f'Rank: {prediction.get("rank")}', description="", color=0x9c824a)
            prediction_dictionary[prediction.get("rank")] = [prediction]
        else:
            prediction_dictionary[prediction.get("rank")].append(prediction)
    
    # all_members = bot.get_all_members()
    
    rank_num = 1
    for v in prediction_dictionary.values():
        # current_embed = embed_dictionary.get(k)
        output_array = []
        for user_prediction in v:
            try:
                # for user in all_members:
                #     if user.id == user_prediction.get("user_id"):
                user = bot.get_user(user_prediction.get("user_id"))
                if user:
                    output_array.append(f'{user.display_name}')
                    # current_embed.add_field(name=f"Rank: {user.display_name}", value=f'{user_prediction.get("score")} points', inline=True)
            except discord.NotFound:
                logger.warning("Missing user mapping", user=user_prediction.get("user_id"))
        output_str = "\n".join(output_array)
        embed.add_field(name=f'Rank {makeOrdinal(rank_num)}:  {user_prediction.get("score")} Points', value=f"```{output_str}```", inline=False)
        rank_num += 1

    await ctx.send(f"{ctx.message.author.mention}", embed=embed)

@bot.command()
async def timezone(ctx):
    '''
    Change timezone
    '''
    log = logger.bind(content=ctx.message.content, author=ctx.message.author.name)
    await checkUserExists(bot.pg_conn, ctx.message.author.id, ctx)

    msg = ctx.message.content
    try:
        tz = re.search(r"\+timezone (.*)", msg).group(1)
    except Exception:
        await ctx.send(f"{ctx.message.author.mention}\n\nYou didn't include a timezone!")
        return
    
    if tz in pytz.all_timezones:
        try:
            async with bot.pg_conn.acquire() as connection:
                async with connection.transaction():
                    await connection.execute("UPDATE predictionsbot.users SET tz = $1 WHERE user_id = $2", tz, ctx.message.author.id)
        except Exception:
            log.error("User encoutered error changing timezone")
        await ctx.send(f"{ctx.message.author.mention}\n\nYour timezone has been set to {tz}")
    else:
        await ctx.send(f"{ctx.message.author.mention}\n\nThat is not a recognized timezone!\nExpected format looks like: 'US/Mountain' or 'America/Chicago' or 'Europe/London'")

@bot.command()
async def next(ctx):
    '''
    Next matches
    '''
    log = logger.bind(content=ctx.message.content, author=ctx.message.author.name)
    msg = ctx.message.content

    split_msg = msg.split()
    
    if len(split_msg) > 2:
        await ctx.send(f"{ctx.message.author.mention}\n\nToo many arguments; should be '+next 2' or similar")
        return

    elif len(split_msg) > 1:
        count = split_msg[1]
        try:
            count = int(count)
        except:
            await ctx.send(f"{ctx.message.author.mention}\n\nExpected usage:\n`+next [1-10]`")
            return
    else: 
        count = 2
        
    if count <= 0:
        await ctx.send(f"{ctx.message.author.mention}\n\nNumber of next matches cannot be a negative number")
    elif count > 10:
        await ctx.send(f"{ctx.message.author.mention}\n\nNumber of next matches cannot be greater than 10")
    else:
        try:
            next_matches = await nextMatches(bot.pg_conn, count=count)
        except Exception:
            log.exception("Error retrieving nextMatches from database")
        output = f"{ctx.message.author.mention}\n\n**Next {count} matches:**\n\n"
        for match in next_matches:
        # await ctx.send(f"{[match for match in next_matches]}")
        # todo: embed icons here
            output += await formatMatch(bot.pg_conn, match, ctx.message.author.id)
        await ctx.send(f"{output}")

# todo paginate some functions from +help
# todo indicate prediction has yet to be scored instead of points 
# todo show missed matches in +predictions

@bot.command()
async def when(ctx):
    '''
    Return next match against given team
    '''
    msg = ctx.message.content
    try:
        team = msg.split(" ", 1)[1]
    except: 
        await ctx.send("Missing a team!")
        return

    try:
        team_id = await getTeamId(bot.pg_conn, team)
        if team_id == main_team:
            await ctx.send(f"You are on the channel for the {team}, we cannot play against ourselves.")
            return
    except:
        await ctx.send(f"{ctx.message.author.mention}\n\n{team} does not seem to be a team I recognize.")
        return

    next_match = await bot.pg_conn.fetchrow(f"SELECT {match_select} FROM predictionsbot.fixtures f WHERE event_date > now() AND ((home = {main_team} AND away = $1) OR (away = {main_team} AND home = $1)) ORDER BY event_date LIMIT 1", team_id)
    next_match = await formatMatch(bot.pg_conn, next_match, ctx.message.author.id)
    await ctx.send(f"{ctx.message.author.mention}\n\n{next_match}")

@bot.command()
async def results(ctx):
    '''
    Return historical match results
    '''
    await checkUserExists(bot.pg_conn, ctx.message.author.id, ctx)
    user_tz = await getUserTimezone(bot.pg_conn, ctx.message.author.id)

    done_matches = await completedMatches(bot.pg_conn, count=10)
    done_matches_output = []
    for match in done_matches:
        match_time = match.get("event_date")
        match_time = prepareTimestamp(match_time, user_tz, str=False)
        done_matches_output.append([match_time.strftime("%m/%d/%Y"), match.get("home_name"), f'{match.get("goals_home")}-{match.get("goals_away")}', match.get("away_name")])

    done_matches_output = f'```{tabulate(done_matches_output, headers=["Date", "Home", "Score", "Away"], tablefmt="github", colalign=("center","center","center","center"))}```'
    await ctx.send(f"{ctx.message.author.mention}\n\n**Past Match Results**\n{done_matches_output}")

def formatStandings(standings):
    standings_formatted = []
    for standing in standings:
        # standings_formatted.append([makeOrdinal(standing["rank"]), standing["teamName"], standing["points"], standing["played"], f'{standing["win"]}-{standing["draw"]}-{standing["loss"]}'])
        standings_formatted.append([standing["rank"], standing["teamName"], f'{standing["win"]}-{standing["draw"]}-{standing["loss"]}', standing["goalsDiff"], standing["played"]])

    return tabulate(standings_formatted, headers=["Rank", "Team", "W-D-L", "GD", "Pts"], tablefmt="github")

# # PL table
@bot.command()
@rateLimit(60, "pltable")
async def pltable(ctx):
    '''
    Current Premier League table
    '''
    standings = await getStandings(bot, league_dict["premier_league"])

    output = formatStandings(standings)
    # \u200b  null space/break char
    # embed = discord.Embed(title=f"Premier League Leaderboard", description=f"```{output}```", color=0x3d195b)
    # embed.set_thumbnail(url="http://www.pngall.com/wp-content/uploads/4/Premier-League-PNG-Image.png")
    # embed.set_footer(text="\u200b", icon_url="https://media.api-sports.io/leagues/2.png")
    # embed.add_field(name="\u200b", value=output, inline=False)
    # embed.add_field(name=f'Rank {makeOrdinal(rank_num)}:  {user_prediction.get("score")} Points', value=f"```{output_str}```", inline=False)
    await ctx.send(f"{ctx.message.author.mention}\n\n**Premier League Leaderboard**\n```{output}```")
    # await ctx.send(f"```{output}```")
    # await ctx.send(embed=embed)


async def checkBotReady():
    await asyncio.sleep(5)

@bot.command()
async def ping(ctx):
    '''
    Return latency between bot and server
    '''
    log = logger.bind(content=ctx.message.content, author=ctx.message.author.name)
    latency = bot.latency
    log.info(latency=latency)
    await ctx.send(f"{ctx.message.author.mention}\n\nBot latency is {latency * 1000:.0f} milliseconds")

@bot.command(hidden=True)
async def echo(ctx, *, content:str):
    '''
    Repeat what you typed for testing/debugging
    '''    
    await ctx.send(content)

# @bot.command(hidden=True)
# async def what_do_you_think_of_tottenham(ctx):
#     '''
#     Who do we think is shit?
#     '''
#     video = "https://www.youtube.com/watch?v=w0R7gWf-nSA"
#     spurs_status = "SHIT"
#     await ctx.send(f"{ctx.message.author.mention}\n\n{spurs_status}\n{video}")

@bot.command(hidden=True)
@commands.check(isAdmin)
async def testEmbed(ctx):
    '''
    Generate a test embed object
    '''
    # log = logger.bind(content=ctx.message.content, author=ctx.message.author)
    paginated_data = [
        {"title": "Test 0", "msg": "TestMessage 0"}, 
        {"title": "Test 1", "msg": "TestMessage 1"},
        {"title": "Test 2", "msg": "TestMessage 2"}
    ]
    max_page = len(paginated_data) - 1
    num = 0
    first_run = True
    while True:
        # log.info(num=num, max_page=max_page)
        if first_run:
            embedVar = discord.Embed(title=paginated_data[num].get("title"), description="Desc", color=0x9c824a)
            embedVar.add_field(name=f"Test {num}", value=paginated_data[num].get("msg"), inline=False)

            first_run = False
            msg = await ctx.send(embed=embedVar)

        reactmoji = []
        if max_page == 0 and num == 0:
            pass
        elif num == 0:
            reactmoji.append('⏩')
        elif num == max_page:
            reactmoji.append('⏪')
        elif num > 0 and num < max_page:
            reactmoji.extend(['⏪', '⏩'])
        # reactmoji.append('✅')

        for react in reactmoji:
            await msg.add_reaction(react)

        def checkReact(reaction, user):
            if reaction.message.id != msg.id:
                return False
            if user != ctx.message.author:
                return False
            if str(reaction.emoji) not in reactmoji:
                return False
            return True

        try:
            res, user = await bot.wait_for('reaction_add', timeout=30.0, check=checkReact)
        except asyncio.TimeoutError:
            return await msg.clear_reactions()

        if user != ctx.message.author:
            pass
        elif '⏪' in str(res.emoji):
            print('<< Going backward')
            num = num - 1
            embedVar = discord.Embed(title=paginated_data[num].get("title"), description="Desc", color=0x9c824a)
            embedVar.add_field(name=f"Test {num}", value=paginated_data[num].get("msg"), inline=False)
            await msg.clear_reactions()
            await msg.edit(embed=embedVar)

        elif '⏩' in str(res.emoji):
            print('\t>> Going forward')
            num = num + 1
            embedVar = discord.Embed(title=paginated_data[num].get("title"), description="Desc", color=0x9c824a)
            embedVar.add_field(name=f"Test {num}", value=paginated_data[num].get("msg"), inline=False)
            await msg.clear_reactions()
            await msg.edit(embed=embedVar)

@bot.command(hidden=True)
@commands.check(isAdmin)
async def userLookup(ctx, *input_str:str):
    '''
    Return possible user matches and user ID
    '''
    for input in input_str:
        current_member = []
        for member in bot.get_all_members():
            if input.lower() in member.display_name.lower() or input.lower() in member.name.lower():
                current_member.append(member)
        if not current_member:
            await ctx.send(f"Could not find any users matching {input}.")
        else:
            output = f"Potential Matches for {input}:\n"
            for user in current_member:
                output += f"{user.display_name} | {user.id}\n"
            await ctx.send(f"{output}")

@bot.command(hidden=True)
@commands.check(isAdmin)
async def messageLookup(ctx, input_id:int):
    '''
    Return message ID and ID of message author
    '''
    id_to_lookup = input_id
    output = None
    for chan in bot.get_all_channels():
        if str(chan.type) == "text":
            logger.debug(f"Searching channel: {chan}")
            try:
                output = await chan.fetch_message(id_to_lookup)
            except (discord.NotFound):
                continue
            except discord.Forbidden:
                logger.debug(f"Access to {chan} forbidden.")
    if not output:
        logger.debug("Could not find in any channels.")
        await ctx.send(f"Could not find message id {id_to_lookup}.")
    else:
        await ctx.send(f"Message id {id_to_lookup} | Author: {output.author.id}")

# @bot.command(hidden=True)
# runs every 15 min to check if fixtures within 5 hours before and after now are complete/scorable for predictions
@tasks.loop(minutes=15)
async def updateFixtures():
    await checkBotReady()

    try:
        fixtures = await bot.pg_conn.fetch("SELECT fixture_id FROM predictionsbot.fixtures WHERE event_date < now() + interval '5 hour' AND event_date > now() + interval '-5 hour' AND NOT scorable")
    except Exception:
        logger.exception("Failed to select fixtures from database")
        raise PleaseTellMeAboutIt("Failed to select fixtures from database in updateFixtures")

    for fixture in fixtures:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://v2.api-football.com/fixtures/id/{fixture.get('fixture_id')}", headers={'X-RapidAPI-Key': api_key}, timeout=20) as resp:
                    fixture_info = await resp.json()
            # fixture_response = requests.get(f"http://v2.api-football.com/fixtures/id/{fixture.get('fixture_id')}", headers={'X-RapidAPI-Key': api_key}, timeout=5)
            fixture_info = fixture_response['api']['fixtures'][0]

            match_completed = status_lookup[fixture_info.get("statusShort")]
        except Exception:
            logger.exception("Failed to get fixture from api", fixture=fixture.get('fixture_id'))
            raise PleaseTellMeAboutIt(f"Failed to get fixture from api: {fixture.get('fixture_id')}")

        try:
            async with bot.pg_conn.acquire() as connection:
                async with connection.transaction():
                    await connection.execute("UPDATE predictionsbot.fixtures SET goals_home = $1, goals_away = $2, scorable = $3 WHERE fixture_id = $4", fixture_info.get("goalsHomeTeam"), fixture_info.get("goalsAwayTeam"), match_completed, fixture.get('fixture_id'))
        except Exception:
            logger.exception("Failed to update fixture", fixture=fixture.get('fixture_id'))
            raise PleaseTellMeAboutIt(f"Failed to get fixture from api: {fixture.get('fixture_id')}")

    logger.info(f"Updated fixtures table, {len(fixtures)} were changed.")
    # await bot.admin_id.send(f"Updated fixtures table, {len(fixtures)} were changed.")

def changesExist(fixture1, fixture2):
    # likeness of bools of these comparisons
    # all() returns True if all elements of likeness are True
    likeness = [
        fixture1.get("home") == fixture2.get("home"),
        fixture1.get("away") == fixture2.get("away"),
        fixture1.get("event_date") == fixture2.get("event_date"),
        fixture1.get("goalsHomeTeam") == fixture2.get("goals_home"),
        fixture1.get("goalsAwayTeam") == fixture2.get("goals_away"),
        fixture1.get("league_id") == fixture2.get("league_id")
    ]
    return not all(likeness)

# runs every hour updating all fixtures in the db that are not identical to the current entry (by fixture id)
# this ensures that we get any new fixtures outside the updateFixtures() 15 min window (ex. date of the CL final gets changed, or for some reason fixtures in the past change)
@tasks.loop(hours=1)
async def updateFixturesbyLeague():
    await checkBotReady()
    # if datetime.utcnow.hour % 8 == 0:
        # logger.info("Not running fixture update script")
    logger.info("Running fixture update script")
    updated_fixtures = 0

    # if not league:
    #     print("No team IDs generated. Pass in a --league <league_id>")
    #     sys.exit(1)
    for league_name, league_id in league_dict.items():
        logger.info("generating fixtures", league_id=league_id, league_name=league_name)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://v2.api-football.com/fixtures/league/{league_id}", headers={'X-RapidAPI-Key': api_key}, timeout=20) as resp:
                    response = await resp.json()
            fixtures = response.get("api").get("fixtures")
        except Exception:
            logger.exception("Unable to fetch league information in updateFixturesbyLeague", league_name=league_name)
            raise PleaseTellMeAboutIt(f"Unable to fetch league information in updateFixturesbyLeague for {league_name}")

        # reset parsed fixtures to empty for each league
        parsed_fixtures = []
        for match in fixtures:
            home = match.get("homeTeam").get("team_id")
            away = match.get("awayTeam").get("team_id")
            event_date = match.get("event_date")

            delete_keys = [key for key in match if key not in ["fixture_id", "league_id", "goalsHomeTeam", "goalsAwayTeam", "statusShort"]]
        
            for key in delete_keys:
                del match[key]

            match["event_date"] = datetime.strptime(event_date, "%Y-%m-%dT%H:%M:%S+00:00") 
            match["home"] = home
            match["away"] = away

            parsed_fixtures.append(match)
        
        for fixture in parsed_fixtures:
            try:
                fixture_exists = await bot.pg_conn.fetchrow("SELECT home, away, fixture_id, league_id, event_date, goals_home, goals_away FROM predictionsbot.fixtures WHERE fixture_id = $1", fixture.get("fixture_id"))
                
                if fixture_exists:
                    if changesExist(fixture, fixture_exists):
                        updated_fixtures += 1
                        logger.info("changes exist", fixture_id=fixture.get("fixture_id"), league_id=league_id)
                        async with bot.pg_conn.acquire() as connection:
                            async with connection.transaction():
                                await connection.execute("UPDATE predictionsbot.fixtures SET home = $1, away = $2, league_id = $3, event_date = $4, goals_home = $5, goals_away = $6, scorable = $7 WHERE fixture_id = $8", 
                                                            fixture.get("home"), fixture.get("away"), fixture.get("league_id"), fixture.get("event_date"), 
                                                            fixture.get("goalsHomeTeam"), fixture.get("goalsAwayTeam"), status_lookup[fixture.get("statusShort")], fixture.get('fixture_id'))
                else:
                    logger.info("new fixture", fixture_id=fixture.get("fixture_id"), league_id=league_id)
                    updated_fixtures += 1
                    async with bot.pg_conn.acquire() as connection:
                        async with connection.transaction():
                            await connection.execute("INSERT INTO predictionsbot.fixtures (home, away, league_id, event_date, goals_home, goals_away, scorable, fixture_id) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)", 
                                                        fixture.get("home"), fixture.get("away"), fixture.get("league_id"), fixture.get("event_date"), fixture.get("goalsHomeTeam"), 
                                                        fixture.get("goalsAwayTeam"), status_lookup[fixture.get("statusShort")], fixture.get('fixture_id'))
            except Exception:
                logger.exception("Failed to verify/update fixtue", fixture_id=fixture.get("league_id"))
                raise PleaseTellMeAboutIt(f'Failed to verify/update fixtue: {fixture.get("league_id")}')

    if updated_fixtures:
        await bot.admin_id.send(f"Updated/Inserted {updated_fixtures} fixtures!")

async def getStandings(bot, league_id):
    parsed_standings = []

    logger.info("Generating standings", league=league_id)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://v2.api-football.com/leagueTable/{league_id}", headers={'X-RapidAPI-Key': api_key}, timeout=20) as resp:
                response = await resp.json()
    except Exception:
        logger.exception("Failed to featch standings", league_id=league_id)
        raise PleaseTellMeAboutIt(f"Failed to featch standings for {league_id}")

    standings = response.get("api").get("standings")
    
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

    return parsed_standings

@bot.event
async def on_command_error(ctx, error):
    logger.error(f"Handling error for {ctx.message.content}", exception=error)
    if isinstance(error, IsNotAdmin):
        await ctx.send(f"You do not have permission to run `{ctx.message.content}`")
    if isinstance(error, RateLimit):
        await ctx.send(error)
    if isinstance(error, CommandNotFound):
        await ctx.send(f"`{ctx.message.content}` is not a recognized command, try `+help` to see available commands")
    if isinstance(error, CommandInvokeError):
        if isinstance(error.original, PleaseTellMeAboutIt):
            await bot.admin_id.send(f"Admin error tagged for notification: {error.original}")
        else:
            await bot.admin_id.send(f"Unhandled Error: {error.original}")

if __name__ == "__main__":
    try:
        # disabling fixture update during testing mode, may need to be further tunable for testing.
        if not testing_mode:
            updateFixtures.start()
            calculatePredictionScores.start()
            updateFixturesbyLeague.start()

        bot.run(token)
    except Exception as e:
        logger.exception("Error in bot")
        sys.exit(1)
    