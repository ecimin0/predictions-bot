#!/usr/local/bin/python3

import requests
import os
from dotenv import load_dotenv
import json

load_dotenv()

all_issues = []

# bug_req = requests.get("https://gitlab.com/api/v4/projects/15728299/issues?labels=bug&state=opened", headers={'PRIVATE-TOKEN': os.environ.get('GITLAB_API', None)})
# all_bugs = bug_req.json()
# for bug in all_bugs:
#     all_issues.append(bug)

# feedback_req = requests.get("https://gitlab.com/api/v4/projects/15728299/issues?labels=feedback&state=opened", headers={'PRIVATE-TOKEN': os.environ.get('GITLAB_API', None)})
# all_feedbacks = feedback_req.json()
# for feedback in all_feedbacks:
#     all_issues.append(feedback)

# requests_req = requests.get("https://gitlab.com/api/v4/projects/15728299/issues?labels=request&state=opened", headers={'PRIVATE-TOKEN': os.environ.get('GITLAB_API', None)})
# all_requests = requests_req.json()
# for request in all_requests:
#     all_issues.append(request)

request = requests.get("https://gitlab.com/api/v4/projects/15728299/issues?labels=user&state=opened", headers={'PRIVATE-TOKEN': os.environ.get('GITLAB_API', None)})
issues = request.json()
for issue in issues:
    all_issues.append(issue)

for issue in all_issues:
    print(f"{issue.get('references').get('short')} - {'/'.join(issue.get('labels'))} | {issue.get('title')}")
