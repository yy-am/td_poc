"""对账分析数据模型 — 4张表"""
from sqlalchemy import String, Integer, Numeric, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class ReconRevenueComparison(Base):
    """收入对比表"""
    __tablename__ = "recon_revenue_comparison"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    taxpayer_id: Mapped[str] = mapped_column(String(20), ForeignKey("enterprise_info.taxpayer_id"), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False, comment="期间")
    vat_declared_revenue: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="增值税申报收入")
    cit_declared_revenue: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="所得税申报收入")
    acct_book_revenue: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="会计账面收入")
    vat_vs_acct_diff: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="增值税与账务差异")
    cit_vs_acct_diff: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="所得税与账务差异")
    vat_vs_cit_diff: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="增值税与所得税差异")
    diff_explanation: Mapped[str] = mapped_column(Text, nullable=True, comment="差异原因说明")


class ReconTaxBurdenAnalysis(Base):
    """税负分析表"""
    __tablename__ = "recon_tax_burden_analysis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    taxpayer_id: Mapped[str] = mapped_column(String(20), ForeignKey("enterprise_info.taxpayer_id"), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False, comment="期间")
    industry_code: Mapped[str] = mapped_column(String(10), nullable=False, comment="行业代码")
    vat_burden_rate: Mapped[float] = mapped_column(Numeric(10, 6), default=0, comment="增值税税负率")
    cit_effective_rate: Mapped[float] = mapped_column(Numeric(10, 6), default=0, comment="所得税有效税率")
    total_tax_burden: Mapped[float] = mapped_column(Numeric(10, 6), default=0, comment="综合税负率")
    industry_avg_vat_burden: Mapped[float] = mapped_column(Numeric(10, 6), default=0, comment="行业平均增值税税负率")
    industry_avg_cit_rate: Mapped[float] = mapped_column(Numeric(10, 6), default=0, comment="行业平均所得税税率")
    deviation_vat: Mapped[float] = mapped_column(Numeric(10, 6), default=0, comment="增值税税负偏离度")
    deviation_cit: Mapped[float] = mapped_column(Numeric(10, 6), default=0, comment="所得税税负偏离度")


class ReconAdjustmentTracking(Base):
    """调整追踪表"""
    __tablename__ = "recon_adjustment_tracking"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    taxpayer_id: Mapped[str] = mapped_column(String(20), ForeignKey("enterprise_info.taxpayer_id"), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False, comment="期间")
    adjustment_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="差异类型: 永久性/暂时性")
    source_category: Mapped[str] = mapped_column(String(50), nullable=False, comment="差异来源: 折旧/收入确认时间/坏账/视同销售/罚款等")
    accounting_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="会计金额")
    tax_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="税法金额")
    difference: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="差异金额")
    deferred_tax_impact: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="递延所得税影响")


class ReconCrossCheckResult(Base):
    """交叉核验结果"""
    __tablename__ = "recon_cross_check_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    taxpayer_id: Mapped[str] = mapped_column(String(20), ForeignKey("enterprise_info.taxpayer_id"), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False, comment="期间")
    check_rule_code: Mapped[str] = mapped_column(String(20), nullable=False, comment="核验规则编码")
    check_rule_name: Mapped[str] = mapped_column(String(200), nullable=False, comment="核验规则名称")
    expected_value: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="预期值")
    actual_value: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="实际值")
    difference: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="差异")
    status: Mapped[str] = mapped_column(String(10), nullable=False, comment="结果: 通过/预警/异常")
    recommendation: Mapped[str] = mapped_column(Text, nullable=True, comment="建议")
