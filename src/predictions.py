#!/usr/local/bin/python3

# pip3 install discord
import discord
from discord.ext import commands
import re
import sys
import os
import datetime
import motor.motor_asyncio
import asyncio
from dotenv import load_dotenv
from pprint import pprint

load_dotenv()

# Predict our next match against West Ham United (A)
rules_set = """** Prediction League Rules: **

2 points – correct result (W/D/L)
2 points – correct number of Arsenal goals
1 point – correct number of goals conceded
1 point – each correct scorer
1 point – correct FGS (first goal scorer, only Arsenal)
2 points bonus – correct all scorers

- Players you predict to score multiple goals should be entered as "player x2" or "player 2x"

- No points for scorers if your prediction's goals exceed the actual goals by 4+

** Remember, we are only counting Arsenal goal scorers **
    - Do not predict opposition goal scorers
    - Do not predict opposition FGS

Example:
+predict 3:0 auba 2x fgs, laca
"""

# initialize connection to mongod
mongodb= motor.motor_asyncio.AsyncIOMotorClient('mongodb://localhost:27017')
print("Connected to mongodb")

# select database
database = mongodb.users
print(f"Connected to mongo database: {database.name}")

# select collection
collection = database['predictions']
print(f"Connected to collection: {collection.name}")


token = os.environ.get("TOKEN", None)

prefix = "+"
help_function = commands.DefaultHelpCommand(no_category="Available Commands", indent=4)
bot = commands.Bot(prefix, help_command=help_function)

# print() statements print to stdout, not Discord
# ctx.send() sends messages via Discord

# class Players()
#     def __init__(self, timestamp, user_id, name, prediction_id, prediction_string, hg, ag, scorers)


async def do_insert(time, msg_id, name, predict_id, prediction, hg, ag, scorers):
    document = {
        'timestamp': time,
        'user_id': msg_id,
        'user_name': name,
        'prediction_id': predict_id,
        'prediction_string': prediction,
        'home_goals': hg,
        'away_goals': ag,
        'scorers': scorers
        }
    result = await database['predictions'].insert_one(document)
    print('result %s' % repr(result.inserted_id))


async def do_find_one(user_id):
    document = await database['predictions'].find({"user_id": user_id}).to_list(10)
    pprint(document)


### Bot Events ###
@bot.event
# on_ready = connected to server
async def on_ready(): 
    print(f'Connected to {[ guild.name for guild in bot.guilds ]} as {bot.user}')


# mostly for debugging, doesn't do anything on Discord
@bot.event
async def on_message(message):
    # if the bot sends messages to itself, don't return anything
    if message.author == bot.user:
        return
    if message.channel.name == 'test-predictions-bot':
        print(f"@{message.author} | {message.author.id} | {message.content}")
        await bot.process_commands(message)


### Bot Commands ###
# rules
@bot.command()
async def rules(ctx):
    # these 3 quote blocks are returned when user enters +help
    '''
    Display Prediction League Rules
    '''
    await ctx.send(f"{ctx.message.author.mention}\n{rules_set}")


# predict
@bot.command()
async def predict(ctx):
    '''
    Make a new prediction
    '''

    temp_msg = ctx.message.content
    goals_regex = "((\d) ?[:-] ?(\d))"
    player_regex = r"[A-Za-z]{1,18}[,]? ?(\dx|x\d)?"

    try:
        temp_msg = temp_msg.replace("+predict ", "")
        print(temp_msg)
        goals_match = re.search(goals_regex, temp_msg)
        temp_msg = re.sub(goals_regex, "", temp_msg)
        # print(temp_msg)

        scorers = temp_msg.strip().split(",")

        scorers = [player.strip() for player in scorers]

        scorer_properties = []

        for player in scorers:
            fgs = False
            num_goals = 1

            if "fgs" in player:
                fgs = True
                player.replace("fgs", "")

            goals_scored = re.search('x?(\d)x?', player)

            if goals_scored:
                player = re.sub('x?(\d)x?', "", player)
                num_goals = goals_scored.group(1)

            scorer_dict = {"name": player, "fgs": fgs, "num goals": num_goals}

            scorer_properties.append(scorer_dict)


        # player_match = re.search(player_regex, temp_msg, re.IGNORECASE)
        # temp_msg = re.sub(player_regex, "", temp_msg)

    except Exception as e:
        print("Failed.")
        await ctx.send(f"FAILED: {e}")
    
    if not goals_match:
        print("Missing goals")
        await ctx.send(f"{ctx.message.author.mention}\nDid not provide a match score in your prediction.\n{ctx.message.content}")
    else:
        message_timestamp = datetime.datetime.utcnow()
        home_goals = goals_match.group(2)
        away_goals = goals_match.group(3)

        # print(ctx.message.content.replace("+predict ", "").split(', '))

        await ctx.send(f"""{ctx.message.author.mention}
        **Prediction against $opponent successful.**

        You have $time_until_next_match-2hr to edit your prediction.

        {ctx.message.content}

        **Score**
        Home {home_goals}:{away_goals} Away

        **Goal Scorers**
        $scorers""")

        await do_insert(message_timestamp, ctx.message.author.id, ctx.message.author.name, ctx.message.id, ctx.message.content, home_goals, away_goals, scorer_properties)


# show user's predictions
@bot.command()
async def predictions(ctx):
    '''
    Show your past predictions
    '''
    await do_find_one(ctx.message.author.id)


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
async def table(ctx):
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


# echo, mostly for testing,
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
    bot.run(token)  
except Exception as e:
    print(f"error: {e}")
    sys.exit(1)
    