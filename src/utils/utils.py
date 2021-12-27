from datetime import datetime
import datetime as dt
import asyncio
import asyncpg
import discord
from discord.ext import commands
import pytz
import aiohttp
from utils.exceptions import *
from tabulate import tabulate
from typing import List, Mapping, Any, NoReturn, Optional, Union
import string
import random
# import phrasier
from typing import Mapping

async def getFixturesWithPredictions(bot: commands.Bot, ctx: commands.Context) -> List:
    fixtures = await bot.db.fetch(f"SELECT f.fixture_id FROM predictionsbot.fixtures f WHERE f.event_date <= (SELECT f.event_date FROM predictionsbot.fixtures f WHERE event_date > now() AND (home = {bot.main_team} OR away = {bot.main_team}) ORDER BY event_date LIMIT 1) AND (f.home = {bot.main_team} or f.away = {bot.main_team}) AND status_short not in ('PST','CANC') ORDER BY f.event_date DESC;")
    # fixtures = await bot.db.fetch(f"SELECT f.fixture_id FROM predictionsbot.predictions p JOIN predictionsbot.fixtures f ON p.fixture_id = f.fixture_id WHERE f.event_date < now() + interval '12 hour' AND (f.home = {bot.main_team} or f.away = {bot.main_team}) ORDER BY f.event_date DESC")
    # fixtures = await bot.db.fetch("SELECT f.fixture_id FROM predictionsbot.predictions p JOIN predictionsbot.fixtures f ON f.fixture_id = p.fixture_id AND guild_id = $1 GROUP BY f.fixture_id ORDER BY f.event_date DESC", ctx.guild.id)
    return fixtures

async def getUserRank(bot: commands.Bot, ctx: commands.Context) -> int:
    user_rank = 0
    ranks = await bot.db.fetch(f"SELECT DENSE_RANK() OVER(ORDER BY SUM(prediction_score) DESC) as rank, user_id FROM predictionsbot.predictions WHERE prediction_score IS NOT NULL AND guild_id = $1 GROUP BY user_id ORDER BY SUM(prediction_score) DESC", ctx.guild.id)
    for rank in ranks:
        if rank.get("user_id") == ctx.message.author.id:
            user_rank = rank.get("rank")
    return user_rank

async def getUserPredictions(bot: commands.Bot, ctx: commands.Context) -> List[asyncpg.Record]:
    '''
    Return the last predictions by user
    '''
    predictions = await bot.db.fetch("SELECT * FROM predictionsbot.predictions WHERE user_id = $1 AND guild_id = $2 ORDER BY timestamp DESC;", ctx.message.author.id, ctx.guild.id)
    return predictions

async def getMatch(bot: commands.Bot, fixture_id: int) -> asyncpg.Record:
    match = await bot.db.fetchrow(f"SELECT {bot.match_select} FROM predictionsbot.fixtures f WHERE fixture_id = $1;", fixture_id)
    return match

async def getRandomTeam(bot: commands.Bot) -> str:
    team = await bot.db.fetchrow(f"SELECT * FROM predictionsbot.teams WHERE team_id != {bot.main_team} ORDER BY random() LIMIT 1;")
    return team.get("name")

async def checkUserExists(bot: commands.Bot, user_id: int, ctx: commands.Context) -> Optional[bool]:
    user = await bot.db.fetch("SELECT * FROM predictionsbot.users WHERE user_id = $1", user_id)

    if not user:
        async with bot.db.acquire() as connection:
            async with connection.transaction():
                try:
                    await connection.execute("INSERT INTO predictionsbot.users (user_id, tz) VALUES ($1, $2);", user_id, "UTC")
                    await ctx.send(f"{ctx.message.author.mention}\n**Welcome to the {discord.utils.get(bot.emojis, name=bot.main_team_name.lower())} Arsenal Discord Predictions League**\nType `+rules` to see the rules for the league\nEnter `+help` for a help message\nTo be reminded about upcoming matches type `+remindme`")                                    
                except Exception as e:
                    await bot.notifyAdmin(f"Error inserting user {user_id} into database:\n{e}")
                    bot.logger.error(f"Error inserting user {user_id} into database: {e}")                
                return True
        # return False
    else:
        return True

