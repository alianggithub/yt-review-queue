# Google OAuth Enrollment Guide

This guide walks you through creating the OAuth credentials needed to
enroll Google/YouTube accounts into the review queue.

## Prerequisites

- A Google account
- Access to [Google Cloud Console](https://console.cloud.google.com)

## Step 1: Enable APIs

1. Go to the [API Library](https://console.cloud.google.com/apis/library)
2. Search for **Data Portability API** and enable it
   - Note: the `dataportability.myactivity.youtube` scope is classified as
     **Restricted**. Your app may need OAuth verification before non-test
     users can authorize. In testing mode, only users listed in your Cloud
     Console can authorize.
   - If the Data Portability API is not visible, it may require joining the
     [trusted tester program](https://developers.google.com/data-portability)
     or waiting for general availability.
3. Search for **YouTube Data API v3** and enable it

## Step 2: Configure OAuth Consent Screen

1. Go to [OAuth consent screen](https://console.cloud.google.com/apis/credentials/consent)
2. Choose **External** (unless you have a Google Workspace)
3. Fill in app name, support email
4. Add scopes:
   - `../auth/dataportability.myactivity.youtube` (Data Portability)
   - `../auth/youtube.readonly` (YouTube Data API)
5. Add your Google account email as a **test user**
6. Save and continue

## Step 3: Create OAuth Credentials

1. Go to [Credentials](https://console.cloud.google.com/apis/credentials)
2. Click **Create Credentials** → **OAuth client ID**
3. Choose **Desktop app** as the type
4. Name it "yt-review-queue"
5. Click **Create**
6. Click **Download JSON** to download the client secret file
7. Save it as `~/workspace/yt-review-queue/client_secret.json`

## Step 4: Enroll an Account

```bash
cd ~/workspace/yt-review-queue
. .venv/bin/activate
python -m yt_review_queue.enroll <label> client_secret.json
```

Replace `<label>` with a short name for this account (e.g. "dan", "alice").

The script will:
1. Open your browser for Data Portability authorization
2. Open your browser again for YouTube Data API authorization
3. Verify your YouTube channel via `channels.list(mine=true)`
4. Save credentials to `var/credentials/<label>_dp.json` and `<label>_yt.json`

## Troubleshooting

### Data Portability API not visible in API Library
The API may still be in limited access. Check
[Google's Data Portability documentation](https://developers.google.com/data-portability)
for current availability. If unavailable, you can still use manual Takeout
exports as the fallback path.

### refresh_token is None
This happens when you've previously authorized and Google returns the same
grant without a fresh refresh_token. Fix: revoke access at
[Google Account permissions](https://myaccount.google.com/permissions), then
re-run enrollment.

### OAuth verification required
If your app is in testing mode, only test users can authorize. Add more
test users in the OAuth consent screen. For production access with arbitrary
users, you'll need Google's verification process (can take weeks for
Restricted scopes).

### Browser doesn't open
The enrollment script uses `run_local_server(port=0)` which opens a browser
and starts a local HTTP server. If you're on a headless server, consider
running enrollment on your local machine first, then copying the credential
files to the server.
