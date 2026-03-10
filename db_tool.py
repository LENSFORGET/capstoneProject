import sys
import json
import argparse
from xhs_db_mcp import (
    start_session, finish_session,
    start_social_session, finish_social_session,
    save_post, save_user, save_comment,
    save_social_post, save_social_user, save_social_comment,
    save_lead, save_liked_post, check_already_liked, get_leads,
    save_social_lead,
    get_db_stats,
)

ACTIONS = [
    "start_session", "finish_session",
    "start_social_session", "finish_social_session",
    "save_post", "save_user", "save_comment",
    "save_social_post", "save_social_user", "save_social_comment",
    "save_lead", "save_liked_post", "check_already_liked", "get_leads",
    "save_social_lead",
    "get_db_stats",
]

def main():
    parser = argparse.ArgumentParser(description="XHS DB Tool CLI")
    parser.add_argument("action", choices=ACTIONS)
    parser.add_argument("--data", help="JSON string of arguments")

    args = parser.parse_args()

    kwargs = {}
    if args.data:
        kwargs = json.loads(args.data)

    action_map = {
        "start_session":      start_session,
        "finish_session":     finish_session,
        "start_social_session": start_social_session,
        "finish_social_session": finish_social_session,
        "save_post":          save_post,
        "save_user":          save_user,
        "save_comment":       save_comment,
        "save_social_post":   save_social_post,
        "save_social_user":   save_social_user,
        "save_social_comment": save_social_comment,
        "save_lead":          save_lead,
        "save_social_lead":   save_social_lead,
        "save_liked_post":    save_liked_post,
        "check_already_liked": check_already_liked,
        "get_leads":          get_leads,
        "get_db_stats":       get_db_stats,
    }

    print(action_map[args.action](**kwargs))

if __name__ == "__main__":
    main()
