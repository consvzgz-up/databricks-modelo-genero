# databricks-genre-model — Predicción de género musical en Databricks (Chinook)

Un **job de Databricks** entrena cada día el modelo que predice el género musical de un cliente que entra a la
tienda (a partir de su tipo de correo, país y ciudad) y lo publica en un **serving endpoint** protegido con token.

Es la continuación de [pipeline-db-ml](https://github.com/consvzgz-up/pipeline-db-ml): los mismos datos (Chinook),
la misma vista `vw_cliente_genero`, el mismo modelo de scikit-learn y el mismo contrato de respuesta (`genero` más
un top 3 con probabilidades). Lo que cambia es dónde corre cada pieza: el entrenamiento lo hace un job serverless
programado, el modelo vive en el registro de MLflow dentro de Unity Catalog y la predicción la sirve Model Serving.

Documento paso a paso (inglés): [docs/databricks-genre-model_step_by_step.pdf](docs/databricks-genre-model_step_by_step.pdf).

## Entrega

| Entregable | Valor |
|---|---|
| Liga del endpoint | `https://dbc-c19856c3-faa2.cloud.databricks.com/serving-endpoints/genero-cliente/invocations` |
| Token de acceso | `<TOKEN>`: se entrega por el canal del curso, no está en este repositorio |
| Ejemplo de consulta | abajo, con curl y con Python |

El endpoint recibe `POST` con el encabezado `Authorization: Bearer <TOKEN>` y un cuerpo JSON con las tres
variables. `tipo_correo` puede ser el proveedor (`yahoo`) o un correo completo (`ana@yahoo.com.br` se convierte en
`yahoo`, igual que en la vista).

### Con curl (bash)

```bash
curl -X POST https://dbc-c19856c3-faa2.cloud.databricks.com/serving-endpoints/genero-cliente/invocations \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"dataframe_records": [{"tipo_correo": "yahoo", "pais": "Germany", "ciudad": "Berlin"}]}'
```

Respuesta real (9 de octubre de 2026, versión 1 del modelo):

```json
{
  "predictions": [
    {
      "genero": "Metal",
      "top_1": "Metal",
      "p_1": 0.4076,
      "top_2": "Rock",
      "p_2": 0.3364,
      "top_3": "Alternative & Punk",
      "p_3": 0.0752
    }
  ]
}
```

`genero` es la predicción; `top_1` a `top_3` son los tres géneros más probables y `p_1` a `p_3` sus
probabilidades. Se pueden mandar varias filas en la misma lista `dataframe_records`; las predicciones regresan en
el mismo orden.

### Con Python (requests)

El token se lee del entorno, nunca se escribe en el código:

```bash
export DATABRICKS_TOKEN=<TOKEN>
```

```python
import os
import requests

url = "https://dbc-c19856c3-faa2.cloud.databricks.com/serving-endpoints/genero-cliente/invocations"
headers = {
    "Authorization": f"Bearer {os.environ['DATABRICKS_TOKEN']}",
    "Content-Type": "application/json",
}
body = {"dataframe_records": [
    {"tipo_correo": "yahoo", "pais": "Germany", "ciudad": "Berlin"},
    {"tipo_correo": "gmail", "pais": "Brazil", "ciudad": "São Paulo"},
]}

r = requests.post(url, headers=headers, json=body, timeout=120)
r.raise_for_status()
for p in r.json()["predictions"]:
    print(p["genero"], p["top_1"], p["p_1"], p["top_2"], p["p_2"], p["top_3"], p["p_3"])
```

El repositorio trae el mismo cliente listo para usar, `scripts/query_endpoint.py`:

```bash
export DATABRICKS_HOST=https://dbc-c19856c3-faa2.cloud.databricks.com
export DATABRICKS_TOKEN=<TOKEN>
python scripts/query_endpoint.py --tipo-correo yahoo --pais Germany --ciudad Berlin
```

Si la primera llamada tarda más de lo normal es porque el endpoint tiene *scale to zero* (se apaga cuando nadie lo
usa) y está arrancando; las siguientes responden rápido.

Otras respuestas de la misma versión (prueba automática del job):

| tipo_correo | pais | ciudad | genero | top 3 |
|---|---|---|---|---|
| `yahoo` | Germany | Berlin | **Metal** | Metal 0.4076, Rock 0.3364, Alternative & Punk 0.0752 |
| `gmail` | Brazil | São Paulo | **Rock** | Rock 0.515, Latin 0.2183, Alternative & Punk 0.0942 |
| `ana@yahoo.com.br` | Brazil | São Paulo | **Rock** | Rock 0.398, Latin 0.2572, Alternative & Punk 0.1059 |

## Arquitectura

```
data/*.csv (5 tablas de Chinook, sacadas del dump de Postgres)  --databricks bundle deploy-->  archivos del workspace
   |
job genre_model_train (serverless, diario 03:00 hora de Ciudad de México; también a mano)
   1 load_chinook   : CSV -> tablas Delta workspace.chinook.{genre,track,invoice_line,invoice,customer}
                      + CREATE OR REPLACE VIEW workspace.chinook.vw_cliente_genero (misma SQL)
   2 train_model    : vista -> pandas -> mismo pipeline de scikit-learn; accuracy y reporte a MLflow;
                      reentrena con todo; registra workspace.chinook.genero_cliente (wrapper pyfunc,
                      genero + top 3); alias Champion -> versión nueva
   3 deploy_endpoint: crea el endpoint genero-cliente (Small, scale to zero) si no existe; si existe, lo
                      actualiza a la versión Champion; espera a que esté READY
   4 smoke_test     : consulta el endpoint con 3 filas conocidas; si no hay predicción, el job falla
   |
https://dbc-c19856c3-faa2.cloud.databricks.com/serving-endpoints/genero-cliente/invocations   (Bearer <TOKEN>)
```

Todo está en un solo **Databricks Asset Bundle** (`databricks.yml` y `resources/`): el código, los CSV y la
definición del job se despliegan juntos con un comando.

## El job

| | |
|---|---|
| Nombre | `genre_model_train` (id 740463899927346) |
| Liga | https://dbc-c19856c3-faa2.cloud.databricks.com/jobs/740463899927346?o=7474649054775928 |
| Cómputo | serverless (Free Edition no tiene clústeres clásicos) |
| Horario | `0 0 3 * * ?` (Quartz cron, primero los segundos) en `America/Mexico_City`: todos los días a las 03:00; `UNPAUSED` |
| Entorno | `scikit-learn==1.6.1`, `mlflow>=2.15,<4`, `pandas>=1.5,<3`, `databricks-sdk>=0.40` (environment_version 2) |
| Definición | `resources/genre_model_train.job.yml` |

Las cuatro tareas corren en secuencia; si una falla, las siguientes no corren y el endpoint sigue sirviendo la
versión anterior.

1. **`load_chinook`** (`src/load_chinook.py`): lee los cinco CSV desde los archivos del bundle, les pone los tipos
   del dump original (enteros, decimales, fechas), los escribe como tablas Delta `workspace.chinook.*`
   (sobrescribe) y vuelve a crear la vista con `sql/vw_cliente_genero.sql`. En la primera corrida: genre 25,
   track 3503, invoice_line 2240, invoice 412 y customer 59 filas; la vista, 2240 filas.
2. **`train_model`** (`src/train_model.py`): lee la vista, separa 20 % para medir, entrena, guarda en MLflow la
   accuracy y el reporte de clasificación, reentrena con todas las filas, registra el modelo en Unity Catalog y
   mueve el alias `Champion` a la versión nueva.
3. **`deploy_endpoint`** (`src/deploy_endpoint.py`): pregunta qué versión tiene el alias `Champion`; crea el
   endpoint si no existe o actualiza su configuración a esa versión; espera hasta que esté listo (máximo 30 min).
4. **`smoke_test`** (`src/smoke_test.py`): consulta el endpoint con tres filas conocidas e imprime las
   predicciones; si falta alguna, marca el job como fallido.

La primera corrida (9 de octubre de 2026, run 278214313505025) empezó a las 22:20:54 y terminó con `SUCCESS` a las
22:32:38: unos 12 minutos, casi todos en la creación del endpoint. Entrenar tarda segundos.

### Correrlo a mano

Con la CLI de Databricks, desde la carpeta del repositorio:

```bash
databricks bundle run -t dev genre_model_train
```

La CLI imprime la liga de la corrida, su estado y, al terminar, la salida de cada tarea.

Desde la interfaz: abrir la liga del job (tabla de arriba) y pulsar **Run now**. En la misma página, la lista de
corridas muestra cada una con su duración, y al abrir una corrida se ve la salida de cada tarea.

## El modelo

- **Datos**: la vista `workspace.chinook.vw_cliente_genero` (`sql/vw_cliente_genero.sql`), la misma SQL que en
  pipeline-db-ml con nombres de tres niveles de Unity Catalog. Una fila por track comprado: 2240 filas, 24 géneros.
- **Variables**: `tipo_correo` (el texto entre `@` y el primer `.` del correo, en minúsculas), `pais` y `ciudad`.
  Objetivo: `genero`.
- **Pipeline**: `OneHotEncoder(handle_unknown="ignore") → LogisticRegression(max_iter=1000)`, igual que antes. Un
  país, ciudad o proveedor nunca visto no rompe la predicción.
- **Medición**: hold-out de 20 % (`random_state=42`, sin `stratify` porque hay géneros con una sola fila).
  Accuracy de la primera corrida: **0.39** (0.393). En EC2 la misma receta dio 0.353; la diferencia viene de que
  Spark entrega las filas de la vista en otro orden, así que el 20 % de prueba es otro. El modelo y los datos son
  los mismos. Como referencia, responder siempre "Rock" acierta en 37 % de las filas.
- **Registro**: MLflow con `mlflow.set_registry_uri("databricks-uc")`. Experimento
  `/Users/0188554@up.edu.mx/genre_model_train` (parámetros, métrica `accuracy`, artefacto
  `classification_report.txt`); modelo registrado `workspace.chinook.genero_cliente`, versión 1 en la primera
  corrida; alias **`Champion`** → la versión más reciente. El `input_example` deja que MLflow infiera la firma
  (columnas de entrada y salida), que Unity Catalog exige.
- **Wrapper pyfunc** (`src/genre_model.py`): envuelve el pipeline para que el endpoint devuelva `genero` y el top 3
  con probabilidades (el mismo contrato que `POST /api/model` en EC2), aplique la misma regla de `tipo_correo` que
  la vista (acepta el correo completo) y tome las columnas por nombre, no por posición.

## El endpoint

| | |
|---|---|
| Nombre | `genero-cliente` |
| Sirve | `workspace.chinook.genero_cliente`, la versión con alias `Champion` |
| Tamaño | `Small` (CPU) |
| Scale to zero | activado: sin tráfico se apaga y no consume; la primera llamada después de un rato sin uso tarda más |
| Autenticación | `Authorization: Bearer <token>` |
| Formato | entrada `{"dataframe_records": [...]}` (o `dataframe_split`); salida `{"predictions": [...]}` |

**Cómo se actualiza en cada corrida.** Cada corrida registra una versión nueva N del modelo, mueve `Champion` a N y
la tarea `deploy_endpoint` cambia la configuración del endpoint para que sirva N. Mientras la versión nueva se
prepara, la anterior sigue respondiendo; el cambio ocurre cuando la nueva está lista, sin tiempo fuera de servicio
([create-manage-serving-endpoints](https://docs.databricks.com/aws/en/machine-learning/model-serving/create-manage-serving-endpoints)).
Así se vio durante la segunda corrida: el endpoint seguía `READY` y sirviendo la versión 1 mientras la versión 2
aparecía como configuración pendiente, y las consultas respondían con normalidad. La liga y el token no cambian.

## Cómo se genera el token (lo hace la dueña o el dueño del workspace)

1. En Databricks, clic en el nombre de usuario (arriba a la derecha) → **Settings** → **Developer** →
   **Access tokens** → **Manage** → **Generate new token**.
2. Nombre `profesor-bases-de-datos`, vigencia 60 días. Si la interfaz ofrece alcance (scope), elegir
   "Other APIs" y limitarlo a serving endpoints.
3. Copiar el token en ese momento (no se vuelve a mostrar) y mandarlo por el canal del curso. Nunca se guarda en
   este repositorio ni en ningún archivo versionado.

El token da los permisos de su dueño a través de la API; por eso tiene vigencia corta. Para cortarlo antes, se
revoca desde la misma lista de **Access tokens**. Un token sin uso durante 90 días se revoca solo. Fuente:
[Databricks personal access tokens](https://docs.databricks.com/aws/en/dev-tools/auth/pat).

## Cómo reproducir desde cero

Requisitos: un workspace de Databricks (Free Edition basta) y Python 3.11 o más reciente para las herramientas
locales.

```bash
# 1. CLI de Databricks (en Windows con winget)
winget install Databricks.DatabricksCLI
databricks --version

# 2. Login por navegador (OAuth); no hay que escribir ningún token
databricks auth login --host https://<tu-workspace>.cloud.databricks.com
databricks current-user me

# 3. (opcional) volver a generar los CSV desde el dump de pipeline-db-ml y probar el modelo en local
python scripts/chinook_to_csv.py --self-test      # 25/3503/2240/412/59
python scripts/local_check.py                     # requiere pandas y scikit-learn

# 4. Validar, desplegar y correr el bundle
#    (antes, cambiar workspace.host en databricks.yml por tu workspace)
databricks bundle validate -t dev
databricks bundle deploy -t dev
databricks bundle run -t dev genre_model_train

# 5. Consultar el endpoint sin token, con la sesión de la CLI
python -m venv .venv
.venv/Scripts/pip install requests databricks-sdk   # en macOS/Linux: .venv/bin/pip
export DATABRICKS_HOST=https://<tu-workspace>.cloud.databricks.com
.venv/Scripts/python scripts/query_endpoint.py
```

`scripts/query_endpoint.py` usa `DATABRICKS_TOKEN` si está definido; si no, usa la autenticación de
`databricks-sdk`: el perfil indicado con `--profile`, o la sesión de `databricks auth login` junto con
`DATABRICKS_HOST` (en este caso el ejecutable `databricks` debe estar en el `PATH`, porque el SDK le pide el token
de la sesión).

## Estructura del repositorio

```
databricks.yml                         bundle genre_model, target dev (host del workspace)
resources/genre_model_train.job.yml    job diario: load_chinook -> train_model -> deploy_endpoint -> smoke_test
src/load_chinook.py                    CSV -> tablas Delta workspace.chinook.* + vista vw_cliente_genero
src/train_model.py                     entrenamiento, MLflow, registro workspace.chinook.genero_cliente@Champion
src/genre_model.py                     wrapper pyfunc (normaliza tipo_correo, devuelve genero + top 3)
src/deploy_endpoint.py                 crea o actualiza el endpoint genero-cliente y espera READY
src/smoke_test.py                      consulta de prueba al endpoint (3 filas)
sql/vw_cliente_genero.sql              la vista (misma SQL que pipeline-db-ml)
data/*.csv                             cinco tablas de Chinook (generadas por scripts/chinook_to_csv.py)
scripts/chinook_to_csv.py              dump de Postgres -> CSV (solo biblioteca estándar, --self-test)
scripts/local_check.py                 prueba del modelo en local, sin Databricks
scripts/query_endpoint.py              cliente local del endpoint
docs/step_by_step.html                 documento paso a paso (inglés), fuente del PDF
docs/databricks-genre-model_step_by_step.pdf
requirements-dev.txt                   dependencias locales (el job instala las suyas)
```

## Notas de Databricks Free Edition

Límites que dieron forma al diseño
([Free Edition limitations](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations),
consultado el 9 de octubre de 2026):

- **Solo cómputo serverless**: por eso las tareas son `spark_python_task` con un entorno declarado en el job, sin
  clústeres.
- **Internet de salida restringido a un conjunto de dominios de confianza**: el job no puede conectarse a la base
  Postgres de EC2 ni a Supabase. Por eso los datos viven en Databricks: los CSV salen del dump
  (`scripts/chinook_to_csv.py`) y viajan con el bundle.
- **Máximo 5 tareas de job concurrentes por cuenta**: el job corre sus cuatro tareas en secuencia y con
  `max_concurrent_runs: 1`.
- **Model Serving con un número limitado de endpoints activos** (el número no se publica) y sin GPU: un solo
  endpoint `Small` de CPU.
- **Cuota de uso justo**: si se excede, el cómputo se apaga el resto del día. Por eso el job corre una vez al día y
  no cada hora como el cron de EC2.

Otras fuentes (consultadas el mismo día): límites por petición de Model Serving,
[model-serving-limits](https://docs.databricks.com/aws/en/machine-learning/model-serving/model-serving-limits);
formato de consulta,
[score-custom-model-endpoints](https://docs.databricks.com/aws/en/machine-learning/model-serving/score-custom-model-endpoints);
registro en Unity Catalog y alias,
[manage-model-lifecycle](https://docs.databricks.com/aws/en/machine-learning/manage-model-lifecycle/);
horario de un job en un bundle,
[bundles/examples](https://docs.databricks.com/aws/en/dev-tools/bundles/examples).

Una trampa del bundle: el target `dev` **no** usa `mode: development`, porque ese modo pausa todos los horarios y
agrega un prefijo a los nombres de los recursos; la tarea pide que el entrenamiento diario esté activo.

## Qué cambió respecto a pipeline-db-ml

| | pipeline-db-ml (EC2) | databricks-genre-model |
|---|---|---|
| Datos | Postgres 16 en un contenedor, dump `01_chinook.sql` | tablas Delta `workspace.chinook.*` cargadas desde CSV |
| Vista | `vw_cliente_genero` en Postgres | `workspace.chinook.vw_cliente_genero`, misma SQL |
| Entrenamiento | cron cada hora en un contenedor | job serverless de Databricks, diario a las 03:00 |
| Modelo guardado | `assets/modelo_entrenado.pkl` en una carpeta compartida | MLflow en Unity Catalog, versiones y alias `Champion` |
| Servicio | FastAPI `POST /api/model` en el puerto 8000 | Model Serving, endpoint `genero-cliente` |
| Acceso | abierto a internet (security group) | token de acceso en el encabezado `Authorization` |
| Respuesta | `genero` + lista `top_3` | `predictions[]` con `genero`, `top_1..3`, `p_1..3` |
| Accuracy (hold-out 20 %) | 0.353 | 0.39 (otro orden de filas, otro 20 % de prueba) |
| Infraestructura | VM `t3.small`, Docker Compose, Elastic IP | nada que administrar: workspace Free Edition |
| Despliegue | `git clone` + `docker compose up -d --build` | `databricks bundle deploy` + `databricks bundle run` |
