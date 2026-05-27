from pathlib import Path
from functools import lru_cache
from typing import TypeVar, Type
from pydantic_settings import BaseSettings

S = TypeVar("S", bound=BaseSettings)


@lru_cache(maxsize=6)
def read_from_secret(
    secret_name: str, settings_class: Type[S], namespace: str = "default"
) -> S:
    """
    Populate the settings from a secret (as loaded in a fission function)
    :param secret_name:
    :param settings_class:
    :param namespace: Namespace where the secret was created
    :return:
    """
    base_path = Path(f"/secrets/{namespace}/{secret_name}")
    pref = settings_class.model_config.get("env_prefix", "")

    vals = {}
    for name, field in settings_class.model_fields.items():
        var_name = f"{pref}{name}".upper()
        full_path = base_path / var_name
        if full_path.is_file():
            with full_path.open("r") as f:
                vals[name] = f.read()
        elif field.default:
            vals[name] = field.default

    return settings_class.model_validate(vals)
