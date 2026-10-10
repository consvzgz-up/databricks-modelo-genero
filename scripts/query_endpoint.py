"""Query the serving endpoint genero-cliente from your machine.

Token auth (what the professor uses):
    export DATABRICKS_HOST=https://<workspace>.cloud.databricks.com
    export DATABRICKS_TOKEN=<token>          # never written to a file in this repo
    python scripts/query_endpoint.py --tipo-correo yahoo --pais Germany --ciudad Berlin

CLI profile auth (no token; after `databricks auth login`):
    python scripts/query_endpoint.py --profile DEFAULT
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
                    help="use this Databricks CLI profile (databricks-sdk) instead of DATABRICKS_TOKEN")
    ap.add_argument("--endpoint", default=ENDPOINT)
    args = ap.parse_args()

    import requests

    if args.profile:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient(profile=args.profile)
        host = w.config.host
        headers = dict(w.config.authenticate())
    else:
        host = os.environ.get("DATABRICKS_HOST")
        token = os.environ.get("DATABRICKS_TOKEN")
        if not host or not token:
            print("set DATABRICKS_HOST and DATABRICKS_TOKEN, or pass --profile", file=sys.stderr)
            return 2
        headers = {"Authorization": f"Bearer {token}"}

    host = host.strip().rstrip("/")
    if not host.startswith("http"):
        host = "https://" + host
    url = f"{host}/serving-endpoints/{args.endpoint}/invocations"
    body = {"dataframe_records": [{"tipo_correo": args.tipo_correo, "pais": args.pais, "ciudad": args.ciudad}]}
    headers["Content-Type"] = "application/json"

    r = requests.post(url, headers=headers, json=body, timeout=120)
    print(f"POST {url} -> HTTP {r.status_code}")
    try:
        print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    except ValueError:
        print(r.text)
    return 0 if r.ok else 1


if __name__ == "__main__":
    sys.exit(main())
