#!/usr/local/bin/python3

import discord
import re
import sys
import os
import json
import requests
import asyncio
import asyncpg # postgres yay
import pytz
import argparse
import random
import string

from discord.ext import commands, tasks
from datetime import timedelta, datetime
from dotenv import load_dotenv
from pprint import pprint


player_nicknames = {
    "13606": ["olayinka"],
    "13609": ["smith-rowe", "esr"],
    "13587": ["leno"],
    "13589": ["martinez", "emi"],
    "13588": ["macey"],
    "13586": ["iliev"],
    "13591": ["bellerin", "hector", "heccy"],
    "13601": ["tierney", "kt"],
    "13599": ["papastathopoulos", "sokratis"],
    "13594": ["holding", "holdinho"],
    "13598": ["mustafi"],
    "13592": ["chambers"],
    "13597": ["luiz"],
    "13595": ["kolasinac", "kola"],
    "13590": ["soares", "cedric"],
    "13596": ["mari"],
    "13600": ["saliba"],
    "13607": ["ozil", "mesut"],
    "13610": ["torreira"],
    "13605": ["maitland-niles", "amn"],
    "13611": ["willock"],
    "13604": ["guendouzi"],
    "13612": ["xhaka"],
    "13608": ["saka"],
    "13603": ["elneny"],
    "13615": ["lacazette", "laca"],
    "13613": ["aubameyang", "auba"],
    "13619": ["pepe"],
    "13617": ["nelson"],
    "13618": ["nketiah", "eddie"],
    "13616": ["martinelli", "gabi"],
    "13585": ["john-jules"],
    "13602": ["ceballos", "dani"],
    "13614": ["willian"],
    "13593": ["gabriel"]
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
    60: ["west brom", "west bromwich albion"], 
    46: ["leicester", "leicester city"], 
    48: ["west ham", "west ham united", "hammers"], 
    34: ["newcastle", "newcastle united"], 
    51: ["brighton", "brighton and hove albion"], 
    49: ["chelsea"], 
    62: ["sheffield united", "sheffield"],
    39: ["wolves", "wolverhampton"]
}


# 2020-2021 season
pl_id = 2790
cl_id = 2771
el_id = 2777
fa_cup_id = 2791
league_cup_id = 2781


# source environment variables
load_dotenv()

utc = pytz.timezone("UTC")

### aws postgres stuff
aws_dbuser = "postgres"
aws_dbpass = os.environ.get("AWS_DBPASS", None)
aws_dbhost = "predictions-bot-database.cdv2z684ki93.us-east-2.rds.amazonaws.com"
aws_db_ip = "3.15.92.33"
aws_dbname = "predictions-bot-data"

# team id of team in API to use as main team
main_team = 42 # arsenal

time_format = "%m/%d/%Y, %H:%M:%S %Z"
match_select = f"home, away, fixture_id, league_id, event_date, goals_home, goals_away, new_date, (SELECT name FROM predictionsbot.teams t WHERE t.team_id = f.home) AS home_name, (SELECT name FROM predictionsbot.teams t WHERE t.team_id = f.away) AS away_name, (SELECT name FROM predictionsbot.leagues t WHERE t.league_id = f.league_id) as league_name, CASE WHEN away = 42 THEN home ELSE away END as opponent, (SELECT name FROM predictionsbot.teams t WHERE t.team_id = (CASE WHEN f.away = 42 THEN f.home ELSE f.away END)) as opponent_name, CASE WHEN away = {main_team} THEN 'away' ELSE 'home' END as home_or_away"


# use the token env var
token = os.environ.get("TOKEN", None)
channel_id = int(os.environ.get("CHANNELID", 0))

# bot only responds to commands prepended with '+'
prefix = "+"

# cleaner output of help function(s)
help_function = commands.DefaultHelpCommand(no_category="Available Commands", indent=4)
bot = commands.Bot(prefix, help_command=help_function)


