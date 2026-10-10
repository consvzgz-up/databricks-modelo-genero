# databricks-genre-model

Bases de Datos assignment (UP), sequel of `../pipeline-db-ml`: the Chinook genre model (tipo_correo, pais, ciudad
-> genero) trained daily by a serverless Databricks job and published on the Model Serving endpoint
`genero-cliente`. Databricks Free Edition; one Databricks Asset Bundle (`databricks.yml`, `resources/`).

## Deployment (live since 2026-10-09)
- Workspace: https://dbc-c19856c3-faa2.cloud.databricks.com (workspace id 7474649054775928), bundle root
  `/Workspace/Users/0188554@up.edu.mx/.bundle/genre_model/dev`.
- Job `genre_model_train`, id 740463899927346:
  https://dbc-c19856c3-faa2.cloud.databricks.com/jobs/740463899927346?o=7474649054775928
  (Quartz `0 0 3 * * ?`, America/Mexico_City, UNPAUSED; first run 278214313505025, SUCCESS).
- Endpoint URL: https://dbc-c19856c3-faa2.cloud.databricks.com/serving-endpoints/genero-cliente/invocations
  (Small, scale to zero; each run moves it to the new Champion version).

## Layout
- `data/*.csv`: five Chinook tables generated from `../pipeline-db-ml/db/init/01_chinook.sql` by
  `scripts/chinook_to_csv.py` (committed; the job reads them from the bundle's workspace files).
- `sql/vw_cliente_genero.sql`: the view, same SQL as `pipeline-db-ml/db/view.sql` with `workspace.chinook.*` names.
- `src/`: the four job tasks (`load_chinook`, `train_model`, `deploy_endpoint`, `smoke_test`) and `genre_model.py`
  (pyfunc wrapper: normalises tipo_correo, returns genero + top 3).
- `scripts/query_endpoint.py`: local client; `scripts/local_check.py`: model check without Databricks.
- `README.md` (Spanish, professor-facing: endpoint URL, `<TOKEN>` placeholder, curl and Python examples);
  `docs/step_by_step.html` (English) and the PDF built from it with Edge headless
  (`msedge --headless --disable-gpu --no-pdf-header-footer --print-to-pdf=<pdf> file:///<html>`).

## Commands
```
python scripts/chinook_to_csv.py --self-test      # 25/3503/2240/412/59
python scripts/local_check.py                     # pandas + scikit-learn, no Databricks
databricks bundle validate -t dev
databricks bundle deploy -t dev                   # leaves the machine: only on the user's yes
databricks bundle run -t dev genre_model_train    # load, train, publish, smoke test: only on the user's yes
databricks serving-endpoints get genero-cliente   # read the endpoint state
python scripts/query_endpoint.py                  # DATABRICKS_TOKEN if set, else databricks-sdk auth
                                                  # (--profile <name>, or DATABRICKS_HOST + CLI login;
                                                  #  the databricks CLI must be on PATH)
```
Local tools: `python -m venv .venv` (git-ignored), `.venv/Scripts/pip install requests databricks-sdk`.

## Rules
- The access token is never stored: not in this repo, not in any file, not in a reply, a log or a commit. It is
  never created, read, printed or guessed by an agent. The user generates it in the Databricks UI and sends it to
  the professor through the course channel; locally it lives only in the user's environment (`DATABRICKS_TOKEN`) or
  the Databricks CLI login. Docs always show the literal placeholder `<TOKEN>`.
- Never read `.env`, `~/.databrickscfg`, `~/.databricks` or any credential file.
- Deploy, run, destroy and push happen only on the user's explicit yes.
- Model name `workspace.chinook.genero_cliente`, alias `Champion` (capital C), endpoint `genero-cliente`.
- No `mode: development` on the target: it pauses the schedule.
