"""TDA-MQL compilation and execution helpers."""

from __future__ import annotations

import calendar
import re
from datetime import date as calendar_date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.semantic import SysSemanticModel
from app.schemas.semantic import TdaMqlRequest

from .catalog import extract_semantic_metadata
from .compiler_v2 import SemanticDefinitionError
from .service_v3 import semantic_query

QUARTER_TOKEN = re.compile(r"^(?P<year>\d{4})Q(?P<quarter>[1-4])$")
MONTH_RANGE_TOKEN = re.compile(r"^(?P<start>\d{4}-\d{2})\.\.(?P<end>\d{4}-\d{2})$")
MONTH_TOKEN = re.compile(r"^\d{4}-\d{2}$")
DATE_TOKEN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
YEAR_TOKEN = re.compile(r"^\d{4}$")
RELATIVE_MONTH_TOKEN = re.compile(r"^last_\d+_months$")

COMPARE_MODE_ALIASES = {
    "yoy": "yoy",
    "year_over_year": "yoy",
    "同比": "yoy",
    "mom": "mom",
    "month_over_month": "mom",
    "环比": "mom",
    "qoq": "qoq",
    "quarter_over_quarter": "qoq",
    "季度环比": "qoq",
    "prev_period": "previous_period",
    "previous_period": "previous_period",
    "上期": "previous_period",
}


async def compile_tda_mql_request(
    payload: TdaMqlRequest,
    db: AsyncSession,
) -> dict[str, Any]:
    model = await _load_semantic_model(db, payload.model_name)
    metadata = extract_semantic_metadata(
        name=model.name,
        label=model.label,
        description=model.description or "",
        source_table=model.source_table,
        model_type=model.model_type,
        yaml_definition=model.yaml_definition,
        status=model.status,
    )

    unsupported_features = _detect_unsupported_features(payload)
    semantic_query_payload = _build_semantic_query_payload(payload, metadata)
    metric_aliases = {
        item.metric: item.alias
        for item in payload.select
        if item.alias and item.alias != item.metric
    }
    compare_context = _build_compare_context(payload, metadata) if payload.time_context and payload.time_context.compare else {}

    return {
        "model_name": payload.model_name,
        "semantic_query": semantic_query_payload,
        "metric_aliases": metric_aliases,
        "unsupported_features": unsupported_features,
        "relationship_graph": metadata.get("relationship_graph") or [],
        "metric_lineage": metadata.get("metric_lineage") or [],
        "detail_fields": metadata.get("detail_fields") or [],
        "query_hints": metadata.get("query_hints") or {},
        "time": metadata.get("time") or {},
        "analysis_mode": payload.analysis_mode.model_dump() if payload.analysis_mode else {},
        "drilldown": payload.drilldown.model_dump() if payload.drilldown else {},
        "compare_context": compare_context,
    }


async def execute_tda_mql_request(
    payload: TdaMqlRequest,
    db: AsyncSession,
) -> dict[str, Any]:
    compiled = await compile_tda_mql_request(payload, db)
    unsupported = compiled.get("unsupported_features") or []
    if unsupported:
        raise SemanticDefinitionError("Phase 1 暂不支持以下 TDA-MQL 能力: " + ", ".join(unsupported))

    semantic_payload = compiled["semantic_query"]
    result = await _execute_semantic_payload(semantic_payload, db)

    compare_context = dict(compiled.get("compare_context") or {})
    if compare_context:
        compare_payload = _build_compare_semantic_payload(semantic_payload, compare_context)
        compare_result = await _execute_semantic_payload(compare_payload, db)
        result = _merge_compare_result(
            result=result,
            compare_result=compare_result,
            metrics=semantic_payload.get("metrics") or [],
            dimensions=semantic_payload.get("dimensions") or [],
            compare_context=compare_context,
            time_meta=compiled.get("time") or {},
        )

    result["tda_mql"] = compiled
    return result


