from datetime import datetime
import asyncio
import discord
from discord.ext import commands
import pytz
import aiohttp
from exceptions import *
from functools import wraps
from tabulate import tabulate
from typing import List
import string
import random

async def notifyAdmin(bot: commands.Bot, message: str) -> None:
    bot.logger.debug("Received admin notification", message=message, testing_mode=bot.testing_mode)
    if not bot.testing_mode:
        for admin in bot.admin_ids:
            adm = await bot.fetch_user(admin)
            await adm.send(message)

async def getFixturesWithPredictions(bot: commands.Bot) -> List:
    fixtures = await bot.pg_conn.fetch("SELECT f.fixture_id FROM predictionsbot.predictions p JOIN predictionsbot.fixtures f ON f.fixture_id = p.fixture_id GROUP BY f.fixture_id ORDER BY f.event_date DESC")
    return fixtures

async def getUserRank(bot, user_id):
    ranks = await bot.pg_conn.fetch(f"SELECT DENSE_RANK() OVER(ORDER BY SUM(prediction_score) DESC) as rank, user_id FROM predictionsbot.predictions WHERE prediction_score IS NOT NULL GROUP BY user_id ORDER BY SUM(prediction_score) DESC")
    for rank in ranks:
        if rank.get("user_id") == user_id:
            user_rank = rank.get("rank")
    return user_rank

async def getUserPredictions(bot: commands.Bot, user_id: int) -> List:
    '''
    Return the last 10 predictions by user
    '''
    predictions = await bot.pg_conn.fetch("SELECT * FROM predictionsbot.predictions WHERE user_id = $1 ORDER BY timestamp DESC LIMIT 10;", user_id)
    return predictions

async def getMatch(bot, fixture_id):
    match = await bot.pg_conn.fetchrow(f"SELECT {bot.match_select} FROM predictionsbot.fixtures f WHERE fixture_id = $1;", fixture_id)
    return match

async def getRandomTeam(bot):
    team = await bot.pg_conn.fetchrow("SELECT * FROM predictionsbot.teams WHERE team_id != 42 ORDER BY random() LIMIT 1;")
    return team.get("name")

async def checkUserExists(bot, user_id, ctx):
    user = await bot.pg_conn.fetch("SELECT * FROM predictionsbot.users WHERE user_id = $1", user_id)

    if not user:
        async with bot.pg_conn.acquire() as connection:
            async with connection.transaction():
                try:
                    await connection.execute("INSERT INTO predictionsbot.users (user_id, tz) VALUES ($1, $2);", user_id, "UTC")
                except Exception as e:
                    await bot.notifyAdmin(bot, f"Error inserting user {user_id} into database:\n{e}")
                    bot.logger.error(f"Error inserting user {user_id} into database: {e}")
        # return False
        # await ctx.send(f"{ctx.message.author.mention}\nHello, this is the Arsenal Discord Predictions League\n\nType `+rules` to see the rules for the league\n\nEnter `+help` for a help message")
    else:
        return True

# nextMatches returns array of fixtures (even for one)
async def nextMatches(bot, count=1):
    matches = await bot.pg_conn.fetch(f"SELECT {bot.match_select} FROM predictionsbot.fixtures f WHERE event_date > now() AND (home = {bot.main_team} OR away = {bot.main_team}) ORDER BY event_date LIMIT $1;", count)
    return matches

# nextMatch returns record (no array)
async def nextMatch(bot):
    match = await bot.pg_conn.fetchrow(f"SELECT {bot.match_select} FROM predictionsbot.fixtures f WHERE event_date > now() AND (home = {bot.main_team} OR away = {bot.main_team}) ORDER BY event_date LIMIT 1;")
    return match

# array of completed fixtures records
async def completedMatches(bot, count=1, offset=0):
    matches = await bot.pg_conn.fetch(f"SELECT {bot.match_select} FROM predictionsbot.fixtures f WHERE event_date + interval '2 hour' < now() AND (home = {bot.main_team} OR away = {bot.main_team}) ORDER BY event_date DESC LIMIT $1 OFFSET $2;", count, offset)
    return matches

async def getPlayerId(bot, userInput):
    player = await bot.pg_conn.fetchrow("SELECT player_id FROM predictionsbot.players WHERE $1 = ANY(nicknames) AND team_id = $2;", userInput.lower(), bot.main_team)
    if not player:
        raise Exception(f"no player named {userInput}")
    return player.get("player_id")

async def getTeamId(bot, userInput):
    player = await bot.pg_conn.fetchrow("SELECT team_id FROM predictionsbot.teams WHERE $1 = ANY(nicknames);", userInput.lower())
    if not player:
        raise Exception(f"no team named {userInput}")
    return player.get("team_id")

