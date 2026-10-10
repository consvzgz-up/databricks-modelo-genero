"""MLflow pyfunc wrapper around the scikit-learn pipeline (OneHotEncoder -> LogisticRegression).

Input: a DataFrame with columns tipo_correo, pais, ciudad (tipo_correo may be a full email).
Output: a DataFrame with genero, top_1, p_1, top_2, p_2, top_3, p_3 (same contract as the
POST /api/model of pipeline-db-ml: the predicted genre plus the top 3 with probabilities).

Logged with code_paths=[this file], so the serving container can import it as `genre_model`.
"""
import pandas as pd

try:  # mlflow is not needed to fit or test the pipeline locally
    from mlflow.pyfunc import PythonModel as _Base
except ImportError:  # pragma: no cover
    _Base = object

FEATURES = ["tipo_correo", "pais", "ciudad"]
TARGET = "genero"
OUTPUT_COLUMNS = ["genero", "top_1", "p_1", "top_2", "p_2", "top_3", "p_3"]


def extraer_tipo_correo(valor) -> str:
    """Same rule as the view vw_cliente_genero (and PredictorRequest in pipeline-db-ml):
    text between '@' and the first '.', lower case. Accepts "gmail" or "ana@yahoo.com.br"."""
    valor = str(valor).strip().lower()
    if "@" in valor:
        valor = valor.split("@", 1)[1]
    return valor.split(".")[0]


def preparar_entrada(model_input) -> pd.DataFrame:
    if not isinstance(model_input, pd.DataFrame):
        model_input = pd.DataFrame(model_input)
    faltan = [c for c in FEATURES if c not in model_input.columns]
    if faltan:
        raise ValueError(f"faltan columnas: {faltan}; se esperan {FEATURES}")
    X = model_input[FEATURES].copy()  # by name: dataframe_records does not guarantee column order
    X["tipo_correo"] = X["tipo_correo"].map(extraer_tipo_correo)
    X["pais"] = X["pais"].astype(str).str.strip()
    X["ciudad"] = X["ciudad"].astype(str).str.strip()
    return X


class GenreModel(_Base):
    def __init__(self, pipeline):
        self.pipeline = pipeline

    def predict(self, context, model_input, params=None):
        X = preparar_entrada(model_input)
        generos = self.pipeline.predict(X)
        probas = self.pipeline.predict_proba(X)
        clases = [str(c) for c in self.pipeline.classes_]
        filas = []
        for genero, fila in zip(generos, probas):
            orden = sorted(range(len(clases)), key=lambda k: fila[k], reverse=True)[:3]
            salida = {"genero": str(genero)}
            for pos in range(3):
                if pos < len(orden):
                    salida[f"top_{pos + 1}"] = clases[orden[pos]]
                    salida[f"p_{pos + 1}"] = round(float(fila[orden[pos]]), 4)
                else:
                    salida[f"top_{pos + 1}"] = ""
                    salida[f"p_{pos + 1}"] = 0.0
            filas.append(salida)
        return pd.DataFrame(filas, columns=OUTPUT_COLUMNS)
