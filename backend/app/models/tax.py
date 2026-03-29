"""税务局端数据模型 — 7张表"""
from sqlalchemy import String, Integer, Numeric, Date, Float, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class TaxVatDeclaration(Base, TimestampMixin):
    """增值税申报主表"""
    __tablename__ = "tax_vat_declaration"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    taxpayer_id: Mapped[str] = mapped_column(String(20), ForeignKey("enterprise_info.taxpayer_id"), nullable=False)
    tax_period: Mapped[str] = mapped_column(String(7), nullable=False, comment="税款所属期 YYYY-MM")
    total_sales_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="销售额合计")
    taxable_sales_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="应税销售额")
    exempt_sales_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="免税销售额")
    output_tax_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="销项税额")
    input_tax_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="进项税额")
    input_tax_transferred_out: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="进项税额转出")
    tax_payable: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="应纳税额")
    declaration_date: Mapped[str] = mapped_column(Date, nullable=True, comment="申报日期")


class TaxVatInvoiceSummary(Base, TimestampMixin):
    """发票汇总表"""
    __tablename__ = "tax_vat_invoice_summary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    taxpayer_id: Mapped[str] = mapped_column(String(20), ForeignKey("enterprise_info.taxpayer_id"), nullable=False)
    tax_period: Mapped[str] = mapped_column(String(7), nullable=False, comment="税款所属期")
    invoice_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="发票类型: 专票/普票/电子票")
    invoice_count: Mapped[int] = mapped_column(Integer, default=0, comment="发票份数")
    total_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="金额合计")
    total_tax: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="税额合计")
    total_amount_with_tax: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="价税合计")


class TaxCitQuarterly(Base, TimestampMixin):
    """企业所得税季度预缴"""
    __tablename__ = "tax_cit_quarterly"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    taxpayer_id: Mapped[str] = mapped_column(String(20), ForeignKey("enterprise_info.taxpayer_id"), nullable=False)
    tax_year: Mapped[int] = mapped_column(Integer, nullable=False, comment="纳税年度")
    quarter: Mapped[int] = mapped_column(Integer, nullable=False, comment="季度 1-4")
    revenue_total: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="营业收入")
    cost_total: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="营业成本")
    profit_total: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="利润总额")
    taxable_income: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="应纳税所得额")
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 4), default=0.25, comment="税率")
    tax_payable: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="应纳税额")
    tax_prepaid: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="已预缴税额")


class TaxCitAnnual(Base, TimestampMixin):
    """企业所得税年度汇算清缴"""
    __tablename__ = "tax_cit_annual"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    taxpayer_id: Mapped[str] = mapped_column(String(20), ForeignKey("enterprise_info.taxpayer_id"), nullable=False)
    tax_year: Mapped[int] = mapped_column(Integer, nullable=False, comment="纳税年度")
    accounting_profit: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="会计利润")
    tax_adjustments_increase: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="纳税调增")
    tax_adjustments_decrease: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="纳税调减")
    taxable_income: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="应纳税所得额")
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 4), default=0.25, comment="税率")
    tax_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="应纳所得税额")
    tax_prepaid: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="已预缴税额")
    tax_refund_or_due: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="应退/补税额")


class TaxCitAdjustmentItem(Base):
    """纳税调整明细项"""
    __tablename__ = "tax_cit_adjustment_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    annual_id: Mapped[int] = mapped_column(Integer, ForeignKey("tax_cit_annual.id"), nullable=False)
    taxpayer_id: Mapped[str] = mapped_column(String(20), nullable=False)
    tax_year: Mapped[int] = mapped_column(Integer, nullable=False)
    item_code: Mapped[str] = mapped_column(String(20), nullable=False, comment="调整项目编码")
    item_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="调整项目名称")
    accounting_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="会计金额")
    tax_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="税法金额")
    adjustment_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="调整金额")
    adjustment_direction: Mapped[str] = mapped_column(String(10), nullable=False, comment="调整方向: 调增/调减")


class TaxOtherTaxes(Base, TimestampMixin):
    """其他税种申报"""
    __tablename__ = "tax_other_taxes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    taxpayer_id: Mapped[str] = mapped_column(String(20), ForeignKey("enterprise_info.taxpayer_id"), nullable=False)
    tax_period: Mapped[str] = mapped_column(String(7), nullable=False, comment="税款所属期")
    tax_type: Mapped[str] = mapped_column(String(30), nullable=False, comment="税种: 印花税/房产税/城镇土地使用税/城市维护建设税")
    tax_basis: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="计税依据")
    tax_rate: Mapped[float] = mapped_column(Numeric(10, 6), default=0, comment="税率")
    tax_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="应纳税额")


class TaxRiskIndicator(Base, TimestampMixin):
    """税务风险指标"""
    __tablename__ = "tax_risk_indicators"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    taxpayer_id: Mapped[str] = mapped_column(String(20), ForeignKey("enterprise_info.taxpayer_id"), nullable=False)
    tax_period: Mapped[str] = mapped_column(String(7), nullable=False, comment="税款所属期")
    indicator_code: Mapped[str] = mapped_column(String(20), nullable=False, comment="指标编码")
    indicator_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="指标名称")
    indicator_value: Mapped[float] = mapped_column(Numeric(18, 6), default=0, comment="指标值")
    threshold_value: Mapped[float] = mapped_column(Numeric(18, 6), default=0, comment="阈值")
    risk_level: Mapped[str] = mapped_column(String(10), nullable=False, comment="风险等级: 低/中/高")
    alert_message: Mapped[str] = mapped_column(Text, nullable=True, comment="预警信息")
