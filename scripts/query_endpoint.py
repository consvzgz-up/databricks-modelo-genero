"""Query the serving endpoint genero-cliente from your machine.

Token auth (what the professor uses):
    export DATABRICKS_HOST=https://<workspace>.cloud.databricks.com
    export DATABRICKS_TOKEN=<token>          # never written to a file in this repo
    python scripts/query_endpoint.py --tipo-correo yahoo --pais Germany --ciudad Berlin

CLI auth (no token), after `databricks auth login --host https://<workspace>.cloud.databricks.com`:
    export DATABRICKS_HOST=https://<workspace>.cloud.databricks.com
    python scripts/query_endpoint.py                     # DATABRICKS_HOST + the CLI's OAuth cache
    python scripts/query_endpoint.py --profile DEFAULT   # or a named profile in ~/.databrickscfg

Auth order: DATABRICKS_TOKEN if it is set; else databricks-sdk WorkspaceClient(profile=...)
when --profile is given; else WorkspaceClient() with its default auth chain.
The token is never printed.
"""
import argparse
import json
import os
import sys

ENDPOINT = "genero-cliente"


def main():
    ap = argparse.ArgumentParser(description="Query the genero-cliente serving endpoint")
    ap.add_argument("--tipo-correo", default="yahoo", help="provider (yahoo) or a full email")
    ap.add_argument("--pais", default="Germany")
    ap.add_argument("--ciudad", default="Berlin")
    ap.add_argument("--profile", default=None,
                    help="CLI profile for databricks-sdk auth (only when DATABRICKS_TOKEN is not set)")
    ap.add_argument("--endpoint", default=ENDPOINT)
    args = ap.parse_args()

    import requests

    token = os.environ.get("DATABRICKS_TOKEN")
    if token:
        host = os.environ.get("DATABRICKS_HOST")
        if not host:
            print("DATABRICKS_TOKEN is set but DATABRICKS_HOST is not", file=sys.stderr)
            return 2
        headers = {"Authorization": f"Bearer {token}"}
        auth = "DATABRICKS_TOKEN"
    else:
        try:
            from databricks.sdk import WorkspaceClient
        except ImportError:
            print("no DATABRICKS_TOKEN and databricks-sdk is not installed (pip install databricks-sdk)",
                  file=sys.stderr)
            return 2
        try:
            w = WorkspaceClient(profile=args.profile) if args.profile else WorkspaceClient()
            host = w.config.host
            headers = dict(w.config.authenticate())
        except Exception as e:  # noqa: BLE001 - report the auth failure plainly
            print(f"databricks-sdk auth failed ({type(e).__name__}): {e}", file=sys.stderr)
            print("set DATABRICKS_HOST and DATABRICKS_TOKEN, run `databricks auth login`,"
                  " or pass --profile", file=sys.stderr)
            return 2
        source = f"profile {args.profile}" if args.profile else "default auth"
        auth = f"databricks-sdk ({source}, {w.config.auth_type})"

    host = host.strip().rstrip("/")
    if not host.startswith("http"):
        host = "https://" + host
    url = f"{host}/serving-endpoints/{args.endpoint}/invocations"
    row = {"tipo_correo": args.tipo_correo, "pais": args.pais, "ciudad": args.ciudad}
    body = {"dataframe_records": [row]}
    headers["Content-Type"] = "application/json"

    r = requests.post(url, headers=headers, json=body, timeout=120)
    print(f"auth: {auth}")
    print(f"POST {url} -> HTTP {r.status_code}")
    try:
        print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    except ValueError:
        print(r.text)
    return 0 if r.ok else 1


if __name__ == "__main__":
    sys.exit(main())