async def _execute_semantic_payload(
    semantic_payload: dict[str, Any],
    db: AsyncSession,
) -> dict[str, Any]:
    return await semantic_query(
        model_name=semantic_payload.get("model_name"),
        dimensions=semantic_payload.get("dimensions"),
        metrics=semantic_payload.get("metrics"),
        filters=semantic_payload.get("filters"),
        order=semantic_payload.get("order"),
        entity_filters=semantic_payload.get("entity_filters"),
        resolved_filters=semantic_payload.get("resolved_filters"),
        grain=semantic_payload.get("grain"),
        limit=semantic_payload.get("limit", 100),
        db=db,
    )


async def _load_semantic_model(db: AsyncSession, model_name: str) -> SysSemanticModel:
    result = await db.execute(select(SysSemanticModel).where(SysSemanticModel.name == model_name))
    model = result.scalar_one_or_none()
    if model is None:
        raise SemanticDefinitionError(f"语义模型不存在: {model_name}")
    if model.status != "active":
        raise SemanticDefinitionError(f"语义模型未激活: {model_name}")
    return model


def _detect_unsupported_features(payload: TdaMqlRequest) -> list[str]:
    unsupported: list[str] = []

    if payload.analysis_mode and payload.analysis_mode.attribution:
        unsupported.append("analysis_mode.attribution")

    if payload.analysis_mode and payload.analysis_mode.type in {"attribution", "diagnosis"}:
        unsupported.append(f"analysis_mode.type={payload.analysis_mode.type}")

    if payload.time_context and payload.time_context.range:
        token = payload.time_context.range.strip()
        if RELATIVE_MONTH_TOKEN.fullmatch(token):
            unsupported.append(f"time_context.range={token}")

    if payload.time_context and payload.time_context.compare and payload.drilldown and payload.drilldown.enabled:
        unsupported.append("compare_with_drilldown")

    return unsupported


