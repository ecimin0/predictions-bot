#!/usr/local/bin/python3

import discord
import re
import sys
import os
import json
import logging 
import requests
import asyncio
import asyncpg
import pytz
import argparse
import random
import string
import structlog
import traceback

from pythonjsonlogger import jsonlogger
from discord.ext import commands, tasks
from datetime import timedelta, datetime
from dotenv import load_dotenv
from pprint import pprint

# bot token, API key, other stuff 
load_dotenv()

def createLogger(level):
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(jsonlogger.JsonFormatter(fmt='%(asctime)s %(levelname)s %(name)s %(message)s'))
    discord_logger = logging.getLogger('discord')
    discord_logger.setLevel(logging.INFO)
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

player_nicknames = {
    138784: ["olayinka"],
    1161: ["smith-rowe", "esr"],
    1438: ["leno"],
    19599: ["martinez", "emi"],
    20386: ["macey"],
    1437: ["iliev"],
    1439: ["bellerin", "hector", "heccy"],
    1117: ["tierney", "kt"],
    1450: ["papastathopoulos", "sokratis"],
    1440: ["holding", "holdinho"],
    1448: ["mustafi"],
    19016: ["chambers"],
    2283: ["luiz"],
    1442: ["kolasinac", "kola"],
    190: ["soares", "cedric"],
    46792: ["mari"],
    22090: ["saliba"],
    1458: ["ozil", "mesut"],
    1462: ["torreira"],
    1456: ["maitland-niles", "amn"],
    1463: ["willock"],
    1454: ["guendouzi"],
    1464: ["xhaka"],
    1460: ["saka"],
    1452: ["elneny"],
    1467: ["lacazette", "laca"],
    1465: ["aubameyang", "auba"],
    3246: ["pepe"],
    727: ["nelson"],
    1468: ["nketiah", "eddie"],
    127769: ["martinelli", "gabi"],
    748: ["ceballos", "dani"],
    2294: ["willian"],
    22224: ["gabriel"]
}

team_nicknames = {
    44: ["burnley"], 
    33: ["manchester united", "man u", "man united", "united"], 
    52: ["crystal palace", "palace"], 
    41: ["southampton", "saints"],
    36: ["fulham"], 
    42: ["arsenal"], 
    40: ["liverpool"], 
    63: ["leeds", "leeds united"], 
    50: ["manchester city", "man city", "city"], 
    66: ["aston villa", "villa"], 
    47: ["tottenham", "tottenham hotspur", "spurs", "spuds", "the shit", "shit", "shite"], 
    45: ["everton", "toffees"], 
    60: ["west brom", "west bromwich albion", "baggies"], 
    46: ["leicester", "leicester city"], 
    48: ["west ham", "west ham united", "hammers"], 
    34: ["newcastle", "newcastle united"], 
    51: ["brighton", "brighton and hove albion"], 
    49: ["chelsea"], 
    62: ["sheffield united", "sheffield"],
    39: ["wolves", "wolverhampton"]
}

# 2020-2021 season league IDs
premier_league_id = 2790
champions_league_id = 2771
europa_league_id = 2777
fa_cup_id = 2791
league_cup_id = 2781

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

time_format = "%m/%d/%Y, %H:%M:%S %Z"

match_select = f"home, away, fixture_id, league_id, event_date, goals_home, goals_away, new_date, (SELECT name FROM predictionsbot.teams t WHERE t.team_id = f.home) AS home_name, (SELECT name FROM predictionsbot.teams t WHERE t.team_id = f.away) AS away_name, (SELECT name FROM predictionsbot.leagues t WHERE t.league_id = f.league_id) as league_name, CASE WHEN away = 42 THEN home ELSE away END as opponent, (SELECT name FROM predictionsbot.teams t WHERE t.team_id = (CASE WHEN f.away = 42 THEN f.home ELSE f.away END)) as opponent_name, CASE WHEN away = {main_team} THEN 'away' ELSE 'home' END as home_or_away, scorable"

