import discord.ext.test as dpytest
import predictions_bot
import pytest


@pytest.mark.asyncio
async def test_bot():
    bot = predictions_bot.bot
    
    # Load any extensions/cogs you want to in here
    bot.load_extension("cogs.util")
    dpytest.configure(bot)
    
    msg = await dpytest.message("+ping test")
    print(msg.content)
    dpytest.verify_message("test")


# @pytest.mark.parametrize("fixture1, fixture2", [
#     ({"home": "test", 
#     "away": "test", 
#     "event_date": "test",
#     "goalsHomeTeam": "test",
#     "goalsAwayTeam": "test",
#     "league_id": "test"}, {"home": "test", 
#     "away": "test", 
#     "event_date": "test",
#     "goalsHomeTeam": "test",
#     "goalsAwayTeam": "test",
#     "league_id": "test"})
# ])
# def test_changesExist(fixture1, fixture2):
#     assert changesExist(fixture1, fixture2)