# nextMatches returns array of fixtures (even for one)
async def nextMatches(bot: commands.Bot, count: int = 1) -> List[asyncpg.Record]:
    matches = await bot.db.fetch(f"SELECT {bot.match_select} FROM predictionsbot.fixtures f WHERE event_date > now() AND (home = {bot.main_team} OR away = {bot.main_team}) AND status_short not in ('PST','CANC') ORDER BY event_date LIMIT $1;", count)
    return matches

# nextMatch returns record (no array)
async def nextMatch(bot: commands.Bot) -> asyncpg.Record:
    match = await bot.db.fetchrow(f"SELECT {bot.match_select} FROM predictionsbot.fixtures f WHERE event_date > now() AND (home = {bot.main_team} OR away = {bot.main_team}) AND status_short not in ('PST','CANC')  ORDER BY event_date LIMIT 1;")
    return match

# array of completed fixtures records
async def completedMatches(bot: commands.Bot, count: int=1, offset: int=0) -> List[asyncpg.Record]:
    matches = await bot.db.fetch(f"SELECT {bot.match_select} FROM predictionsbot.fixtures f WHERE event_date + interval '2 hour' < now() AND (home = {bot.main_team} OR away = {bot.main_team}) AND status_short not in ('PST','CANC') ORDER BY event_date DESC LIMIT $1 OFFSET $2;", count, offset)
    return matches

# todo will need context eventually
async def getUsersPredictionCurrentMatch(bot: commands.Bot) -> List[asyncpg.Record]:
    users = await bot.db.fetch(f"SELECT user_id FROM predictionsbot.predictions p WHERE p.fixture_id IN (SELECT f.fixture_id FROM predictionsbot.fixtures f WHERE event_date > now() AND (home = {bot.main_team} OR away = {bot.main_team}) AND status_short not in ('PST','CANC') ORDER BY event_date LIMIT 1)")
    return users

async def getUserPredictedLastMatches(bot: commands.Bot) -> List[asyncpg.Record]:
    users = await bot.db.fetch(f"SELECT DISTINCT user_id FROM predictionsbot.predictions p WHERE p.fixture_id IN (SELECT f.fixture_id FROM predictionsbot.fixtures f WHERE event_date + interval '2 hour' < now() AND (home = {bot.main_team} OR away = {bot.main_team}) AND status_short not in ('PST','CANC') ORDER BY event_date DESC LIMIT 2)")
    return users

async def getPlayerId(bot: commands.Bot, userInput: str, active_only=True) -> int:
    # player = await bot.db.fetchrow("SELECT player_id FROM predictionsbot.players WHERE $1 = ANY(nicknames) AND team_id = $2;", userInput.lower(), bot.main_team)
    
    sql_active_flag = "AND active = true" if active_only else ""
    
    player_obj = await bot.db.fetch(f"select * from predictionsbot.players where team_id = {bot.main_team} {sql_active_flag} AND (exists (SELECT 1 FROM unnest(nicknames) AS name WHERE unaccent(name) ILIKE unaccent($1)) OR unaccent(lastname) ILIKE unaccent($1) OR unaccent(firstname) ILIKE unaccent($1));", f"%{userInput}%")
    
    if not player_obj:
        raise Exception(f"no player named {userInput}")
    elif len(player_obj) > 1:
        # if input exactly matches a nickname then prefer results with nicknames
        for player in player_obj:
            if userInput.lower() in player.get("nicknames"):
                return player.get("player_id")
        player_str = "\n".join([f"  - {player.get('player_name')}" for player in player_obj])
        raise Exception(f"`{userInput}` matches more than 1 player, please be more specific.\n**Matched Players:**\n{player_str}")
    return player_obj[0].get("player_id")

async def playerNames(bot: commands.Bot, userInput: str) -> List[str]:
    if len(userInput) >= 3:
        player_obj = await bot.db.fetch("SELECT * FROM predictionsbot.players WHERE EXISTS (SELECT 1 FROM unnest(nicknames) as name WHERE name LIKE $1 OR lastname ILIKE $1 OR firstname ILIKE $1)", f"%{userInput}%")
        return([f"{player.get('firstname')} {player.get('lastname')}: {', '.join(player.get('nicknames'))}" for player in player_obj])
    return([])

