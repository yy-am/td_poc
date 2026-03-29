"""Seed semantic YAML definitions for test data."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.semantic import SysSemanticModel


SEMANTIC_YAML_MAP: dict[str, str] = {
    "vat_declaration": """
name: vat_declaration
label: 增值税申报数据
table: tax_vat_declaration
description: 增值税申报明细数据，可用于按期间、纳税人、销售额和应纳税额分析。
dimensions:
  - name: taxpayer_id
    label: 纳税人识别号
    column: taxpayer_id
  - name: tax_period
    label: 申报期间
    column: tax_period
metrics:
  - name: total_sales_amount
    label: 销售额
    column: total_sales_amount
    agg: sum
  - name: output_tax_amount
    label: 销项税额
    column: output_tax_amount
    agg: sum
  - name: input_tax_amount
    label: 进项税额
    column: input_tax_amount
    agg: sum
  - name: tax_payable
    label: 应纳税额
    column: tax_payable
    agg: sum
default_limit: 100
""".strip(),
    "reconciliation_dashboard": """
name: reconciliation_dashboard
label: 对账分析看板
table: recon_revenue_comparison
description: 收入对账与税负分析数据，可用于查看税务口径与账务口径的差异。
dimensions:
  - name: taxpayer_id
    label: 纳税人识别号
    column: taxpayer_id
  - name: period
    label: 期间
    column: period
metrics:
  - name: vat_declared_revenue
    label: 增值税申报收入
    column: vat_declared_revenue
    agg: sum
  - name: cit_declared_revenue
    label: 所得税申报收入
    column: cit_declared_revenue
    agg: sum
  - name: acct_book_revenue
    label: 账务收入
    column: acct_book_revenue
    agg: sum
  - name: vat_vs_acct_diff
    label: 增值税与账务差异
    column: vat_vs_acct_diff
    agg: sum
  - name: cit_vs_acct_diff
    label: 所得税与账务差异
    column: cit_vs_acct_diff
    agg: sum
default_limit: 100
""".strip(),
    "enterprise_tax_overview": """
name: enterprise_tax_overview
label: 企业税务总览
table: enterprise_info
description: 企业基础信息总览，可用于按行业和主管税务机关维度分析企业分布。
dimensions:
  - name: taxpayer_id
    label: 纳税人识别号
    column: taxpayer_id
  - name: industry_code
    label: 行业代码
    column: industry_code
  - name: tax_authority
    label: 主管税务机关
    column: tax_authority
metrics:
  - name: enterprise_count
    label: 企业数量
    expression: COUNT(*)
default_limit: 100
""".strip(),
}


async def seed_semantic_yaml_definitions(session: AsyncSession) -> None:
    result = await session.execute(select(SysSemanticModel))
    models = result.scalars().all()
    for model in models:
        yaml_definition = SEMANTIC_YAML_MAP.get(model.name)
        if yaml_definition:
            model.yaml_definition = yaml_definition
    await session.flush()
