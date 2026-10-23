"""The live model's registry steps in Unity Catalog (<catalog>.ml.heat_model, alias champion): the refit runs once, and
the nightly job loads the version the alias points to when it starts, by that version number.

Standard library only at import (mlflow is imported where it is used), so the tests can run in the throwaway MLflow
venv (tests/backtest/test_live_model_mlflow.py).
"""
ALIAS = "champion"


def model_versions(client, name):
    """The registered versions of `name`; none when the model does not exist yet."""
    from mlflow.exceptions import MlflowException

    try:
        return list(client.search_model_versions(f"name = '{name}'"))
    except MlflowException as e:
        if getattr(e, "error_code", "") in ("RESOURCE_DOES_NOT_EXIST", "NOT_FOUND"):
            return []
        raise


def refuse_if_registered(client, name):
    """The live model is refit once: stop when `name` already has a version (before anything is read or fitted)."""
    versions = model_versions(client, name)
    if versions:
        raise SystemExit(f"{name} already has version(s) {', '.join(sorted(str(v.version) for v in versions))}: the live "
                         "model is refit once, so nothing was read, fitted or registered")


def champion(client, name, alias=ALIAS):
    """The version the alias points to now, and the URI that loads exactly that version for the whole run."""
    mv = client.get_model_version_by_alias(name, alias)
    return mv, f"models:/{name}/{mv.version}"
