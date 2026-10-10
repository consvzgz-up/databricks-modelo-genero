"""Task 1: load the five Chinook CSVs into Delta tables and (re)create the view vw_cliente_genero.

Reads <data-dir>/{genre,track,invoice_line,invoice,customer}.csv (bundle workspace files), writes
workspace.chinook.<table> (overwrite) and runs sql/vw_cliente_genero.sql.
"""
import argparse
import os

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

CATALOG = "workspace"
SCHEMA = "chinook"
VIEW = f"{CATALOG}.{SCHEMA}.vw_cliente_genero"

# Column types from the CREATE TABLE statements of the Postgres dump; everything else stays string.
CASTS = {
    "genre": {"genre_id": "int"},
    "track": {"track_id": "int", "album_id": "int", "media_type_id": "int", "genre_id": "int",
              "milliseconds": "int", "bytes": "int", "unit_price": "decimal(10,2)"},
    "invoice_line": {"invoice_line_id": "int", "invoice_id": "int", "track_id": "int",
                     "unit_price": "decimal(10,2)", "quantity": "int"},
    "invoice": {"invoice_id": "int", "customer_id": "int", "total": "decimal(10,2)"},
    "customer": {"customer_id": "int", "support_rep_id": "int"},
}
TABLES = list(CASTS)

VIEW_SQL_FALLBACK = f"""
CREATE OR REPLACE VIEW {VIEW} AS
SELECT
    lower(split_part(split_part(c.email, '@', 2), '.', 1)) AS tipo_correo,
    c.country AS pais,
    c.city    AS ciudad,
    g.name    AS genero
FROM {CATALOG}.{SCHEMA}.customer     c
JOIN {CATALOG}.{SCHEMA}.invoice      i  ON i.customer_id = c.customer_id
JOIN {CATALOG}.{SCHEMA}.invoice_line il ON il.invoice_id = i.invoice_id
JOIN {CATALOG}.{SCHEMA}.track        t  ON t.track_id    = il.track_id
JOIN {CATALOG}.{SCHEMA}.genre        g  ON g.genre_id    = t.genre_id
"""


def read_csv(spark, path):
    """spark.read first; if Spark cannot reach workspace files, read with pandas and convert."""
    try:
        df = (spark.read.option("header", "true").option("inferSchema", "false")
              .option("quote", '"').option("escape", '"').option("encoding", "UTF-8")
              .csv(path))
        df.limit(1).collect()
        return df, "spark.read"
    except Exception as e:  # noqa: BLE001 - fall back on any read failure
        print(f"spark.read failed for {path} ({type(e).__name__}: {str(e)[:200]}); using pandas")
    import pandas as pd
    pdf = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")
    pdf = pdf.astype(object).where(pdf != "", None)
    schema = ", ".join(f"`{c}` string" for c in pdf.columns)
    return spark.createDataFrame(pdf.values.tolist(), schema=schema), "pandas"


def typed(table, df):
    for col, typ in CASTS[table].items():
        df = df.withColumn(col, F.col(col).cast(typ))
    if table == "invoice":
        # the dump writes dates as 2021/1/1
        df = df.withColumn("invoice_date", F.to_timestamp(F.col("invoice_date"), "yyyy/M/d"))
    return df


def view_sql(data_dir):
    """Read sql/vw_cliente_genero.sql next to the bundle's src/ and data/; inline copy as fallback."""
    candidates = []
    try:
        candidates.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                       "sql", "vw_cliente_genero.sql"))
    except NameError:  # __file__ is not always defined in a job's python task
        pass
    candidates.append(os.path.join(os.path.dirname(data_dir.rstrip("/")), "sql", "vw_cliente_genero.sql"))
    for path in candidates:
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            print(f"view SQL read from {path}")
            break
        except OSError as e:
            print(f"cannot read {path}: {e}")
    else:
        print("view SQL: using the inlined copy")
        return VIEW_SQL_FALLBACK.strip()
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("--")]
    return "\n".join(lines).strip().rstrip(";").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    args = ap.parse_args()

    spark = SparkSession.builder.getOrCreate()
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")

    for table in TABLES:
        path = f"{args.data_dir.rstrip('/')}/{table}.csv"
        raw, how = read_csv(spark, path)
        df = typed(table, raw)
        (df.write.format("delta").mode("overwrite").option("overwriteSchema", "true")
           .saveAsTable(f"{CATALOG}.{SCHEMA}.{table}"))
        n = spark.table(f"{CATALOG}.{SCHEMA}.{table}").count()
        print(f"{CATALOG}.{SCHEMA}.{table}: {n} rows ({how})")

    spark.sql(view_sql(args.data_dir))
    rows = spark.table(VIEW).count()
    print(f"{VIEW}: {rows} rows (expected 2240)")
    if rows == 0:
        raise SystemExit("the view is empty")


if __name__ == "__main__":
    main()
