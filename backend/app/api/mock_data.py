"""Mock数据管理 API"""
from sqlalchemy import text
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.mock.generator import generate_all_mock_data
from app.mock.semantic_seed import seed_semantic_yaml_definitions

router = APIRouter()
settings = get_settings()


@router.post("/generate")
async def generate_mock(db: AsyncSession = Depends(get_db)):
    """生成/重置Mock数据"""
    # 清空所有业务表
    tables = [
        "sys_conversation_message", "sys_conversation",
        "recon_cross_check_result", "recon_adjustment_tracking",
        "recon_tax_burden_analysis", "recon_revenue_comparison",
        "acct_depreciation_schedule", "acct_tax_payable_detail",
        "acct_balance_sheet", "acct_income_statement",
        "acct_general_ledger", "acct_journal_line", "acct_journal_entry",
        "acct_chart_of_accounts",
        "tax_risk_indicators", "tax_other_taxes",
        "tax_cit_adjustment_items", "tax_cit_annual", "tax_cit_quarterly",
        "tax_vat_invoice_summary", "tax_vat_declaration",
        "enterprise_contact", "enterprise_bank_account", "enterprise_info",
        "sys_semantic_model", "sys_user_preference",
        "dict_industry", "dict_tax_type",
    ]
    for table in tables:
        quoted_table = f'"{table}"'
        try:
            if settings.is_sqlite:
                await db.execute(text(f"DELETE FROM {quoted_table}"))
            else:
                await db.execute(text(f"TRUNCATE TABLE {quoted_table} CASCADE"))
        except Exception:
            pass

    if settings.is_sqlite:
        try:
            await db.execute(text("DELETE FROM sqlite_sequence"))
        except Exception:
            pass
    await db.commit()

    await generate_all_mock_data(db)
    return {"status": "success", "message": "Mock数据生成完毕"}
