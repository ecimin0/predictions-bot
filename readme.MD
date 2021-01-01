# Football :soccer: Predictions :thinking: Bot :robot:
## Run a prediction league in your team's Discord server
<br>

## League Rules
These rules are considered from the point of view of the Discord server's team
```
2 points – correct result (W/D/L)
2 points – correct number of goals scored
1 point – correct number of goals conceded
1 point – each correct scorer
1 point – correct FGS (first goal scorer)
2 points bonus – all scorers correct

- Players to score multiple goals should be entered as 'player x2' or 'player 2x'

- No points for scorers if prediction's goals exceed actual goals by 4+

- Do not predict opposition goal scorers
- Do not predict opposition FGS
```

### **Predictions may not be made after team lineups are announced**
Usually the cutoff is 1 hour before domestic matches and 1.5 hours before European (UEL/UCL) matches
<br>
<br>

---
## Currently Supported Sides
- Planned support for European clubs across most leagues
- Other leagues worldwide curently not in scope

### **Arsenal**
<br>

---
## Chat Commands
**More specific help messages for each command can be accessed with `+help <command>`**
<br>
<br>
### Fixures  
  `next` | Upcoming matches or next match against another side  
  ```
  +next
  +next 3
  +next arsenal

  +help next
  ```

  `pltable` | Current Premier League table
  ```
  +pltable

  +help pltable
  ```
  
  `results` | Return past fixture results
  ```
  +results

  +help results
  ```
<br>

### Predictions
  `leaderboard` | Show leaderboard once every 30 seconds
  ```
  +leaderboard

  +help leaderboard
  ```
  
  `predict` | Make a prediction
  ```
  # home
  +predict 2-0 aubameyang fgs, lacazette
  +predict 2-0 auba, laca

  # away
  +predict 0-1 auba

  +help predict
  ```
  
  `predictions` | Show your past predictions
  ```
  +predictions

  +help predictions
  ```
<br>

### User Functions
  `remindme` | Toggle reminders; sent 2h before kickoff
  ```
  +remindme

  +help remindme
  ```

  `timezone` | Change timezone | https://stackoverflow.com/questions/13866926/is-there-a-list-of-pytz-timezones
  ```
  +timezone Europe/London

  +help timezone
  ```
<br>

### Utility
  `botissues` | See list of open bugs, requests, and feedback
  ```
  +botissues

  +help botissues
  ```
  
  `feedback` | Open an issue on GitLab | https://gitlab.com/ecimino/predictions-bot/-/issues
  ```
  +feedback <type a simple feedback message here>

  +bug <type a simple bug report here>
  
  +request <type a simple request here>

  +help feedback
  ```

  `ping` | Return latency between bot and server
  ```
  +ping

  +help ping
  ```
<br>

### Help
  `rules` | Display Prediction League Rules
  ```
  +rules

  +help rules
  ```
  
  `help` | Shows this message

<br>

### Admin Functions
**TBD**

---
<br>

## Infrastructure
### Details
- Code written in Python and Dockerized. The container entrypoint is simply the command to run the script:
    ```Dockerfile
    ENTRYPOINT [ "python3", "/usr/local/bin/predictions_bot.py" ]
    ```

- Images stored in GitLab registry

- Registry and ECS linked using AWS Secrets Manager

- Containers run in AWS ECS

- Logging, alarms, and metrics via AWS Cloudwatch

- Database used is Postgres via AWS RDS

- API: https://dashboard.api-football.com