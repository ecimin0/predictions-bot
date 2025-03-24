import asyncio
import discord.ext.test as dpytest
import discord
import predictions_bot
import pytest
import re 
import json

from utils.utils import *

class MockResponse:
    def __init__(self, text, status):
        self._text = text
        self.status = status

    async def json(self):
        return {"definitely_json": True}

    async def text(self):
        return self._text

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def __aenter__(self):
        return self

# init tests
@pytest.fixture(scope='module')
def event_loop():
    return asyncio.get_event_loop()


@pytest.fixture(scope='module')
async def bot(event_loop):    
    bot = await predictions_bot.init(predictions_bot.credentials, predictions_bot.options, predictions_bot.token, predictions_bot.cogs, loop=event_loop)
    dpytest.configure(bot)
    async with bot.db.acquire() as connection:
        async with connection.transaction():
            for guild in bot.guilds:
                await connection.execute("INSERT INTO predictionsbot.guilds (guild_id, main_team) VALUES ($1, 42);", guild.id)
    return dpytest


@pytest.mark.asyncio
async def test_welcome_message(bot):
    msg = await bot.message("+prediction")
    assert re.search(".*Welcome.*", bot.get_message().content)


@pytest.mark.asyncio
async def test_welcome_message_2(bot):
    msg = await bot.message("+prediction")
    assert re.search(".*you have no predictions!.*", bot.get_message().content)


@pytest.mark.asyncio
async def test_echo(bot):    
    bot.get_message().content
    msg = await bot.message("+echo test")
    bot.verify_message("test", contains=True)


@pytest.mark.asyncio
async def test_predict_no_prediction(bot):
    with pytest.raises(discord.ext.commands.errors.MissingRequiredArgument) as e:
        msg = await bot.message("+predict")
    assert 'prediction is a required argument' in str(e.value)


@pytest.mark.asyncio
async def test_timezone(bot):
    message = bot.get_message().content
    msg = await bot.message("+timezone")
    bot.verify_message("Your current timezone is UTC", contains=True) 


@pytest.mark.asyncio
async def test_set_timezone_spaces(bot):
    msg = await bot.message("+timezone        Asia/Kolkata")
    bot.verify_message("Your timezone has been set to Asia/Kolkata", contains=True) 


@pytest.mark.asyncio
async def test_rules(bot):
    msg = await bot.message("+rules")
    bot.verify_message("**Remember, we are only counting Arsenal goal scorers**", contains=True) 


@pytest.mark.asyncio
async def test_when_arsenal(bot):
    msg = await bot.message("+when arsenal")
    bot.verify_message("You are on the channel for Arsenal, we cannot play against ourselves.", contains=True)


@pytest.mark.asyncio
async def test_when_team(bot):
    msg = await bot.message("+when brentford")
    bot.verify_message("vs", contains=True)


@pytest.mark.asyncio
async def test_when_team_no_remaining(bot):
    msg = await bot.message("+when biggleswade united")
    bot.verify_message("Arsenal does not have any upcoming matches against biggleswade united", contains=True)


@pytest.mark.asyncio
async def test_when_team_invalid(bot):
    msg = await bot.message("+when nobody")
    bot.verify_message("nobody does not seem to be a team I recognize.", contains=True)


@pytest.mark.asyncio
async def test_next_negative(bot):
    msg = await bot.message("+next -1")
    bot.verify_message("Number of next matches cannot be a negative number", contains=True)


@pytest.mark.asyncio
async def test_next_too_many(bot):
    msg = await bot.message("+next 49")
    bot.verify_message("Number of next matches cannot be greater than 20", contains=True)


# invokes 55s timeout; works as long as no pages are needed
@pytest.mark.asyncio
async def test_next_with_no_arg_is_2(bot):
    msg = await bot.message("+next")
    bot.verify_message("Next 2 matches:", contains=True)


@pytest.mark.asyncio
async def test_next_team_more_than_one(bot):
    msg = await bot.message("+next preston")
    bot.verify_message("matches more than 1 team, please be more specific.", contains=True)


