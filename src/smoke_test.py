"""Task 4: query the endpoint genero-cliente with three known rows; fail the job if it does not answer."""
import argparse
import json
import sys

ENDPOINT = "genero-cliente"
ROWS = [
    {"tipo_correo": "yahoo", "pais": "Germany", "ciudad": "Berlin"},
    {"tipo_correo": "gmail", "pais": "Brazil", "ciudad": "São Paulo"},
    {"tipo_correo": "ana@yahoo.com.br", "pais": "Brazil", "ciudad": "São Paulo"},
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=None)  # accepted for symmetry with the other tasks
    ap.parse_args()

    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    response = w.serving_endpoints.query(name=ENDPOINT, dataframe_records=ROWS)
    predictions = response.predictions or []
    for row, pred in zip(ROWS, predictions):
        print(json.dumps({"entrada": row, "prediccion": pred}, ensure_ascii=False))

    if len(predictions) != len(ROWS):
        print(f"expected {len(ROWS)} predictions, got {len(predictions)}: {predictions!r}")
        sys.exit(1)
    empty = [i for i, p in enumerate(predictions) if not (isinstance(p, dict) and p.get("genero"))]
    if empty:
        print(f"empty genero in predictions {empty}: {predictions!r}")
        sys.exit(1)

    berlin = predictions[0].get("genero")
    print(f"yahoo/Germany/Berlin -> {berlin} ({'Metal, as the previous model' if berlin == 'Metal' else 'not Metal'})")
    print("smoke test passed")


if __name__ == "__main__":
    main()
