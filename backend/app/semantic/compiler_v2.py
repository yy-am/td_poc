"""Semantic query compiler with backward-compatible YAML v1/v2 support."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import re

import yaml

VALID_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
VALID_QUALIFIED_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?$")
VALID_JOIN_TYPE = {"inner", "left", "right", "full", "cross"}
OP_ALIASES = {
    "=": "eq",
    "==": "eq",
    "!=": "ne",
    "<>": "ne",
    ">": "gt",
    ">=": "gte",
    "<": "lt",
    "<=": "lte",
}


class SemanticDefinitionError(ValueError):
    """Raised when a semantic definition or query payload is invalid."""


@dataclass(slots=True)
class CompiledSemanticQuery:
    sql: str
    params: dict[str, Any]
    source_table: str
    model_name: str
    model_label: str
    selected_dimensions: list[str]
    selected_metrics: list[str]
    warnings: list[str] = field(default_factory=list)


def quote_identifier(identifier: str) -> str:
    if not VALID_IDENTIFIER.fullmatch(identifier):
        raise SemanticDefinitionError(f"非法标识符: {identifier}")
    return f'"{identifier}"'


def load_semantic_definition(yaml_definition: str | None) -> dict[str, Any]:
    if not yaml_definition or not yaml_definition.strip():
        raise SemanticDefinitionError("语义模型尚未配置 yaml_definition")

    try:
        loaded = yaml.safe_load(yaml_definition)
    except yaml.YAMLError as exc:
        raise SemanticDefinitionError(f"yaml_definition 解析失败: {exc}") from exc
    if not isinstance(loaded, dict):
        raise SemanticDefinitionError("yaml_definition 必须是一个映射对象")
    return loaded


def normalize_definition(
    definition: dict[str, Any],
    fallback_name: str,
    fallback_label: str,
    fallback_table: str,
) -> dict[str, Any]:
    normalized = dict(definition)
    normalized.setdefault("name", fallback_name)
    normalized.setdefault("label", fallback_label)
    normalized.setdefault("table", fallback_table)
    normalized.setdefault("description", "")
    normalized.setdefault("kind", "atomic_fact")
    normalized.setdefault("domain", "general")
    normalized.setdefault("grain", "")
    normalized["sources"] = _normalize_sources(normalized.get("sources"), fallback_table)
    normalized["joins"] = _normalize_joins(normalized.get("joins"))
    normalized["dimensions"] = _normalize_items(
        normalized.get("dimensions", []),
        default_alias=normalized["sources"][0]["alias"],
    )
    normalized["metrics"] = _normalize_items(
        normalized.get("metrics", []),
        default_alias=normalized["sources"][0]["alias"],
    )
    normalized["entities"] = normalized.get("entities") if isinstance(normalized.get("entities"), dict) else {}
    normalized["time"] = normalized.get("time") if isinstance(normalized.get("time"), dict) else {}
    normalized["business_terms"] = _normalize_string_list(normalized.get("business_terms"))
    normalized["intent_aliases"] = _normalize_string_list(normalized.get("intent_aliases"))
    normalized["analysis_patterns"] = _normalize_string_list(normalized.get("analysis_patterns"))
    normalized["evidence_requirements"] = _normalize_string_list(normalized.get("evidence_requirements"))
    normalized["detail_fields"] = _normalize_items(
        normalized.get("detail_fields", normalized.get("dimensions", [])),
        default_alias=normalized["sources"][0]["alias"],
    )
    normalized["relationship_graph"] = (
        normalized.get("relationship_graph") if isinstance(normalized.get("relationship_graph"), list) else []
    )
    normalized["metric_lineage"] = (
        normalized.get("metric_lineage") if isinstance(normalized.get("metric_lineage"), list) else []
    )
    normalized["materialization_policy"] = (
        normalized.get("materialization_policy")
        if isinstance(normalized.get("materialization_policy"), dict)
        else {}
    )
    normalized["query_hints"] = normalized.get("query_hints") if isinstance(normalized.get("query_hints"), dict) else {}
    normalized["default_limit"] = _safe_int(normalized.get("default_limit"), 100)
    normalized["entry_enabled"] = bool(normalized.get("entry_enabled", True))
    return normalized


def compile_semantic_query(
    definition: dict[str, Any],
    model_name: str,
    model_label: str,
    request_dimensions: list[str] | None = None,
    request_metrics: list[str] | None = None,
    filters: list[dict[str, Any]] | None = None,
    order: list[dict[str, Any]] | None = None,
    limit: int = 100,
) -> CompiledSemanticQuery:
    request_dimensions = request_dimensions or []
    request_metrics = request_metrics or []
    filters = filters or []
    order = order or []

    sources = definition.get("sources") or []
    if not sources:
        raise SemanticDefinitionError("语义模型缺少 sources/table 定义")

    unresolved_sources = [item for item in sources if not item.get("table")]
    if unresolved_sources:
        unresolved_labels = ", ".join(item.get("model") or item.get("alias") or "unknown" for item in unresolved_sources)
        raise SemanticDefinitionError(f"语义模型存在未解析的数据源引用: {unresolved_labels}")

    default_alias = sources[0]["alias"]
    source_table = ", ".join(str(item.get("table")) for item in sources)
    dimension_map = {item["name"]: item for item in definition.get("dimensions", [])}
    metric_map = {item["name"]: item for item in definition.get("metrics", [])}

    selected_dimensions = list(request_dimensions)
    selected_metrics = list(request_metrics)
    if not selected_dimensions and not selected_metrics:
        raise SemanticDefinitionError("至少需要一个 dimension 或 metric")

    warnings: list[str] = []
    params: dict[str, Any] = {}
    select_clauses: list[str] = []
    group_by_clauses: list[str] = []
    where_clauses: list[str] = []
    having_clauses: list[str] = []
    order_clauses: list[str] = []

    for dimension_name in selected_dimensions:
        column_expr, alias = _resolve_dimension(dimension_name, dimension_map, default_alias)
        select_clauses.append(f"{column_expr} AS {quote_identifier(alias)}")
        if selected_metrics and column_expr not in group_by_clauses:
            group_by_clauses.append(column_expr)

    for metric_name in selected_metrics:
        expr, alias = _resolve_metric(metric_name, metric_map, default_alias)
        select_clauses.append(f"{expr} AS {quote_identifier(alias)}")

    for idx, item in enumerate(filters):
        field = str(item.get("field") or "").strip()
        if not field:
            raise SemanticDefinitionError("filter 缺少 field")
        op = str(item.get("op", "eq"))
        value = item.get("value")
        clause, clause_params, use_having = _compile_filter_clause(
            field=field,
            op=op,
            value=value,
            dimension_map=dimension_map,
            metric_map=metric_map,
            default_alias=default_alias,
            param_prefix=f"f{idx}",
        )
        params.update(clause_params)
        if use_having:
            having_clauses.append(clause)
        else:
            where_clauses.append(clause)

    for item in order:
        field = str(item.get("field") or "").strip()
        if not field:
            continue
        direction = str(item.get("direction", "asc")).lower()
        if direction not in {"asc", "desc"}:
            direction = "asc"
        order_expr = _resolve_order_field(field, dimension_map, metric_map, default_alias)
        order_clauses.append(f"{order_expr} {direction.upper()}")

    if not limit or limit < 1:
        limit = int(definition.get("default_limit") or 100)
    limit = min(int(limit), 5000)

    from_clause = _build_from_clause(sources, definition.get("joins") or [])
    if selected_metrics:
        sql = f"SELECT {', '.join(select_clauses)} FROM {from_clause}"
        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)
        if group_by_clauses:
            sql += " GROUP BY " + ", ".join(group_by_clauses)
        if having_clauses:
            sql += " HAVING " + " AND ".join(having_clauses)
    else:
        sql = f"SELECT DISTINCT {', '.join(select_clauses)} FROM {from_clause}"
        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)

    if order_clauses:
        sql += " ORDER BY " + ", ".join(order_clauses)

    sql += " LIMIT :limit"
    params["limit"] = limit

    return CompiledSemanticQuery(
        sql=sql,
        params=params,
        source_table=source_table,
        model_name=model_name,
        model_label=model_label,
        selected_dimensions=selected_dimensions,
        selected_metrics=selected_metrics,
        warnings=warnings,
    )


def _normalize_sources(value: Any, fallback_table: str) -> list[dict[str, str]]:
    items = value if isinstance(value, list) and value else [{"table": fallback_table, "alias": "t"}]
    normalized: list[dict[str, str]] = []

    for index, item in enumerate(items, start=1):
        if isinstance(item, str):
            table = item.strip()
            alias = _default_alias_from_name(table, index)
            model = ""
        elif isinstance(item, dict):
            table = str(item.get("table") or "").strip()
            model = str(item.get("model") or "").strip()
            alias = str(item.get("alias") or "").strip() or _default_alias_from_name(table or model, index)
        else:
            continue

        if table and not VALID_IDENTIFIER.fullmatch(table):
            raise SemanticDefinitionError(f"非法 table 名称: {table}")
        if model and not VALID_IDENTIFIER.fullmatch(model):
            raise SemanticDefinitionError(f"非法 model 名称: {model}")
        if not VALID_IDENTIFIER.fullmatch(alias):
            raise SemanticDefinitionError(f"非法 source alias: {alias}")
        if not table and not model:
            raise SemanticDefinitionError("sources 项必须提供 table 或 model")

        normalized.append({"table": table, "model": model, "alias": alias})

    if not normalized:
        raise SemanticDefinitionError("语义模型缺少有效 sources")
    return normalized


def _normalize_joins(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    normalized: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        left = str(item.get("left") or "").strip()
        right = str(item.get("right") or "").strip()
        join_type = str(item.get("type") or "left").strip().lower()
        if not left or not right:
            continue
        if not VALID_QUALIFIED_IDENTIFIER.fullmatch(left) or not VALID_QUALIFIED_IDENTIFIER.fullmatch(right):
            raise SemanticDefinitionError(f"非法 join 条件: {left} = {right}")
        if join_type not in VALID_JOIN_TYPE:
            raise SemanticDefinitionError(f"不支持的 join 类型: {join_type}")
        normalized.append({"left": left, "right": right, "type": join_type})
    return normalized


def _normalize_items(items: Any, default_alias: str) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, str):
            normalized.append({"name": item, "column": item, "label": item, "source": default_alias})
            continue
        if not isinstance(item, dict) or not item.get("name"):
            continue

        row = dict(item)
        row["name"] = str(row["name"]).strip()
        if not row["name"]:
            continue
        row.setdefault("label", row["name"])
        row.setdefault("source", default_alias)
        normalized.append(row)
    return normalized


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in items:
            items.append(text)
    return items


def _safe_int(value: Any, default: int) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _default_alias_from_name(name: str, index: int) -> str:
    token = re.sub(r"[^A-Za-z0-9_]", "_", name or "").strip("_").lower()
    if not token:
        return f"s{index}"
    parts = [part for part in token.split("_") if part]
    candidate = "".join(part[0] for part in parts[:3]) if len(parts) > 1 else token[:3]
    if not candidate or not candidate[0].isalpha():
        candidate = f"s{index}"
    return candidate


def _build_from_clause(sources: list[dict[str, str]], joins: list[dict[str, str]]) -> str:
    first = sources[0]
    clause = f'{quote_identifier(first["table"])} AS {quote_identifier(first["alias"])}'
    if len(sources) == 1:
        return clause

    joined_aliases = {first["alias"]}
    remaining = {item["alias"]: item for item in sources[1:]}

    while remaining:
        progress = False
        for alias, item in list(remaining.items()):
            join = _find_join_for_alias(alias, joins, joined_aliases)
            if join is None:
                continue
            clause += (
                f' {join["type"].upper()} JOIN {quote_identifier(item["table"])} AS {quote_identifier(alias)}'
                f' ON {_compile_join_side(join["left"])} = {_compile_join_side(join["right"])}'
            )
            joined_aliases.add(alias)
            remaining.pop(alias)
            progress = True
        if not progress:
            unresolved = ", ".join(sorted(remaining))
            raise SemanticDefinitionError(f"sources 无法通过 joins 连通: {unresolved}")

    return clause


def _find_join_for_alias(alias: str, joins: list[dict[str, str]], joined_aliases: set[str]) -> dict[str, str] | None:
    for join in joins:
        left_alias = join["left"].split(".", 1)[0]
        right_alias = join["right"].split(".", 1)[0]
        if left_alias == alias and right_alias in joined_aliases:
            return {"left": join["left"], "right": join["right"], "type": join["type"]}
        if right_alias == alias and left_alias in joined_aliases:
            return {"left": join["left"], "right": join["right"], "type": join["type"]}
    return None


def _compile_join_side(value: str) -> str:
    alias, column = value.split(".", 1)
    return f"{quote_identifier(alias)}.{quote_identifier(column)}"


def _resolve_dimension(
    name: str,
    dimension_map: dict[str, dict[str, Any]],
    default_alias: str,
) -> tuple[str, str]:
    spec = dimension_map.get(name)
    if spec is None:
        return _resolve_raw_field(name, default_alias), name

    alias = str(spec.get("alias") or spec.get("name") or name)
    expression = _resolve_expression(spec, default_alias)
    return expression, alias


def _resolve_metric(
    name: str,
    metric_map: dict[str, dict[str, Any]],
    default_alias: str,
) -> tuple[str, str]:
    spec = metric_map.get(name)
    if spec is None:
        raise SemanticDefinitionError(f"未知 metric: {name}")

    alias = str(spec.get("alias") or spec.get("name") or name)
    expression = spec.get("expr") or spec.get("expression")
    if expression:
        return f"({expression})", alias

    column = str(spec.get("column") or "").strip()
    if not column:
        raise SemanticDefinitionError(f"metric {name} 缺少合法 column 或 expr")

    agg = str(spec.get("agg", "")).lower().strip()
    qualified_column = _qualify_column(column, str(spec.get("source") or default_alias))
    if agg:
        return f"{agg.upper()}({qualified_column})", alias
    return qualified_column, alias


def _resolve_expression(spec: dict[str, Any], default_alias: str) -> str:
    expression = spec.get("expr") or spec.get("expression")
    if expression:
        return str(expression)

    column = str(spec.get("column") or spec.get("name") or "").strip()
    if not column:
        raise SemanticDefinitionError(f"字段定义缺少 column/expr: {spec}")
    return _qualify_column(column, str(spec.get("source") or default_alias))


def _resolve_raw_field(name: str, default_alias: str) -> str:
    if not VALID_QUALIFIED_IDENTIFIER.fullmatch(name):
        raise SemanticDefinitionError(f"未知字段: {name}")
    if "." in name:
        alias, column = name.split(".", 1)
        return f"{quote_identifier(alias)}.{quote_identifier(column)}"
    return f"{quote_identifier(default_alias)}.{quote_identifier(name)}"


def _qualify_column(column: str, source_alias: str) -> str:
    if "." in column:
        alias, field = column.split(".", 1)
        return f"{quote_identifier(alias)}.{quote_identifier(field)}"
    return f"{quote_identifier(source_alias)}.{quote_identifier(column)}"


def _resolve_order_field(
    name: str,
    dimension_map: dict[str, dict[str, Any]],
    metric_map: dict[str, dict[str, Any]],
    default_alias: str,
) -> str:
    if name in metric_map:
        alias = metric_map[name].get("alias") or metric_map[name].get("name") or name
        return quote_identifier(str(alias))
    if name in dimension_map:
        alias = dimension_map[name].get("alias") or dimension_map[name].get("name") or name
        return quote_identifier(str(alias))
    return _resolve_raw_field(name, default_alias)


def _compile_filter_clause(
    field: str,
    op: str,
    value: Any,
    dimension_map: dict[str, dict[str, Any]],
    metric_map: dict[str, dict[str, Any]],
    default_alias: str,
    param_prefix: str,
) -> tuple[str, dict[str, Any], bool]:
    if field in metric_map:
        expr, _alias = _resolve_metric(field, metric_map, default_alias)
        return _compile_predicate(expr, op, value, param_prefix, having=True)

    if field in dimension_map:
        expr, _alias = _resolve_dimension(field, dimension_map, default_alias)
        return _compile_predicate(expr, op, value, param_prefix, having=False)

    expr = _resolve_raw_field(field, default_alias)
    return _compile_predicate(expr, op, value, param_prefix, having=False)


def _compile_predicate(
    expr: str,
    op: str,
    value: Any,
    param_prefix: str,
    having: bool,
) -> tuple[str, dict[str, Any], bool]:
    params: dict[str, Any] = {}
    op = OP_ALIASES.get(op.lower().strip(), op.lower().strip())

    if op in {"is_null", "not_null"}:
        return (f"{expr} IS {'NOT ' if op == 'not_null' else ''}NULL", params, having)

    if op == "between":
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise SemanticDefinitionError("between 需要两个值")
        params[f"{param_prefix}_start"] = value[0]
        params[f"{param_prefix}_end"] = value[1]
        return (f"{expr} BETWEEN :{param_prefix}_start AND :{param_prefix}_end", params, having)

    if op in {"in", "not_in"}:
        if not isinstance(value, (list, tuple)) or not value:
            raise SemanticDefinitionError(f"{op} 需要非空列表")
        placeholder_names = []
        for idx, item in enumerate(value):
            pname = f"{param_prefix}_{idx}"
            params[pname] = item
            placeholder_names.append(f":{pname}")
        clause = f"{expr} {'NOT ' if op == 'not_in' else ''}IN ({', '.join(placeholder_names)})"
        return (clause, params, having)

    param_name = f"{param_prefix}_value"
    params[param_name] = value

    if op == "eq":
        return (f"{expr} = :{param_name}", params, having)
    if op == "ne":
        return (f"{expr} <> :{param_name}", params, having)
    if op == "gt":
        return (f"{expr} > :{param_name}", params, having)
    if op == "gte":
        return (f"{expr} >= :{param_name}", params, having)
    if op == "lt":
        return (f"{expr} < :{param_name}", params, having)
    if op == "lte":
        return (f"{expr} <= :{param_name}", params, having)
    if op == "like":
        return (f"{expr} LIKE :{param_name}", params, having)
    if op == "ilike":
        return (f"{expr} ILIKE :{param_name}", params, having)
    if op == "contains":
        params[param_name] = f"%{value}%"
        return (f"{expr} ILIKE :{param_name}", params, having)
    if op == "startswith":
        params[param_name] = f"{value}%"
        return (f"{expr} ILIKE :{param_name}", params, having)
    if op == "endswith":
        params[param_name] = f"%{value}"
        return (f"{expr} ILIKE :{param_name}", params, having)

    raise SemanticDefinitionError(f"不支持的过滤操作: {op}")