token = os.environ.get("TOKEN", None)
if not token:
    logger.error("Missing Discord bot token! Set TOKEN env value.")
    sys.exit(1)

last_run = datetime.utcnow() - timedelta(hours=1)

channel_id = int(os.environ.get("CHANNELID", 0))

# bot only responds to commands prepended with {prefix}
prefix = "+"

# cleaner output of help function(s)
help_function = commands.DefaultHelpCommand(no_category="Available Commands", indent=4)
bot = commands.Bot(prefix, help_command=help_function)

class IsNotAdmin(commands.CheckFailure):
    pass

class RateLimit(commands.CheckFailure):
    pass

def getPlayerId(userInput):
    for k,v in player_nicknames.items():
        if userInput.lower() in v:
            return k
    raise Exception(f"no player named {userInput}")

def getTeamId(userInput):
    for k,v in team_nicknames.items():
        if userInput.lower() in v:
            return k
    raise Exception(f"no team named {userInput}")

def randomAlphanumericString(length):
    letters_and_digits = string.ascii_letters + string.digits
    result_str = ''.join((random.choice(letters_and_digits) for i in range(length)))
    return result_str

def rateLimit(seconds):
    async def predicate(ctx):
        global last_run
        seconds_since_last_run = (datetime.utcnow() - last_run).total_seconds()
        if seconds_since_last_run > seconds:
            last_run = datetime.utcnow()
            return True
        else:
            raise RateLimit(f"Leaderboard command is under a rate limit. May run again in {seconds - seconds_since_last_run:.0f} seconds.")
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
    '''
    Return the array of next fixtures records from Database 
    '''
    matches = await dbconn.fetch(f"SELECT {match_select} FROM predictionsbot.fixtures f WHERE event_date > now() AND (home = {main_team} OR away = {main_team}) ORDER BY event_date LIMIT $1;", count)
    return matches

# nextMatch returns record (no array)
async def nextMatch(dbconn):
    '''
    Return the next fixture record from Database 
    '''
    match = await dbconn.fetchrow(f"SELECT {match_select} FROM predictionsbot.fixtures f WHERE event_date > now() AND (home = {main_team} OR away = {main_team}) ORDER BY event_date LIMIT 1;")
    return match

async def completedMatches(dbconn, count=1, offset=0):
    '''
    Return the array of completed fixtures records from Database 
    '''
    matches = await dbconn.fetch(f"SELECT {match_select} FROM predictionsbot.fixtures f WHERE event_date + interval '2 hour' < now() AND (home = {main_team} OR away = {main_team}) ORDER BY event_date DESC LIMIT $1 OFFSET $2;", count, offset)
    return matches

async def formatMatch(dbconn, match, user):
    tz = await getUserTimezone(dbconn, user)
    match_time = prepareTimestamp(match.get('event_date'), tz)

    time_until_match = (match.get('event_date') - datetime.now()).total_seconds()
    return f"{match.get('league_name')}\n\({match.get('home_or_away')}\) vs {match.get('opponent_name')}\n{match_time}\n*match starts in {time_until_match // 86400:.0f} days, {time_until_match // 3600 %24:.0f} hours, and {time_until_match // 60 %60:.0f} minutes*\n\n" 

async def connectToDB():
    try:
        bot.pg_conn = await asyncpg.create_pool(user=aws_dbuser, password=aws_dbpass, database=aws_dbname, host=aws_db_ip)
        logger.info("Connected to postgres")
    except Exception as e:
        logger.error(f"{e}")
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
    if message.channel.name == channel:
        logger.info("Received message", channel=message.channel.name, author=message.author.name, author_id=message.author.id, content=message.content)
        # logger.info(f"{message.channel.name} | {message.author} | {message.author.id} | {message.content}")
        await bot.process_commands(message)