async def getTeamId(bot: commands.Bot, userInput: str) -> int:
    team_obj = await bot.db.fetch("SELECT team_id, name, nicknames FROM predictionsbot.teams WHERE (EXISTS (select 1 from unnest(nicknames) as nickname where unaccent(nickname) like unaccent($1)) OR unaccent(name) ILIKE unaccent($1));", f"%{userInput}%")
    if not team_obj:
        raise Exception(f"no team named {userInput}")
    elif len(team_obj) > 1:
        # if input exactly matches a nickname then prefer results with nicknames
        for team in team_obj:
            if team.get("nicknames") and userInput.lower() in team.get("nicknames"):
                return team.get("team_id")
        if len(team_obj) < 10:
            team_str = "\n".join([f"  - {team.get('name')}" for team in team_obj])
            raise TooManyResults(f"`{userInput}` matches more than 1 team, please be more specific.\n**Matched Teams:**\n{team_str}")
        elif len(team_obj) >= 10:
            raise TooManyResults(f"`{userInput}` matches more than 10 teams, please be more specific.")
    return team_obj[0].get("team_id")

async def getUserTimezone(bot: commands.Bot, user: int) -> dt.tzinfo:
    user_tz = await bot.db.fetchrow(f"SELECT tz FROM predictionsbot.users WHERE user_id = $1;", user)
    tz = pytz.timezone(user_tz.get("tz", "UTC"))
    return tz 

async def getTeamsInLeague(bot: commands.Bot, league_id: int) -> List[int]:
    team_ids_list = []
    async with aiohttp.ClientSession() as session:
        async with session.get(f"http://v2.api-football.com/teams/league/{league_id}", headers={'X-RapidAPI-Key': bot.api_key}, timeout=60) as resp:
            response = await resp.json()

    league_teams = response.get("api").get("teams")
    for team in league_teams:
        team_ids_list.append(team.get("team_id"))
    return team_ids_list
    
async def checkBotReady() -> None:
    await asyncio.sleep(5)

def prepareTimestamp(timestamp: datetime, tz: dt.tzinfo, str: bool=True):
    # time_format = "%m/%d/%Y, %H:%M:%S %Z"
    time_format = "%A, %d %B %I:%M %p %Z"
    datet = pytz.timezone("UTC").localize(timestamp)
    datet = datet.astimezone(tz)
    if str:
        return datet.strftime(time_format)
    else:
        return datet

async def checkOptOut(bot: commands.Bot, user: int):
    notification_preference = await bot.db.fetchrow("SELECT allow_notifications FROM predictionsbot.users WHERE user_id = $1", user)
    return notification_preference.get("allow_notifications", False)

async def formatMatch(bot: commands.Bot, match, user: int, score: bool=False) -> str:
    tz: dt.tzinfo = await getUserTimezone(bot, user)

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

        match_time_str = match_time.strftime('%m/%d/%Y')
        if match.get("status_short") == "TBD":
            match_time_str = f"{match.get('event_date').strftime('%m/%d/%Y')}, TBD"
        return f"{league_emoji} **{match.get('league_name')} | {match_time_str}**\n{home_emoji} {match.get('home_name')} {match.get('goals_home')} - {match.get('goals_away')} {away_emoji} {match.get('away_name')}\n" 
    else:
        match_time_str = prepareTimestamp(match.get('event_date'), tz)
        if match.get("status_short") == "TBD":
            match_time_str = f"{match.get('event_date').strftime('%A, %d %B')}, TBD"
        # return f"{league_emoji} **{match.get('league_name')}**\n{home_emoji} {match.get('home_name')} vs {away_emoji} {match.get('away_name')}\n{match_time}\n*match starts in {time_until_match // 86400:.0f} days, {time_until_match // 3600 %24:.0f} hours, and {time_until_match // 60 %60:.0f} minutes*\n\n" 
        return f"{league_emoji} **{match.get('league_name')}**\n{home_emoji} {match.get('home_name')} vs {away_emoji} {match.get('away_name')}\n{match_time_str}\n\n" 

