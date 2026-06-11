from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

# Change scopes based on what you need.
# Gmail modify allows reading, labeling, archiving, moving messages, etc.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify"
]

CLIENT_FILE = "google_oauth_client.json"
TOKEN_FILE = "google_oauth_token.json"


def main():
    if not Path(CLIENT_FILE).exists():
        raise FileNotFoundError(
            f"{CLIENT_FILE} not found. Download your OAuth client JSON from Google Cloud "
            f"and save it as {CLIENT_FILE} in this folder."
        )

    flow = InstalledAppFlow.from_client_secrets_file(
        CLIENT_FILE,
        SCOPES
    )

    creds = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true"
    )

    Path(TOKEN_FILE).write_text(creds.to_json(), encoding="utf-8")

    print(f"Token created successfully: {TOKEN_FILE}")
    print("Keep this file private. Do not commit it to GitHub.")


if __name__ == "__main__":
    main()