def getPlayerId(userInput):
    for k,v in player_nicknames.items():
        if userInput.lower() in v:
            return k
    raise Exception(f"no player by that name {userInput}")

def getTeamId(userInput):
    for k,v in team_nicknames.items():
        if userInput.lower() in v:
            return k
    raise Exception(f"no team by that name {userInput}")

### generate random prediction ID
def get_random_alphanumeric_string(length):
    letters_and_digits = string.ascii_letters + string.digits
    result_str = ''.join((random.choice(letters_and_digits) for i in range(length)))
    return result_str

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
#  bot.pg_conn.fetch("<sql>")
# returns array of fixtures (even for one)
async def nextMatches(dbconn, count=1):
    '''
    Return the array of next fixtures records from Database 
    '''
    matches = await dbconn.fetch(f"SELECT {match_select} FROM predictionsbot.fixtures f WHERE event_date > now() AND (home = {main_team} OR away = {main_team}) ORDER BY event_date LIMIT $1;", count)
    return matches

# returns record (no array)
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
    matches = await dbconn.fetch(f"SELECT {match_select} FROM predictionsbot.fixtures f WHERE event_date + interval '2 hour' < now() AND (home = {main_team} OR away = {main_team}) ORDER BY event_date LIMIT $1 OFFSET $2;", count, offset)
    return matches

async def formatMatch(dbconn, match, user):
    tz = await getUserTimezone(dbconn, user)
    match_time = prepareTimestamp(match.get('event_date'), tz)

    time_until_match = (match.get('event_date') - datetime.now()).total_seconds()
    return f"{match.get('league_name')}\n\({match.get('home_or_away')}\) vs {match.get('opponent_name')}\n{match_time}\n*match starts in {time_until_match // 86400:.0f} days, {time_until_match // 3600 %24:.0f} hours, and {time_until_match // 60 %60:.0f} minutes*\n\n" 

### database operations ###
async def connectToDB():
    try:
        bot.pg_conn = await asyncpg.create_pool(user=aws_dbuser, password=aws_dbpass, database=aws_dbname, host=aws_db_ip)
        print("Connected to postgres")
    except Exception as e:
        print(f"{e}")
        sys.exit(1)

async def getAdminDiscordId():
    try:
        bot.admin_id = await bot.fetch_user("249231078303203329")
        await bot.admin_id.send(f"found admin ID {bot.admin_id}")
    except Exception as e:
        print(f"{e}")

async def getUserPredictions(dbconn, user_id):
    '''
    Return the last 10 predictions by user
    '''
    predictions = await dbconn.fetch("SELECT * FROM predictionsbot.predictions WHERE user_id = $1 ORDER BY timestamp DESC LIMIT 10;", user_id)
    return predictions


async def checkUserExists(dbconn, user_id, ctx):
    user = await dbconn.fetch("SELECT * FROM predictionsbot.users WHERE user_id = $1", user_id)

    if not user:
        async with bot.pg_conn.acquire() as connection:
            async with connection.transaction():
                try:
                    await connection.execute("INSERT INTO predictionsbot.users (user_id, tz) VALUES ($1, $2);", user_id, "UTC")
                except Exception as e:
                    print(e)
        # return False
        # await ctx.send(f"{ctx.message.author.mention}\n\nHello, this is the Arsenal Discord Predictions League\n\nType `+rules` to see the rules for the league\n\nEnter `+help` for a help message")
    else:
        return True

### Bot Events ###
# on_ready = connected to server
@bot.event
async def on_ready(): 
    # async connect to postgres
    await connectToDB()
    await getAdminDiscordId()
    print(f'connected to {[ guild.name for guild in bot.guilds ]} as {bot.user}')


