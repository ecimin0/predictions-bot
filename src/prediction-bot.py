#!/usr/local/bin/python3

# pip3 install discord
import discord
from discord.ext import commands, tasks
import re
import sys
import os
import json
import requests
import asyncio
import asyncpg # postgres yay
import sqlalchemy
from dotenv import load_dotenv
from pprint import pprint
import psycopg2
import argparse
import random
import string

from datetime import timedelta, datetime
from psycopg2.extras import Json # import the new JSON method from psycopg2

player_nicknames = {
    "13298": ["cech"],
    "13299": ["burton"],
    "13300": ["olayinka"],
    "13301": ["mavropanos"],
    "13302": ["monreal", "nacho"],
    "13303": ["iwobi"],
    "13304": ["smith-rowe", "esr"],
    "13305": ["leno"],
    "13306": ["martinez", "emi"],
    "13307": ["macey"],
    "13308": ["iliev"],
    "13309": ["bellerin", "hector", "heccy"],
    "13310": ["tierney", "kt"],
    "13311": ["papastathopoulos", "sokratis"],
    "13312": ["holding", "rob"],
    "13313": ["mustafi"],
    "13314": ["chambers"],
    "13315": ["luiz"],
    "13316": ["kolasinac", "kola"],
    "13317": ["medley"],
    "13318": ["smith"],
    "13319": ["soares", "cedric"],
    "13320": ["bola"],
    "13321": ["mari"],
    "13322": ["osei-tutu"],
    "13323": ["saliba"],
    "13324": ["ozil", "mesut"],
    "13325": ["torreira"],
    "13326": ["maitland-niles", "amn"],
    "13327": ["willock"],
    "13328": ["guendouzi"],
    "13329": ["xhaka"],
    "13330": ["saka"],
    "13331": ["balogun"],
    "13332": ["elneny"],
    "13333": ["lacazette", "laca"],
    "13334": ["aubameyang", "auba"],
    "13335": ["pepe"],
    "13336": ["nelson"],
    "13337": ["nketiah", "eddie"],
    "13338": ["martinelli", "gabi"],
    "13339": ["john-jules"],
    "13340": ["mkhitaryan"],
    "13341": ["ceballos", "dani"]
}

# source environment variables
load_dotenv()

### aws postgres stuff
aws_dbuser = "postgres"
aws_dbpass = "2d9t728EAIRhtAcHW3Bw"
aws_dbhost = "predictions-bot-database.cdv2z684ki93.us-east-2.rds.amazonaws.com"
aws_db_ip = "3.15.92.33"
aws_dbname = "predictions-bot-data"

# use the token env var
token = os.environ.get("TOKEN", None)
channel_id = int(os.environ.get("CHANNELID", 0))

# bot only responds to commands prepended with '+'
prefix = "+"

# cleaner output of help function(s)
help_function = commands.DefaultHelpCommand(no_category="Available Commands", indent=4)
bot = commands.Bot(prefix, help_command=help_function)

# team id of team in API to use as main team
main_team = 42 # arsenal


def getPlayerId(userInput):
    for k,v in player_nicknames.items():
        if userInput.lower() in v:
            return k
    raise Exception(f"no player by that name {userInput}")

### generate random prediction ID
def get_random_alphanumeric_string(length):
    letters_and_digits = string.ascii_letters + string.digits
    result_str = ''.join((random.choice(letters_and_digits) for i in range(length)))
    return result_str

# use something like these functions to get data from db
#  bot.pg_conn.fetch("<sql>")
# returns array of fixtures (even for one)
async def nextMatches(dbconn, count=1):
    '''
    Return the array of next fixtures records from Database 
    '''
    matches = await dbconn.fetch(f"SELECT home, away, fixture_id, league_id, event_date, goals_home, goals_away, new_date, (SELECT name FROM predictionsbot.teams t WHERE t.team_id = f.home) AS home_name, (SELECT name FROM predictionsbot.teams t WHERE t.team_id = f.away) AS away_name FROM predictionsbot.fixtures f WHERE event_date > now() AND (home = {main_team} OR away = {main_team}) ORDER BY event_date LIMIT $1;", count)
    return matches

