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
import time

from tabulate import tabulate
from pythonjsonlogger import jsonlogger
from discord.ext import commands, tasks
from discord.ext.commands import CommandNotFound, CommandInvokeError, CommandOnCooldown, MissingRequiredArgument, BadArgument
from datetime import timedelta, datetime
from dotenv import load_dotenv

from utils.exceptions import IsNotAdmin, PleaseTellMeAboutIt

# bot token, API key, other stuff 
load_dotenv()

class Bot(commands.Bot):
    def __init__(self, db, **kwargs):
        super().__init__(
            description=kwargs.pop("description"),
            command_prefix=kwargs.pop("prefix"),
            help_command=commands.DefaultHelpCommand(dm_help=True)
        )
        self.db = db
        self.testing_mode = kwargs.pop("testing_mode")
        self.admin_ids = kwargs.pop("admin_ids")
        self.main_team = kwargs.pop("main_team")
        self.main_team_name = kwargs.pop("main_team_name")
        self.logger = kwargs.pop("logger")
        self.api_key = kwargs.pop("api_key")
        self.tracing = kwargs.pop("tracing", False)
        self.league_dict = kwargs.pop("league_dict")
        self.season_full = kwargs.pop("season_full")
        self.season = kwargs.pop("season")
        self.channel = kwargs.pop("channel")
        self.gitlab_api = kwargs.pop("gitlab_api")
        self.step = kwargs.pop("step", 5)
        self.match_select = f"home, away, fixture_id, league_id, event_date, goals_home, goals_away, new_date, (SELECT name FROM predictionsbot.teams t WHERE t.team_id = f.home) AS home_name, (SELECT name FROM predictionsbot.teams t WHERE t.team_id = f.away) AS away_name, (SELECT name FROM predictionsbot.leagues t WHERE t.league_id = f.league_id) as league_name, CASE WHEN away = {self.main_team} THEN home ELSE away END as opponent, (SELECT name FROM predictionsbot.teams t WHERE t.team_id = (CASE WHEN f.away = {self.main_team} THEN f.home ELSE f.away END)) as opponent_name, CASE WHEN away = {self.main_team} THEN 'away' ELSE 'home' END as home_or_away, scorable, status_short, notifications_sent"

    async def close(self):
        await self.notifyAdmin("Closing bot connection to discord and postgres")
        await super().close()
        self.logger.info("closed database pool")
        await self.db.close()

    async def notifyAdmin(self, message: str) -> None:
        self.logger.debug("Received admin notification", message=message, testing_mode=self.testing_mode)
        if not self.testing_mode:
            for admin in self.admin_ids:
                adm = await self.fetch_user(admin)
                await adm.send(message)

    async def on_ready(self):
        # .format() is for the lazy people who aren't on 3.6+
        # print(f"Username: {self.user}\nID: {self.user.id}")
        await self.notifyAdmin(f'connected to {channel} within {[guild.name for guild in self.guilds ]} as {self.user}')

    async def on_message(self, message):
        # if the bot sends messages to itself don't return anything
        if message.author == self.user:
            return
        if type(message.channel) == discord.DMChannel:
            if "+help" in message.content:
                t0= time.perf_counter()
                await self.process_commands(message)
                if self.tracing:
                    duration = time.perf_counter() - t0
                    self.logger.debug(performance=duration,channel="DM", author=message.author.name, author_id=message.author.id, content=message.content)

            else:
                channel_str = ""
                for channel in self.get_all_channels():
                    if channel.name == self.channel:
                        channel_str = channel.mention
                await message.channel.send(f"I only respond to help commands in DMs. Everything else needs to be in the {channel_str} channel.")
            return
        if message.channel.name == self.channel or message.channel.name == "Channel_0":
            self.logger.info("Received message", channel=message.channel.name, author=message.author.name, author_id=message.author.id, content=message.content)
            # logger.info(f"{message.channel.name} | {message.author} | {message.author.id} | {message.content}")
            if re.match(r"\+\s+\w+.*", message.content):
                await message.channel.send(f"{message.author.mention}```{message.content}```Do not include any spaces after '+'\nExamples: `+help | +rules | +predict ...`")
            else:    
                t0= time.perf_counter()
                await self.process_commands(message)
                if self.tracing:
                    duration = time.perf_counter() - t0
                    self.logger.debug(performance=duration,channel=message.channel.name, author=message.author.name, author_id=message.author.id, content=message.content)

    async def on_command_error(self, ctx, error):
        self.logger.error(f"Handling error for {ctx.message.content}", exception=error)
        if isinstance(error, IsNotAdmin):
            await ctx.send(f"You do not have permission to run `{ctx.message.content}`")
        if isinstance(error, BadArgument):
            await ctx.send(f"Bad argument for {ctx.message.content}, {error}")
        if isinstance(error, MissingRequiredArgument):
            await ctx.send(f"Missing argument `{error.param.name}` for command `{ctx.message.content}`\n```{ctx.command.help}```")
        if isinstance(error, CommandOnCooldown):
            # raise RateLimit(f"+{name} command is under a rate limit. May run again in {seconds - seconds_since_last_run:.0f} seconds.")
            # await ctx.send(f"{ctx.message.content.split()[0]} is under a rate limit, try again in {error.retry_after:.2f} seconds.")
            await ctx.send(f"{ctx.message.content.split()[0]} is under a rate limit, try again in {str(timedelta(seconds=round(error.retry_after)))}.")
        if isinstance(error, CommandNotFound):
            await ctx.send(f"`{ctx.message.content}` is not a recognized command, try `+help` to see available commands")
        if isinstance(error, CommandInvokeError):
            if not testing_mode:
                if isinstance(error.original, PleaseTellMeAboutIt):
                    await self.notifyAdmin(f"Admin error tagged for notification: {error.original}")
                else:
                    await self.notifyAdmin(f"Unhandled Error: {error.original}")

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
    if os.environ.get("HGOSCENSKI", False):
        channel = 'test-predictions-bot-2'
    else:
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
main_team_name = "Arsenal"
main_league = 2790

