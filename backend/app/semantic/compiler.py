"""Minimal semantic query compiler."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import re

import yaml

VALID_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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
    warnings: list[str]


def quote_identifier(identifier: str) -> str:
    if not VALID_IDENTIFIER.fullmatch(identifier):
        raise SemanticDefinitionError(f"非法标识符: {identifier}")
    return f'"{identifier}"'


def load_semantic_definition(yaml_definition: str | None) -> dict[str, Any]:
    if not yaml_definition or not yaml_definition.strip():
        raise SemanticDefinitionError("语义模型尚未配置 yaml_definition")

    loaded = yaml.safe_load(yaml_definition)
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
    normalized["dimensions"] = _normalize_items(normalized.get("dimensions", []))
    normalized["metrics"] = _normalize_items(normalized.get("metrics", []))
    normalized["default_limit"] = _safe_int(normalized.get("default_limit"), 100)
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

    source_table = definition.get("table")
    if not source_table:
        raise SemanticDefinitionError("语义模型缺少 table")
    if not VALID_IDENTIFIER.fullmatch(source_table):
        raise SemanticDefinitionError(f"非法 table 名称: {source_table}")

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
        column_expr, alias = _resolve_dimension(dimension_name, dimension_map)
        select_clauses.append(f"{column_expr} AS {quote_identifier(alias)}")
        if column_expr not in group_by_clauses:
            group_by_clauses.append(column_expr)

    for metric_name in selected_metrics:
        expr, alias = _resolve_metric(metric_name, metric_map)
        select_clauses.append(f"{expr} AS {quote_identifier(alias)}")

    for idx, item in enumerate(filters):
        field = item.get("field")
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
            param_prefix=f"f{idx}",
        )
        params.update(clause_params)
        if use_having:
            having_clauses.append(clause)
        else:
            where_clauses.append(clause)

    for item in order:
        field = item.get("field")
        if not field:
            continue
        direction = str(item.get("direction", "asc")).lower()
        if direction not in {"asc", "desc"}:
            direction = "asc"
        order_expr = _resolve_order_field(field, dimension_map, metric_map)
        order_clauses.append(f"{order_expr} {direction.upper()}")

    if not limit or limit < 1:
        limit = int(definition.get("default_limit") or 100)
    limit = min(int(limit), 5000)

    if selected_metrics:
        sql = f"SELECT {', '.join(select_clauses)} FROM {quote_identifier(source_table)} AS t"
        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)
        if group_by_clauses:
            sql += " GROUP BY " + ", ".join(group_by_clauses)
        if having_clauses:
            sql += " HAVING " + " AND ".join(having_clauses)
    else:
        sql = f"SELECT DISTINCT {', '.join(select_clauses)} FROM {quote_identifier(source_table)} AS t"
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


def _normalize_items(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, str):
            normalized.append({"name": item, "column": item, "label": item})
        elif isinstance(item, dict) and item.get("name"):
            normalized.append(dict(item))
    return normalized


def _safe_int(value: Any, default: int) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _resolve_dimension(name: str, dimension_map: dict[str, dict[str, Any]]) -> tuple[str, str]:
    spec = dimension_map.get(name)
    if spec is None:
        if not VALID_IDENTIFIER.fullmatch(name):
            raise SemanticDefinitionError(f"未知 dimension: {name}")
        return f"t.{quote_identifier(name)}", name

    column = spec.get("column") or name
    if not VALID_IDENTIFIER.fullmatch(column):
        raise SemanticDefinitionError(f"非法 dimension column: {column}")
    alias = spec.get("alias") or spec.get("name") or name
    return f"t.{quote_identifier(column)}", alias


def _resolve_metric(name: str, metric_map: dict[str, dict[str, Any]]) -> tuple[str, str]:
    spec = metric_map.get(name)
    if spec is None:
        raise SemanticDefinitionError(f"未知 metric: {name}")

    alias = spec.get("alias") or spec.get("name") or name
    expression = spec.get("expression")
    if expression:
        return f"({expression})", alias

    column = spec.get("column")
    if not column or not VALID_IDENTIFIER.fullmatch(column):
        raise SemanticDefinitionError(f"metric {name} 缺少合法 column 或 expression")

    agg = str(spec.get("agg", "")).lower().strip()
    if agg:
        return f"{agg.upper()}(t.{quote_identifier(column)})", alias
    return f"t.{quote_identifier(column)}", alias


def _resolve_order_field(name: str, dimension_map: dict[str, dict[str, Any]], metric_map: dict[str, dict[str, Any]]) -> str:
    if name in metric_map:
        alias = metric_map[name].get("alias") or metric_map[name].get("name") or name
        return quote_identifier(alias)
    if name in dimension_map:
        alias = dimension_map[name].get("alias") or dimension_map[name].get("name") or name
        return quote_identifier(alias)
    if not VALID_IDENTIFIER.fullmatch(name):
        raise SemanticDefinitionError(f"非法 order 字段: {name}")
    return f"t.{quote_identifier(name)}"


def _compile_filter_clause(
    field: str,
    op: str,
    value: Any,
    dimension_map: dict[str, dict[str, Any]],
    metric_map: dict[str, dict[str, Any]],
    param_prefix: str,
) -> tuple[str, dict[str, Any], bool]:
    if field in metric_map:
        expr, _alias = _resolve_metric(field, metric_map)
        return _compile_predicate(expr, op, value, param_prefix, having=True)

    if field in dimension_map:
        expr, _alias = _resolve_dimension(field, dimension_map)
        return _compile_predicate(expr, op, value, param_prefix, having=False)

    if not VALID_IDENTIFIER.fullmatch(field):
        raise SemanticDefinitionError(f"非法 filter 字段: {field}")

    expr = f"t.{quote_identifier(field)}"
    return _compile_predicate(expr, op, value, param_prefix, having=False)


def _compile_predicate(expr: str, op: str, value: Any, param_prefix: str, having: bool) -> tuple[str, dict[str, Any], bool]:
    params: dict[str, Any] = {}
    op = op.lower().strip()

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