# mostly for debugging in terminal, doesn't do anything on Discord
@bot.event
async def on_message(message):
    # if the bot sends messages to itself, don't return anything
    if message.author == bot.user:
        return
    # if message.channel.name == 'test-predictions-bot': # TEST #kubernauts
    if message.channel.name == 'prediction-league': # PROD #gunners
        #todo print(f"{bot.guild} | @{message.author} | {message.author.id} | {message.content}")
        print(f"@{message.author} | {message.author.id} | {message.content}")
        await bot.process_commands(message)


### Bot Commands ###
# Predict next match
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
#todo code block on prediction example above

# rules
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
    

# predict
@bot.command()
async def predict(ctx):
    '''
    Make a new prediction
    '''
    #checkUserExists inserts the user_id if not present
    #todo should we split this into checkUserExists() and insertUser() ?
    await checkUserExists(bot.pg_conn, str(ctx.message.author.id), ctx)

    current_match = await nextMatch(bot.pg_conn)
    user_tz = await getUserTimezone(bot.pg_conn, str(ctx.message.author.id))

    #todo
    # if premier league then timedelta(hours=1)
    # elif europa league then timedelta(hours=1.5)
    time_limit = current_match.get("event_date") - timedelta(hours=2)
    time_limit_str = prepareTimestamp(time_limit, user_tz)
    time_limit = prepareTimestamp(time_limit, user_tz, str=False)

    fixture_id = current_match.get('fixture_id')

    opponent = current_match.get('opponent_name')

    if utc.localize(datetime.utcnow()) > time_limit:
        team = await getRandomTeam(bot.pg_conn)
        await ctx.send(f"{ctx.message.author.mention}\n\nError: prediction time too close to match start time. Go support {team} instead.")
        return

    # raw incoming messaged typed by user
    temp_msg = ctx.message.content

    goals_regex = r"((\d) ?[:-] ?(\d))"
    player_regex = r"[A-Za-z]{1,18}[,]? ?(\dx|x\d)?"

    try:
        # remove '+predict ' from message string
        prediction_string = temp_msg
        temp_msg = temp_msg.replace("+predict ", "")
        # print(temp_msg)

        # store string matching the score/goals in the prediction
        goals_match = re.search(goals_regex, temp_msg)
        
        # remove goals string from raw message
        temp_msg = re.sub(goals_regex, "", temp_msg)

        # store string of player names in prediction
        scorers = temp_msg.strip().split(",")

        # convert scoring player names into array
        scorers = [player.strip() for player in scorers]

        # initial array to score scorer details
        scorer_properties = []

        # initialize fgs and num goals to False/1 for each scorer
        for player in scorers:
            if not player:
                continue
            fgs = False
            num_goals = 1

            # if predicted fgs flag as True and remove 'fgs' from string
            if "fgs" in player:
                fgs = True
                player = player.replace("fgs", "")

            # number of goals scored by player(s)
            goals_scored = re.search(r'x?(\d)x?', player)
            if goals_scored:
                player = re.sub(r'x?(\d)x?', "", player)
                num_goals = int(goals_scored.group(1))

            fgs_str = ""
            if fgs:
                fgs_str = "fgs"

            # append dictionary of scorer names, fgs status, goals predicted to properties array
            scorer_dict = {"name": player.strip(), "fgs": fgs, "num_goals": num_goals, "fgs_string": fgs_str}
            scorer_properties.append(scorer_dict)

        # player_match = re.search(player_regex, temp_msg, re.IGNORECASE)
        # temp_msg = re.sub(player_regex, "", temp_msg)

    except Exception as e:
        print(f"{e}")
        await ctx.send(f"FAILED: {e}")
    
    if not goals_match:
        # print("Missing goals")
        await ctx.send(f"{ctx.message.author.mention}\n\nDid not provide a match score in your prediction.\n{ctx.message.content}")
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


    # if prediction syntax was OK load it into the db
    try:
        for scorer in scorer_properties:
            try:
                getPlayerId(scorer.get('name'))
                # print(f"{getPlayerId(scorer.get('name'))}")
            except Exception as e:
                await ctx.send(f"Please try again, {e}")
                return 
            

        prediction_id = get_random_alphanumeric_string(16)
        # print(f"{prediction_id}, {ctx.message.author.id}, {prediction_string}")
        # use similar syntax as next 5 lines for any insert/update to the db
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
                    prev_prediction = await connection.fetchrow("SELECT * FROM predictionsbot.predictions WHERE user_id = $1 AND fixture_id = $2", str(ctx.message.author.id), fixture_id)
                    if prev_prediction:
                        await connection.execute(f"UPDATE predictionsbot.predictions SET prediction_string = $1, home_goals = $2, away_goals = $3, scorers = $4::json, timestamp = now() WHERE user_id = $5 AND fixture_id = $6", prediction_string, home_goals, away_goals, scorer_properties, str(ctx.message.author.id), fixture_id)
                    else:
                        await connection.execute("INSERT INTO predictionsbot.predictions (prediction_id, user_id, prediction_string, fixture_id, home_goals, away_goals, scorers) VALUES ($1, $2, $3, $4, $5, $6, $7);", prediction_id, str(ctx.message.author.id), prediction_string, fixture_id, home_goals, away_goals, scorer_properties)
                except Exception as e:
                    print(e)
                    await ctx.send("There was an error adding your prediction, please try again later.")
                    # await client.send_message(bot.admin_id, f"Error with prediction {prediction_string}")
                    return

        goal_scorers_array = [f'{scorer.get("name")}: {scorer.get("num_goals")} {scorer.get("fgs_string")}' for scorer in scorer_properties]
        goal_scorers = "\n".join(goal_scorers_array)

        # tell the user their prediction was logged and show it to them
        output = f"""{ctx.message.author.mention}\n**Prediction against {opponent} successful.**\n\nYou have until {time_limit_str} to edit your prediction.\n\n`{ctx.message.content}`"""
        output += f"""\n\n**Score**\n{current_match.get('home_name')} {home_goals} : {away_goals} {current_match.get('away_name')}\n\n"""
        if goal_scorers:
            output += f"""**Goal Scorers**\n{goal_scorers}"""
        await ctx.send(output)

    except (Exception) as e:
        print(f"{e}")



