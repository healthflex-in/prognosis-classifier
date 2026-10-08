"""Deployment checks; never initialize the API, listeners or an AI request."""
import argparse
import ast
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_SOURCES = (
    "LLM/prognosis/prognosis_agent.py",
    "LLM/prognosis/prognosis_langchain_agent.py",
    "LLM/prognosis/push_prognosis_to_mongo.py",
)


def check_sources(root=ROOT):
    for relative in REQUIRED_SOURCES:
        path = root / relative
        if not path.is_file():
            raise ValueError(f"Missing source: {relative}. Recover and commit the original Python file.")
        ast.parse(path.read_text(), filename=relative)


def check_credentials():
    path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if not path or not Path(path).is_file():
        raise ValueError("GOOGLE_APPLICATION_CREDENTIALS must point to a readable JSON file, not a directory.")
    if not os.environ.get("MONGO_URI") or not os.environ.get("MONGO_DB"):
        raise ValueError("MONGO_URI and MONGO_DB must be configured for this environment.")
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    # Parse the private key and verify that Google accepts it, without AI calls
    # or database writes. Never print credentials, tokens or exception bodies.
    credentials = service_account.Credentials.from_service_account_file(
        path, scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    credentials.refresh(Request())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    try:
        check_sources()
    except (ValueError, OSError, SyntaxError) as error:
        print(f"Source check failed: {error}", file=sys.stderr)
        return 1
    if not args.source_only:
        try:
            check_credentials()
        except ValueError as error:
            # Third-party errors can contain credential details; keep output generic.
            print("Credential/configuration check failed. Check the JSON file, environment and Google access.", file=sys.stderr)
            return 1
        except Exception:
            print("Google authentication check failed. Check credentials and network access.", file=sys.stderr)
            return 1
    print("Deployment checks passed" + (" (source only)." if args.source_only else "."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
