import discord
from discord.ext import commands
from datetime import timedelta, datetime
import random
import pytz 
import re 
import json

from utils import makeOrdinal, checkUserExists, getUserTimezone, getUserPredictions, getMatch, getPlayerId, randomAlphanumericString, nextMatch, prepareTimestamp, getFixturesWithPredictions, getUserRank
from exceptions import *

class PredictionsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def predictions(self, ctx):
        '''
        Show your past predictions
        '''
        await checkUserExists(self.bot, ctx.message.author.id, ctx)

        #compare all fixtures with predictions to user predictions
        predictions = await getUserPredictions(self.bot, ctx.message.author.id)
        fixtures = await getFixturesWithPredictions(self.bot)
        rank = await getUserRank(self.bot, ctx.message.author.id)
        # print(rank)

        if not predictions:
            await ctx.send(f"{ctx.message.author.mention}\nIt looks like you have no predictions! Get started by typing `+predict`")
            return

        embed = discord.Embed(title=f"Predictions for {ctx.message.author.display_name}")

        total = 0
        offset = 0
        
        self.bot.logger.debug(fixtures=fixtures, len_fixture=len(fixtures), predictions=predictions, len_predictions=len(predictions))
        for i in range(0,len(fixtures)):
            fixture = fixtures[i]
            if i - offset > len(predictions) - 1:
                offset += 1
            prediction = predictions[i - offset]
            self.bot.logger.debug(count=i,fixture_id=fixture.get("fixture_id"), prediction_fixture_id=prediction.get("fixture_id"))
            match = await getMatch(self.bot, fixture.get("fixture_id"))

            if not fixture.get("fixture_id") == prediction.get("fixture_id"):
                offset += 1
                embed.add_field(name=f'{match.get("event_date").strftime("%m/%d/%Y")} {match.get("home_name")} vs {match.get("away_name")}', value="Score: 0 `no prediction made`", inline=False)
            else:
                if prediction.get("prediction_score"):
                    total += prediction.get("prediction_score")
                prediction_value = "TBD"
                if prediction.get("prediction_score"):
                    prediction_value = prediction.get("prediction_score")
                embed.add_field(name=f'{match.get("event_date").strftime("%m/%d/%Y")} {match.get("home_name")} vs {match.get("away_name")}', value=f'Score: **{prediction_value}** | `{prediction.get("prediction_string")}`\n\n', inline=False)
                # output += f'`{match.get("event_date").strftime("%m/%d/%Y")} {match.get("home_name")} vs {match.get("away_name")}` | `{prediction.get("prediction_string")}` | Score: `{prediction.get("prediction_score")}`\n'
        embed.description=f"_League score: **{total}** | League pos. **{makeOrdinal(rank)}**_"
        await ctx.send(f"{ctx.message.author.mention}\n",embed=embed)


    @commands.command()
    @commands.cooldown(1, 60, commands.BucketType.default)
    async def leaderboard(self, ctx):
        '''
        Show leaderboard
        '''
        log = self.bot.logger.bind(content=ctx.message.content, author=ctx.message.author.name)
        embed_colors = [0x9C824A, 0x023474, 0xEF0107, 0xDB0007]
        embed_color = random.choice(embed_colors)
        embed = discord.Embed(title="Arsenal Prediction League Leaderboard", description="\u200b", color=embed_color)
        embed.set_thumbnail(url="https://media.api-sports.io/football/teams/42.png")

        # if need to change the way the tied users are displayed change "RANK()" to "DENSE_RANK()"
        try:
            leaderboard = await self.bot.pg_conn.fetch(f"SELECT DENSE_RANK() OVER(ORDER BY SUM(prediction_score) DESC) as rank, SUM(prediction_score) as score, user_id FROM predictionsbot.predictions WHERE prediction_score IS NOT NULL GROUP BY user_id ORDER BY SUM(prediction_score) DESC")
        except Exception:
            log.error("Failed to retrieve predictions leaderboard from database")

        prediction_dictionary = {}
        # embed_dictionary = {}
        for prediction in leaderboard:
            # self.bot.logger.debug(user_id=prediction.get("user_id"), rank=prediction.get("rank"))
            if prediction.get("rank") not in prediction_dictionary:
                self.bot.logger.debug("Creating new rank in dictionary", user_id=prediction.get("user_id"), rank=prediction.get("rank"))
                # embed_dictionary[prediction.get("rank")] = discord.Embed(title=f'Rank: {prediction.get("rank")}', description="", color=0x9c824a)
                prediction_dictionary[prediction.get("rank")] = [prediction]
            else:
                prediction_dictionary[prediction.get("rank")].append(prediction)
            # self.bot.logger.debug("Dump dictionary", dictionary=prediction_dictionary)
        
        # all_members = bot.get_all_members()
        
        rank_num = 1
        for v in prediction_dictionary.values():
            # current_embed = embed_dictionary.get(k)
            output_array = []
            for user_prediction in v:
                try:
                    # for user in all_members:
                    #     if user.id == user_prediction.get("user_id"):
                    user = self.bot.get_user(user_prediction.get("user_id"))
                    if user:
                        self.bot.logger.debug(user_id=user_prediction.get("user_id"), rank=user_prediction.get("rank"))
                        output_array.append(f'{user.display_name}')
                        # current_embed.add_field(name=f"Rank: {user.display_name}", value=f'{user_prediction.get("score")} points', inline=True)
                except discord.NotFound:
                    logger.warning("Missing user mapping", user=user_prediction.get("user_id"))
            self.bot.logger.debug(output_array)
            output_str = "\n".join(output_array)
            self.bot.logger.debug(output_str)
            embed.add_field(name=f'Rank {makeOrdinal(rank_num)}:  {user_prediction.get("score")} Points', value=f"```\n{output_str}```", inline=False)
            rank_num += 1

        await ctx.send(f"{ctx.message.author.mention}", embed=embed)

    @commands.command()
    async def predict(self, ctx):
        '''
        Make a new prediction
        '''
        log = self.bot.logger.bind(content=ctx.message.content, author=ctx.message.author.name)

        #checkUserExists inserts the user_id if not present
        try:
            await checkUserExists(self.bot, ctx.message.author.id, ctx)
            current_match = await nextMatch(self.bot)
            user_tz = await getUserTimezone(self.bot, ctx.message.author.id)
        except Exception:
            log.exception("Error initializing user, match, or user tz")
            raise PleaseTellMeAboutIt("Error initializing user, match, or user tz")

        time_limit_offset = {
            self.bot.league_dict["europa_league"]: 1.5
        }
        # if europa league then timedelta(hours=1.5)
        # else timedelta(hours=1)
        time_offset = 1
        if current_match.get("league_id") in time_limit_offset:
            time_offset = time_limit_offset[current_match.get("league_id")]

        time_limit = current_match.get("event_date") - timedelta(hours=time_offset)
        time_limit_str = prepareTimestamp(time_limit, user_tz)
        time_limit = prepareTimestamp(time_limit, user_tz, str=False)

        fixture_id = current_match.get('fixture_id')

        opponent = current_match.get('opponent_name')

        if pytz.timezone("UTC").localize(datetime.utcnow()) > time_limit:
            team = await getRandomTeam(self.bot)
            await ctx.send(f"{ctx.message.author.mention}\nPrediction time too close to match start time. Go support {team} instead.")
            return

        temp_msg = ctx.message.content
        if len(temp_msg.split()) < 2:
            await ctx.send(f"{ctx.message.author.mention}\nIt looks like you didn't actually predict anything!\nTry something like `+predict 3-2 auba fgs, laca`")
            return 

        goals_regex = r"((\d) ?[:-] ?(\d))"
        # player_regex = r"[A-Za-z]{1,18}[,]? ?(\d[xX]|[xX]\d)?"

        try:
            prediction_string = temp_msg
            temp_msg = temp_msg.replace("+predict ", "")

            goals_match = re.search(goals_regex, temp_msg)
        
            temp_msg = re.sub(goals_regex, "", temp_msg)

            scorers = temp_msg.strip().split(",")

            scorers = [player.strip() for player in scorers]

            scorer_properties = []

            player_scores = {}
            
            for player in scorers:
                if not player:
                    continue

                fgs = False
                num_goals = 1

                if re.search("[fF][gG][sS]", player):
                    fgs = True
                    player = re.sub("[fF][gG][sS]", "", player)

                goals_scored = re.search(r'[xX]?(\d)[xX]?', player)
                if goals_scored:
                    player = re.sub(r'[xX]?(\d)[xX]?', "", player)
                    num_goals = int(goals_scored.group(1))

                fgs_str = ""
                if fgs:
                    fgs_str = "fgs"

                try:
                    player_id = await getPlayerId(self.bot, player.strip())
                    player_real_name = await self.bot.pg_conn.fetchrow("SELECT player_name FROM predictionsbot.players WHERE player_id = $1;", player_id)
                    real_name = player_real_name.get("player_name")
                except Exception as e:
                    await ctx.send(f"{ctx.message.author.mention}\nPlease try again, {e}")
                    return 

                if player_id not in player_scores:
                    player_scores[player_id] = {"name": player.strip(), "fgs": fgs, "num_goals": num_goals, "fgs_string": fgs_str, "real_name": real_name}
                else:
                    player_scores[player_id]["num_goals"] += num_goals
                    if not player_scores[player_id]["fgs"] and fgs:
                        player_scores[player_id]["fgs"] = True
                        player_scores[player_id]["fgs_string"] = "fgs"

            log.debug(player_scores)

            scorer_properties = [player for player in player_scores.values()]
            if len([player for player in player_scores.values() if player.get("fgs")]) > 1:
                await ctx.send(f"{ctx.message.author.mention}\nWhy are you the way that you are?\nTwo players cannot be first goal scorer. Predict again.")
                return

        except Exception as e:
            log.exception(f"{e}")
            await ctx.send(f"There was an error parsing this prediction:\n{e}")
            return
        
        if not goals_match:
            await ctx.send(f"{ctx.message.author.mention}\nDid not provide a match score in your prediction.\n`{ctx.message.content}`")
            return
        else:        
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
            await ctx.send(f"{ctx.message.author.mention}\nIt looks like you have predicted Arsenal to score {arsenal_goals}, but have included too many goal scorers:\nPrediction: `{prediction_string}`\nNumber of scorers predicted: {predicted_goal_count} | Predicted goals scored: {arsenal_goals}")
            return

        try:
            prediction_id = randomAlphanumericString(16)
            successful_or_updated = "successful"

            # print(f"{prediction_id}, {ctx.message.author.id}, {prediction_string}")
            # use similar syntax as next lines for any insert/update to the db
            # also include the magic json stuff for things accessing the predictions table
            async with self.bot.pg_conn.acquire() as connection:
                async with connection.transaction():
                    await connection.set_type_codec(
                        'json',
                        encoder=json.dumps,
                        decoder=json.loads,
                        schema='pg_catalog'
                    )
                    try:
                        prev_prediction = await connection.fetchrow("SELECT * FROM predictionsbot.predictions WHERE user_id = $1 AND fixture_id = $2", ctx.message.author.id, fixture_id)
                        if prev_prediction:
                            successful_or_updated = "updated"
                            await connection.execute(f"UPDATE predictionsbot.predictions SET prediction_string = $1, home_goals = $2, away_goals = $3, scorers = $4::json, timestamp = now() WHERE user_id = $5 AND fixture_id = $6", prediction_string, home_goals, away_goals, scorer_properties, ctx.message.author.id, fixture_id)
                        else:
                            await connection.execute("INSERT INTO predictionsbot.predictions (prediction_id, user_id, prediction_string, fixture_id, home_goals, away_goals, scorers) VALUES ($1, $2, $3, $4, $5, $6, $7);", prediction_id, ctx.message.author.id, prediction_string, fixture_id, home_goals, away_goals, scorer_properties)
                    except Exception as e:
                        log.exception("Error adding prediction")
                        await ctx.send(f"{ctx.message.author.mention}\nThere was an error adding your prediction, please try again later.")
                        return

            goal_scorers_array = [f'{scorer.get("real_name")}: {scorer.get("num_goals")} {scorer.get("fgs_string")}' for scorer in scorer_properties]
            goal_scorers = "\n".join(goal_scorers_array)
            home_emoji = discord.utils.get(self.bot.emojis, name=current_match.get('home_name').lower().replace(' ', ''))
            away_emoji = discord.utils.get(self.bot.emojis, name=current_match.get('away_name').lower().replace(' ', ''))
            output = f"""{ctx.message.author.mention}\n**Prediction against {opponent} {successful_or_updated}.**\nYou have until {time_limit_str} to edit your prediction.\n\n`{ctx.message.content}`"""
            output += f"""\n\n**Score**\n{home_emoji} {current_match.get('home_name')} {home_goals} - {away_goals} {away_emoji} {current_match.get('away_name')}\n\n"""
            if goal_scorers:
                output += f"""**Goal Scorers**\n{goal_scorers}"""
            await ctx.send(output)

        except (Exception) as e:
            log.exception(f"There was an error loading this prediction into the database: {e}")
            await self.bot.notifyAdmin(self.bot, f"There was an error loading this prediction into the databse:\n{e}")
            return


def setup(bot):
    bot.add_cog(PredictionsCog(bot))