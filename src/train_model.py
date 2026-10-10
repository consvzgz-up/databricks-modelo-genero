"""Task 2: train the genre model from the view and register it in Unity Catalog.

Same features, target, pipeline and hold-out as pipeline-db-ml/src/contexts/train_model/TrainModel.py.
Logs accuracy and the classification report to MLflow, refits on all rows, logs the pyfunc wrapper
(GenreModel) as workspace.chinook.genero_cliente and points the alias Champion at the new version.
"""
import argparse
import os
import sys
import tempfile

VIEW = "workspace.chinook.vw_cliente_genero"
MODEL_NAME = "workspace.chinook.genero_cliente"
ALIAS = "Champion"


def src_dir(data_dir):
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:  # __file__ is not always defined in a job's python task
        return os.path.join(os.path.dirname(data_dir.rstrip("/")), "src")


def get_dbutils(spark):
    try:
        from databricks.sdk.runtime import dbutils  # noqa: F401
        return dbutils
    except Exception:  # noqa: BLE001
        pass
    try:
        from pyspark.dbutils import DBUtils
        return DBUtils(spark)
    except Exception:  # noqa: BLE001
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--experiment", default=None, help="MLflow experiment path, e.g. /Users/<me>/genre_model_train")
    args = ap.parse_args()

    here = src_dir(args.data_dir)
    if here not in sys.path:
        sys.path.insert(0, here)
    from genre_model import FEATURES, TARGET, GenreModel  # noqa: E402

    import mlflow
    import numpy as np
    import pandas as pd
    import sklearn
    from mlflow.tracking import MlflowClient
    from pyspark.sql import SparkSession
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, classification_report
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder

    spark = SparkSession.builder.getOrCreate()
    df = spark.table(VIEW).select(*FEATURES, TARGET).toPandas()
    print(f"Filas recuperadas: {len(df)}")
    if df.empty:
        raise SystemExit(f"{VIEW} is empty")
    print(df.head(3).to_string(index=False))
    print(f"Géneros distintos: {df[TARGET].nunique()}")

    X = df[FEATURES]
    y = df[TARGET]
    # Sin stratify: hay géneros con una sola fila y stratify lanzaría error.
    x_train, x_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    def nuevo_pipeline():
        return Pipeline([
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
            ("clf", LogisticRegression(max_iter=1000)),
        ])

    mlflow.set_tracking_uri("databricks")
    mlflow.set_registry_uri("databricks-uc")
    if args.experiment:
        mlflow.set_experiment(args.experiment)

    with mlflow.start_run(run_name="genre_model_train") as run:
        model = nuevo_pipeline()
        model.fit(x_train, y_train)
        y_pred = model.predict(x_test)
        accuracy = accuracy_score(y_test, y_pred)
        report = classification_report(y_test, y_pred, zero_division=0)
        print(f"Accuracy (hold-out 20%): {accuracy:.3f}")
        print(report)
        mlflow.log_params({"features": ",".join(FEATURES), "test_size": 0.2, "random_state": 42,
                           "max_iter": 1000, "rows": len(df), "classes": int(y.nunique())})
        mlflow.log_metric("accuracy", accuracy)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "classification_report.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(f"Accuracy (hold-out 20%): {accuracy:.4f}\n\n{report}")
            mlflow.log_artifact(path)

        # Reentrenar con todos los datos
        model = nuevo_pipeline()
        model.fit(X, y)

        input_example = pd.DataFrame([
            {"tipo_correo": "yahoo", "pais": "Germany", "ciudad": "Berlin"},
            {"tipo_correo": "gmail", "pais": "Brazil", "ciudad": "São Paulo"},
            {"tipo_correo": "hotmail", "pais": "United Kingdom", "ciudad": "London"},
        ])
        pip_requirements = [
            f"mlflow=={mlflow.__version__}",
            f"scikit-learn=={sklearn.__version__}",
            f"pandas=={pd.__version__}",
            f"numpy=={np.__version__}",
        ]
        try:
            import cloudpickle
            pip_requirements.append(f"cloudpickle=={cloudpickle.__version__}")
        except ImportError:
            pass

        log_kwargs = dict(
            python_model=GenreModel(model),
            input_example=input_example,
            code_paths=[os.path.join(here, "genre_model.py")],
            pip_requirements=pip_requirements,
            registered_model_name=MODEL_NAME,
        )
        if int(mlflow.__version__.split(".")[0]) >= 3:
            info = mlflow.pyfunc.log_model(name="model", **log_kwargs)
        else:
            info = mlflow.pyfunc.log_model(artifact_path="model", **log_kwargs)

    client = MlflowClient(registry_uri="databricks-uc")
    version = getattr(info, "registered_model_version", None)
    if version is None:
        versions = [mv for mv in client.search_model_versions(f"name='{MODEL_NAME}'")
                    if mv.run_id == run.info.run_id]
        if not versions:
            raise SystemExit(f"no version of {MODEL_NAME} found for run {run.info.run_id}")
        version = max(int(mv.version) for mv in versions)
    version = str(version)
    client.set_registered_model_alias(MODEL_NAME, ALIAS, version)
    print(f"Registered {MODEL_NAME} version {version}; alias {ALIAS} -> {version}; run {run.info.run_id}")

    dbutils = get_dbutils(spark)
    try:
        dbutils.jobs.taskValues.set(key="model_version", value=version)
        print("task value model_version set")
    except Exception as e:  # noqa: BLE001 - the next task falls back to the alias
        print(f"task value not set ({type(e).__name__}); deploy_endpoint will resolve the alias")


if __name__ == "__main__":
    main()
