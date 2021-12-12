#!/usr/local/bin/python3

from pprint import pprint
from dataclasses import dataclass
from typing import Optional
import datetime

@dataclass
class Team:
    # dataclasses is not as important to include init
    id: int
    name: str
    comment: str
    image: Optional[str] = None

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
    nicknames: Optional[str] = None
    sidelined: Optional[bool] = None
    sidelined_start: Optional[datetime.datetime] = None
    sidelined_end: Optional[datetime.datetime] = None
    sidelined_reason: Optional[str] = None
    active: Optional[bool] = None


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
        return f"{self.winner.name} {self.winner.comment.lower()}\n{self.odds.output()}"