def _build_semantic_query_payload(
    payload: TdaMqlRequest,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    if payload.drilldown and payload.drilldown.enabled:
        detail_fields = list(payload.drilldown.detail_fields or _detail_field_names(metadata))
        if not detail_fields:
            raise SemanticDefinitionError(
                f"语义模型 {payload.model_name} 未声明 detail_fields，无法执行 drilldown"
            )
        dimensions = detail_fields
        metrics: list[str] = []
        limit = payload.drilldown.limit or payload.limit
    else:
        metrics = [item.metric for item in payload.select]
        dimensions = list(payload.group_by)
        limit = payload.limit

    if not metrics and not dimensions:
        raise SemanticDefinitionError("TDA-MQL 至少需要 select 或 group_by，或者开启 drilldown")

    filters = [_normalize_filter(item) for item in payload.filters]
    filters.extend(_build_time_filters(payload, metadata))

    return {
        "model_name": payload.model_name,
        "dimensions": dimensions,
        "metrics": metrics,
        "filters": filters,
        "order": [item.model_dump() for item in payload.order],
        "entity_filters": payload.entity_filters,
        "resolved_filters": payload.resolved_filters,
        "grain": payload.time_context.grain if payload.time_context else None,
        "limit": limit,
    }


def _normalize_filter(item: Any) -> dict[str, Any]:
    payload = item.model_dump()
    if payload.get("values") and payload.get("value") is None:
        payload["value"] = payload["values"]
    payload.pop("values", None)
    return payload


def _resolve_time_context_metadata(
    payload: TdaMqlRequest,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    time_meta = metadata.get("time") or {}
    role_name = str((payload.time_context.role if payload.time_context else "") or "").strip()
    roles = time_meta.get("roles") if isinstance(time_meta.get("roles"), dict) else {}
    default_role = str(time_meta.get("default_role") or "").strip()
    selected_role = role_name or default_role
    role_meta = roles.get(selected_role) if selected_role else None

    if role_name and roles and not isinstance(role_meta, dict):
        supported_roles = ", ".join(sorted(str(item) for item in roles.keys()))
        raise SemanticDefinitionError(
            f"语义模型 {payload.model_name} 不支持 time_context.role={role_name}"
            + (f"，可选角色: {supported_roles}" if supported_roles else "")
        )

    field = str((role_meta or {}).get("field") or time_meta.get("field") or "").strip()
    if not field:
        raise SemanticDefinitionError(f"语义模型 {payload.model_name} 未声明 time.field")

    grain = str((role_meta or {}).get("grain") or time_meta.get("grain") or "").strip()
    range_mode = str((role_meta or {}).get("range_mode") or time_meta.get("range_mode") or "").strip().lower()
    if not range_mode:
        range_mode = "date" if field.endswith("_date") else "period"

    return {
        "field": field,
        "grain": grain,
        "role": selected_role,
        "range_mode": range_mode,
    }


def _build_time_filters(payload: TdaMqlRequest, metadata: dict[str, Any]) -> list[dict[str, Any]]:
    if payload.time_context is None or not payload.time_context.range:
        return []

    time_spec = _resolve_time_context_metadata(payload, metadata)
    token = payload.time_context.range.strip()
    return _build_time_filters_from_token(
        field=time_spec["field"],
        token=token,
        grain=time_spec.get("grain") or "",
        range_mode=time_spec.get("range_mode") or "period",
        model_name=payload.model_name,
    )


def _build_compare_context(
    payload: TdaMqlRequest,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    time_context = payload.time_context
    if time_context is None or not time_context.compare:
        return {}
    if not time_context.range:
        raise SemanticDefinitionError("?? compare ????? time_context.range")
    if not payload.select:
        raise SemanticDefinitionError("?? compare ?????????????")
    if payload.drilldown and payload.drilldown.enabled:
        raise SemanticDefinitionError("Phase 1 ???? compare ? drilldown ????")

    mode = _normalize_compare_mode(time_context.compare)
    target_range = time_context.range.strip()
    baseline_range = _shift_compare_range(target_range, mode)
    offset = _build_alignment_offset(target_range, baseline_range)
    time_spec = _resolve_time_context_metadata(payload, metadata)

    return {
        "enabled": True,
        "mode": mode,
        "label": time_context.compare,
        "target_range": target_range,
        "baseline_range": baseline_range,
        "time_field": time_spec.get("field") or "",
        "time_grain": time_spec.get("grain") or "",
        "range_mode": time_spec.get("range_mode") or "period",
        "alignment_offset": offset,
    }


def _normalize_compare_mode(raw_value: str) -> str:
    key = str(raw_value or "").strip().lower()
    mode = COMPARE_MODE_ALIASES.get(key)
    if not mode:
        raise SemanticDefinitionError(f"????? time_context.compare: {raw_value}")
    return mode


def _build_compare_semantic_payload(
    semantic_payload: dict[str, Any],
    compare_context: dict[str, Any],
) -> dict[str, Any]:
    filters = []
    time_field = str(compare_context.get("time_field") or "").strip()
    baseline_range = str(compare_context.get("baseline_range") or "").strip()
    time_grain = str(compare_context.get("time_grain") or "").strip()
    range_mode = str(compare_context.get("range_mode") or "period").strip().lower()

    for item in semantic_payload.get("filters") or []:
        if time_field and item.get("field") == time_field:
            continue
        filters.append(dict(item))

    if time_field and baseline_range:
        filters.extend(
            _build_time_filters_from_token(
                field=time_field,
                token=baseline_range,
                grain=time_grain,
                range_mode=range_mode,
            )
        )

    compare_payload = dict(semantic_payload)
    compare_payload["filters"] = filters
    return compare_payload


def _build_time_filters_from_token(
    field: str,
    token: str,
    grain: str = "",
    range_mode: str = "period",
    model_name: str = "",
) -> list[dict[str, Any]]:
    range_mode = str(range_mode or "period").strip().lower()
    if range_mode == "date":
        return _build_date_filters_from_token(field, token)

    quarter_match = QUARTER_TOKEN.fullmatch(token)
    if quarter_match:
        if grain == "year":
            raise SemanticDefinitionError(f"???? {model_name or field} ????????????????????")
        year = quarter_match.group("year")
        quarter = int(quarter_match.group("quarter"))
        start_month = (quarter - 1) * 3 + 1
        months = [f"{year}-{month:02d}" for month in range(start_month, start_month + 3)]
        return [{"field": field, "op": "in", "value": months}]

    month_range_match = MONTH_RANGE_TOKEN.fullmatch(token)
    if month_range_match:
        return [{"field": field, "op": "between", "value": [month_range_match.group("start"), month_range_match.group("end")]}]

    if MONTH_TOKEN.fullmatch(token):
        return [{"field": field, "op": "eq", "value": token}]

    if YEAR_TOKEN.fullmatch(token):
        if grain == "year" or field.endswith("year"):
            return [{"field": field, "op": "eq", "value": int(token)}]
        return [{"field": field, "op": "between", "value": [f"{token}-01", f"{token}-12"]}]

    raise SemanticDefinitionError(f"?????????: {token}")


def _build_date_filters_from_token(field: str, token: str) -> list[dict[str, Any]]:
    if DATE_TOKEN.fullmatch(token):
        return [{"field": field, "op": "eq", "value": token}]

    quarter_match = QUARTER_TOKEN.fullmatch(token)
    if quarter_match:
        year = int(quarter_match.group("year"))
        quarter = int(quarter_match.group("quarter"))
        start_month = (quarter - 1) * 3 + 1
        start_date = calendar_date(year, start_month, 1)
        end_date = calendar_date(year, start_month + 2, calendar.monthrange(year, start_month + 2)[1])
        return [{"field": field, "op": "between", "value": [start_date.isoformat(), end_date.isoformat()]}]

    month_range_match = MONTH_RANGE_TOKEN.fullmatch(token)
    if month_range_match:
        start_date = _month_start_date(month_range_match.group("start"))
        end_date = _month_end_date(month_range_match.group("end"))
        return [{"field": field, "op": "between", "value": [start_date.isoformat(), end_date.isoformat()]}]

    if MONTH_TOKEN.fullmatch(token):
        start_date = _month_start_date(token)
        end_date = _month_end_date(token)
        return [{"field": field, "op": "between", "value": [start_date.isoformat(), end_date.isoformat()]}]

    if YEAR_TOKEN.fullmatch(token):
        start_date = calendar_date(int(token), 1, 1)
        end_date = calendar_date(int(token), 12, 31)
        return [{"field": field, "op": "between", "value": [start_date.isoformat(), end_date.isoformat()]}]

    raise SemanticDefinitionError(f"???????????: {token}")


def _month_start_date(token: str) -> calendar_date:
    year, month = token.split("-")
    return calendar_date(int(year), int(month), 1)


def _month_end_date(token: str) -> calendar_date:
    year, month = token.split("-")
    end_day = calendar.monthrange(int(year), int(month))[1]
    return calendar_date(int(year), int(month), end_day)


def _shift_compare_range(token: str, mode: str) -> str:
    if YEAR_TOKEN.fullmatch(token):
        year = int(token)
        if mode in {"yoy", "previous_period"}:
            return f"{year - 1}"
        raise SemanticDefinitionError(f"范围 {token} 不支持 compare 模式 {mode}")

    quarter_match = QUARTER_TOKEN.fullmatch(token)
    if quarter_match:
        year = int(quarter_match.group("year"))
        quarter = int(quarter_match.group("quarter"))
        if mode == "yoy":
            return f"{year - 1}Q{quarter}"
        if mode in {"qoq", "previous_period", "mom"}:
            total_quarters = year * 4 + (quarter - 1)
            shifted_total = total_quarters - 1
            shifted_year = shifted_total // 4
            shifted_quarter = shifted_total % 4 + 1
            return f"{shifted_year}Q{shifted_quarter}"
        raise SemanticDefinitionError(f"范围 {token} 不支持 compare 模式 {mode}")

    if MONTH_TOKEN.fullmatch(token):
        total_months = _parse_month_token(token)
        if mode == "yoy":
            return _format_month_token(total_months - 12)
        if mode == "qoq":
            return _format_month_token(total_months - 3)
        if mode in {"mom", "previous_period"}:
            return _format_month_token(total_months - 1)
        raise SemanticDefinitionError(f"范围 {token} 不支持 compare 模式 {mode}")

    month_range_match = MONTH_RANGE_TOKEN.fullmatch(token)
    if month_range_match:
        start_total = _parse_month_token(month_range_match.group("start"))
        end_total = _parse_month_token(month_range_match.group("end"))
        if end_total < start_total:
            raise SemanticDefinitionError(f"时间范围非法: {token}")

        if mode == "yoy":
            offset = 12
        elif mode == "qoq":
            offset = 3
        elif mode == "mom":
            offset = 1
        elif mode == "previous_period":
            offset = end_total - start_total + 1
        else:
            raise SemanticDefinitionError(f"范围 {token} 不支持 compare 模式 {mode}")

        return f"{_format_month_token(start_total - offset)}..{_format_month_token(end_total - offset)}"

    raise SemanticDefinitionError(f"暂不支持 compare 的范围: {token}")


def _build_alignment_offset(target_range: str, baseline_range: str) -> dict[str, int]:
    if YEAR_TOKEN.fullmatch(target_range) and YEAR_TOKEN.fullmatch(baseline_range):
        return {"years": int(target_range) - int(baseline_range)}

    target_start = _parse_range_start(target_range)
    baseline_start = _parse_range_start(baseline_range)
    if target_start is None or baseline_start is None:
        return {}
    return {"months": target_start - baseline_start}


def _parse_range_start(token: str) -> int | None:
    if YEAR_TOKEN.fullmatch(token):
        return int(token) * 12
    quarter_match = QUARTER_TOKEN.fullmatch(token)
    if quarter_match:
        year = int(quarter_match.group("year"))
        quarter = int(quarter_match.group("quarter"))
        return year * 12 + (quarter - 1) * 3
    if MONTH_TOKEN.fullmatch(token):
        return _parse_month_token(token)
    range_match = MONTH_RANGE_TOKEN.fullmatch(token)
    if range_match:
        return _parse_month_token(range_match.group("start"))
    return None


def _parse_month_token(token: str) -> int:
    year, month = token.split("-")
    return int(year) * 12 + (int(month) - 1)


def _format_month_token(total_months: int) -> str:
    year = total_months // 12
    month = total_months % 12 + 1
    return f"{year:04d}-{month:02d}"


def _merge_compare_result(
    *,
    result: dict[str, Any],
    compare_result: dict[str, Any],
    metrics: list[str],
    dimensions: list[str],
    compare_context: dict[str, Any],
    time_meta: dict[str, Any],
) -> dict[str, Any]:
    rows = [dict(item) for item in (result.get("rows") or [])]
    compare_rows = [dict(item) for item in (compare_result.get("rows") or [])]
    time_field = str(compare_context.get("time_field") or time_meta.get("field") or "").strip()

    compare_map: dict[tuple[Any, ...], dict[str, Any]] = {}
    for raw_row in compare_rows:
        aligned_row = dict(raw_row)
        if time_field and time_field in aligned_row:
            aligned_row[time_field] = _shift_time_value_for_alignment(
                aligned_row[time_field],
                compare_context.get("alignment_offset") or {},
            )
        compare_map[_build_row_key(aligned_row, dimensions)] = raw_row

    extra_columns: list[str] = []
    matched_rows = 0
    for row in rows:
        compare_row = compare_map.get(_build_row_key(row, dimensions))
        if compare_row is not None:
            matched_rows += 1
        for metric in metrics:
            compare_column = f"compare_{metric}"
            delta_column = f"delta_{metric}"
            delta_rate_column = f"delta_rate_{metric}"

            compare_value = compare_row.get(metric) if compare_row else None
            delta_value = _subtract_numbers(row.get(metric), compare_value)
            delta_rate_value = _compute_delta_rate(delta_value, compare_value)

            row[compare_column] = compare_value
            row[delta_column] = delta_value
            row[delta_rate_column] = delta_rate_value

            for column_name in (compare_column, delta_column, delta_rate_column):
                if column_name not in extra_columns:
                    extra_columns.append(column_name)

    merged_columns = list(result.get("columns") or [])
    for column_name in extra_columns:
        if column_name not in merged_columns:
            merged_columns.append(column_name)

    merged_result = dict(result)
    merged_result["columns"] = merged_columns
    merged_result["rows"] = rows
    merged_result["row_count"] = len(rows)
    merged_result["compare"] = {
        "mode": compare_context.get("mode"),
        "label": compare_context.get("label"),
        "target_range": compare_context.get("target_range"),
        "baseline_range": compare_context.get("baseline_range"),
        "time_field": time_field,
        "matched_rows": matched_rows,
        "baseline_row_count": len(compare_rows),
    }
    return merged_result


def _build_row_key(row: dict[str, Any], dimensions: list[str]) -> tuple[Any, ...]:
    if not dimensions:
        return tuple()
    return tuple(row.get(field) for field in dimensions)


def _shift_time_value_for_alignment(value: Any, offset: dict[str, Any]) -> Any:
    if value is None:
        return value

    years = int(offset.get("years") or 0)
    months = int(offset.get("months") or 0)

    if isinstance(value, int) and years:
        return value + years

    raw_value = str(value).strip()
    if not raw_value:
        return value

    if YEAR_TOKEN.fullmatch(raw_value):
        shift = years or (months // 12)
        return str(int(raw_value) + shift)

    quarter_match = QUARTER_TOKEN.fullmatch(raw_value)
    if quarter_match and months:
        year = int(quarter_match.group("year"))
        quarter = int(quarter_match.group("quarter"))
        total_months = year * 12 + (quarter - 1) * 3 + months
        shifted_year = total_months // 12
        shifted_quarter = total_months % 12 // 3 + 1
        return f"{shifted_year:04d}Q{shifted_quarter}"

    if MONTH_TOKEN.fullmatch(raw_value) and months:
        return _format_month_token(_parse_month_token(raw_value) + months)

    if DATE_TOKEN.fullmatch(raw_value) and (months or years):
        year, month, day = (int(part) for part in raw_value.split("-"))
        total_months = year * 12 + (month - 1) + months + years * 12
        shifted_year = total_months // 12
        shifted_month = total_months % 12 + 1
        shifted_day = min(day, calendar.monthrange(shifted_year, shifted_month)[1])
        return f"{shifted_year:04d}-{shifted_month:02d}-{shifted_day:02d}"

    return value


def _subtract_numbers(left: Any, right: Any) -> Decimal | None:
    left_number = _to_decimal(left)
    right_number = _to_decimal(right)
    if left_number is None or right_number is None:
        return None
    return left_number - right_number


def _compute_delta_rate(delta: Any, baseline: Any) -> Decimal | None:
    delta_number = _to_decimal(delta)
    baseline_number = _to_decimal(baseline)
    if delta_number is None or baseline_number in {None, Decimal("0")}:
        return None
    return delta_number / baseline_number


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _detail_field_names(metadata: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for item in metadata.get("detail_fields") or []:
        name = str(item.get("name") or "").strip()
        if name:
            names.append(name)
    return names
