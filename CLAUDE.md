# databricks-genre-model

Bases de Datos assignment (UP), sequel of `../pipeline-db-ml`: the Chinook genre model (tipo_correo, pais, ciudad
-> genero) trained daily by a serverless Databricks job and published on the Model Serving endpoint
`genero-cliente`. Databricks Free Edition; one Databricks Asset Bundle (`databricks.yml`, `resources/`).

## Layout
- `data/*.csv`: five Chinook tables generated from `../pipeline-db-ml/db/init/01_chinook.sql` by
  `scripts/chinook_to_csv.py` (committed; the job reads them from the bundle's workspace files).
- `sql/vw_cliente_genero.sql`: the view, same SQL as `pipeline-db-ml/db/view.sql` with `workspace.chinook.*` names.
- `src/`: the four job tasks (`load_chinook`, `train_model`, `deploy_endpoint`, `smoke_test`) and `genre_model.py`
  (pyfunc wrapper: normalises tipo_correo, returns genero + top 3).
- `scripts/query_endpoint.py`: local client; `scripts/local_check.py`: model check without Databricks.

## Commands
```
python scripts/chinook_to_csv.py --self-test      # 25/3503/2240/412/59
python scripts/local_check.py                     # pandas + scikit-learn, no Databricks
databricks bundle validate -t dev
databricks bundle deploy -t dev                   # leaves the machine: only on the user's yes
databricks bundle run -t dev genre_model_train    # load, train, publish, smoke test
python scripts/query_endpoint.py --profile <cli-profile>
```

## Rules
- The access token is never stored in this repo, never printed, never committed: it lives in the user's
  environment (`DATABRICKS_TOKEN`) or the Databricks CLI profile. Docs show `<TOKEN>` as a placeholder.
- Deploy, run and push happen only on the user's explicit yes.
- Model name `workspace.chinook.genero_cliente`, alias `Champion` (capital C), endpoint `genero-cliente`.
