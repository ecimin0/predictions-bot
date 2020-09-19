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
from discord.ext.commands import CommandNotFound, CommandInvokeError, CommandOnCooldown
from datetime import timedelta, datetime
from dotenv import load_dotenv

from exceptions import *
from utils import *

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

utc = pytz.timezone("UTC")

# 2020-2021 season league IDs
league_dict = {
    "premier_league": 2790,
    "champions_league": 2771,
    "europa_league": 2777,
    "fa_cup": 2791,
    "league_cup": 2781
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

testing_mode = os.environ.get("TESTING", False)
if testing_mode:
    channel = 'test-predictions-bot'
    logger.info("Starting in testing mode", channel=channel)
else:
    channel = 'prediction-league'
    logger.info("Starting in production mode", channel=channel)

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

token = os.environ.get("TOKEN", None)
if not token:
    logger.error("Missing Discord bot token! Set TOKEN env value.")
    sys.exit(1)

last_run = {}

# use something like these functions to get data from db
## bot.pg_conn.fetch("<sql>")

# bot only responds to commands prepended with {prefix}
prefix = "+"
# cleaner output of help function(s)
help_function = commands.DefaultHelpCommand(no_category="Available Commands", indent=4, dm_help=True)
bot = commands.Bot(prefix, help_command=help_function)
bot.remove_command('help')


# async def connectToDB():
#     try:
#         bot.pg_conn = await asyncpg.create_pool(user=aws_dbuser, password=aws_dbpass, database=aws_dbname, host=aws_db_ip)
#         logger.info("Connected to postgres")
#         bot.pg_conn_ready = True
#     except Exception:
#         logger.exception("Error connecting to db")
#         sys.exit(1)

# async def getAdminDiscordId():
#     try:
#         bot.admin_id = await bot.fetch_user("249231078303203329")
#         if not testing_mode:
#             await bot.admin_id.send(f"found admin ID {bot.admin_id}")
#     except Exception as e:
#         logger.error(f"{e}")


# on_ready = when bot is connected to server
@bot.event
async def on_ready(): 
    # await connectToDB()
    try:
        bot.pg_conn = await asyncpg.create_pool(user=aws_dbuser, password=aws_dbpass, database=aws_dbname, host=aws_db_ip)
        logger.info("Connected to postgres")
        bot.pg_conn_ready = True
    except Exception:
        logger.exception("Error connecting to db")
        sys.exit(1)
    # await getAdminDiscordId()
    # try:
    #     bot.admin_id = await bot.fetch_user("249231078303203329")
    #     if not testing_mode:
    #         await bot.admin_id.send(f"found admin ID {bot.admin_id}")
    # except Exception as e:
    #     logger.exception(f"{e}")
    bot.testing_mode = testing_mode
    bot.notify_admin = notifyAdmin
    bot.admin_ids = [260908554758782977, 249231078303203329]
    bot.main_team = main_team
    bot.logger = logger
    bot.api_key = api_key
    bot.league_dict = league_dict
    bot.match_select = f"home, away, fixture_id, league_id, event_date, goals_home, goals_away, new_date, (SELECT name FROM predictionsbot.teams t WHERE t.team_id = f.home) AS home_name, (SELECT name FROM predictionsbot.teams t WHERE t.team_id = f.away) AS away_name, (SELECT name FROM predictionsbot.leagues t WHERE t.league_id = f.league_id) as league_name, CASE WHEN away = 42 THEN home ELSE away END as opponent, (SELECT name FROM predictionsbot.teams t WHERE t.team_id = (CASE WHEN f.away = 42 THEN f.home ELSE f.away END)) as opponent_name, CASE WHEN away = {bot.main_team} THEN 'away' ELSE 'home' END as home_or_away, scorable"
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
# @commands.check(isAdmin())
# async def updateNicknames(ctx):
#     '''
#     Add player nickname to database
#     '''
#     for k,v in player_nicknames.items():
#         async with bot.pg_conn.acquire() as connection:
#             async with connection.transaction():
#                 await connection.execute("UPDATE predictionsbot.players SET nicknames = '{{ {0} }}' WHERE player_id = $1".format(", ".join(v)), k)

# @bot.command(hidden=True)
# @commands.check(isAdmin())
# async def updateTeamNickNames(ctx):
#     '''
#     Add team nickname to database
#     '''
#     for k,v in team_nicknames.items():
#         async with bot.pg_conn.acquire() as connection:
#             async with connection.transaction():
#                 await connection.execute("UPDATE predictionsbot.teams SET nicknames = '{{ {0} }}' WHERE team_id = $1".format(", ".join(v)), k)


# todo paginate some functions from +help
# todo indicate prediction has yet to be scored instead of points 
# todo show missed matches in +predictions

@bot.command()
async def results(ctx):
    '''
    Return historical match results
    '''
    await checkUserExists(bot, ctx.message.author.id, ctx)
    user_tz = await getUserTimezone(bot.pg_conn, ctx.message.author.id)

    done_matches = await completedMatches(bot.pg_conn, count=10)
    done_matches_output = []
    for match in done_matches:
        match_time = match.get("event_date")
        match_time = prepareTimestamp(match_time, user_tz, str=False)
        done_matches_output.append([match_time.strftime("%m/%d/%Y"), match.get("home_name"), f'{match.get("goals_home")}-{match.get("goals_away")}', match.get("away_name")])

    done_matches_output = f'```{tabulate(done_matches_output, headers=["Date", "Home", "Score", "Away"], tablefmt="github", colalign=("center","center","center","center"))}```'
    await ctx.send(f"{ctx.message.author.mention}\n\n**Past Match Results**\n{done_matches_output}")

@bot.event
async def on_command_error(ctx, error):
    logger.error(f"Handling error for {ctx.message.content}", exception=error)
    if isinstance(error, IsNotAdmin):
        await ctx.send(f"You do not have permission to run `{ctx.message.content}`")
    if isinstance(error, RateLimit):
        await ctx.send(error)
    if isinstance(error, CommandOnCooldown):
        # raise RateLimit(f"+{name} command is under a rate limit. May run again in {seconds - seconds_since_last_run:.0f} seconds.")
        await ctx.send(f"{ctx.message.content.split()[0]} is under a rate limit, try again in {error.retry_after:.2f} seconds.")
    if isinstance(error, CommandNotFound):
        await ctx.send(f"`{ctx.message.content}` is not a recognized command, try `+help` to see available commands")
    if isinstance(error, CommandInvokeError):
        if not testing_mode:
            if isinstance(error.original, PleaseTellMeAboutIt):
                await bot.admin_id.send(f"Admin error tagged for notification: {error.original}")
            else:
                await bot.admin_id.send(f"Unhandled Error: {error.original}")

if __name__ == "__main__":
    try:
        # disabling fixture update during testing mode, may need to be further tunable for testing.
        if not testing_mode:
            bot.load_extension("cogs.tasks")
            # updateFixtures.start()
            # calculatePredictionScores.start()
            # updateFixturesbyLeague.start()

        bot.load_extension("cogs.fixtures")
        bot.load_extension("cogs.admin")
        bot.load_extension("cogs.develop")
        bot.load_extension("cogs.predictions")
        bot.load_extension("cogs.user")
        bot.load_extension("cogs.util")

        bot.run(token)
    except Exception as e:
        logger.exception("Error in bot")
        sys.exit(1)
    