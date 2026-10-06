"""Contrato: o schema exposto ao modelo == o dispatch/validação do Harness."""

import agent
import tools.manager as manager


def schema_by_name():
    return {t["function"]["name"]: t["function"] for t in agent.TOOLS}


def test_schema_and_dispatch_expose_the_same_tools():
    assert set(schema_by_name()) == set(manager.TOOLS)


def test_schema_properties_match_allowed_arguments():
    for name, fn in schema_by_name().items():
        properties = set(fn["parameters"].get("properties", {}))
        assert properties == manager.ALLOWED_ARGUMENTS[name], name


def test_schema_required_match_required_arguments():
    for name, fn in schema_by_name().items():
        required = set(fn["parameters"].get("required", []))
        assert required == manager.REQUIRED_ARGUMENTS[name], name


def test_every_tool_has_validation_rules():
    assert set(manager.TOOLS) == set(manager.ALLOWED_ARGUMENTS) == set(manager.REQUIRED_ARGUMENTS)


def test_set_smart_candidate_for_benchmark_is_exposed_to_the_model():
    assert "set_smart_candidate_for_benchmark" in schema_by_name()