async def addTeam(bot: commands.Bot, team_id: int) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"http://v2.api-football.com/teams/team/{team_id}", headers={'X-RapidAPI-Key': bot.api_key}, timeout=60) as resp:
            response = await resp.json()
    teams = response.get("api").get("teams")

    for team in teams:
        delete_keys = [key for key in team if key not in ["team_id", "name", "logo", "country"]]

    for key in delete_keys:
        del team[key]

    async with bot.db.acquire() as connection:
        async with connection.transaction():
            existing_info = await connection.fetchrow("SELECT * FROM predictionsbot.teams WHERE team_id = $1", team_id)
            if existing_info:
                if changesExistTeam(team, existing_info):
                    await connection.execute("UPDATE predictionsbot.teams SET name = $1, logo = $2, country = $3 WHERE team_id = $4", team.get("name"), team.get("logo"), team.get("country"), team_id)
            else:
                await connection.execute("INSERT INTO predictionsbot.teams (team_id, name, logo, country) VALUES ($1, $2, $3, $4);", team.get("team_id"), team.get("name"), team.get("logo"), team.get("country"))

async def getStandings(bot: commands.Bot, league_id: int) -> List[Mapping]:
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

def formatStandings(standings: List[Mapping]) -> str:
    standings_formatted = []
    for standing in standings:
        # standings_formatted.append([makeOrdinal(standing["rank"]), standing["teamName"], standing["points"], standing["played"], f'{standing["win"]}-{standing["draw"]}-{standing["loss"]}'])
        standings_formatted.append([standing["rank"], standing["teamName"], standing["played"], f'{standing["win"]}-{standing["draw"]}-{standing["loss"]}', standing["goalsDiff"], standing["points"]])

    return tabulate(standings_formatted, headers=["Rank", "Team", "P", "W-D-L", "GD", "Pts"], tablefmt="github")


def changesExist(fixture1: Mapping, fixture2: Mapping) -> bool:
    # list of Boolean evaluations of these comparisons
    # all() returns True if all elements of likeness are True
    likeness = [
        fixture1.get("home") == fixture2.get("home"),
        fixture1.get("away") == fixture2.get("away"),
        fixture1.get("event_date") == fixture2.get("event_date"),
        fixture1.get("goalsHomeTeam") == fixture2.get("goals_home"),
        fixture1.get("goalsAwayTeam") == fixture2.get("goals_away"),
        fixture1.get("league_id") == fixture2.get("league_id"),
        fixture1.get("statusShort") == fixture2.get("status_short")
    ]
    return not all(likeness)

def changesExistLeague(league1: Mapping, league2: Mapping) -> bool:
    # list of Boolean evaluations of these comparisons
    # all() returns True if all elements of likeness are True
    likeness = [
        league1.get("name") == league2.get("name"),
        league1.get("logo") == league2.get("logo"),
        league1.get("season") == league2.get("season"),
        league1.get("country") == league2.get("country")
    ]
    return not all(likeness)

def changesExistPlayer(player1: Mapping, player2: Mapping) -> bool:
    # list of Boolean evaluations of these comparisons
    # all() returns True if all elements of likeness are True
    likeness = [
        player1.get("lastname") == player2.get("lastname"),
        player1.get("firstname") == player2.get("firstname"),
        player1.get("player_name") == player2.get("player_name")
        # player1.get("season") == player2.get("season")
    ]
    return not all(likeness)

def changesExistTeam(team1: Mapping, team2: Mapping) -> bool:
    # list of Boolean evaluations of these comparisons
    # all() returns True if all elements of likeness are True
    likeness = [
        team1.get("name") == team2.get("name"),
        team1.get("logo") == team2.get("logo"),
        team1.get("country") == team2.get("country")
    ]
    return not all(likeness)

def isAdmin() -> bool:
    return True

# Convert an integer into its ordinal representation::
# https://stackoverflow.com/questions/9647202/ordinal-numbers-replacement
def makeOrdinal(n: int) -> str:
    n = int(n)
    suffix = ['th', 'st', 'nd', 'rd', 'th'][min(n % 10, 4)]
    if 11 <= (n % 100) <= 13:
        suffix = 'th'
    return str(n) + suffix

def randomAlphanumericString(length: int) -> str:
    letters_and_digits = string.ascii_letters + string.digits
    result_str = ''.join((random.choice(letters_and_digits) for i in range(length)))
    return result_str

def makeEmbed(embedInfo: Mapping) -> discord.Embed:
    embed = discord.Embed(title=embedInfo.get("title", ""), description=embedInfo.get("description", ""), color=embedInfo.get("color", 0x000000))
    embed.set_thumbnail(url=embedInfo.get("thumbnail", "")) 

    for page in embedInfo.get("fields", []):
        value = page.get("value")
        if value == "":
            value = "N/A"
        embed.add_field(name=page.get("name", ""), value=value, inline=False)
    return embed

