"""
Script to obtain a Mastodon API Auth token

Usage:
```shell
# Kickoff the script, then follow the instructions to get the auth token
uv run --env-file .env get_mastodon_token.py
```
"""

from mastodon import Mastodon

from mastodon_retrieve.settings import MastodonSettings

SCOPES = [
    "read:statuses",
    "read:notifications",
    "read:search",
    "read:timelines",
]


if __name__ == "__main__":
    settings = MastodonSettings()
    if not settings.output_path.is_file():
        print("Did not find Mastodon registration secret")
        print("Registering Mastodon App...")
        Mastodon.create_app(
            client_name=settings.api_name,
            to_file=settings.output_path,
            api_base_url=settings.base_url,
            scopes=SCOPES,
        )

    print("Logging in to Mastodon app...")
    app = Mastodon(client_id=settings.output_path)
    print(
        "Please go to the following URL to retrieve your API access code: %s"
        % app.auth_request_url(scopes=SCOPES)
    )
    token = app.log_in(
        code=input("Enter the OAuth authorization code: "),
        to_file="mastodon_user.secret",
        scopes=SCOPES,
    )
    print("*" * 50)
    print("Received Mastodon Access Token!")
    print(f"Token: '{token}'")
    print("*" * 50)