# returns record (no array)
async def nextMatch(dbconn):
    '''
    Return the next fixture record from Database 
    '''
    match = await dbconn.fetchrow(f"SELECT home, away, fixture_id, league_id, event_date, goals_home, goals_away, new_date, (SELECT name FROM predictionsbot.teams t WHERE t.team_id = f.home) AS home_name, (SELECT name FROM predictionsbot.teams t WHERE t.team_id = f.away) AS away_name FROM predictionsbot.fixtures f WHERE event_date > now() AND (home = {main_team} OR away = {main_team}) ORDER BY event_date LIMIT 1;")
    return match

async def completedMatches(dbconn, count=1, offset=0):
    '''
    Return the array of completed fixtures records from Database 
    '''
    matches = await dbconn.fetch(f"SELECT home, away, fixture_id, league_id, event_date, goals_home, goals_away, new_date, (SELECT name FROM predictionsbot.teams t WHERE t.team_id = f.home) AS home_name, (SELECT name FROM predictionsbot.teams t WHERE t.team_id = f.away) AS away_name FROM predictionsbot.fixtures f WHERE event_date + interval '2 hour' < now() AND (home = {main_team} OR away = {main_team}) ORDER BY event_date LIMIT $1 OFFSET $2;", count, offset)
    return matches

### database operations ###
async def connectToDB():
    try:
        bot.pg_conn = await asyncpg.create_pool(user=aws_dbuser, password=aws_dbpass, database=aws_dbname, host=aws_db_ip)
        print("Connected to postgres")
    except Exception as e:
        print(f"{e}")
        sys.exit(1)


async def getUserPredictions(dbconn, user_id):
    '''
    Return the last 10 predictions by user
    '''
    predictions = await dbconn.fetch("SELECT * FROM predictionsbot.fixtures ON j.team_id = t.team_id WHERE event_date > now() AND (home = 42 OR away = 42) ORDER BY event_date LIMIT 10;")
    return predictions


### Bot Events ###
# on_ready = connected to server
@bot.event
async def on_ready(): 
    # async connect to postgres
    await connectToDB()
    print(f'connected to {[ guild.name for guild in bot.guilds ]} as {bot.user}')

# mostly for debugging in terminal, doesn't do anything on Discord
@bot.event
async def on_message(message):
    # if the bot sends messages to itself, don't return anything
    if message.author == bot.user:
        return
    if message.channel.name == 'test-predictions-bot':
        print(f"@{message.author} | {message.author.id} | {message.content} | {message.channel}")
        await bot.process_commands(message)


### Bot Commands ###
# Predict next match
rules_set = """**Predict our next match against $next_opponent**

** Prediction League Rules: **

2 points – correct result (W/D/L)
2 points – correct number of Arsenal goals
1 point – correct number of goals conceded
1 point – each correct scorer
1 point – correct FGS (first goal scorer, only Arsenal)
2 points bonus – all scorers correct

- Players you predict to score multiple goals should be entered as "player x2" or "player 2x"

- No points for scorers if your prediction's goals exceed the actual goals by 4+

** Remember, we are only counting Arsenal goal scorers **
    - Do not predict opposition goal scorers
    - Do not predict opposition FGS

Example:
+predict 3:0 auba 2x fgs, laca
"""

# rules
@bot.command()
async def rules(ctx):
    # these 3 quote blocks in all of the commands are returned when user enters +help
    '''
    Display Prediction League Rules
    '''
    await ctx.send(f"{ctx.message.author.mention}\n{rules_set}")

async def getRandomTeam(dbconn):
    team = await dbconn.fetchrow("SELECT * FROM predictionsbot.teams WHERE team_id != 42 ORDER BY random() LIMIT 1;")
    return team.get("name")
    

