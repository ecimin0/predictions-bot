import discord
from discord.ext import tasks, commands
import json 
import asyncio

from exceptions import *
from utils import checkBotReady

class TasksCog(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.status_lookup = {
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
        self.updateFixtures.start()
        self.updateFixturesbyLeague.start()
        self.calculatePredictionScores.start()


    # @bot.command(hidden=True)
    # runs every 15 min to check if fixtures within 5 hours before and after now are complete/scorable for predictions
    @tasks.loop(minutes=15)
    async def updateFixtures(self):
        await checkBotReady()

        try:
            fixtures = await self.bot.pg_conn.fetch("SELECT fixture_id FROM predictionsbot.fixtures WHERE event_date < now() + interval '5 hour' AND event_date > now() + interval '-5 hour' AND NOT scorable")
        except Exception:
            self.bot.logger.exception("Failed to select fixtures from database")
            raise PleaseTellMeAboutIt("Failed to select fixtures from database in updateFixtures")

        for fixture in fixtures:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"http://v2.api-football.com/fixtures/id/{fixture.get('fixture_id')}", headers={'X-RapidAPI-Key': self.bot.api_key}, timeout=60) as resp:
                        fixture_info = await resp.json()
                fixture_info = fixture_info['api']['fixtures'][0]

                match_completed = self.status_lookup[fixture_info.get("statusShort")]
            except asyncio.TimeoutError:
                logger.exception("API call to update fixture timed out", fixture=fixture.get('fixture_id'))
                return
            except Exception:
                self.bot.logger.exception("Failed to get fixture from api", fixture=fixture.get('fixture_id'))
                raise PleaseTellMeAboutIt(f"Failed to get fixture from api: {fixture.get('fixture_id')}")

            try:
                async with self.bot.pg_conn.acquire() as connection:
                    async with connection.transaction():
                        await connection.execute("UPDATE predictionsbot.fixtures SET goals_home = $1, goals_away = $2, scorable = $3 WHERE fixture_id = $4", fixture_info.get("goalsHomeTeam"), fixture_info.get("goalsAwayTeam"), match_completed, fixture.get('fixture_id'))
            except Exception:
                self.bot.logger.exception("Failed to update fixture", fixture=fixture.get('fixture_id'))
                raise PleaseTellMeAboutIt(f"Failed to get fixture from api: {fixture.get('fixture_id')}")

        self.bot.logger.info(f"Updated fixtures table, {len(fixtures)} were changed.")
        # await bot.admin_id.send(f"Updated fixtures table, {len(fixtures)} were changed.")

    # runs every hour updating all fixtures in the db that are not identical to the current entry (by fixture id)
    # this ensures that we get any new fixtures outside the updateFixtures() 15 min window (ex. date of the CL final gets changed, or for some reason fixtures in the past change)
    @tasks.loop(hours=1)
    async def updateFixturesbyLeague(self):
        await checkBotReady()
        # if datetime.utcnow.hour % 8 == 0:
            # logger.info("Not running fixture update script")
        self.bot.logger.info("Running fixture update script")
        updated_fixtures = 0

        # if not league:
        #     print("No team IDs generated. Pass in a --league <league_id>")
        #     sys.exit(1)
        for league_name, league_id in league_dict.items():
            self.bot.logger.info("generating fixtures", league_id=league_id, league_name=league_name)
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"http://v2.api-football.com/fixtures/league/{league_id}", headers={'X-RapidAPI-Key': self.bot.api_key}, timeout=60) as resp:
                        response = await resp.json()
                fixtures = response.get("api").get("fixtures")
            except asyncio.TimeoutError:
                logger.exception("API call to update fixture timed out", fixture=fixture.get('fixture_id'))
                return
            except Exception:
                self.bot.logger.exception("Unable to fetch league information in updateFixturesbyLeague", league_name=league_name)
                raise PleaseTellMeAboutIt(f"Unable to fetch league information in updateFixturesbyLeague for {league_name}")

            # reset parsed fixtures to empty for each league
            parsed_fixtures = []
            for match in fixtures:
                home = match.get("homeTeam").get("team_id")
                away = match.get("awayTeam").get("team_id")
                event_date = match.get("event_date")

                delete_keys = [key for key in match if key not in ["fixture_id", "league_id", "goalsHomeTeam", "goalsAwayTeam", "statusShort"]]
            
                for key in delete_keys:
                    del match[key]

                match["event_date"] = datetime.strptime(event_date, "%Y-%m-%dT%H:%M:%S+00:00") 
                match["home"] = home
                match["away"] = away

                parsed_fixtures.append(match)
            
            for fixture in parsed_fixtures:
                try:
                    fixture_exists = await self.bot.pg_conn.fetchrow("SELECT home, away, fixture_id, league_id, event_date, goals_home, goals_away FROM predictionsbot.fixtures WHERE fixture_id = $1", fixture.get("fixture_id"))
                    
                    if fixture_exists:
                        if changesExist(fixture, fixture_exists):
                            updated_fixtures += 1
                            self.bot.logger.info("changes exist", fixture_id=fixture.get("fixture_id"), league_id=league_id)
                            async with self.bot.pg_conn.acquire() as connection:
                                async with connection.transaction():
                                    await connection.execute("UPDATE predictionsbot.fixtures SET home = $1, away = $2, league_id = $3, event_date = $4, goals_home = $5, goals_away = $6, scorable = $7 WHERE fixture_id = $8", 
                                                                fixture.get("home"), fixture.get("away"), fixture.get("league_id"), fixture.get("event_date"), 
                                                                fixture.get("goalsHomeTeam"), fixture.get("goalsAwayTeam"), self.status_lookup[fixture.get("statusShort")], fixture.get('fixture_id'))
                    else:
                        self.bot.logger.info("new fixture", fixture_id=fixture.get("fixture_id"), league_id=league_id)
                        updated_fixtures += 1
                        async with self.bot.pg_conn.acquire() as connection:
                            async with connection.transaction():
                                await connection.execute("INSERT INTO predictionsbot.fixtures (home, away, league_id, event_date, goals_home, goals_away, scorable, fixture_id) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)", 
                                                            fixture.get("home"), fixture.get("away"), fixture.get("league_id"), fixture.get("event_date"), fixture.get("goalsHomeTeam"), 
                                                            fixture.get("goalsAwayTeam"), self.status_lookup[fixture.get("statusShort")], fixture.get('fixture_id'))
                except Exception:
                    self.bot.logger.exception("Failed to verify/update fixture", fixture_id=fixture.get("league_id"))
                    raise PleaseTellMeAboutIt(f'Failed to verify/update fixture: {fixture.get("league_id")}')

        if updated_fixtures:
            await self.bot.admin_id.send(f"Updated/Inserted {updated_fixtures} fixtures!")


    # @bot.command(hidden=True)
    # @commands.check(isAdmin())
    # async def calculatePredictionScores(ctx):
    @tasks.loop(minutes=5)
    async def calculatePredictionScores(self):
        await checkBotReady()
        scorable_fixtures = {}
        try:
            async with self.bot.pg_conn.acquire() as connection:
                async with connection.transaction():
                    await connection.set_type_codec(
                        'json',
                        encoder=json.dumps,
                        decoder=json.loads,
                        schema='pg_catalog'
                    )
                    unscored_predictions = await connection.fetch("SELECT * FROM predictionsbot.predictions WHERE prediction_score is null")
                    unscored_fixtures = await connection.fetch("SELECT DISTINCT fixture_id FROM predictionsbot.predictions WHERE prediction_score is null")
        except Exception:
            self.bot.logger.exception("encountered error while selecting predictions from database")
            raise PleaseTellMeAboutIt("encountered error while selecting predictions from database")
            
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
            try:       
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"http://v2.api-football.com/fixtures/id/{fix}", headers={'X-RapidAPI-Key': self.bot.api_key}, timeout=60) as resp:
                        fixture_response = await resp.json()
                fixture_info = fixture_response['api']['fixtures'][0]
                goals = [event for event in fixture_info.get("events") if event.get("type") == "Goal" and event.get("teamName") == "Arsenal"]
                scorable_fixtures[fix]["goals"] = sorted(goals, key=lambda k: k['elapsed'])
                scorable_fixtures[fix]["fgs"] = scorable_fixtures[fix]["goals"][0].get("player_id")
            except asyncio.TimeoutError:
                logger.exception("API call to update fixture timed out", fixture=fixture.get('fixture_id'))
            except Exception:
                logger.exception("error retrieving scorable fixture", fixture=fix)
                raise PleaseTellMeAboutIt(f"error retrieving scorable fixture: {fix}")

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
                    prediction.get("scorers")[idx]["player_id"] = await getPlayerId(self.bot, player.get("name"))

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

                self.bot.logger.info("calculated prediction", prediction_id=prediction.get("prediction_id"), user_id=prediction.get("user_id"), prediction_string=prediction.get("prediction_string"), prediction_score=prediction_score)
                try:
                    async with self.bot.pg_conn.acquire() as connection:
                        async with connection.transaction():
                            await connection.execute("UPDATE predictionsbot.predictions SET prediction_score = $1 WHERE prediction_id = $2", prediction_score, prediction.get("prediction_id"))
                except Exception:
                    self.bot.logger.exception("")
                    raise PleaseTellMeAboutIt(f"Could not insert an prediction")


def setup(bot):
    bot.add_cog(TasksCog(bot))