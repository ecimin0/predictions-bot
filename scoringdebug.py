# // goals = [event for event in fixture_info.get("events") if
# // event.get("type") == "Goal" and
# // event.get("team").get("id") == self.bot.main_team
# // and "Penalty Shootout" != event.get("comments","")]


# // {"goals_home": 4, "goals_away": 1, "winner": "home", "home_or_away": "home"}

# //"id": 38734,

goals = [
        {
            "time": {"elapsed": 18, "extra": "null"},
            "team": {
                "id": 42,
                "name": "Arsenal",
                "logo": "https:\/\/media.api-sports.io\/football\/teams\/42.png",
            },
            "player": {"id": 38734, "name": "S. Botman"},
            "assist": {"id": "null", "name": "null"},
            "type": "Goal",
            "detail": "Own Goal",
            "comments": "null",
        },
        {
            "time": {"elapsed": 24, "extra": "null"},
            "team": {
                "id": 42,
                "name": "Arsenal",
                "logo": "https:\/\/media.api-sports.io\/football\/teams\/42.png",
            },
            "player": {"id": 978, "name": "K. Havertz"},
            "assist": {"id": 127769, "name": "Gabriel Martinelli"},
            "type": "Goal",
            "detail": "Normal Goal",
            "comments": "null",
        },
        {
            "time": {"elapsed": 65, "extra": "null"},
            "team": {
                "id": 42,
                "name": "Arsenal",
                "logo": "https:\/\/media.api-sports.io\/football\/teams\/42.png",
            },
            "player": {"id": 1460, "name": "B. Saka"},
            "assist": {"id": 978, "name": "K. Havertz"},
            "type": "Goal",
            "detail": "Normal Goal",
            "comments": "null",
        },
        {
            "time": {"elapsed": 69, "extra": "null"},
            "team": {
                "id": 42,
                "name": "Arsenal",
                "logo": "https:\/\/media.api-sports.io\/football\/teams\/42.png",
            },
            "player": {"id": 61431, "name": "J. Kiwior"},
            "assist": {"id": 2937, "name": "D. Rice"},
            "type": "Goal",
            "detail": "Normal Goal",
            "comments": "null",
        },
        {
            "time": {"elapsed": 84, "extra": "null"},
            "team": {
                "id": 34,
                "name": "Newcastle",
                "logo": "https:\/\/media.api-sports.io\/football\/teams\/34.png",
            },
            "player": {"id": 1463, "name": "J. Willock"},
            "assist": {"id": 18961, "name": "D. Burn"},
            "type": "Goal",
            "detail": "Normal Goal",
            "comments": "null",
        }
    ]



new_goals = []
for goal in goals:
    if goal.get("detail") == "Own Goal":
        # goal["player_id"] = 0
        goal["player"]["id"] = 0
        new_goals.append(goal)
#     else:
#         new_goals.append(goal)
# goals = new_goals

print(new_goals)
