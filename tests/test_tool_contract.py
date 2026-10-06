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


def test_compact_schema_keeps_names_properties_types_and_required():
    full = {t["function"]["name"]: t["function"] for t in agent.TOOLS}
    compact = {t["function"]["name"]: t["function"] for t in agent.visible_tools(True)}

    assert set(compact) == set(full)

    for name, fn in full.items():
        small = compact[name]["parameters"]
        big = fn["parameters"]

        assert set(small.get("properties", {})) == set(big.get("properties", {})), name
        assert small.get("required", []) == big.get("required", []), name

        for prop, spec in big.get("properties", {}).items():
            assert small["properties"][prop].get("type") == spec.get("type"), (name, prop)


def test_compact_schema_is_much_smaller_and_bounded():
    import json

    full_chars = len(json.dumps(agent.TOOLS, ensure_ascii=False))
    compact_chars = len(json.dumps(agent.visible_tools(True), ensure_ascii=False))

    assert compact_chars < full_chars * 0.85

    for tool in agent.visible_tools(True):
        function = tool["function"]

        assert len(function["description"]) <= agent.TOOL_DESCRIPTION_MAX_CHARS + 3

        for spec in function["parameters"].get("properties", {}).values():
            assert len(spec.get("description", "")) <= agent.PARAM_DESCRIPTION_MAX_CHARS + 3
