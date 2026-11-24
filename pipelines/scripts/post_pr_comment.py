"""Post a markdown file as a comment thread on the current Azure DevOps pull request.

Usage: python post_pr_comment.py <file.md>
Does nothing when the file is empty or the build is not for a pull request.
Needs SYSTEM_ACCESSTOKEN and the build service permission "Contribute to pull requests".
"""

import os
import sys
from pathlib import Path

import requests


def main() -> int:
    path = Path(sys.argv[1])
    body = path.read_text(encoding="utf-8").strip() if path.is_file() else ""
    pr_id = os.environ.get("SYSTEM_PULLREQUEST_PULLREQUESTID")
    if not body or not pr_id:
        print("nothing to post")
        return 0
    url = (f"{os.environ['SYSTEM_COLLECTIONURI']}{os.environ['SYSTEM_TEAMPROJECT']}/_apis/git/repositories/"
           f"{os.environ['BUILD_REPOSITORY_ID']}/pullRequests/{pr_id}/threads?api-version=7.1")
    payload = {"comments": [{"parentCommentId": 0, "content": body, "commentType": 1}], "status": 1}
    resp = requests.post(url, json=payload, timeout=30,
                         headers={"Authorization": f"Bearer {os.environ['SYSTEM_ACCESSTOKEN']}"})
    if resp.status_code >= 300:
        print(f"could not post comment: {resp.status_code} {resp.text[:300]}")
        return 0  # never fail the build over a comment
    print("comment posted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