@pytest.mark.asyncio
async def test_next_team_more_than_ten(bot):
    msg = await bot.message("+next ham")
    bot.verify_message("`ham` matches more than 10 teams, please be more specific.", contains=True)


# invokes 55s timeout; works as long as no pages are needed
@pytest.mark.asyncio
async def test_no_sidelined(bot):
    msg = await bot.message("+sidelined")
    response = bot.get_message().content
    assert("There are no players currently sidelined" == response or "Sidelined Arsenal Players")


# @pytest.mark.asyncio
# async def test_remindme(bot):
#     msg = await bot.message("+remindme")
#     bot.verify_message("Send prediction reminders set to", contains=True)

# @pytest.mark.asyncio
# async def test_botissues(bot):
#     msg = await bot.message("+botissues")
#     bot.verify_message("Open Issues:", contains=True)

# @pytest.mark.asyncio
# async def test_feedback(bot, mocker):
#     data = {}
#     resp = MockResponse(json.dumps(data), 200)
#     resptext = resp.text()
#     mocker.patch('aiohttp.ClientSession.post', return_value=resp)    
#     msg = await bot.message("+feedback pytest_test_feedback")
#     bot.verify_message("Thank you for your feedback", contains=True)


@pytest.mark.asyncio
async def test_getRandomTeam(bot):
    assert await getRandomTeam(bot.get_config().client)


@pytest.mark.asyncio
async def test_nextMatches(bot):
    assert await nextMatches(bot.get_config().client, 4)


@pytest.mark.asyncio
async def test_getUsersPredictionCurrentMatch(bot):
    assert await getUsersPredictionCurrentMatch(bot.get_config().client)


# @pytest.mark.asyncio
# async def test_getUserPredictedLastMatches(bot):
#     assert await getUserPredictedLastMatches(bot.get_config().client)


@pytest.mark.asyncio
async def test_playerNames(bot):
    result = await playerNames(bot.get_config().client, "odegaard")
    assert result
    assert "Martin Ødegaard" in result[0]
    assert "odegaard" in result[0]


@pytest.mark.asyncio
async def test_playerNames_multiple(bot):
    result = await playerNames(bot.get_config().client, "gab")
    assert len(result) > 1


@pytest.mark.asyncio
async def test_playerNames_input_too_short(bot):
    result = await playerNames(bot.get_config().client, "ga")
    assert len(result) == 0


@pytest.mark.asyncio
async def test_getPlayerId_not(bot):
    with pytest.raises(Exception) as excinfo:
        result = await getPlayerId(bot.get_config().client, "luffy")
        assert str(excinfo.value) == "no player named luffy"


@pytest.mark.asyncio
async def test_getPlayerId_match_nickname(bot):
    assert await getPlayerId(bot.get_config().client, "gabriel") == 22224


@pytest.mark.asyncio
async def test_getPlayerId_multiple(bot):
    with pytest.raises(Exception) as excinfo:
        result = await getPlayerId(bot.get_config().client, "gab")
        assert "matches more than 1 player" in str(excinfo.value)


@pytest.mark.asyncio
async def test_getPlayerId(bot):
    assert await getPlayerId(bot.get_config().client, "saka") == 1460


@pytest.mark.asyncio
async def test_checkBotReady():
    await checkBotReady() # no return on this?


@pytest.mark.asyncio
async def test_makeOrdinal():
    assert makeOrdinal(1)


@pytest.mark.asyncio
async def test_checkUserExists(bot):
    result = await checkUserExists(bot.get_config().client, 249231078303203329, "@globstar_hip_hop", ":arsenal:")
    assert not result.actions
    assert result.upstream_value


@pytest.mark.asyncio
async def test_id_generator():
    assert await id_generator()


@pytest.mark.asyncio
async def test_id_generator_3():
    assert await id_generator(size=3)


@pytest.mark.asyncio
async def test_checkUserExists_not(bot):
    result = await checkUserExists(bot.get_config().client, await id_generator(), "@globstar_hip_hop", ":arsenal:")
    assert len(result.actions) == 1
    assert result.upstream_value


def test_isAdmin():
    assert isAdmin()


