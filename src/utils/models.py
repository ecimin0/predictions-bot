#!/usr/local/bin/python3

import discord
from discord.ext import commands
from pprint import pprint
from dataclasses import dataclass
from typing import Dict, Optional, List, Any
import datetime


@dataclass
class Team:
    # dataclasses is not as important to include init
    team_id: int
    name: Optional[str] = None
    comment: str = ""
    logo: Optional[str] = None
    country: Optional[str] = None
    nicknames: Optional[List[Any]] = None
    emoji: str = ""

    def setEmoji(self, bot) -> None:
        assert self.name is not None
        try:
            self.emoji = Emoji(bot, self.name).emoji
        except Exception as e:
            bot.logger.error(f"{e}")


@dataclass
class Emoji:
# init func to do lookup
    name: str
    emoji: str = ""
    def __init__(self, bot, name: str) -> None:
        self.name = name
        self.emoji =  discord.utils.get(bot.emojis, name=name.lower().replace(' ', '').replace('/', ''))

@dataclass
class Odds:
    home: str
    draw: str
    away: str

    def output(self):
        return f"home: {self.home}\ndraw: {self.draw}\naway: {self.away}"

@dataclass
class Player:
    player_id: int
    season: Optional[str] = None
    team_id: Optional[int] = None
    player_name: Optional[str] = None
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    nicknames: Optional[List[Any]] = None
    sidelined: Optional[bool] = None
    sidelined_start: Optional[datetime.datetime] = None
    sidelined_end: Optional[datetime.datetime] = None
    sidelined_reason: Optional[str] = None
    active: Optional[bool] = None

@dataclass
class User:
    user_id: int
    tz = Optional[str]
    allow_notifications = Optional[str]
    rank = Optional[int]

@dataclass
class Fixture: # matches
    fixture_id: int
    home: Optional[int] = None
    home_name: Optional[str] = None
    away: Optional[int] = None
    away_name: Optional[str] = None
    opponent: Optional[str] = None
    opponent_name: Optional[str] = None
    home_or_away: Optional[str] = None
    league_id: Optional[int] = None
    league_name: Optional[str] = None
    event_date: Optional[datetime.datetime] = None
    new_date: Optional[datetime.datetime] = None
    goals_home: Optional[int] = None
    goals_away: Optional[int] = None
    scorable: Optional[bool] = None
    status_short: Optional[str] = None
    notifications_sent: Optional[bool] = None

class Scorer(Player):
    pass

@dataclass
class UserPrediction:
    prediction_id: str
    user_id: int
    prediction_string: str
    fixture_id: int
    timestamp: datetime.datetime
    prediction_score: int
    home_goals: int
    away_goals: int
    scorers: List[Dict]
    guild_id: int


class V3Predictions:
    """
    This is a prediction from the V3 football api.

    :param predictions: a dict object generated from an api call to the predictions endpoint
    :param **kwargs: other data provided from the API
    """
    def __init__(self, predictions, **kwargs) -> None: # kwargs == Key Word arguments
        self.winner = Team(**predictions.get("winner"))
        self.odds = Odds(**predictions.get("percent"))

    def __str__(self) -> str:
        return f"Winner: {self.winner} Odds: {self.odds}"

    def output(self) -> str:
        return f"**{self.winner.emoji}{self.winner.name}** {self.winner.comment.lower() if self.winner.comment else ''}\n{self.odds.output()}"