token = os.environ.get("TOKEN", None)
if not token:
    logger.error("Missing Discord bot token! Set TOKEN env value.")
    sys.exit(1)

# use something like these functions to get data from db
## bot.db.fetch("<sql>")
credentials = {"user": aws_dbuser, "password": aws_dbpass, "database": aws_dbname, "host": aws_db_ip}

options = {
    "description": "**Arsenal Discord Prediction League Bot**",
    "testing_mode": testing_mode,
    # "admin_ids": [],
    "admin_ids": [260908554758782977, 249231078303203329],
    "main_team": main_team,
    "main_team_name": main_team_name,
    "logger": logger,
    "api_key": api_key,
    "league_dict": league_dict,
    "season_full": "2020-2021",
    "season": "2020",
    "gitlab_api": os.environ.get("GITLAB_API", None),
    "tracing": os.environ.get("TRACING", False),
    "prefix": "+",
    "channel": channel
}

cogs = [
    "cogs.fixtures",
    "cogs.admin",
    "cogs.develop",
    "cogs.predictions",
    "cogs.user",
    "cogs.util"
]

async def init(credentials, options, token, cogs, loop=False):
    db = await asyncpg.create_pool(**credentials)
    if loop:
        bot = Bot(db=db, **options, loop=loop)
    else:
        bot = Bot(db=db, **options)

    for cog in cogs:
        bot.load_extension(cog)

    if testing_mode and os.environ.get("RUN_TASKS_ANYWAY", False):
        bot.load_extension("cogs.tasks")
    elif not testing_mode:
        bot.load_extension("cogs.tasks")

    return bot

# try:
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    bot = loop.run_until_complete(init(credentials, options, token, cogs))

    # @bot.command()
    # async def help(ctx):
    #     '''
    #     This help message
    #     '''
    #     log = logger.bind(content=ctx.message.content, author=ctx.message.author.name)
    #     output = []
    #     adminOutput = []
    #     tabulate.PRESERVE_WHITESPACE = True
    #     for com, value in bot.all_commands.items():
    #         if not value.hidden:
    #             output.append(["\t", com, value.help])
    #         elif value.hidden:
    #             adminOutput.append(["\t", com, value.help])

    #     output = tabulate(output, tablefmt="plain")
    #     adminOutput = tabulate(adminOutput, tablefmt="plain")
        
    #     user = bot.get_user(ctx.author.id)

    #     try:
    #         if ctx.author.id in bot.admin_ids:
    #             await user.send(f"```Available Commands:\n{output}```\n```Available Administrative Commands:\n{adminOutput}```")
    #         else:
    #             await user.send(f"```Available Commands:\n{output}```")
    #     except discord.Forbidden:
    #         log.exception("user either blocked bot or disabled DMs")
    #     except Exception:
    #         log.exception("error sending help command to user")

    bot.run(token)
# except KeyboardInterrupt:
#     logger.exception("Stopping there")
# finally:
#     loop.stop()
#     loop.close()

    