@pytest.mark.asyncio
async def test_ping(bot):
    msg = await bot.message("+ping")
    bot.verify_message("Bot latency is", contains=True)


@pytest.mark.asyncio
async def test_player(bot):
    msg = await bot.message("+player saka")
    bot.verify_message("B. Saka", contains=True)


@pytest.mark.asyncio
async def test_predict_fgs(bot):
    msg = await bot.message("+predict 1-1 saka fgs")
    message = bot.get_message().content
    assert re.search(".*B. Saka: 1 fgs.*", message, re.DOTALL)


@pytest.mark.asyncio
async def test_predict_too_many_goal_scorers(bot):
    msg = await bot.message("+predict 1-1 saka 2x")
    message = bot.get_message().content
    assert not re.match("It looks like you have predicted Arsenal to score 1, but have included too many goal scorers:\nPrediction: `+predict 1-1 saka 2x`\nNumber of scorers predicted: 2 | Predicted goals scored: 1", message, re.DOTALL)


@pytest.mark.asyncio
async def test_predict_not_a_player(bot):
    msg = await bot.message("+predict 1-1 notaplayer fgs")
    bot.verify_message("Please try again, no player named notaplayer", contains=True)


@pytest.mark.asyncio
async def test_getFixtureByID(bot):
    assert await getFixtureByID(bot.get_config().client, 710716)


# @pytest.mark.asyncio
# async def test_getUserRank(bot):
#     print(bot.get_config())
#     assert await getUserRank(bot.get_config().client)


# # won't work until testing db works
# @pytest.mark.asyncio
# async def test_rank(bot):
#     msg = await bot.message("+rank")
#     bot.verify_message("Score", contains=True)


# # invokes 55s timeout
# @pytest.mark.asyncio
# async def test_past_fixtures(bot):
#     msg = await bot.message("+results")
#     bot.verify_message("Past Match Results", contains=True)


@pytest.mark.asyncio
async def test_past(bot):
    msg = await completedMatches(bot.get_config().client, count=2)
    assert len(msg) == 2



# @pytest.mark.asyncio                                              # doesnt work, see https://gitlab.com/ecimino/predictions-bot/-/jobs/1899995664
# async def test_getTeamsInLeague(bot):
#     assert await getTeamsInLeague(bot.get_config().client, 3456)

# this is an API hit, not db; testing run needs API key
# @pytest.mark.asyncio
# async def test_getTeamsInLeague(bot):
#     result = await getTeamsInLeague(bot.get_config().client, 39)
#     assert len(result) == 20


# failing due to gitlab db stuff as well
# @pytest.mark.asyncio
# async def test_getTopPredictions(bot):
#     assert await getTopPredictions(bot.get_config().client, 710556)


# @pytest.mark.asyncio
# async def test_getAveragePredictionScore(bot):
#     assert await getAveragePredictionScore(bot.get_config().client, 710556)


# # this works but is slow as hell
# @pytest.mark.asyncio
# async def test_next(bot):
#     msg = await bot.message("+next")
#     message = bot.get_message().content
#     assert re.match(".*?\n\*\*Next 2 matches:\*\*\n\n(.*?\n.*?vs.*?\n\w*, \d+? \w+ \d\d:\d\d \w{2} \w{3}\n?\n?){2}", message)   
    # assert re.match(".*\n\*\*Next 2 matches:\*\*\n\n([a-zA-Z: ]*\n[a-zA-Z: ]*?vs[a-zA-Z: ]*?\n\w*, \d{1,2}? \w+ \d\d:\d\d \w{2} \w{3}\n?\n?){2}", message)


# # don't work due to pagination of output results > 5, also slow
# @pytest.mark.asyncio
# async def test_next_nine(bot):
#     msg = await bot.message("+next 9")
#     message = bot.get_message().content
#     assert re.match(".*?\n\*\*Next 9 matches:\*\*\n\n(.*?\n.*?vs.*?\n\w*, \d+? \w+ \d\d:\d\d \w{2} \w{3}\n?\n?){9}", message)   


