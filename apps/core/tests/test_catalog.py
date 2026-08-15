import pytest
from aegis.actions import docker_ops, execute
from aegis.actions.catalog import CatalogError, get_action, load_catalog, validate_params
from aegis.actions.execute import DEMO_CONTAINERS, ContainerNotAllowed, guard_container


def test_load_catalog_has_all_eight_keys() -> None:
    catalog = load_catalog()
    assert set(catalog) == {
        "restart_service",
        "clear_cache",
        "remove_toxic",
        "restart_dependency",
        "scale_service",
        "rollback_config",
        "flush_queue",
        "restart_database",
    }


def test_get_action_unknown_key_raises() -> None:
    with pytest.raises(CatalogError):
        get_action("delete_everything")


def test_validate_params_accepts_a_valid_target_service() -> None:
    validate_params("restart_service", {"service": "target-payments"})


def test_validate_params_rejects_a_non_target_service() -> None:
    with pytest.raises(CatalogError):
        validate_params("restart_service", {"service": "shop-db"})


def test_validate_params_rejects_missing_required_param() -> None:
    with pytest.raises(CatalogError):
        validate_params("remove_toxic", {})


def test_validate_params_rejects_unexpected_extra_param() -> None:
    with pytest.raises(CatalogError):
        validate_params("clear_cache", {"unexpected": "value"})


def test_validate_params_accepts_empty_params_for_clear_cache() -> None:
    validate_params("clear_cache", {})


def test_restart_dependency_accepts_the_shop_cache() -> None:
    validate_params("restart_dependency", {"service": "shop-redis"})


def test_restart_dependency_rejects_the_event_stream() -> None:
    """aegis-redis carries aegis:events. An agent that names it is asking to
    restart the bus its own incident is being reported on, which is what the
    phase 8 live run actually did to `redis` when there was only one."""
    with pytest.raises(CatalogError):
        validate_params("restart_dependency", {"service": "aegis-redis"})


@pytest.mark.parametrize(
    "container",
    ["aegis-redis", "aegis-db", "core-worker", "core-api", "core-executor", "opa", "lgtm"],
)
def test_guard_container_rejects_aegis_infrastructure(container: str) -> None:
    with pytest.raises(ContainerNotAllowed):
        guard_container(container)


@pytest.mark.parametrize(
    "container",
    ["target-gateway", "target-orders", "target-payments", "shop-db", "shop-redis", "toxiproxy"],
)
def test_guard_container_allows_the_demo_target_set(container: str) -> None:
    assert guard_container(container) == container


def test_guard_container_allows_a_scale_clone() -> None:
    assert guard_container("target-payments-scale-2") == "target-payments-scale-2"


@pytest.mark.parametrize(
    ("catalog_key", "params"),
    [
        ("restart_service", {"service": "aegis-redis"}),
        ("restart_dependency", {"service": "aegis-redis"}),
        ("rollback_config", {"service": "core-worker"}),
        ("scale_service", {"service": "aegis-db", "replicas": 2}),
    ],
)
async def test_run_rejects_a_non_demo_container_before_docker(
    monkeypatch: pytest.MonkeyPatch, catalog_key: str, params: dict[str, object]
) -> None:
    """Defense in depth behind the catalog's param enums and OPA: even with
    both bypassed, nothing reaches the Docker socket."""

    def _fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("docker_ops was called for a non-demo container")

    for name in ("restart_container", "clone_and_start", "stop_and_remove"):
        monkeypatch.setattr(docker_ops, name, _fail)

    with pytest.raises(ContainerNotAllowed):
        await execute.run(catalog_key, params)


def test_demo_containers_holds_no_aegis_service() -> None:
    """The guard is only as good as its set: an aegis-* name landing in
    DEMO_CONTAINERS by a later edit would make every test above pass while
    reopening the hole."""
    assert not [name for name in DEMO_CONTAINERS if name.startswith("aegis-")]
