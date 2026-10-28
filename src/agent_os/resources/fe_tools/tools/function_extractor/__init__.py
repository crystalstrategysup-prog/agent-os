"""Deterministic, offline Function Extractor public API. No target import at load."""

__version__ = "0.4.6"
_EXPORTS = ("resolve_entry", "extract_route", "freeze_source", "discover_boundaries",
            "compile_fixture", "build_sandbox", "execute_route", "inject_fault",
            "compare_contract", "render_route_report", "propose_contract_update",
            "verify_repeatability")
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    from . import api
    return getattr(api, name)