# predict
@bot.command()
async def predict(ctx):
    '''
    Make a new prediction
    '''
    current_match = await nextMatch(bot.pg_conn)
    time_limit = current_match.get("event_date") - timedelta(hours=2)
    fixture_id = current_match.get('fixture_id')

    opponent = current_match.get('away_name')
    if current_match.get('away') == main_team:
        opponent = current_match.get('home_name')

    if datetime.utcnow() > time_limit:
        team = await getRandomTeam(bot.pg_conn)
        await ctx.send(f"{ctx.message.author.mention}\nError: time is too late, go support {team} instead.")
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
                num_goals = goals_scored.group(1)

            # append dictionary of scorer names, fgs status, goals predicted to properties array
            scorer_dict = {"name": player.strip(), "fgs": fgs, "num goals": num_goals}
            scorer_properties.append(scorer_dict)

        # player_match = re.search(player_regex, temp_msg, re.IGNORECASE)
        # temp_msg = re.sub(player_regex, "", temp_msg)

    except Exception as e:
        print(f"{e}")
        await ctx.send(f"FAILED: {e}")
    
    if not goals_match:
        print("Missing goals")
        await ctx.send(f"{ctx.message.author.mention}\nDid not provide a match score in your prediction.\n{ctx.message.content}")
    else:
        message_timestamp = datetime.utcnow()
        
        # football home teams listed first
        home_goals = goals_match.group(2)
        # football away teams listed second
        away_goals = goals_match.group(3)

    
    # if prediction syntax was OK load it into the db
    # tell the user their prediction was logged and show it to them
    try:
        for scorer in scorer_properties:
            try:
                print(f"{getPlayerId(scorer.get('name'))}")
            except Exception as e:
                await ctx.send(f"Please try again, {e}")
                return 
            

        prediction_id = get_random_alphanumeric_string(16)
        print(f"{prediction_id}, {ctx.message.author.id}, {prediction_string}")
        # use similar syntax as 300-305 for any insert/update to the db
        async with bot.pg_conn.acquire() as connection:
            async with connection.transaction():
                try:
                    await connection.execute("INSERT INTO predictionsbot.predictions (prediction_id, user_id, prediction_string, fixture_id) VALUES ($1, $2, $3, $4);", prediction_id, str(ctx.message.author.id), prediction_string, fixture_id)
                except Exception as e:
                    print(e)

        await ctx.send(f"""{ctx.message.author.mention}
        **Prediction against {opponent} successful.**

        You have until {time_limit} UTC to edit your prediction.

        {ctx.message.content}

        **Score**
        Home {home_goals} : {away_goals} Away

        **Goal Scorers**
        {[scorer.get("name") for scorer in scorer_properties]}""")

    except (Exception) as e:    
        print(f"{e}")

# todo
# init discord user into db
#make a function to do this

# check if user has made predciton for current match
# logic to update that prediction

# add TZ field for users

# score in predictions table

# timestamp on predictions

# add seperate prediction data fields to table

# show user's predictions
@bot.command()
async def predictions(ctx):
    '''
    Show your past predictions
    '''
    discord_document = await getUserPredictions(bot.pg_conn, ctx.message.author.id)

    pprint(discord_document)
    await ctx.send(f"{ctx.message.author.mention}\n{discord_document}")


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

# next 2 matches of each competition
@bot.command()
async def next(ctx):
    '''
    Next 2 matches in each competition
    '''
    # todo format this better
    next_matches = await nextMatches(bot.pg_conn, count=2)
    await ctx.send(f"{[match for match in next_matches]}")

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
    Return next match against given team | when <team>
    '''
    # todo lookup table for team abbrevs (like players)

# results
@bot.command()
async def results(ctx):
    '''
    Return historical match results
    '''
    done_matches = await completedMatches(bot.pg_conn, count=10)
    done_matches_output = ""
    for match in done_matches:
        done_matches_output += f'{match.get("event_date")} {match.get("home_name")} vs. {match.get("away_name")} {match.get("goals_home")}-{match.get("goals_away")}\n'

    done_matches_output = f"```\n{done_matches_output}\n```"
    await ctx.send(f"{done_matches_output}")

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
# EFL Cup
@bot.command()
async def efltable(ctx):
    '''
    Current League Cup table
    '''            
    efl_id = 955

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
    await ctx.send(f"{ctx.message.author.mention}\n{latency}")


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
    await ctx.send(f"{ctx.message.author.mention}\n{spurs_status}\n{video}")

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
    