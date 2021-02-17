import discord
from discord.ext import commands
from datetime import timedelta, datetime
import random
import pytz 
import re 
import json
import asyncio

from utils.utils import *
from utils.exceptions import *
from typing import List, Dict, Optional

class Predictions(commands.Cog, name="Prediction Functions"): # type: ignore
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["prediction"])
    async def predictions(self, ctx: commands.Context):
        '''
        Show your past predictions
        '''
        await checkUserExists(self.bot, ctx.message.author.id, ctx)

        #compare all fixtures with predictions to user predictions
        predictions = await getUserPredictions(self.bot, ctx)
        fixtures = await getFixturesWithPredictions(self.bot, ctx)
        rank = await getUserRank(self.bot, ctx)
        # print(rank)

        if not predictions:
            await ctx.send(f"{ctx.message.author.mention}\nIt looks like you have no predictions! Get started by typing `+predict`")
            return

        paginated_data = []

        color = getArsenalColor()

        total = 0
        offset = 0
        
        self.bot.logger.debug(fixtures=fixtures, len_fixture=len(fixtures), predictions=predictions, len_predictions=len(predictions))
        fields = []
        for i in range(0,len(fixtures)):
            fixture = fixtures[i]
            if i - offset > len(predictions) - 1:
                offset += 1
            prediction = predictions[i - offset]
            self.bot.logger.debug(count=i,offset=offset,fixture_id=fixture.get("fixture_id"), prediction_fixture_id=prediction.get("fixture_id"))
            match = await getMatch(self.bot, fixture.get("fixture_id"))

            home_emoji = discord.utils.get(self.bot.emojis, name=match.get('home_name').lower().replace(' ', ''))
            away_emoji = discord.utils.get(self.bot.emojis, name=match.get('away_name').lower().replace(' ', ''))

            if not fixture.get("fixture_id") == prediction.get("fixture_id"):
                offset += 1
                fields.append({
                    "name": f'{match.get("event_date").strftime("%m/%d/%y")} | {home_emoji} {match.get("home_name")} {match.get("goals_home") or 0} - {match.get("goals_away") or 0} {away_emoji} {match.get("away_name")}', 
                    "value": "Score: **0** | `no prediction made`"
                })
            else:
                if prediction.get("prediction_score"):
                    total += prediction.get("prediction_score")
                prediction_value = "TBD"
                if prediction.get("prediction_score") is not None:
                    prediction_value = prediction.get("prediction_score")
                fields.append({
                    "name": f'{match.get("event_date").strftime("%m/%d/%y")} | {home_emoji} {match.get("home_name")} {match.get("goals_home") or 0} - {match.get("goals_away") or 0} {away_emoji} {match.get("away_name")}', 
                    "value": f'Score: **{prediction_value}** | `{prediction.get("prediction_string")}`\n\n'
                })
                # output += f'`{match.get("event_date").strftime("%m/%d/%Y")} {match.get("home_name")} vs {match.get("away_name")}` | `{prediction.get("prediction_string")}` | Score: `{prediction.get("prediction_score")}`\n'

        if rank == 0:
            description = f"_League score: **{total}** | League pos. **N/A - no predictions scored**_"
        else:
            description = f"_League score: **{total}** | League pos. **{makeOrdinal(rank)}**_"

        for i in range(0, len(fields), self.bot.step):
            paginated_data.append({"title": f"Predictions for {ctx.message.author.display_name}", "description": description, "color": color, "thumbnail": "", "fields": fields[i:i + self.bot.step]})

        await makePagedEmbed(self.bot, ctx, paginated_data)
        # await ctx.send(f"{ctx.message.author.mention}\n",embed=embed)


    @commands.command()
    @commands.cooldown(1, 30, commands.BucketType.default)
    async def leaderboard(self, ctx: commands.Context):
        '''
        Show leaderboard | Once every 30 seconds
        '''
        log = self.bot.logger.bind(content=ctx.message.content, author=ctx.message.author.name)
        # embed = discord.Embed(title="Arsenal Prediction League Leaderboard", description="\u200b", color=embed_color)
        # embed.set_thumbnail(url="https://media.api-sports.io/football/teams/42.png")

        # if need to change the way the tied users are displayed change "RANK()" to "DENSE_RANK()"
        try:
            leaderboard = await self.bot.db.fetch(f"SELECT DENSE_RANK() OVER(ORDER BY SUM(prediction_score) DESC) as rank, SUM(prediction_score) as score, user_id FROM predictionsbot.predictions WHERE prediction_score IS NOT NULL AND guild_id = $1 GROUP BY user_id ORDER BY SUM(prediction_score) DESC", ctx.guild.id)
        except Exception:
            log.exception("Failed to retrieve predictions leaderboard from database")

        prediction_dictionary: Dict[int, List] = {}
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
        # self.bot.logger.debug(prediction_dictionary)
        
        rank_num = 1
        paginated_data = []
        color = getArsenalColor()
        output_paged_array = []
        for v in prediction_dictionary.values():
            # current_embed = embed_dictionary.get(k)
            output_array = []
            for user_prediction in v:
                try:
                    # for user in all_members:
                    #     if user.id == user_prediction.get("user_id"):

                    user = ctx.guild.get_member(user_prediction.get("user_id"))
                    # user = self.bot.get_user(user_prediction.get("user_id"))
                    # self.bot.logger.debug(user=user, rank=user_prediction.get("rank"))
                    if user:
                        self.bot.logger.debug(user_id=user_prediction.get("user_id"), rank=user_prediction.get("rank"))
                        output_array.append(f'{user.display_name}')
                    else:
                        self.bot.logger.debug("Missing user", user_id=user_prediction.get("user_id"), rank=user_prediction.get("rank"))
                        output_array.append("*transferred to spurs*")
                        # current_embed.add_field(name=f"Rank: {user.display_name}", value=f'{user_prediction.get("score")} points', inline=True)
                except discord.NotFound:
                    self.bot.logger.warning("Missing user mapping", user=user_prediction.get("user_id"))
            self.bot.logger.debug(output_array)
            output_str = "\n".join(output_array)
            self.bot.logger.debug(output_str)
            output_paged_array.append({"name": f"{makeOrdinal(rank_num)}: {user_prediction.get('score')} Points", "value": output_str})
        
            if len(output_paged_array) == self.bot.step:        
                paginated_data.append({
                    "title": "**Arsenal Prediction League Leaderboard**", 
                    "description": "", 
                    # "description": f"{rank_num}/{len(prediction_dictionary)}", 
                    "color": color, 
                    "thumbnail": "https://media.api-sports.io/football/teams/42.png", 
                    "fields": output_paged_array
                    })
                output_paged_array = []

            # paginated_data.append({"rank": f"{rank_num}", "rank_score": f"{user_prediction.get('score')}", "leaders": f"{output_str}"})
            rank_num += 1
        if output_paged_array:
            paginated_data.append({
                    "title": "**Arsenal Prediction League Leaderboard**", 
                    "description": "", 
                    # "description": f"{rank_num}/{len(prediction_dictionary)}", 
                    "color": color, 
                    "thumbnail": "https://media.api-sports.io/football/teams/42.png", 
                    "fields": output_paged_array
                    })

        await makePagedEmbed(self.bot, ctx, paginated_data)


    @commands.command(brief="Make a prediction.")
    async def predict(self, ctx: commands.Context, *, prediction: str):
        '''
        Make a new prediction | +predict 1-1 auba fgs, laca | Type scores as home - away.'
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

        time_limit_offset: Dict[str, float] = {
            self.bot.league_dict["europa_league"]: 1.5
        }
        # if europa league then timedelta(hours=1.5)
        # else timedelta(hours=1)
        time_offset = 1.0
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

        # temp_msg = ctx.message.content
        if not prediction:
            await ctx.send(f"{ctx.message.author.mention}\nIt looks like you didn't actually predict anything!\nTry something like `+predict 3-2 auba fgs, laca`")
            return 

        goals_regex = r"((\d{1,2}) ?[:-] ?(\d{1,2}))"
        # player_regex = r"[A-Za-z]{1,18}[,]? ?(\d[xX]|[xX]\d)?"
        prediction_string = ctx.message.content
        try:
            goals_match = re.search(goals_regex, prediction)
        
            prediction = re.sub(goals_regex, "", prediction)

            scorers = prediction.strip().split(",")

            scorers = [player.strip() for player in scorers]

            scorer_properties = []

            player_scores: Dict[int, Dict] = {}
            first_player: Optional[int] = None
            for player in scorers:
                if not player:
                    continue

                fgs = False
                num_goals = 1
                fgs_str = ""

                if re.search("[fF][gG][sS]", player) or len(scorers) == 1:
                    fgs = True
                    player = re.sub("[fF][gG][sS]", "", player)
                    fgs_str = "fgs"

                goals_scored = re.search(r'[xX]?(\d{1,2})[xX]?', player)
                if goals_scored:
                    player = re.sub(r'[xX]?(\d{1,2})[xX]?', "", player)
                    num_goals = int(goals_scored.group(1))

                try:
                    player_id = await getPlayerId(self.bot, player.strip())
                    if not first_player:
                        first_player = player_id
                    player_real_name = await self.bot.db.fetchrow("SELECT player_name FROM predictionsbot.players WHERE player_id = $1;", player_id)
                    real_name = player_real_name.get("player_name")
                except Exception as e:
                    await ctx.send(f"{ctx.message.author.mention}\nPlease try again, {e}")
                    # names = await playerNames(self.bot, player.strip())
                    # names_str = '\n'.join(names)
                    # await ctx.send(f"Here are some possible players\n{names_str}")
                    return

                if player_id not in player_scores:
                    player_scores[player_id] = {"name": player.strip(), "fgs": fgs, "num_goals": num_goals, "fgs_string": fgs_str, "real_name": real_name}
                else:
                    player_scores[player_id]["num_goals"] += num_goals
                    if not player_scores[player_id]["fgs"] and fgs:
                        player_scores[player_id]["fgs"] = True
                        player_scores[player_id]["fgs_string"] = "fgs"

            if not any([score.get('fgs') for score in player_scores.values()]) and first_player:
                player_scores[first_player]["fgs"] = True
                player_scores[first_player]["fgs_string"] = "fgs"

            log.debug(player_scores)

            scorer_properties = [player for player in player_scores.values()]
            if len([player for player in player_scores.values() if player.get("fgs")]) > 1:
                await ctx.send(f"{ctx.message.author.mention}\nTwo players cannot be first goal scorer, predict again.")
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
            predicted_goal_count += scorer.get("num_goals", 0)

        if predicted_goal_count > arsenal_goals:
            await ctx.send(f"{ctx.message.author.mention}\nIt looks like you have predicted Arsenal to score {arsenal_goals}, but have included too many goal scorers:\nPrediction: `{prediction_string}`\nNumber of scorers predicted: {predicted_goal_count} | Predicted goals scored: {arsenal_goals}")
            return

        try:
            prediction_id = randomAlphanumericString(16)
            successful_or_updated = "successful"

            # print(f"{prediction_id}, {ctx.message.author.id}, {prediction_string}")
            # use similar syntax as next lines for any insert/update to the db
            # also include the magic json stuff for things accessing the predictions table
            async with self.bot.db.acquire() as connection:
                async with connection.transaction():
                    await connection.set_type_codec(
                        'json',
                        encoder=json.dumps,
                        decoder=json.loads,
                        schema='pg_catalog'
                    )
                    try:
                        prev_prediction = await connection.fetchrow("SELECT * FROM predictionsbot.predictions WHERE user_id = $1 AND fixture_id = $2 AND guild_id = $3", ctx.message.author.id, fixture_id, ctx.guild.id)
                        if prev_prediction:
                            successful_or_updated = "updated"
                            await connection.execute(f"UPDATE predictionsbot.predictions SET prediction_string = $1, home_goals = $2, away_goals = $3, scorers = $4::json, timestamp = now() WHERE user_id = $5 AND fixture_id = $6 AND guild_id = $7", prediction_string, home_goals, away_goals, scorer_properties, ctx.message.author.id, fixture_id, ctx.guild.id)
                        else:
                            await connection.execute("INSERT INTO predictionsbot.predictions (prediction_id, user_id, prediction_string, fixture_id, home_goals, away_goals, scorers, guild_id) VALUES ($1, $2, $3, $4, $5, $6, $7, $8);", prediction_id, ctx.message.author.id, prediction_string, fixture_id, home_goals, away_goals, scorer_properties, ctx.guild.id)
                    except Exception as e:
                        log.exception("Error adding prediction")
                        await ctx.send(f"{ctx.message.author.mention}\nThere was an error adding your prediction, please try again later.")
                        return

            goal_scorers_array = [f'{scorer.get("real_name")}: {scorer.get("num_goals")} {scorer.get("fgs_string")}' for scorer in scorer_properties]
            goal_scorers = "\n".join(goal_scorers_array)
            home_emoji = discord.utils.get(self.bot.emojis, name=current_match.get('home_name').lower().replace(' ', ''))
            away_emoji = discord.utils.get(self.bot.emojis, name=current_match.get('away_name').lower().replace(' ', ''))
            output = f"""{ctx.message.author.mention}\n**Prediction against {discord.utils.get(self.bot.emojis, name=opponent.lower().replace(' ', ''))} {opponent} {successful_or_updated}.**\nYou have until {time_limit_str} to edit your prediction.\n`{ctx.message.content}`"""
            output += f"""\n\n**Score**\n{home_emoji} {current_match.get('home_name')} {home_goals} - {away_goals} {away_emoji} {current_match.get('away_name')}\n\n"""
            if goal_scorers:
                output += f"""**Goal Scorers**\n{goal_scorers}"""
            await ctx.send(output)

        except (Exception) as e:
            log.exception(f"There was an error loading this prediction into the database: {e}")
            await self.bot.notifyAdmin(f"There was an error loading this prediction into the databse:\n{e}")
            return


    @commands.command(brief="Show your league rank")
    async def rank(self, ctx: commands.Context, aliases=['position']):
        '''
        Show your league rank
        '''
        log = self.bot.logger.bind(content=ctx.message.content, author=ctx.message.author.name)

        try:
            leaderboard = await self.bot.db.fetch(f"SELECT DENSE_RANK() OVER(ORDER BY SUM(prediction_score) DESC) as rank, SUM(prediction_score) as score, user_id FROM predictionsbot.predictions WHERE prediction_score IS NOT NULL AND guild_id = $1 GROUP BY user_id ORDER BY SUM(prediction_score) DESC", ctx.guild.id)
        except Exception as e:
            log.exception(f"Failed to retrieve predictions leaderboard from database for rank command, {e}")
        
        prediction_dictionary: Dict[int, List] = {}

        for prediction in leaderboard:
            if prediction.get("rank") not in prediction_dictionary:
                self.bot.logger.debug("Creating new rank in dictionary for rank command", user_id=prediction.get("user_id"), rank=prediction.get("rank"))
                prediction_dictionary[prediction.get("rank")] = [prediction]
            else:
                prediction_dictionary[prediction.get("rank")].append(prediction)

        try:
            for k,v in prediction_dictionary.items():
                for prediction in v:
                    # user = ctx.guild.get_member(prediction.get("user_id"))
                    if prediction.get("user_id") == ctx.message.author.id:
                    # if user == ctx.message.author.id:
                        rank = prediction.get("rank")
                        score = prediction.get("score")

                        first_score = prediction_dictionary.get(1)[0].get("score")

                        # print(f'{rank} {score}')
                        ahead_rank = prediction_dictionary.get(rank - 1)
                        behind_rank = prediction_dictionary.get(rank + 1)
                        off_first = first_score - score
                        output_str = ""

                        if not ahead_rank:
                            # print(f'{rank}: {score}, {behind_rank[0].get("rank")}: {behind_rank[0].get("score")}')
                            # print("First place")
                            output_str = f"**{makeOrdinal(rank)}** :crown: out of {len(prediction_dictionary)}\nScore: **{score}**\n**{score - behind_rank[0].get('rank')}** ahead of {makeOrdinal(behind_rank[0].get('rank'))}"
                        elif not behind_rank:
                            # print("Last place")
                            # print(f'{rank}: {score}, {ahead_rank[0].get("rank")}: {ahead_rank[0].get("score")}')
                            # print(f'pts behind first place: {off_first}')
                            output_str = f"**{makeOrdinal(rank)}** out of {len(prediction_dictionary)}\nScore: **{score}**\n**{ahead_rank[0].get('score') - score}** behind {makeOrdinal(ahead_rank[0].get('rank'))}\n**{off_first}** points off top"
                        else:
                            # print(f'{rank}: {score}, {ahead_rank[0].get("rank")}: {ahead_rank[0].get("score")}, {behind_rank[0].get("rank")}: {behind_rank[0].get("score")}')
                            # print("Neither first nor last")
                            # print(f'pts behind first place: {off_first}')
                            output_str = f"**{makeOrdinal(rank)}** out of {len(prediction_dictionary)}\nScore: **{score}**\n**{ahead_rank[0].get('score') - score}** behind {makeOrdinal(ahead_rank[0].get('rank'))}\n**{score - behind_rank[0].get('score')}** ahead of {makeOrdinal(behind_rank[0].get('rank'))}\n**{off_first}** points off top"
        
            await ctx.send(f"{ctx.message.author.mention}\n{output_str}")

        except Exception as e:
            # print(e)
            log.exception(f"Failed to return rank to user: {e}")

            
    @commands.command(brief="Show unavailable players", aliases=["available", "out", "injured", "injury"])
    async def sidelined(self, ctx: commands.Context):
        '''
        Show players currently unavailable for team selection
        '''
        log = self.bot.logger.bind(content=ctx.message.content, author=ctx.message.author.name, command="sidelined")

        try:
            players_that_suck = await self.bot.db.fetch(f"SELECT player_name, sidelined_reason, sidelined_end FROM predictionsbot.players WHERE sidelined;")
        except Exception:
            log.exception("Failed to retrieve players_that_suck from database")
        
        if not players_that_suck:
            if random.randrange(1,255) % 7: 
                await ctx.send("Believe it or not Granit Xhaka is not currently suspended")
            else:
                await ctx.send("There are no players currently sidelined")
        else:
            paginated_data = []
            color = getArsenalColor()
            output_paged_array = []
            for player in players_that_suck:
                end_time = "TBD"
                if end_time_obj := player.get('sidelined_end'):
                    end_time = end_time_obj.strftime('%d %b %Y')

                output_paged_array.append({"name": f"{player.get('player_name')}", "value": f"{player.get('sidelined_reason')} - {end_time}"})
            
                if len(output_paged_array) == self.bot.step:        
                    paginated_data.append({
                        "title": "**Sidelined Arsenal Players**", 
                        "description": "", 
                        # "description": f"{rank_num}/{len(prediction_dictionary)}", 
                        "color": color, 
                        "thumbnail": "https://media.api-sports.io/football/teams/42.png", 
                        "fields": output_paged_array
                        })
                    output_paged_array = []

                # paginated_data.append({"rank": f"{rank_num}", "rank_score": f"{user_prediction.get('score')}", "leaders": f"{output_str}"})
            if output_paged_array:
                paginated_data.append({
                        "title": "**Sidelined Arsenal Players**", 
                        "description": "", 
                        # "description": f"{rank_num}/{len(prediction_dictionary)}", 
                        "color": color, 
                        "thumbnail": "https://media.api-sports.io/football/teams/42.png", 
                        "fields": output_paged_array
                        })

            await makePagedEmbed(self.bot, ctx, paginated_data)


def setup(bot):
    bot.add_cog(Predictions(bot))