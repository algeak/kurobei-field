#!/usr/bin/env python3
"""
Kurobei Email Checker - Daily email monitoring for kurobei@algeak.com

This script:
1. Checks Gmail API for new emails with [Kurobei] or [くろべー] in subject
2. Filters emails received in the last 6 hours
3. Creates GitHub issues for new emails
4. Avoids duplicates by checking existing issues
"""

import os
import sys
import json
import base64
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import requests


def get_access_token() -> str:
    """Get fresh access token using refresh token."""
    refresh_token = os.environ.get('GMAIL_REFRESH_TOKEN')
    client_id = os.environ.get('GMAIL_CLIENT_ID')
    client_secret = os.environ.get('GMAIL_CLIENT_SECRET')

    if not all([refresh_token, client_id, client_secret]):
        raise ValueError("Missing required environment variables for Gmail API")

    response = requests.post(
        'https://oauth2.googleapis.com/token',
        data={
            'refresh_token': refresh_token,
            'client_id': client_id,
            'client_secret': client_secret,
            'grant_type': 'refresh_token'
        }
    )

    if response.status_code != 200:
        raise Exception(f"Failed to get access token: {response.text}")

    return response.json()['access_token']


def get_recent_messages(access_token: str, hours: int = 6) -> List[Dict]:
    """Get messages from the last N hours with [Kurobei] or [くろべー] in subject."""
    # Calculate timestamp for N hours ago
    after_timestamp = int((datetime.now() - timedelta(hours=hours)).timestamp())

    # Search for messages with specific subject tags
    query = f'subject:([Kurobei] OR [くろべー]) after:{after_timestamp}'

    response = requests.get(
        'https://gmail.googleapis.com/gmail/v1/users/me/messages',
        headers={'Authorization': f'Bearer {access_token}'},
        params={'q': query, 'maxResults': 10}
    )

    if response.status_code != 200:
        raise Exception(f"Failed to fetch messages: {response.text}")

    messages = response.json().get('messages', [])
    print(f"Found {len(messages)} messages with [Kurobei] or [くろべー] tag")

    return messages


def get_message_details(access_token: str, message_id: str) -> Dict:
    """Get full details of a specific message."""
    response = requests.get(
        f'https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}',
        headers={'Authorization': f'Bearer {access_token}'},
        params={'format': 'full'}
    )

    if response.status_code != 200:
        raise Exception(f"Failed to fetch message details: {response.text}")

    return response.json()


def extract_email_data(message: Dict) -> Dict:
    """Extract relevant data from Gmail API message."""
    headers = {h['name']: h['value'] for h in message['payload']['headers']}

    # Get message body
    body = ""
    if 'parts' in message['payload']:
        for part in message['payload']['parts']:
            if part['mimeType'] == 'text/plain':
                if 'data' in part['body']:
                    body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                    break
    elif 'body' in message['payload'] and 'data' in message['payload']['body']:
        body = base64.urlsafe_b64decode(message['payload']['body']['data']).decode('utf-8')

    return {
        'id': message['id'],
        'from': headers.get('From', 'Unknown'),
        'subject': headers.get('Subject', 'No Subject'),
        'date': headers.get('Date', 'Unknown'),
        'body': body[:2000]  # Limit body to 2000 chars
    }


def check_existing_issue(email_id: str) -> bool:
    """Check if an issue already exists for this email."""
    github_token = os.environ.get('GITHUB_TOKEN')
    repo = os.environ.get('GITHUB_REPOSITORY')

    if not github_token or not repo:
        raise ValueError("Missing GITHUB_TOKEN or GITHUB_REPOSITORY")

    # Search for issues with the email ID in the title or body
    response = requests.get(
        f'https://api.github.com/repos/{repo}/issues',
        headers={
            'Authorization': f'Bearer {github_token}',
            'Accept': 'application/vnd.github.v3+json'
        },
        params={'state': 'all', 'per_page': 100}
    )

    if response.status_code != 200:
        print(f"Warning: Failed to check existing issues: {response.text}")
        return False

    for issue in response.json():
        if email_id in issue.get('body', ''):
            return True

    return False


def create_github_issue(email_data: Dict) -> bool:
    """Create a GitHub issue for the email."""
    github_token = os.environ.get('GITHUB_TOKEN')
    repo = os.environ.get('GITHUB_REPOSITORY')

    if not github_token or not repo:
        raise ValueError("Missing GITHUB_TOKEN or GITHUB_REPOSITORY")

    # Check if issue already exists
    if check_existing_issue(email_data['id']):
        print(f"Issue already exists for email: {email_data['subject']}")
        return False

    # Create issue title and body
    title = f"[Email] {email_data['from']}: {email_data['subject']}"

    body = f"""## Email Details

**From**: {email_data['from']}
**Subject**: {email_data['subject']}
**Date**: {email_data['date']}
**Email ID**: `{email_data['id']}`

---

## Message

{email_data['body']}

---

*This issue was automatically created by Kurobei's email checker workflow at {datetime.now().isoformat()}*
"""

    response = requests.post(
        f'https://api.github.com/repos/{repo}/issues',
        headers={
            'Authorization': f'Bearer {github_token}',
            'Accept': 'application/vnd.github.v3+json'
        },
        json={
            'title': title,
            'body': body,
            'labels': ['email', 'auto-created']
        }
    )

    if response.status_code == 201:
        issue_url = response.json()['html_url']
        print(f"✅ Created issue: {issue_url}")
        return True
    else:
        print(f"❌ Failed to create issue: {response.text}")
        return False


def main():
    """Main execution function."""
    print("=" * 60)
    print("Kurobei Email Checker - Starting...")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 60)

    try:
        # Get access token
        print("\n1. Getting Gmail API access token...")
        access_token = get_access_token()
        print("✅ Access token obtained")

        # Get recent messages
        print("\n2. Fetching recent emails...")
        messages = get_recent_messages(access_token, hours=6)

        if not messages:
            print("ℹ️  No new emails with [Kurobei] or [くろべー] tag found")
            return

        # Process each message
        print(f"\n3. Processing {len(messages)} message(s)...")
        created_count = 0

        for msg in messages:
            print(f"\n  Processing message ID: {msg['id']}")
            details = get_message_details(access_token, msg['id'])
            email_data = extract_email_data(details)

            print(f"  Subject: {email_data['subject']}")
            print(f"  From: {email_data['from']}")

            if create_github_issue(email_data):
                created_count += 1

        print("\n" + "=" * 60)
        print(f"✅ Email check completed!")
        print(f"   Total emails found: {len(messages)}")
        print(f"   New issues created: {created_count}")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