# todo print real palyer name in prediction ouptut to user

# todo add scoring function/scheduled task

# todo fix sending errors to admin account




# show user's predictions
@bot.command()
async def predictions(ctx):
    '''
    Show your past predictions
    '''
    #todo: format user predictions

    await checkUserExists(bot.pg_conn, str(ctx.message.author.id), ctx)
    discord_document = await getUserPredictions(bot.pg_conn, str(ctx.message.author.id))

    # pprint(discord_document)
    output = f"{ctx.message.author.mention}\n\n"
    for prediction in discord_document:
        # todo: get actual fixture vs and date?
        output += f'Fixture ID: `{prediction.get("fixture_id")}` | `{prediction.get("prediction_string")}` | Score: `{prediction.get("prediction_score")}`'
    await ctx.send(f"{output}")


# show leaderboard
@bot.command()
async def leaderboard(ctx):
    '''
    Show leaderboard
    '''        

# change timezone
@bot.command()
async def timezone(ctx):
    '''
    Change timezone
    '''
    await checkUserExists(bot.pg_conn, str(ctx.message.author.id), ctx)

    msg = ctx.message.content
    try:
        tz = re.search("\+timezone (.*)", msg).group(1)
    except Exception as e:
        await ctx.send(f"{ctx.message.author.mention}\n\nYou didn't include a timezone!")
        return
    
    if tz in pytz.all_timezones:
        async with bot.pg_conn.acquire() as connection:
            async with connection.transaction():
                await connection.execute("UPDATE predictionsbot.users SET tz = $1 WHERE user_id = $2", tz, str(ctx.message.author.id))
        await ctx.send(f"{ctx.message.author.mention}\n\nYour timezone has been set to {tz}")
    else:
        await ctx.send(f"{ctx.message.author.mention}\n\nThat is not a recognized timezone!\nExpected format looks like: 'US/Mountain' or 'America/Chicago' or 'Europe/London'")


