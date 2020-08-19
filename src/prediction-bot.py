#!/usr/local/bin/python3

# pip3 install discord
import discord
from discord.ext import commands
import re
import sys
import os
import json
import datetime
import requests
import asyncio
import asyncpg # postgres yay
import sqlalchemy
from dotenv import load_dotenv
from pprint import pprint
# import asyncio
import psycopg2
from psycopg2.extras import Json # import the new JSON method from psycopg2
import argparse
import random
import string


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

# bot only responds to commands prepended with '+'
prefix = "+"

# cleaner output of help function(s)
help_function = commands.DefaultHelpCommand(no_category="Available Commands", indent=4)
bot = commands.Bot(prefix, help_command=help_function)

# team id of team in API to use as main team
main_team = "42" # arsenal


# class Players()
#     def __init__(self, timestamp, user_id, name, prediction_id, prediction_string, hg, ag, scorers)


### generate random prediction ID
def get_random_alphanumeric_string(length):
    letters_and_digits = string.ascii_letters + string.digits
    result_str = ''.join((random.choice(letters_and_digits) for i in range(length)))
    return result_str


# def nextMatch(league):


### database operations ###
async def connectToDB():
    try:
        postgresconnection = await asyncpg.create_pool(user=aws_dbuser, password=aws_dbpass, database=aws_dbname, host=aws_db_ip)
        print("Connected to postgres")
            # postgresconnection.autocommit = True
            # pgcursor = await postgresconnection.cursor()

    #         with psycopg2.connect("postgres://{0}:{1}@{2}:5432/{3}".format(aws_dbuser, aws_dbpass, aws_dbhost, aws_dbname)) as postgresconnection:
    #             postgresconnection.autocommit = True
    #             pgcursor = postgresconnection.cursor()
    #             print("connected to postgres\n")
    except Exception as e:
        print(f"{e}")
        # postgresconnection.rollback()
        sys.exit(1)


# async def dbInsertPrediction(time, user_id, name, predict_id, prediction, hg, ag, scorers):
#     await pgcursor.execute("INSERT INTO predictionsbot.leagues (league_id, name, season, logo, country) VALUES (%s, %s, %s, %s, %s);", (league.get("league_id"), league.get("name"), league.get("season"), league.get("logo"), league.get("country")))
#     connection = await bot.pgconnection.acquire()
#     # testprint = await bot.pgconnection.fetchrow("SELECT * FROM predictionsbot.teams WHERE team_id = $1", (42))
#     print(testprint)


# async def getUserPredictions(user_id):
#     document = await database['predictions'].find({"user_id": user_id}).to_list(5)
    
    # pprint(document[1]['timestamp'])
    # return document


### Bot Events ###
@bot.event
# on_ready = connected to server
async def on_ready(): 
    print(f'connected to {[ guild.name for guild in bot.guilds ]} as {bot.user}')

    # async connect to postgres
    await connectToDB()

# mostly for debugging in terminal, doesn't do anything on Discord
@bot.event
async def on_message(message):
    # if the bot sends messages to itself, don't return anything
    if message.author == bot.user:
        return
    if message.channel.name == 'test-predictions-bot':
        print(f"@{message.author} | {message.author.id} | {message.content}")
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
    # connection = await bot.pgconnection.acquire()
    # testprint = await bot.pgconnection.fetchrow("SELECT * FROM predictionsbot.teams WHERE team_id = $1", (42))
    # print(testprint)
    await ctx.send(f"{ctx.message.author.mention}\n{rules_set}")


# predict
@bot.command()
async def predict(ctx):
    '''
    Make a new prediction
    '''

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
                player.replace("fgs", "")

            # number of goals scored by player(s)
            goals_scored = re.search(r'x?(\d)x?', player)
            if goals_scored:
                player = re.sub(r'x?(\d)x?', "", player)
                num_goals = goals_scored.group(1)

            # append dictionary of scorer names, fgs status, goals predicted to properties array
            scorer_dict = {"name": player, "fgs": fgs, "num goals": num_goals}
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
        message_timestamp = datetime.datetime.utcnow()
        
        # football home teams listed first
        home_goals = goals_match.group(2)
        # football away teams listed second
        away_goals = goals_match.group(3)

    
    # if prediction syntax was OK load it into the db
    # tell the user their prediction was logged and show it to them
    try:
        prediction_id = get_random_alphanumeric_string(16)
        print(f"{prediction_id}, {ctx.message.author.id}, {prediction_string}")
        pgcursor.execute("INSERT INTO predictionsbot.predictions (prediction_id, user_id, prediction_string) VALUES (%s, %s, %s);", (prediction_id, ctx.message.author.id, prediction_string))

        await ctx.send(f"""{ctx.message.author.mention}
        **Prediction against $opponent successful.**

        You have $time_until_next_match-2hr to edit your prediction.

        {ctx.message.content}

        **Score**
        Home {home_goals} : {away_goals} Away

        **Goal Scorers**
        {scorers}""")

    except (Exception) as e:    
            print(f"{e}")
            postgresconnection.rollback()



# show user's predictions
@bot.command()
async def predictions(ctx):
    '''
    Show your past predictions
    '''
    discord_document = await getUserPredictions(ctx.message.author.id)

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

# results
@bot.command()
async def results(ctx):
    '''
    Return historical match results
    '''        

# PL table
@bot.command()
async def pltable(ctx):
    '''
    Current Premier League table
    '''        

# CL table
@bot.command()
async def cltable(ctx):
    '''
    Current Champion's League table
    '''        

# EL table
@bot.command()
async def eltable(ctx):
    '''
    Current Europa League table
    '''

# FA Cup table
@bot.command()
async def fatable(ctx):
    '''
    Current FA Cup table
    '''        

# League Cup table
# EFL Cup
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



# bot.load_extension("cogs.MainCog")

# 'token' is the bot token from Discord Developer config
try:
    # with psycopg2.connect("postgres://{0}:{1}@{2}:5432/{3}".format(aws_dbuser, aws_dbpass, aws_dbhost, aws_dbname)) as postgresconnection:
    #     postgresconnection.autocommit = True
    #     pgcursor = postgresconnection.cursor()
    #     print("connected to postgres")
    bot.run(token)
except Exception as e:
    print(f"{e}")
    # postgresconnection.rollback()
    sys.exit(1)
    