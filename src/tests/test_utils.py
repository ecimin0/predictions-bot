import asyncio
import discord.ext.test as dpytest
import discord
import predictions_bot
import pytest
import re 
import json

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

@pytest.fixture(scope='module')
def event_loop():
    return asyncio.get_event_loop()

@pytest.fixture(scope='module')
async def bot(event_loop):    
    bot = await predictions_bot.init(predictions_bot.credentials, predictions_bot.options, predictions_bot.token, predictions_bot.cogs, loop=event_loop)
    dpytest.configure(bot)
    return dpytest
    
@pytest.mark.asyncio
async def test_welcome_message(bot):
    msg = await bot.message("+prediction")
    # bot.verify_message(".*Predictions League.*", contains=True)
    # bot.get_message().content
    assert re.search(".*Welcome.*", bot.get_message().content)

@pytest.mark.asyncio
async def test_welcome_message_2(bot):
    msg = await bot.message("+prediction")
    # bot.verify_message(".*Predictions League.*", contains=True)
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
    msg = await bot.message("+when palace")
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
async def test_no_sidelined(bot):
    msg = await bot.message("+sidelined")
    response = bot.get_message().content
    assert("Believe it or not Granit Xhaka is not currently suspended" == response or "There are no players currently sidelined" == response)


@pytest.mark.asyncio
async def test_remindme(bot):
    msg = await bot.message("+remindme")
    bot.verify_message("Send prediction reminders set to", contains=True)

@pytest.mark.asyncio
async def test_botissues(bot):
    msg = await bot.message("+botissues")
    bot.verify_message("Open Issues:", contains=True)


# how to do this without opening an actual issue?
@pytest.mark.asyncio
async def test_feedback(bot, mocker):
    data = {}
    resp = MockResponse(json.dumps(data), 200)
    mocker.patch('aiohttp.ClientSession.post', return_value=resp)
    
    msg = await bot.message("+feedback pytest_test_feedback")
    bot.verify_message("Thank you for your feedback", contains=True)

@pytest.mark.asyncio
async def test_ping(bot):
    msg = await bot.message("+ping")
    bot.verify_message("Bot latency is", contains=True)

@pytest.mark.asyncio
async def test_player(bot):
    msg = await bot.message("+player auba")
    bot.verify_message("P. Aubameyang", contains=True)




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






# need to solve the 'new guild has no predictions and thus no leaderboard' problem
# @pytest.mark.asyncio
# async def test_leaderboard(bot):
#     msg = await bot.message("+leaderboard")
#     print(bot.get_message())

# # won't work until testing db works
# @pytest.mark.asyncio
# async def test_rank(bot):
#     msg = await bot.message("+rank")
#     bot.verify_message("Score", contains=True)

# fails due to no guild ID in insert
# @pytest.mark.asyncio
# async def test_predict_fgs(bot):
#     msg = await bot.message("+predict 1-1 auba fgs")
#     message = bot.get_message().content
#     assert re.search(".*P. Aubameyang: 1 fgs.*", message, re.DOTALL)

# @pytest.mark.asyncio
# async def test_predict_fgs_without_fgs(bot):
#     msg = await bot.message("+predict 1-1 auba")
#     message = bot.get_message().content
#     assert re.match(".*`\+predict 1-1 auba`\n\n\*\*Score\*\*\nNone [a-zA-Z]+ 1 - 1 None [a-zA-Z]+\n\n\*\*Goal Scorers\*\*\nP. Aubameyang: 1 fgs.*", message, re.DOTALL)

# @pytest.mark.asyncio
# async def test_predict_too_many_goal_scorers(bot):
#     msg = await bot.message("+predict 1-1 auba 2x")
#     message = bot.get_message().content
#     assert not re.match("It looks like you have predicted Arsenal to score 1, but have included too many goal scorers:\nPrediction: `+predict 1-1 auba 2x`\nNumber of scorers predicted: 2 | Predicted goals scored: 1", message, re.DOTALL)

# @pytest.mark.asyncio
# async def test_predict_not_a_player(bot):
#     msg = await bot.message("+predict 1-1 notaplayer fgs")
#     bot.verify_message("Please try again, no player named notaplayer", contains=True) 







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



# has to wait for page turn reaction to time out, raises NotImplementedError
@pytest.mark.asyncio
async def test_past_fixtures(bot):
    msg = await bot.message("+results")
    bot.verify_message("Past Match Results", contains=True)

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