# next matches
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
            await ctx.send(f"{ctx.message.author.mention}\n\nExpected usage:\n`+next <number>`")
            return
    else: 
        count = 2
    
    next_matches = await nextMatches(bot.pg_conn, count=count)
    output = f"{ctx.message.author.mention}\n\n**Next {count} matches:**\n\n"
    for match in next_matches:
    # await ctx.send(f"{[match for match in next_matches]}")
    # todo: embed icons here
        output += await formatMatch(bot.pg_conn, match, str(ctx.message.author.id))
    await ctx.send(f"{output}")


# list fixtures
@bot.command()
async def fixtures(ctx):
    '''
    Full fixture list
    '''

# show match vs specific team
@bot.command()
async def when(ctx):
    '''
    Return next match against given team | +when <team>
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
    next_match = await formatMatch(bot.pg_conn, next_match, str(ctx.message.author.id))
    await ctx.send(f"{ctx.message.author.mention}\n\n{next_match}")

# results
@bot.command()
async def results(ctx):
    # todo get results from all leagues and cap results by season
    '''
    Return historical match results
    '''
    done_matches = await completedMatches(bot.pg_conn, count=10)
    done_matches_output = ""
    for match in done_matches:
        done_matches_output += f'{match.get("event_date")} {match.get("home_name")} {match.get("goals_home")}-{match.get("goals_away")} {match.get("away_name")}\n'

    done_matches_output = f"```\n{done_matches_output}\n```"
    await ctx.send(f"{ctx.message.author.mention}\n\n{done_matches_output}")

# PL table
@bot.command()
async def pltable(ctx):
    '''
    Current Premier League table
    '''
    pl_id = 524

# CL table
@bot.command()
async def cltable(ctx):
    '''
    Current Champion's League table
    '''        
    cl_id = 530

# EL table
@bot.command()
async def eltable(ctx):
    '''
    Current Europa League table
    '''
    el_id = 514

# FA Cup table
@bot.command()
async def fatable(ctx):
    '''
    Current FA Cup table
    '''        
    fa_id = 956

# League Cup table
@bot.command()
async def efltable(ctx):
    '''
    Current League Cup table
    '''            


# ping
@bot.command()
async def ping(ctx):
    '''
    Return latency between bot and server
    '''
    # Get the latency of the bot
    # Included in the Discord.py library
    latency = bot.latency
    # Send it to the user
    await ctx.send(f"{ctx.message.author.mention}\n\n{latency}")


# echo, mostly for testing
@bot.command(hidden=True)
async def echo(ctx, *, content:str):
    '''
    Repeat what you typed (for testing/debugging)
    '''    
    await ctx.send(content)


# tottenham is shit
@bot.command(hidden=True)
async def what_do_you_think_of_tottenham(ctx):
    '''
    Who do we think is shit?
    '''
    video = "https://www.youtube.com/watch?v=w0R7gWf-nSA"
    spurs_status = "SHIT"
    await ctx.send(f"{ctx.message.author.mention}\n\n{spurs_status}\n{video}")


# scheduled task configuration example
@tasks.loop(minutes=1)
async def called_once_a_day():
    message_channel = bot.get_channel(channel_id)
    print(f"Got channel {message_channel}")
    await message_channel.send("Test scheduled message")


@called_once_a_day.before_loop
async def before():
    await bot.wait_until_ready()
    print("Finished waiting")


# 'token' is the bot token from Discord Developer config
try:
    # Scheduled task enabling only if channel is specified.
    if channel_id != 0:
        called_once_a_day.start()
    bot.run(token)
except Exception as e:
    print(f"{e}")
    sys.exit(1)
    