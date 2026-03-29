"""账务数据模型 — 8张表"""
from sqlalchemy import String, Integer, Numeric, Date, Boolean, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class AcctChartOfAccounts(Base):
    """会计科目表"""
    __tablename__ = "acct_chart_of_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, comment="科目编码")
    account_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="科目名称")
    account_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="科目类型: 资产/负债/权益/收入/费用")
    parent_code: Mapped[str] = mapped_column(String(20), nullable=True, comment="上级科目编码")
    level: Mapped[int] = mapped_column(Integer, default=1, comment="科目级次")
    is_leaf: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否末级科目")
    direction: Mapped[str] = mapped_column(String(5), nullable=False, comment="余额方向: 借/贷")


class AcctJournalEntry(Base, TimestampMixin):
    """凭证表头"""
    __tablename__ = "acct_journal_entry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    taxpayer_id: Mapped[str] = mapped_column(String(20), ForeignKey("enterprise_info.taxpayer_id"), nullable=False)
    entry_number: Mapped[str] = mapped_column(String(30), nullable=False, comment="凭证号")
    entry_date: Mapped[str] = mapped_column(Date, nullable=False, comment="凭证日期")
    period: Mapped[str] = mapped_column(String(7), nullable=False, comment="会计期间 YYYY-MM")
    description: Mapped[str] = mapped_column(Text, nullable=True, comment="摘要")
    created_by: Mapped[str] = mapped_column(String(50), nullable=True, comment="制单人")
    is_adjusted: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否调整凭证")


class AcctJournalLine(Base):
    """凭证明细行"""
    __tablename__ = "acct_journal_line"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(Integer, ForeignKey("acct_journal_entry.id"), nullable=False)
    account_code: Mapped[str] = mapped_column(String(20), nullable=False, comment="科目编码")
    sub_account: Mapped[str] = mapped_column(String(50), nullable=True, comment="辅助核算")
    debit_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="借方金额")
    credit_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="贷方金额")
    currency: Mapped[str] = mapped_column(String(5), default="CNY", comment="币种")
    description: Mapped[str] = mapped_column(Text, nullable=True, comment="摘要")


class AcctGeneralLedger(Base):
    """总账余额表"""
    __tablename__ = "acct_general_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    taxpayer_id: Mapped[str] = mapped_column(String(20), ForeignKey("enterprise_info.taxpayer_id"), nullable=False)
    account_code: Mapped[str] = mapped_column(String(20), nullable=False, comment="科目编码")
    period: Mapped[str] = mapped_column(String(7), nullable=False, comment="会计期间")
    opening_balance: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="期初余额")
    debit_total: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="本期借方发生额")
    credit_total: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="本期贷方发生额")
    closing_balance: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="期末余额")


class AcctIncomeStatement(Base):
    """利润表"""
    __tablename__ = "acct_income_statement"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    taxpayer_id: Mapped[str] = mapped_column(String(20), ForeignKey("enterprise_info.taxpayer_id"), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False, comment="会计期间")
    revenue_main: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="主营业务收入")
    revenue_other: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="其他业务收入")
    cost_main: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="主营业务成本")
    cost_other: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="其他业务成本")
    tax_surcharges: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="税金及附加")
    selling_expenses: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="销售费用")
    admin_expenses: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="管理费用")
    finance_expenses: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="财务费用")
    investment_income: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="投资收益")
    non_operating_income: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="营业外收入")
    non_operating_expense: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="营业外支出")
    profit_total: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="利润总额")
    income_tax_expense: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="所得税费用")
    net_profit: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="净利润")


class AcctBalanceSheet(Base):
    """资产负债表"""
    __tablename__ = "acct_balance_sheet"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    taxpayer_id: Mapped[str] = mapped_column(String(20), ForeignKey("enterprise_info.taxpayer_id"), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False, comment="会计期间")
    cash: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="货币资金")
    receivables: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="应收账款")
    inventory: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="存货")
    fixed_assets: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="固定资产")
    total_assets: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="资产合计")
    payables: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="应付账款")
    tax_payable_bs: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="应交税费")
    total_liabilities: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="负债合计")
    paid_in_capital: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="实收资本")
    retained_earnings: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="未分配利润")
    total_equity: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="所有者权益合计")


class AcctTaxPayableDetail(Base):
    """应交税费明细账"""
    __tablename__ = "acct_tax_payable_detail"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    taxpayer_id: Mapped[str] = mapped_column(String(20), ForeignKey("enterprise_info.taxpayer_id"), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False, comment="会计期间")
    tax_type: Mapped[str] = mapped_column(String(30), nullable=False, comment="税种")
    opening_balance: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="期初余额")
    accrued_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="本期计提")
    paid_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="本期缴纳")
    closing_balance: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="期末余额")


class AcctDepreciationSchedule(Base):
    """折旧台账（会计与税法差异）"""
    __tablename__ = "acct_depreciation_schedule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    taxpayer_id: Mapped[str] = mapped_column(String(20), ForeignKey("enterprise_info.taxpayer_id"), nullable=False)
    asset_id: Mapped[str] = mapped_column(String(30), nullable=False, comment="资产编号")
    asset_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="资产名称")
    category: Mapped[str] = mapped_column(String(50), nullable=False, comment="资产类别")
    original_value: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="原值")
    acct_useful_life: Mapped[int] = mapped_column(Integer, default=0, comment="会计折旧年限(月)")
    acct_method: Mapped[str] = mapped_column(String(20), default="直线法", comment="会计折旧方法")
    acct_depreciation_monthly: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="会计月折旧额")
    tax_useful_life: Mapped[int] = mapped_column(Integer, default=0, comment="税法折旧年限(月)")
    tax_method: Mapped[str] = mapped_column(String(20), default="直线法", comment="税法折旧方法")
    tax_depreciation_monthly: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="税法月折旧额")
    difference_monthly: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="月差异额")
