import pytest
from aegis.actions.catalog import CatalogError, get_action, load_catalog, validate_params


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
