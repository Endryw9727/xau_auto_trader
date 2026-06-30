"""Regression tests for the Starlette app wiring.

These are deliberately lightweight: they make sure ``src.api.app`` imports and
constructs the application object across Starlette versions. A previous build
passed ``on_startup=`` to the ``Starlette`` constructor, which newer Starlette
releases reject with ``TypeError: unexpected keyword argument 'on_startup'`` —
breaking the API process entirely (and, downstream, the ngrok tunnel). This
test fails fast if anything reintroduces a version-specific constructor kwarg.
"""

from starlette.applications import Starlette


def test_app_constructs():
    from src.api.app import app

    assert isinstance(app, Starlette)


def test_app_exposes_health_route():
    from src.api.app import app

    paths = {route.path for route in app.routes}
    assert "/api/health" in paths
    assert "/api/edge/significance-audit" in paths


def test_warm_cache_helper_is_non_blocking():
    # Starting the warmer must never raise even with no data present.
    from src.api.app import _warm_cache_in_background

    _warm_cache_in_background()
