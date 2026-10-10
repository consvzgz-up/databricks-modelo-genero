# databricks-genre-model — Predicción de género musical en Databricks (Chinook)

Continuación de [pipeline-db-ml](../pipeline-db-ml): el mismo modelo (tipo de correo, país y ciudad → género
musical que probablemente le guste a un cliente que entra a la tienda), ahora entrenado cada día a las 03:00
(hora de Ciudad de México) por un **job serverless de Databricks** y publicado en el **serving endpoint**
`genero-cliente`. *Borrador: la versión completa del README (URL del endpoint, cómo generar el token, ejemplos con
curl y Python) llega en una fase posterior.*

```
databricks.yml                         bundle (target dev)
resources/genre_model_train.job.yml    job diario: load_chinook -> train_model -> deploy_endpoint -> smoke_test
src/load_chinook.py                    CSV -> tablas Delta workspace.chinook.* + vista vw_cliente_genero
src/train_model.py                     entrenamiento, MLflow, registro workspace.chinook.genero_cliente@Champion
src/genre_model.py                     wrapper pyfunc (genero + top 3)
src/deploy_endpoint.py                 crea o actualiza el endpoint genero-cliente
src/smoke_test.py                      consulta de prueba al endpoint
sql/vw_cliente_genero.sql              la vista (misma SQL que pipeline-db-ml)
data/*.csv                             cinco tablas de Chinook (scripts/chinook_to_csv.py)
scripts/query_endpoint.py              cliente local (DATABRICKS_HOST y DATABRICKS_TOKEN del entorno)
```