def getArsenalColor():
    colors = [0x9C824A, 0x023474, 0xEF0107, 0xDB0007]
    color = random.choice(colors)
    return color

async def makePagedEmbed(bot, ctx, paginated_data):
    max_page = len(paginated_data) - 1
    user_max_pages = len(paginated_data)
    num = 0
    rank_num = 1
    embed_color = 0xcd4589
    first_run = True
    while True:
        try:
            # log.info(num=num, max_page=max_page
            if first_run:
                embed = makeEmbed(paginated_data[num])
                # embed = discord.Embed(title="Arsenal Prediction League Leaderboard", description=f"{rank_num}/{user_max_pages}", color=embed_color)
                # embed.set_thumbnail(url="https://media.api-sports.io/football/teams/42.png") 
                # embed.add_field(name=f'{makeOrdinal(rank_num)}:  {paginated_data[num].get("rank_score")} Points', value=f"\n{paginated_data[num].get('leaders')}", inline=False)
                first_run = False
                msg = await ctx.send(f"{ctx.message.author.mention}", embed=embed)

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
                res, user = await bot.wait_for('reaction_add', timeout=55.0, check=checkReact)
            except asyncio.TimeoutError:
                return await msg.clear_reactions()

            # if user != ctx.message.author:
            #     pass
            if '⏪' in str(res.emoji):
                bot.logger.debug("Going backwards", max=max_page, current=num)
                num = num - 1
                rank_num -= 1
                embed = makeEmbed(paginated_data[num])
                await msg.clear_reactions()
                await msg.edit(embed=embed)

            elif '⏩' in str(res.emoji):
                bot.logger.debug("Going forwards", max=max_page, current=num)
                num = num + 1
                rank_num += 1
                embed = makeEmbed(paginated_data[num])
                await msg.clear_reactions()
                await msg.edit(embed=embed)
        except Exception:
            bot.logger.exception("Error creating or reacting to paged function", num=num, paginated_data=paginated_data)
            break


async def makePaged(bot: commands.Bot, ctx: commands.Context, paginated_data: List[str]):
    max_page = len(paginated_data) - 1
    user_max_pages = len(paginated_data)
    num = 0
    rank_num = 1
    embed_color = 0xcd4589
    first_run = True
    while True:
        try:
            # log.info(num=num, max_page=max_page
            if first_run:
                first_run = False
                msg = await ctx.send(content=paginated_data[num])

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
                res, user = await bot.wait_for('reaction_add', timeout=55.0, check=checkReact)
            except asyncio.TimeoutError:
                return await msg.clear_reactions()

            # if user != ctx.message.author:
            #     pass
            if '⏪' in str(res.emoji):
                bot.logger.debug('Going backwards')
                num = num - 1
                rank_num -= 1
                await msg.clear_reactions()
                await msg.edit(content=paginated_data[num])

            elif '⏩' in str(res.emoji):
                bot.logger.debug("Going forwards")
                num = num + 1
                rank_num += 1
                await msg.clear_reactions()
                await msg.edit(content=paginated_data[num])
        except Exception:
            bot.logger.exception("Error creating or reacting to paged function")
            break
        

async def getTopPredictions(bot, fixture):
    async with bot.db.acquire() as connection:
        async with connection.transaction():
            predictions = await connection.fetch("SELECT DENSE_RANK() OVER(ORDER BY SUM(prediction_score) DESC) as rank, SUM(prediction_score) as score, user_id, guild_id FROM predictionsbot.predictions WHERE prediction_score IS NOT NULL AND fixture_id = $1 GROUP BY user_id, guild_id ORDER BY SUM(prediction_score) DESC", fixture)
    return predictions

async def getAveragePredictionScore(bot, fixture):
    async with bot.db.acquire() as connection:
        async with connection.transaction():
            avgscore = await connection.fetchrow("SELECT ROUND(AVG(prediction_score), 2) FROM predictionsbot.predictions WHERE prediction_score IS NOT NULL AND fixture_id = $1", fixture)
            final_avg = avgscore[0]
    return final_avg


# async def makePhrase():
#     return phrasier.newphrase()
    