# @bot.command(hidden=True)
# @commands.check(isAdmin)
# async def calculatePredictionScores(ctx):
@tasks.loop(minutes=5)
async def calculatePredictionScores():
    scorable_fixtures = {}
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
        fixture_response = requests.get(f"http://v2.api-football.com/fixtures/id/{fix}", headers={'X-RapidAPI-Key': api_key}, timeout=5)
        fixture_info = fixture_response.json()['api']['fixtures'][0]
        goals = [event for event in fixture_info.get("events") if event.get("type") == "Goal" and event.get("teamName") == "Arsenal"]
        scorable_fixtures[fix]["goals"] = sorted(goals, key=lambda k: k['elapsed'])
        scorable_fixtures[fix]["fgs"] = scorable_fixtures[fix]["goals"][0].get("player_id")

    pprint(scorable_fixtures)
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
            opponent_goals = 0
            arsenal_goals = 0
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
                prediction.get("scorers")[idx]["player_id"] = getPlayerId(player.get("name"))

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

            print(f'{prediction.get("prediction_id")} | {prediction.get("user_id")} | {prediction.get("prediction_string")} | {prediction_score}')
            async with bot.pg_conn.acquire() as connection:
                async with connection.transaction():
                    await connection.execute("UPDATE predictionsbot.predictions SET prediction_score = $1 WHERE prediction_id = $2", prediction_score, prediction.get("prediction_id"))

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

async def getRandomTeam(dbconn):
    team = await dbconn.fetchrow("SELECT * FROM predictionsbot.teams WHERE team_id != 42 ORDER BY random() LIMIT 1;")
    return team.get("name")

