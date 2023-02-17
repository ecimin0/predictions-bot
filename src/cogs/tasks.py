from ast import parse
from nis import match
import sys
from datetime import datetime, timedelta
import discord
from discord.ext import tasks, commands
import json 
import asyncio
import aiohttp
from utils.exceptions import *
from utils.utils import *
from typing import Dict
from utils.models import Emoji

class TasksCog(commands.Cog, name="Scheduled Tasks"): # type: ignore

    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot
        self.status_lookup: Dict[str, bool] = {
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
        # below functions are in the proper order to fill a new season's db or fix an old one

        self.sendNotifications.start()

        self.calculatePredictionScores.add_exception_type(Exception)
        self.calculatePredictionScores.start()

        self.updateLeagues.add_exception_type(Exception)
        self.updateLeagues.start()

        self.updateTeams.add_exception_type(Exception)
        self.updateTeams.start()

        self.updatePlayers.add_exception_type(Exception)
        self.updatePlayers.start()

        # scoring related, will not add or remove fixtures
        self.updateFixtures.add_exception_type(Exception)
        self.updateFixtures.start()

        # new fixtures, no scoring
        self.updateFixturesbyLeague.add_exception_type(Exception)
        self.updateFixturesbyLeague.start()
        
        # todo: should be the first function migrated to v3
        self.sidelinedPlayers.add_exception_type(Exception)
        self.sidelinedPlayers.start()

        self.updateTeamLineups.add_exception_type(Exception)
        self.updateTeamLineups.start()

        self.updateFixtureLineups.add_exception_type(Exception)
        self.updateFixtureLineups.start()

    # @bot.command(hidden=True)
    # runs every 15 min to check if fixtures within 5 hours before and after now are complete/scorable for predictions
    @tasks.loop(minutes=5)
    async def updateFixtures(self):
        await checkBotReady()
        log = self.bot.logger.bind(task="updateFixtures")
        try:
            log.info("Starting updateFixtures")

            try:
                fixtures = await self.bot.db.fetch("SELECT fixture_id FROM predictionsbot.fixtures WHERE event_date < now() + interval '5 hour' AND event_date > now() + interval '-5 hour' AND NOT scorable")
            except Exception:
                log.exception("Failed to select fixtures from database")
                raise PleaseTellMeAboutIt("Failed to select fixtures from database in updateFixtures")

            for fixture in fixtures:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(f"https://v3.football.api-sports.io/fixtures?id={fixture.get('fixture_id')}", headers={'X-RapidAPI-Key': self.bot.api_key}, timeout=60) as resp:
                            match = await resp.json()
                    match = match['response'][0]
                    tempmatch = {}
                    event_date = match.get("fixture").get("date")
                    tempmatch["event_date"] = datetime.strptime(event_date, "%Y-%m-%dT%H:%M:%S+00:00") 
                    tempmatch["home"] = match.get("teams").get("home").get("id")
                    tempmatch["away"] = match.get("teams").get("away").get("id")
                    tempmatch["fixture_id"] = match.get("fixture").get("id")
                    tempmatch["league_id"] = match.get("league").get("id")
                    tempmatch["goalsHomeTeam"] = match.get("goals").get("home")
                    tempmatch["goalsAwayTeam"] = match.get("goals").get("away")
                    tempmatch["statusShort"] = match.get("fixture").get("status").get("short")
                    tempmatch["season"] = match.get("league").get("season")
                    match_completed = self.status_lookup[tempmatch.get("statusShort")]
                
                except asyncio.TimeoutError:
                    log.exception("API call to update fixture timed out", fixture=fixture.get('fixture_id'))
                    return

                except Exception:
                    log.exception("Failed to get fixture from api", fixture=fixture.get('fixture_id'))
                    raise PleaseTellMeAboutIt(f"Failed to get fixture from api: {fixture.get('fixture_id')}")

                try:
                    async with self.bot.db.acquire() as connection:
                        async with connection.transaction():
                            await connection.execute("UPDATE predictionsbot.fixtures SET goals_home = $1, goals_away = $2, scorable = $3, status_short = $4 WHERE fixture_id = $5", tempmatch.get("goalsHomeTeam"), tempmatch.get("goalsAwayTeam"), match_completed, tempmatch.get('statusShort'), fixture.get('fixture_id'))
                
                except Exception:
                    log.exception("Failed to update fixture", fixture=fixture.get('fixture_id'))
                    raise PleaseTellMeAboutIt(f"Failed to get fixture from api: {fixture.get('fixture_id')}")

            log.info(f"Completed updateFixtures", fixtures_updated=len(fixtures))
            
        except Exception as e:
            log.exception()


    # runs every hour updating all fixtures in the db that are not identical to the current entry (by fixture id)
    # this ensures that we get any new fixtures outside the updateFixtures() 15 min window (ex. date of the CL final gets changed, or for some reason fixtures in the past change)
    @tasks.loop(hours=1)
    async def updateFixturesbyLeague(self):
        await checkBotReady()
        try:
            log = self.bot.logger.bind(task="updateFixturesbyLeague")
            log.info("Starting updateFixturesbyLeague")
            updated_fixtures = 0

            for league_name, league_id in self.bot.v3league_dict.items():
                log.info("generating fixtures", league_id=league_id, league_name=league_name)
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(f"https://v3.football.api-sports.io/fixtures?league={league_id}&season={self.bot.season}", headers={'X-RapidAPI-Key': self.bot.api_key}, timeout=60) as resp:
                            r = await resp.json()
                    fixtures = r.get("response")
                except asyncio.TimeoutError:
                    log.exception("API call to update fixture timed out", fixture=fixture.get('fixture_id'))
                    return
                except Exception:
                    log.exception("Unable to fetch league information in updateFixturesbyLeague", league_name=league_name)
                    raise PleaseTellMeAboutIt(f"Unable to fetch league information in updateFixturesbyLeague for {league_name}")

                # reset parsed fixtures to empty for each league
                parsed_fixtures = []
                for match in fixtures:
                    tempmatch = {}
                    event_date = match.get("fixture").get("date")
                    tempmatch["event_date"] = datetime.strptime(event_date, "%Y-%m-%dT%H:%M:%S+00:00") 
                    tempmatch["home"] = match.get("teams").get("home").get("id")
                    tempmatch["away"] = match.get("teams").get("away").get("id")
                    tempmatch["fixture_id"] = match.get("fixture").get("id")
                    tempmatch["league_id"] = int(match.get("league").get("id"))
                    tempmatch["goalsHomeTeam"] = match.get("goals").get("home")
                    tempmatch["goalsAwayTeam"] = match.get("goals").get("away")
                    tempmatch["statusShort"] = match.get("fixture").get("status").get("short")
                    tempmatch["season"] = str(match.get("league").get("season"))

                    parsed_fixtures.append(tempmatch)

                for fixture in parsed_fixtures:
                    try:
                        home_team_exists = await self.bot.db.fetchrow("SELECT * FROM predictionsbot.teams WHERE team_id = $1", fixture.get("home"))
                        away_team_exists = await self.bot.db.fetchrow("SELECT * FROM predictionsbot.teams WHERE team_id = $1", fixture.get("away"))
                        if not home_team_exists:
                            await addTeam(self.bot, fixture.get("home"))
                            log.info("Added team (home)", fixture=fixture.get("fixture_id"), team=fixture.get("home"))
                        if not away_team_exists:
                            await addTeam(self.bot, fixture.get("away"))
                            log.info("Added team (away)", fixture=fixture.get("fixture_id"), team=fixture.get("away"))

                        fixture_exists = await self.bot.db.fetchrow("SELECT home, away, fixture_id, league_id, event_date, goals_home, goals_away, status_short, season FROM predictionsbot.fixtures WHERE fixture_id = $1", fixture.get("fixture_id"))

                        if fixture_exists:
                            if changesExist(fixture, fixture_exists):
                                updated_fixtures += 1
                                log.info("changes exist", fixture_id=fixture.get("fixture_id"), league_id=fixture.get("league_id"))
                                async with self.bot.db.acquire() as connection:
                                    async with connection.transaction():
                                        await connection.execute("UPDATE predictionsbot.fixtures SET home = $1, away = $2, league_id = $3, event_date = $4, goals_home = $5, goals_away = $6, scorable = $7, status_short = $8, season = $9 WHERE fixture_id = $10", 
                                                                    fixture.get("home"), fixture.get("away"), fixture.get("league_id"), fixture.get("event_date"), 
                                                                    fixture.get("goalsHomeTeam"), fixture.get("goalsAwayTeam"), self.status_lookup[fixture.get("statusShort")], fixture.get("statusShort"), fixture.get("season") ,fixture.get('fixture_id'))
                        else:
                            log.info("new fixture", fixture_id=fixture.get("fixture_id"), league_id=fixture.get("league_id"))
                            updated_fixtures += 1
                            async with self.bot.db.acquire() as connection:
                                async with connection.transaction():
                                    await connection.execute("INSERT INTO predictionsbot.fixtures (home, away, league_id, event_date, goals_home, goals_away, scorable, fixture_id, status_short, season) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)", 
                                                                fixture.get("home"), fixture.get("away"), fixture.get("league_id"), fixture.get("event_date"), fixture.get("goalsHomeTeam"), 
                                                                fixture.get("goalsAwayTeam"), self.status_lookup[fixture.get("statusShort")], fixture.get('fixture_id'), fixture.get("statusShort"), fixture.get("season"))
                    except Exception:
                        log.exception("Failed to verify/update fixture", fixture_id=fixture.get("fixture_id"))


            # if updated_fixtures:
            #     await self.bot.notifyAdmin(f"Updated/Inserted {updated_fixtures} fixtures!")
            log.info("Completed updateFixturesbyLeague", updated_fixtures=updated_fixtures)
        except Exception:
            log.exception()

    @tasks.loop(minutes=1)
    async def sendNotifications(self):
        await self.bot.wait_until_ready()
        log = self.bot.logger.bind(task="sendNotifications")
        try:
            now = datetime.utcnow()
            if now.minute % 5 == 0:
                next_match = await nextMatch(self.bot)

                time_limit_offset: Dict[str, float] = {
                    self.bot.league_dict["europa_league"]: 1.5
                }

                time_offset = 1.0
                if next_match.league_id in time_limit_offset:
                    time_offset = time_limit_offset[next_match.league_id]

                time_limit = next_match.event_date - timedelta(hours=time_offset + 1)

                log.debug(next_match=next_match.fixture_id, time_limit=time_limit)
                if next_match.notifications_sent == False and now > time_limit:

                    opted_in_users = await self.bot.db.fetch("SELECT user_id FROM predictionsbot.users WHERE allow_notifications")
                    users_wpredictions = await getUsersPredictionCurrentMatch(self.bot)
                    dedupe_users_wpredictions = set(users_wpredictions)

                    users_to_notify = set(opted_in_users)

                    for channel in self.bot.get_all_channels():
                        if channel.name == self.bot.channel:
                            channel_str = channel.mention
                    if self.bot.testing_mode:
                        users_to_notify = [user.get("user_id") for user in users_to_notify if user.get("user_id") in self.bot.admin_ids]
                    else:
                        users_to_notify = [user.get("user_id") for user in users_to_notify]
                    log.debug(users_to_notify=users_to_notify)
                    
                    for user in users_to_notify:
                        allow_notifications = await checkOptOut(self.bot, user)
                        log.debug(user=user, allow_notifications=allow_notifications)
                        if allow_notifications:
                            user_obj = await self.bot.fetch_user(user)
                            match_str = await formatMatch(self.bot, next_match, user)

                            try:
                                if user in dedupe_users_wpredictions:
                                    await user_obj.send(f"Hey {user_obj.display_name}, the next Arsenal match starts soon! Join the others in the {channel_str} channel.\n\n{match_str}")
                                else:
                                    await user_obj.send(f"Hey {user_obj.display_name}, the next Arsenal match starts soon! Make a prediction in the {channel_str} channel.\n\n{match_str}")
                            except:
                                log.exception()
                    log.debug("Sent notifications for upcoming match", number=len(users_to_notify), next_match=next_match.fixture_id)
                    async with self.bot.db.acquire() as connection:
                        async with connection.transaction():
                            await connection.execute("UPDATE predictionsbot.fixtures SET notifications_sent = $1 WHERE fixture_id = $2", True, next_match.fixture_id)
        except:
            log.exception()


    # @bot.command(hidden=True)
    # @commands.check(isAdmin())
    @tasks.loop(minutes=5)
    async def calculatePredictionScores(self):
        await checkBotReady()
        log = self.bot.logger.bind(task="calculatePredictionScores")
        try:
            log.info("Starting calculatePredictionScores")
            scorable_fixtures = {}
            try:
                async with self.bot.db.acquire() as connection:
                    async with connection.transaction():
                        await connection.set_type_codec(
                            'json',
                            encoder=json.dumps,
                            decoder=json.loads,
                            schema='pg_catalog'
                        )
                        unscored_predictions = await connection.fetch("SELECT * FROM predictionsbot.predictions p join predictionsbot.fixtures f on f.fixture_id = p.fixture_id WHERE f.scorable and prediction_score is null")
                        unscored_fixtures = await connection.fetch("SELECT DISTINCT fixture_id FROM predictionsbot.predictions WHERE prediction_score is null")
                        
            except Exception:
                log.exception("encountered error while selecting predictions from database")
                raise PleaseTellMeAboutIt("encountered error while selecting predictions from database")
                
            for fixture in unscored_fixtures:
                fixture_status = await self.bot.db.fetchrow(f"SELECT {self.bot.match_select} FROM predictionsbot.fixtures f WHERE fixture_id = $1", fixture.get("fixture_id"))
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
                        async with session.get(f"https://v3.football.api-sports.io/fixtures?id={fix}", headers={'X-RapidAPI-Key': self.bot.api_key}, timeout=60) as resp:
                            fixture_response = await resp.json()
                    fixture_info = fixture_response['response'][0]
                    goals = [event for event in fixture_info.get("events") if event.get("type") == "Goal" and event.get("team").get("id") == self.bot.main_team and "Penalty Shootout" != event.get("comments","")]
                    new_goals = []
                    for goal in goals:
                        if goal.get("detail") == "Own Goal":
                            goal["player_id"] = 0
                            new_goals.append(goal)
                        else:
                            new_goals.append(goal)
                    goals = new_goals
                    scorable_fixtures[fix]["goals"] = sorted(goals, key=lambda k: k['time']['elapsed'])
                    if scorable_fixtures[fix]["goals"]:
                        scorable_fixtures[fix]["fgs"] = scorable_fixtures[fix]["goals"][0].get("player").get("id")
                    else:
                        scorable_fixtures[fix]["fgs"] = None
                except asyncio.TimeoutError:
                    log.exception("API call to update fixture timed out", fixture=fix)
                except Exception:
                    log.exception("error retrieving scorable fixture", fixture=fix)
                    raise PleaseTellMeAboutIt(f"error retrieving scorable fixture: {fix}")

            log.debug("Predictions to score", predictions=unscored_predictions, scorable_fixtures=scorable_fixtures)

            arsenal_actual_goals = 0
            send_notifications = False

            if unscored_predictions:
                for prediction in unscored_predictions:
                    max_score = 8
                    if prediction.get("fixture_id") in scorable_fixtures:
                        send_notifications = True
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

                        for idx,player in enumerate(prediction.get("scorers")): # TODO look at this maybe, possibly doesnt reset
                            prediction.get("scorers")[idx]["player_id"] = await getPlayerId(self.bot, player.get("name"), active_only=False)

                        # 1 point – each correct scorer
                        actual_goal_scorers = {}
                        for goal in match_results.get("goals"):
                            if goal.get("player").get("id") not in actual_goal_scorers:
                                actual_goal_scorers[goal.get("player").get("id")] = 1
                            else:
                                actual_goal_scorers[goal.get("player").get("id")] += 1
                    
                        predicted_scorers = {v.get("player_id"):v.get("num_goals") for v in prediction.get("scorers")}
                        all_scorers_correct = True
                        
                        # No points for scorers if your prediction's goals exceed the actual goals by 4+
                        # No points for any part of the prediction related to scorers or fgs if predicted goals > actual goals + 4
                        if arsenal_predicted_goals < arsenal_actual_goals + 4:
                            for actual_scorer, count in actual_goal_scorers.items():
                                if actual_scorer in predicted_scorers:
                                    if count == predicted_scorers.get(actual_scorer):
                                        prediction_score += count
                                    elif count < predicted_scorers.get(actual_scorer):
                                        prediction_score += count
                                        all_scorers_correct = False
                                    else:
                                        prediction_score += predicted_scorers.get(actual_scorer)
                                        all_scorers_correct = False

                            actual_scorers_set = set(actual_goal_scorers.keys())
                            predicted_scorers_set = set(predicted_scorers.keys())
                            if predicted_scorers_set.symmetric_difference(actual_scorers_set):
                                all_scorers_correct = False

                            # 1 point – correct FGS (first goal scorer, only Arsenal)
                            predicted_fgs = None
                            for player in prediction.get("scorers"):
                                if player.get("fgs"):
                                    predicted_fgs = player.get("player_id")
                            if predicted_fgs == match_results.get("fgs") and match_results.get("fgs") is not None: # using 'is not None' because player id of OG is 0, thus Falsey
                                prediction_score += 1

                            # 2 points bonus – all scorers correct
                            if all_scorers_correct:
                                prediction_score += 2

                        log.info("calculated prediction", prediction_id=prediction.get("prediction_id"), user_id=prediction.get("user_id"), prediction_string=prediction.get("prediction_string"), prediction_score=prediction_score)
                        try:
                            async with self.bot.db.acquire() as connection:
                                async with connection.transaction():
                                    await connection.execute("UPDATE predictionsbot.predictions SET prediction_score = $1 WHERE prediction_id = $2", prediction_score, prediction.get("prediction_id"))
                        except Exception:
                            log.exception()
                            raise PleaseTellMeAboutIt(f"Could not update prediction score(s)")
                if arsenal_actual_goals:
                    max_score += arsenal_actual_goals
                else:
                    max_score -= 1 # only subtract 1 here since a prediction of no scorers and 0 goals scored is 'all scorers correct'

                if send_notifications:# and not self.bot.testing_mode:
                    # channel = self.bot.get_channel(652580035483402250) # test bot channel 1
                    # channel = self.bot.get_channel(523472428517556244) # prod channel gunners
                    channel = self.bot.get_channel(self.bot.channel_id)

                    for fix in scorable_fixtures: # re-use the scorable fixture(s) from this run
                        top_predictions = await getTopPredictions(self.bot, fix)

                    user_array = []

                    max_score_achieved = ""

                    if top_predictions[0].get("score") == max_score:
                        max_score_achieved = ":medal:"

                    top_rank_dict = {
                        1: [],
                        2: [],
                        3: []
                    }

                    for user in top_predictions:
                        if user.get('rank') in top_rank_dict:
                            for guild in self.bot.guilds:
                                if guild.id == user.get("guild_id"):
                                    disc_user = guild.get_member(user.get("user_id"))
                                    if disc_user:
                                        uname = disc_user.display_name
                                        top_rank_dict[user.get('rank')].append(uname)

                    for rank, users in top_rank_dict.items():
                        top_rank_dict[rank] = "\n".join(users)

                    scores = sorted([i[1] for i in set([(score.get("rank"), score.get("score")) for score in top_predictions])], reverse=True)
                    num_predictions = len(top_predictions)

                    match = await getFixtureByID(self.bot, prediction.get("fixture_id"))
                    home_emoji = Emoji(self.bot, match.home_name).emoji
                    away_emoji = Emoji(self.bot, match.away_name).emoji


                    output_str = f'**{home_emoji} {match.home_name} {match.goals_home} - {match.goals_away} {away_emoji} {match.away_name}**\n' + \
                        f'\n:fire: Maximum possible score this fixture: **{max_score}**' + \
                        f'\n:soccer: Total predictions this fixture: **{num_predictions}**' + \
                        f'\n:loudspeaker: Average prediction score: **{await getAveragePredictionScore(self.bot, match.fixture_id)}**\n\n' +\
                        f':first_place: {max_score_achieved} **{scores[0]} pts\n**{top_rank_dict[1]}\n'

                    if len(scores) >= 2:
                        output_str += f':second_place: **{scores[1]} pts\n**{top_rank_dict[2]}\n'
                    
                    if len(scores) >= 3:
                        output_str += f':third_place: **{scores[2]} pts\n**{top_rank_dict[3]}'

                    await channel.send(output_str)

            else:
                log.info("No predictions to score")    
            log.info("Completed calculatePredictionScores")

        except Exception:
            log.exception()

    @tasks.loop(hours=24)
    async def updateTeams(self):
        await checkBotReady()
        try:
            update_counter = 0
            added_counter = 0
            log = self.bot.logger.bind(task="updateTeams")
            log.info("Starting updateTeams")
            for name, league_id in self.bot.league_dict.items():
                team_ids_list = await getTeamsInLeague(self.bot, league_id)
                for team_id in team_ids_list:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(f"http://v2.api-football.com/teams/team/{team_id}", headers={'X-RapidAPI-Key': self.bot.api_key}, timeout=60) as resp:
                            response = await resp.json()
                    teams = response.get("api").get("teams")

                    for team in teams:
                        delete_keys = [key for key in team if key not in ["team_id", "name", "logo", "country"]]

                    for key in delete_keys:
                        del team[key]

                    try:
                        async with self.bot.db.acquire() as connection:
                            async with connection.transaction():
                                existing_info = await connection.fetchrow("SELECT * FROM predictionsbot.teams WHERE team_id = $1", team_id)
                                if existing_info:
                                    if changesExistTeam(team, existing_info):
                                        await connection.execute("UPDATE predictionsbot.teams SET name = $1, logo = $2, country = $3 WHERE team_id = $4", team.get("name"), team.get("logo"), team.get("country"), team_id)
                                        update_counter += 1
                                else:
                                    await connection.execute("INSERT INTO predictionsbot.teams (team_id, name, logo, country) VALUES ($1, $2, $3, $4);", team.get("team_id"), team.get("name"), team.get("logo"), team.get("country"))
                                    added_counter += 1
                    except Exception:
                        log.exception("Failed to insert/update teams", team_id=team.get("team_id"))
            log.info("Completed updateTeams", added_teams=added_counter, updated_teams=update_counter)
        except Exception:
            log.exception()

    @tasks.loop(hours=6)
    async def updatePlayers(self):
        await checkBotReady()
        log = self.bot.logger.bind(task="updatePlayers")
        try:
            log.info("Starting updatePlayers")
            teams = {}
            updated_players = 0
            added_players = 0
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://v2.api-football.com/players/squad/{self.bot.main_team}/{self.bot.season_full}", headers={'X-RapidAPI-Key': self.bot.api_key}, timeout=60) as resp:
                    response = await resp.json()
            players = response.get("api").get("players")

            async with aiohttp.ClientSession() as session2:
                async with session2.get(f"https://v3.football.api-sports.io/players/squads?team={self.bot.main_team}", headers={'X-RapidAPI-Key': self.bot.api_key}, timeout=60) as resp2:
                    response2 = await resp2.json()
            squad = response2.get("response")[0].get("players")

            teams[self.bot.main_team] = players

            for team, player_array in teams.items():
                for player in player_array:
                    delete_keys = [key for key in player if key not in ["player_name", "firstname", "lastname", "player_id"]]
                    for key in delete_keys: 
                        del player[key]
                    for p in squad:
                        if p.get("id") == player.get("player_id"):
                            player["number"] = p.get("number")
                    # print(player)
                    try:
                        async with self.bot.db.acquire() as connection:
                            async with connection.transaction():
                                existing_player = await connection.fetchrow("SELECT * FROM predictionsbot.players WHERE player_id = $1", player.get("player_id"))
                                if existing_player:
                                    if changesExistPlayer(player, existing_player):
                                        await connection.execute("UPDATE predictionsbot.players SET season = $1, team_id = $2, player_name = $3, firstname = $4, lastname = $5 WHERE player_id = $6", self.bot.season, team, player.get("player_name"), player.get("firstname"), player.get("lastname"), player.get("player_id"))
                                        updated_players += 1
                                else:
                                    await connection.execute("INSERT INTO predictionsbot.players (player_id, season, team_id, player_name, firstname, lastname) VALUES ($1, $2, $3, $4, $5, $6);", player.get("player_id"), self.bot.season, team, player.get("player_name"), player.get("firstname"), player.get("lastname"))
                                    added_players += 1
                    except Exception:
                        log.exception("Failed to insert/update player", player_id=player.get("player_id"))
            log.info("Completed updatePlayers", added_players=added_players, updated_players=updated_players)
        except Exception:
            log.exception()


    @tasks.loop(hours=72)
    async def updateLeagues(self):
        await checkBotReady()
        log = self.bot.logger.bind(task="updateLeagues")
        try:
            log.info("Starting updateLeagues")
            updated_leagues = 0
            added_leagues = 0
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://v3.football.api-sports.io/leagues?season={self.bot.season}", headers={'X-RapidAPI-Key': self.bot.api_key}, timeout=60) as resp:
                    response = await resp.json()
            leagues = response.get("response")
    
            parsed_leagues = []
            for league in leagues:
                temp_league = {}
                temp_league["league_id"] = league.get("league").get("id")
                temp_league["name"] = league.get("league").get("name")
                temp_league["logo"] = league.get("league").get("logo")

                temp_league["season"] = str(self.bot.season)
                temp_league["country"] = league.get("country").get("name")

                parsed_leagues.append(temp_league)
            
            # for league in leagues:
            #     delete_keys = [key for key in league if key not in ["id", "name", "logo"]]
            #     for key in delete_keys: 
            #         del league[key]
            #     parsed_leagues.append(league)

            # # only get leagues for the current season
            # # season '2019' is for calendar years 2019-2020
            # log.debug("Seasons", season_count=len(parsed_leagues))
            # delete_seasons = [row for row in parsed_leagues if row.get("is_current") != 1]
            # for season in delete_seasons:
            #     parsed_leagues.remove(season)
            # log.debug("Seasons (after removal)", season_count=len(parsed_leagues))
                
            for league in parsed_leagues:
                try:
                    async with self.bot.db.acquire() as connection:
                        async with connection.transaction():
                            existing_league = await connection.fetchrow("SELECT * FROM predictionsbot.leagues WHERE league_id = $1", league.get("league_id"))
                            if existing_league:
                                if changesExistLeague(league, existing_league):
                                    await connection.execute("UPDATE predictionsbot.leagues SET name = $1, season = $2, logo = $3, country = $4 WHERE league_id = $5", league.get("name"), str(league.get("season")), league.get("logo"), league.get("country"), league.get("league_id"))
                                    updated_leagues += 1
                            else:
                                await connection.execute("INSERT INTO predictionsbot.leagues (league_id, name, season, logo, country) VALUES ($1, $2, $3, $4, $5);", league.get("league_id"), league.get("name"), str(league.get("season")),  league.get("logo"), league.get("country"))
                                added_leagues += 1
                except Exception:
                    log.exception("Failed to insert/update league", league_id=league.get("league_id"))
            log.info("Completed updateLeagues", added_leagues=added_leagues, updated_leagues=updated_leagues)
        except Exception:
            log.exception()


    @tasks.loop(hours=12)
    async def sidelinedPlayers(self):
        await checkBotReady()
        log = self.bot.logger.bind(task="sidelinedPlayers")
        try:
            async with self.bot.db.acquire() as connection:
                async with connection.transaction():
                    players_list = await connection.fetch(f"SELECT player_id, sidelined_reason, sidelined_end, sidelined FROM predictionsbot.players WHERE team_id = {self.bot.main_team}")
                    for player in players_list:
                        async with aiohttp.ClientSession() as session:
                            async with session.get(f"https://v2.api-football.com/sidelined/player/{player.get('player_id')}", headers={'X-RapidAPI-Key': self.bot.api_key}, timeout=60) as resp:
                                response = await resp.json()
                            
                        player_info = response.get("api").get("sidelined")

                        if player_info:
                            latest_status = player_info[0]

                            sidelined = True
                            endtime_dtobj = None
                            if latest_status.get("end"):
                                format_str = '%d/%m/%y'
                                endtime_dtobj = datetime.strptime(latest_status.get("end"), format_str)

                                if datetime.utcnow() > endtime_dtobj:
                                    sidelined = False
                                else:
                                    sidelined = True

                            format_str = '%d/%m/%y'
                            starttime_dtobj = datetime.strptime(player_info[0].get("start"), format_str)

                            update_counter = 0 
                            if player.get("sidelined_reason") != player_info[0].get("type") or player.get("sidelined_end") != endtime_dtobj or player.get("sidelined") != sidelined:
                                update_counter += 1
                                try:
                                    async with self.bot.db.acquire() as connection:
                                        async with connection.transaction():
                                            await connection.execute("UPDATE predictionsbot.players SET sidelined_reason = $1, sidelined_end = $2, sidelined_start = $3, sidelined = $4 WHERE player_id = $5;", player_info[0].get("type"), endtime_dtobj, starttime_dtobj, sidelined, player.get("player_id"))
                                except Exception:
                                    log.exception("Sidelined players update failed")
            log.info("Updated sidelined player information", players_updated=update_counter)
        except Exception:
            log.exception("Failed to get player IDs", team_id=self.bot.main_team)

    @tasks.loop(hours=168)
    async def updateTeamLineups(self):
        await checkBotReady()
        try:
            log = self.bot.logger.bind(task="updateTeamLineups")
            log.info("Starting updateTeamLineups")
            # need to add other teams to db so that we dont get a key error for players on other teams
            # for name, league_id in self.bot.league_dict.items(): # should be v3league_dict or something better
            # team_ids_list = await getTeamsInLeague(self.bot, 4335) # needs to NOT be the v2/old league IDs, see that really good league mapping thing we did
            # for team_id in team_ids_list:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://v3.football.api-sports.io/players/squads?team=42", headers={'X-RapidAPI-Key': self.bot.api_key}, timeout=60) as resp:
                    response = await resp.json()
            team_squad = response.get("response")[0].get("players")
                # log.info(team_squad)
                # sys.exit(0)

            for player in team_squad:
                # get season so dont have to hardcode it, 
                # also
                # check if player is already in lineup, if so then skip
                # else if in this list but not in the db lineup, insert to db
                # else if not in this list, but in db, update end field
                async with self.bot.db.acquire() as connection:
                    async with connection.transaction():
                        await connection.execute("INSERT INTO predictionsbot.team_lineups (season, team_id, player_id, start, kit_number) VALUES ($1, $2, $3, $4, $5);", "2022", 42, player.get("id"), datetime.utcnow(), player.get("number"))
        except Exception as e:
            log.error(e)
        log.info("completed updateTeamLineups")

    @tasks.loop(hours=24)
    async def updateFixtureLineups(self):
        await checkBotReady()
        try:
            log = self.bot.logger.bind(task="updateFixtureLineups")
            log.info("Starting updateFixtureLineups")
            fixtures = await completedMatches(self.bot, count=10)
            log.info(fixtures)
            for fixture in fixtures:
                # clear the tables for these one last time before fixing this for good
                # write select statement to check for existing fixtures in fixture lineup and skip hitting the API if exists
                if fixture.home == 42 or fixture.away == 42:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(f"https://v3.football.api-sports.io/fixtures/players?fixture={fixture.fixture_id}&team=42", headers={'X-RapidAPI-Key': self.bot.api_key}, timeout=60) as resp:
                            response = await resp.json()
                    players = response.get("response")[0].get("players")
                # log.info(team_squad)
                # sys.exit(0)

                for player in players:
                    # get current season
                    async with self.bot.db.acquire() as connection:
                        async with connection.transaction():
                            team_lineup_id = await connection.fetchrow("SELECT id FROM predictionsbot.team_lineups i WHERE i.player_id = $1", player.get('player').get('id'))
                            tlid = int(team_lineup_id[0])
                            await connection.execute("INSERT INTO predictionsbot.fixture_lineups (fixture_id, team_lineup_id, minutes_played) VALUES ($1, $2, $3);", fixture.fixture_id, tlid, player.get("statistics")[0].get("games").get("minutes"))
        except Exception as e:
            log.exception(e)
        log.info("completed updateFixtureLineups")





def setup(bot):
    bot.add_cog(TasksCog(bot))
