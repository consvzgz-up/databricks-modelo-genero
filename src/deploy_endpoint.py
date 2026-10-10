"""Task 3: publish the Champion version of workspace.chinook.genero_cliente on the endpoint genero-cliente.

Creates the endpoint (Small, scale to zero) if it does not exist, otherwise updates its config to the
new version; waits until it is ready. Auth is the job's ambient identity (WorkspaceClient()).
The old config keeps serving until the new one is ready, so a daily update has no downtime.
"""
import argparse
from datetime import timedelta

ENDPOINT = "genero-cliente"
MODEL_NAME = "workspace.chinook.genero_cliente"
ALIAS = "Champion"
TIMEOUT = timedelta(minutes=30)


def version_from_task_value():
    try:
        from databricks.sdk.runtime import dbutils
        v = dbutils.jobs.taskValues.get(taskKey="train_model", key="model_version", debugValue="")
        return str(v) if v else None
    except Exception as e:  # noqa: BLE001
        print(f"task value not available ({type(e).__name__})")
        return None


def champion_version():
    import mlflow
    from mlflow.tracking import MlflowClient
    mlflow.set_registry_uri("databricks-uc")
    mv = MlflowClient(registry_uri="databricks-uc").get_model_version_by_alias(MODEL_NAME, ALIAS)
    return str(mv.version)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=None)  # accepted for symmetry with the other tasks
    ap.parse_args()

    from databricks.sdk import WorkspaceClient
    from databricks.sdk.errors import NotFound, ResourceDoesNotExist
    from databricks.sdk.service.serving import EndpointCoreConfigInput, ServedEntityInput

    w = WorkspaceClient()

    alias_version = champion_version()
    task_version = version_from_task_value()
    if task_version and task_version != alias_version:
        print(f"note: task value says version {task_version}, alias {ALIAS} says {alias_version}; using the alias")
    version = alias_version
    print(f"{MODEL_NAME}@{ALIAS} = version {version}")

    entity = ServedEntityInput(
        entity_name=MODEL_NAME,
        entity_version=version,
        workload_size="Small",
        scale_to_zero_enabled=True,
    )

    try:
        existing = w.serving_endpoints.get(ENDPOINT)
    except (NotFound, ResourceDoesNotExist):
        existing = None

    if existing is None:
        print(f"creating endpoint {ENDPOINT} with version {version} (waiting up to {TIMEOUT})")
        endpoint = w.serving_endpoints.create_and_wait(
            name=ENDPOINT,
            config=EndpointCoreConfigInput(name=ENDPOINT, served_entities=[entity]),
            timeout=TIMEOUT,
        )
    else:
        served = [(e.entity_name, str(e.entity_version))
                  for e in ((existing.config.served_entities if existing.config else None) or [])]
        updating = existing.state and existing.state.config_update and \
            existing.state.config_update.value == "IN_PROGRESS"
        if updating:
            print(f"endpoint {ENDPOINT} is updating; waiting for it first")
            existing = w.serving_endpoints.wait_get_serving_endpoint_not_updating(ENDPOINT, timeout=TIMEOUT)
            served = [(e.entity_name, str(e.entity_version))
                      for e in ((existing.config.served_entities if existing.config else None) or [])]
        if served == [(MODEL_NAME, version)]:
            print(f"endpoint {ENDPOINT} already serves version {version}; no update")
            endpoint = existing
        else:
            print(f"updating endpoint {ENDPOINT}: {served} -> {MODEL_NAME} v{version} (waiting up to {TIMEOUT})")
            endpoint = w.serving_endpoints.update_config_and_wait(
                name=ENDPOINT,
                served_entities=[entity],
                timeout=TIMEOUT,
            )

    state = endpoint.state
    ready = state.ready.value if state and state.ready else None
    config_update = state.config_update.value if state and state.config_update else None
    print(f"endpoint {ENDPOINT}: ready={ready} config_update={config_update}")
    for e in (endpoint.config.served_entities if endpoint.config else None) or []:
        print(f"  serves {e.entity_name} version {e.entity_version}")
    host = w.config.host.rstrip("/")
    print(f"invocation URL: {host}/serving-endpoints/{ENDPOINT}/invocations")
    if ready != "READY":
        raise SystemExit(f"endpoint {ENDPOINT} is not READY (ready={ready})")


if __name__ == "__main__":
    main()