@bot.command()
async def predict(ctx):
    '''
    Make a new prediction
    '''
    log = logger.bind(content=ctx.message.content, author=ctx.message.author.name)

    #checkUserExists inserts the user_id if not present
    await checkUserExists(bot.pg_conn, ctx.message.author.id, ctx)

    current_match = await nextMatch(bot.pg_conn)
    user_tz = await getUserTimezone(bot.pg_conn, ctx.message.author.id)

    time_limit_offset = {
        europa_league_id: 1.5
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
    player_regex = r"[A-Za-z]{1,18}[,]? ?(\d[xX]|[xX]\d)?"

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

            if "fgs" in player:
                fgs = True
                player = player.replace("fgs", "")

            goals_scored = re.search(r'[xX]?(\d)[xX]?', player)
            if goals_scored:
                player = re.sub(r'[xX]?(\d)[xX]?', "", player)
                num_goals = int(goals_scored.group(1))

            fgs_str = ""
            if fgs:
                fgs_str = "fgs"

            try:
                player_id = getPlayerId(player.strip())
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
        message_timestamp = datetime.utcnow()
        
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
                    log.exception(e)
                    await ctx.send("There was an error adding your prediction, please try again later.")
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

    output = f"{ctx.message.author.mention}\n\n"
    for prediction in predictions:
        match = await getMatch(bot.pg_conn, prediction.get("fixture_id"))
        output += f'`{match.get("event_date").strftime("%m/%d/%Y")} {match.get("home_name")} vs {match.get("away_name")}` | `{prediction.get("prediction_string")}` | Score: `{prediction.get("prediction_score")}`\n'
    await ctx.send(f"{output}")


@bot.command()
@rateLimit(60)
async def leaderboard(ctx):
    '''
    Show leaderboard
    '''  
    embed_colors = [0x9C824A, 0x023474, 0xEF0107, 0xDB0007]
    embed_color = random.choice(embed_colors)
    embed = discord.Embed(title="Arsenal Prediction League Leaderboard", description="", color=embed_color)
    embed.set_thumbnail(url="https://media.api-sports.io/football/teams/42.png")

    # if need to change the way the tied users are displayed change "RANK()" to "DENSE_RANK()"
    leaderboard = await bot.pg_conn.fetch(f"SELECT DENSE_RANK() OVER(ORDER BY SUM(prediction_score) DESC) as rank, SUM(prediction_score) as score, user_id FROM predictionsbot.predictions WHERE prediction_score IS NOT NULL GROUP BY user_id ORDER BY SUM(prediction_score) DESC")

    prediction_dictionary = {}
    embed_dictionary = {}
    for prediction in leaderboard:
        if prediction.get("rank") not in prediction_dictionary:
            # embed_dictionary[prediction.get("rank")] = discord.Embed(title=f'Rank: {prediction.get("rank")}', description="", color=0x9c824a)
            prediction_dictionary[prediction.get("rank")] = [prediction]
        else:
            prediction_dictionary[prediction.get("rank")].append(prediction)
    
    # all_members = bot.get_all_members()
    
    rank_num = 1
    for k,v in prediction_dictionary.items():
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

    # embeds = [v for k,v in embed_dictionary.items()]
    # first_embed = True
    # for embed_fin in embeds:
    #     if first_embed:
    #         await ctx.send(f"{ctx.message.author.mention}", embed=embed_fin)
    #         first_embed = False
    #     else:
    #         await ctx.send(embed=embed_fin)
    
    # for prediction in leaderboard:
    #         if first:
    #             embed.add_field(name=prediction.get("rank"), value="test", inline=False)
    #             embed.add_field(name=f"{user.display_name}", value=f'{prediction.get("score")}', inline=True)
    #             first = False
    #         elif rank == prediction.get("rank"):
    #             embed.add_field(name=f"{user.display_name}", value=f'{prediction.get("score")}', inline=True)
    #         else:
    #             rank = prediction.get("rank")
    #             embed.add_field(name=prediction.get("rank"), value="test", inline=False)
    #             embed.add_field(name=f"{user.display_name}", value=f'{prediction.get("score")}', inline=True)
    #     except discord.NotFound as e:
    #         logger.exception(e, user=prediction.get('user_id'), method="leaderboard")

@bot.command()
async def timezone(ctx):
    '''
    Change timezone
    '''
    await checkUserExists(bot.pg_conn, ctx.message.author.id, ctx)

    msg = ctx.message.content
    try:
        tz = re.search("\+timezone (.*)", msg).group(1)
    except Exception as e:
        await ctx.send(f"{ctx.message.author.mention}\n\nYou didn't include a timezone!")
        return
    
    if tz in pytz.all_timezones:
        async with bot.pg_conn.acquire() as connection:
            async with connection.transaction():
                await connection.execute("UPDATE predictionsbot.users SET tz = $1 WHERE user_id = $2", tz, ctx.message.author.id)
        await ctx.send(f"{ctx.message.author.mention}\n\nYour timezone has been set to {tz}")
    else:
        await ctx.send(f"{ctx.message.author.mention}\n\nThat is not a recognized timezone!\nExpected format looks like: 'US/Mountain' or 'America/Chicago' or 'Europe/London'")

@bot.command()
async def next(ctx):
    '''
    Next matches
    '''
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
        await ctx.send(f"{ctx.message.author.mention}\n\nNumber of next matches cannot be a negative number.")
    elif count > 10:
        await ctx.send(f"{ctx.message.author.mention}\n\nNumber of next matches cannot be greater than 10.")
    else:
        next_matches = await nextMatches(bot.pg_conn, count=count)
        output = f"{ctx.message.author.mention}\n\n**Next {count} matches:**\n\n"
        for match in next_matches:
        # await ctx.send(f"{[match for match in next_matches]}")
        # todo: embed icons here
            output += await formatMatch(bot.pg_conn, match, ctx.message.author.id)
        await ctx.send(f"{output}")


#todo paginate some functions from +help

# # list fixtures
# @bot.command()
# async def fixtures(ctx):
#     '''
#     Full fixture list
#     '''

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
        team_id = getTeamId(team)
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
    done_matches_output = ""
    for match in done_matches:
        match_time = match.get("event_date")
        match_time = prepareTimestamp(match_time, user_tz)
        done_matches_output += f'{match_time} {match.get("home_name")} {match.get("goals_home")}-{match.get("goals_away")} {match.get("away_name")}\n'

    done_matches_output = f"```\n{done_matches_output}\n```"
    await ctx.send(f"{ctx.message.author.mention}\n\n{done_matches_output}")

# # PL table
# @bot.command()
# async def pltable(ctx):
#     '''
#     Current Premier League table
#     '''
#     pl_id = 524

# # CL table
# @bot.command()
# async def cltable(ctx):
#     '''
#     Current Champion's League table
#     '''        
#     cl_id = 530

# # EL table
# @bot.command()
# async def eltable(ctx):
#     '''
#     Current Europa League table
#     '''
#     el_id = 514

# # FA Cup table
# @bot.command()
# async def fatable(ctx):
#     '''
#     Current FA Cup table
#     '''        
#     fa_id = 956

# # League Cup table
# @bot.command()
# async def efltable(ctx):
#     '''
#     Current League Cup table
#     '''            


# # fixtures in progess
# @bot.command()
# async def inProgress(ctx):
#     pass


@bot.command()
async def ping(ctx):
    '''
    Return latency between bot and server
    '''
    log = logger.bind(content=ctx.message.content, author=ctx.message.author.name)
    latency = bot.latency
    log.info(latency=latency)
    await ctx.send(f"{ctx.message.author.mention}\n\nBot latency is {latency * 1000} milliseconds")

@bot.command(hidden=True)
async def echo(ctx, *, content:str):
    '''
    Repeat what you typed (for testing/debugging)
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
async def testembed(ctx):
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

# scheduled task configuration example
@tasks.loop(minutes=1)
async def loopOncePerDay():
    message_channel = bot.get_channel(channel_id)
    print(f"Got channel {message_channel}")
    await message_channel.send("Test scheduled message")


# @bot.command(hidden=True)
@tasks.loop(minutes=15)
async def updateFixtures():
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

    fixtures = await bot.pg_conn.fetch("SELECT fixture_id FROM predictionsbot.fixtures WHERE event_date < now() + interval '5 hour' AND event_date > now() + interval '-5 hour' AND NOT scorable")
    for fixture in fixtures:
        fixture_response = requests.get(f"http://v2.api-football.com/fixtures/id/{fixture.get('fixture_id')}", headers={'X-RapidAPI-Key': api_key}, timeout=5)
        fixture_info = fixture_response.json()['api']['fixtures'][0]

        match_completed = status_lookup[fixture_info.get("statusShort")]

        async with bot.pg_conn.acquire() as connection:
            async with connection.transaction():
                await connection.execute("UPDATE predictionsbot.fixtures SET goals_home = $1, goals_away = $2, scorable = $3 WHERE fixture_id = $4", fixture_info.get("goalsHomeTeam"), fixture_info.get("goalsAwayTeam"), match_completed, fixture.get('fixture_id'))
    
    logger.info(f"Updated fixtures table, {len(fixtures)} were changed.")
    # await bot.admin_id.send(f"Updated fixtures table, {len(fixtures)} were changed.")

@calculatePredictionScores.before_loop
async def before_calculatePredictionScores():
    await bot.wait_until_ready()
    # async sleep/wait here for bot to acquire db connection object
    await asyncio.sleep(10)

@updateFixtures.before_loop
async def before_updateFixtures():
    await bot.wait_until_ready()
    # async sleep/wait here for bot to acquire db connection object
    await asyncio.sleep(10)

@bot.event
async def onCommandError(ctx, error):
    logger.exception(f"Handling error `{error}` for {ctx.message.content}")
    if isinstance(error, IsNotAdmin):
        await ctx.send(f"You do not have permission to run `{ctx.message.content}`")
    if isinstance(error, RateLimit):
        await ctx.send(error)

#todo what is channel_id stuff doing
try:
    # scheduled task enabling only if channel is specified
    if channel_id != 0:
        loopOncePerDay.start()

    # disabling fixture update during testing mode, may need to be further tunable for testing.
    if not testing_mode:
        updateFixtures.start()
        calculatePredictionScores.start()
    logger.debug("test")
    logger.error("test error")
    bot.run(token)
except Exception as e:
    print(f"{e}")
    sys.exit(1)
    