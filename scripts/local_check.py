"""Local check of the model without Databricks: rebuild vw_cliente_genero from data/*.csv in pandas,
fit the same pipeline as src/train_model.py and call GenreModel.predict on the smoke-test rows.

    python scripts/local_check.py

Needs pandas and scikit-learn; mlflow is optional (genre_model.py guards its import).
"""
import os
import sys

sys.dont_write_bytecode = True

import pandas as pd  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import accuracy_score  # noqa: E402
from sklearn.model_selection import train_test_split  # noqa: E402
from sklearn.pipeline import Pipeline  # noqa: E402
from sklearn.preprocessing import OneHotEncoder  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))
from genre_model import FEATURES, TARGET, GenreModel  # noqa: E402

ROWS = [
    {"tipo_correo": "yahoo", "pais": "Germany", "ciudad": "Berlin"},
    {"tipo_correo": "gmail", "pais": "Brazil", "ciudad": "São Paulo"},
    {"tipo_correo": "ana@yahoo.com.br", "pais": "Brazil", "ciudad": "São Paulo"},
]


def split_part(s, delim, n):
    """Postgres/Databricks split_part: 1-based, empty string when the part does not exist."""
    parts = str(s).split(delim)
    return parts[n - 1] if len(parts) >= n else ""


def vista(data_dir):
    read = lambda t: pd.read_csv(os.path.join(data_dir, f"{t}.csv"), dtype=str, keep_default_na=False)  # noqa: E731
    c, i, il, t, g = (read(x) for x in ("customer", "invoice", "invoice_line", "track", "genre"))
    df = (c.merge(i, on="customer_id")
           .merge(il, on="invoice_id")
           .merge(t, on="track_id", suffixes=("", "_track"))
           .merge(g, on="genre_id", suffixes=("", "_genre")))
    return pd.DataFrame({
        "tipo_correo": df["email"].map(lambda e: split_part(split_part(e, "@", 2), ".", 1).lower()),
        "pais": df["country"],
        "ciudad": df["city"],
        "genero": df["name_genre"],
    })


def main():
    df = vista(os.path.join(REPO, "data"))
    print(f"vw_cliente_genero rebuilt in pandas: {len(df)} rows, {df[TARGET].nunique()} genres")
    X, y = df[FEATURES], df[TARGET]
    x_train, x_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    def nuevo():
        return Pipeline([("onehot", OneHotEncoder(handle_unknown="ignore")),
                         ("clf", LogisticRegression(max_iter=1000))])

    m = nuevo().fit(x_train, y_train)
    print(f"Accuracy (hold-out 20%): {accuracy_score(y_test, m.predict(x_test)):.3f}")
    model = GenreModel(nuevo().fit(X, y))
    out = model.predict(None, pd.DataFrame(ROWS))
    pd.set_option("display.width", 200)
    print(pd.concat([pd.DataFrame(ROWS), out], axis=1).to_string(index=False))
    ok = len(out) == 3 and out["genero"].astype(bool).all()
    same_email = out.loc[2, "genero"] == model.predict(None, pd.DataFrame([{**ROWS[2], "tipo_correo": "yahoo"}])).loc[0, "genero"]
    print(f"full email normalises like the provider: {same_email}")
    print(f"Berlin top genre: {out.loc[0, 'genero']}")
    return 0 if ok and same_email else 1


if __name__ == "__main__":
    sys.exit(main())