async def getUserTimezone(bot, user):
    user_tz = await bot.pg_conn.fetchrow(f"SELECT tz FROM predictionsbot.users WHERE user_id = $1;", user)
    tz = pytz.timezone(user_tz.get("tz", "UTC"))
    return tz 
    
async def checkBotReady():
    await asyncio.sleep(5)

def prepareTimestamp(timestamp, tz, str=True):
    # time_format = "%m/%d/%Y, %H:%M:%S %Z"
    time_format = "%A, %d %B %I:%M %p %Z"
    dt = pytz.timezone("UTC").localize(timestamp)
    dt = dt.astimezone(tz)
    if str:
        return dt.strftime(time_format)
    else:
        return dt

async def formatMatch(bot, match, user, score=False):
    tz = await getUserTimezone(bot, user)
    match_time = prepareTimestamp(match.get('event_date'), tz)

    time_until_match = (match.get('event_date') - datetime.now()).total_seconds()
    home_emoji = discord.utils.get(bot.emojis, name=match.get('home_name').lower().replace(' ', ''))
    away_emoji = discord.utils.get(bot.emojis, name=match.get('away_name').lower().replace(' ', ''))
    league_emoji = discord.utils.get(bot.emojis, name=match.get('league_name').lower().replace(' ', ''))
    if not home_emoji:
        home_emoji = ""
    if not away_emoji:
        away_emoji = ""
    if not league_emoji:
        league_emoji = ""

    if score:
        match_time = match.get("event_date")
        match_time = prepareTimestamp(match_time, tz, str=False)
        return f"{league_emoji} **{match.get('league_name')} | {match_time.strftime('%m/%d/%Y')}**\n{home_emoji} {match.get('home_name')} {match.get('goals_home')} - {match.get('goals_away')} {away_emoji} {match.get('away_name')}\n" 
    else:
        # return f"{league_emoji} **{match.get('league_name')}**\n{home_emoji} {match.get('home_name')} vs {away_emoji} {match.get('away_name')}\n{match_time}\n*match starts in {time_until_match // 86400:.0f} days, {time_until_match // 3600 %24:.0f} hours, and {time_until_match // 60 %60:.0f} minutes*\n\n" 
        return f"{league_emoji} **{match.get('league_name')}**\n{home_emoji} {match.get('home_name')} vs {away_emoji} {match.get('away_name')}\n{match_time}\n\n" 

async def getStandings(bot, league_id):
    parsed_standings = []

    bot.logger.info("Generating standings", league=league_id)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://v2.api-football.com/leagueTable/{league_id}", headers={'X-RapidAPI-Key': bot.api_key}, timeout=20) as resp:
                response = await resp.json()
    except Exception:
        bot.logger.exception("Failed to featch standings", league_id=league_id)
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

def formatStandings(standings):
    standings_formatted = []
    for standing in standings:
        # standings_formatted.append([makeOrdinal(standing["rank"]), standing["teamName"], standing["points"], standing["played"], f'{standing["win"]}-{standing["draw"]}-{standing["loss"]}'])
        standings_formatted.append([standing["rank"], standing["teamName"], f'{standing["win"]}-{standing["draw"]}-{standing["loss"]}', standing["goalsDiff"], standing["points"]])

    return tabulate(standings_formatted, headers=["Rank", "Team", "W-D-L", "GD", "Pts"], tablefmt="github")


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

def isAdmin():
    return True


# Convert an integer into its ordinal representation::
# https://stackoverflow.com/questions/9647202/ordinal-numbers-replacement
def makeOrdinal(n):
    n = int(n)
    suffix = ['th', 'st', 'nd', 'rd', 'th'][min(n % 10, 4)]
    if 11 <= (n % 100) <= 13:
        suffix = 'th'
    return str(n) + suffix

def randomAlphanumericString(length):
    letters_and_digits = string.ascii_letters + string.digits
    result_str = ''.join((random.choice(letters_and_digits) for i in range(length)))
    return result_str

# def isAdmin()(method):
#     @wraps(method)
#     async def predicate(self, ctx):
#         if ctx.message.author.id in self.bot.admin_ids:
#             return True
#         else:
#             raise IsNotAdmin(f"User {ctx.message.author.name} is not an admin and cannot use this function.")
#     return commands.check(predicate)


#this already exists as @commands.cooldown()
# def rateLimit(seconds, name, last_run):
#     async def predicate(ctx):
#         if name not in last_run:
#             last_run[name] = datetime.utcnow()
#             return True
#         else:
#             seconds_since_last_run = (datetime.utcnow() - last_run[name]).total_seconds()
#             if seconds_since_last_run > seconds:
#                 last_run[name] = datetime.utcnow()
#                 return True
#             else:
#                 raise RateLimit(f"+{name} command is under a rate limit. May run again in {seconds - seconds_since_last_run:.0f} seconds.")
#     return commands.check(predicate)