# @pytest.mark.asyncio
# async def test_next_eleven(bot):
#     msg = await bot.message("+next 11")
#     message = bot.get_message().content
#     assert re.match(".*?\n\*\*Next 11 matches:\*\*\n\n(.*?\n.*?vs.*?\n\w*, \d+? \w+ \d\d:\d\d \w{2} \w{3}\n?\n?){11}", message)  


# @pytest.mark.asyncio
# async def test_predict_fgs_without_fgs(bot):
#     msg = await bot.message("+predict 1-1 saka")
#     message = bot.get_message().content
#     assert re.match(".*`\+predict 1-1 saka`\n\n\*\*Score\*\*\nNone [a-zA-Z]+ 1 - 1 None [a-zA-Z]+\n\n\*\*Goal Scorers\*\*\nB. Saka: 1 fgs.*", message, re.DOTALL)


# need to solve the 'new guild has no predictions and thus no leaderboard' problem
# @pytest.mark.asyncio
# async def test_leaderboard(bot):
#     msg = await bot.message("+leaderboard")
#     message = bot.get_message().content
#     assert re.search(".*1st:.*points.*", message, re.DOTALL)
#     print(bot.get_message())


# admin stuff
# @pytest.mark.asyncio
# async def test_list_cogs(bot):
#     # bot.verify_message("", contains=True)
#     with pytest.raises(IsNotAdmin) as e:
#         msg = await bot.message("+list_cogs")
#     assert re.search('User .* is not an admin and cannot use this function.', e)


# @pytest.mark.asyncio
# async def test_test_embed(bot):
#     msg = await bot.message("+testEmbed")
#     bot.verify_embed("Test 0", contains=True)


# fails due to nothing in db in gitlab run
# @pytest.mark.asyncio
# async def test_table(bot):
#     msg = await bot.message("+table")
#     bot.verify_message("```|   Rank | Team              |   P | W-D-L   |   GD |   Pts |", contains=True)


# @pytest.mark.asyncio
# async def test_results(bot):
#     msg = await bot.message("+results")
#     bot.verify_message("Past Match Results", contains=True)
#     # how to test len(paged_results) > 0?



@pytest.mark.asyncio
async def test_getFixturesWithPredictions(bot):
    assert len(await getFixturesWithPredictions(bot.get_config().client)) > 0


# needs guild ID somehow
# @pytest.mark.asyncio
# async def test_getUserPredictions(bot):
#     assert len(await getUserPredictions(bot.get_config().client)) > 0


@pytest.mark.asyncio
async def test_completedMatches(bot):
    assert len(await completedMatches(bot.get_config().client)) > 0


@pytest.mark.asyncio
async def test_getTeamId(bot):
    result = await getTeamId(bot.get_config().client, "arsenal")
    assert result
    assert result == 42

@pytest.mark.asyncio
async def test_getTeamId_match_nickname(bot):
    result = await getTeamId(bot.get_config().client, "city")
    assert result
    assert result == 50


@pytest.mark.asyncio
async def test_checkOptOut(bot):
    result = await checkOptOut(bot.get_config().client, 1139746543851667459)
    assert result
    assert result == True



# @pytest.mark.asyncio
# async def test_(bot):
#     msg = await bot.message("+")
#     bot.verify_message("", contains=True)

# @pytest.mark.asyncio
# async def test_(bot):
#     msg = await bot.message("+")
#     bot.verify_message("", contains=True)

# @pytest.mark.asyncio
# async def test_(bot):
#     msg = await bot.message("+")
#     bot.verify_message("", contains=True)

# @pytest.mark.asyncio
# async def test_(bot):
#     msg = await bot.message("+")
#     bot.verify_message("", contains=True)

# @pytest.mark.asyncio
# async def test_(bot):
#     msg = await bot.message("+")
#     bot.verify_message("", contains=True)

# @pytest.mark.asyncio
# async def test_(bot):
#     msg = await bot.message("+")
#     bot.verify_message("", contains=True)

# @pytest.mark.asyncio
# async def test_(bot):
#     msg = await bot.message("+")
#     bot.verify_message("", contains=True)

