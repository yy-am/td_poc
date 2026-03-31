"""对账分析数据模型 — 7张表"""
from sqlalchemy import String, Integer, Numeric, Text, ForeignKey, Date, Boolean
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


class ReconExportBookRevenueLine(Base, TimestampMixin):
    """出口退税账面收入明细"""
    __tablename__ = "recon_export_book_revenue_line"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    taxpayer_id: Mapped[str] = mapped_column(String(20), ForeignKey("enterprise_info.taxpayer_id"), nullable=False)
    book_period: Mapped[str] = mapped_column(String(7), nullable=False, comment="账面期间 YYYY-MM")
    recognition_date: Mapped[str] = mapped_column(Date, nullable=False, comment="收入确认日期")
    contract_id: Mapped[str] = mapped_column(String(40), nullable=False, comment="合同号")
    contract_line_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="合同明细行号")
    customer_name: Mapped[str] = mapped_column(String(120), nullable=False, comment="客户名称")
    product_name: Mapped[str] = mapped_column(String(120), nullable=False, comment="产品名称")
    shipment_no: Mapped[str] = mapped_column(String(40), nullable=True, comment="发运单号")
    declaration_no: Mapped[str] = mapped_column(String(40), nullable=True, comment="报关单号")
    declaration_line_no: Mapped[int] = mapped_column(Integer, nullable=True, comment="报关单行号")
    sales_invoice_no: Mapped[str] = mapped_column(String(40), nullable=True, comment="销售发票号")
    voucher_no: Mapped[str] = mapped_column(String(40), nullable=True, comment="凭证号")
    currency_code: Mapped[str] = mapped_column(String(10), default="USD", comment="币种")
    fx_rate_book: Mapped[float] = mapped_column(Numeric(12, 6), default=0, comment="账面汇率")
    gross_revenue_amount_doc: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="原币毛收入")
    gross_revenue_amount_cny: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="毛收入人民币")
    freight_amount_cny: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="运费人民币")
    insurance_amount_cny: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="保费人民币")
    commission_amount_cny: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="佣金人民币")
    other_non_basis_exclusion_amount_cny: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="其他非税基剔除额")
    book_non_basis_exclusion_amount_cny: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="账面非税基剔除额")
    book_net_revenue_before_discount_cny: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="折扣前账面可比收入")
    source_system: Mapped[str] = mapped_column(String(30), default="ERP", comment="来源系统")
    doc_status: Mapped[str] = mapped_column(String(20), default="已入账", comment="单据状态")


class ReconExportRefundTaxBasisLine(Base, TimestampMixin):
    """出口退税税基明细"""
    __tablename__ = "recon_export_refund_tax_basis_line"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    taxpayer_id: Mapped[str] = mapped_column(String(20), ForeignKey("enterprise_info.taxpayer_id"), nullable=False)
    rebate_period: Mapped[str] = mapped_column(String(7), nullable=False, comment="退税所属期 YYYY-MM")
    export_date: Mapped[str] = mapped_column(Date, nullable=False, comment="出口日期")
    contract_id: Mapped[str] = mapped_column(String(40), nullable=False, comment="合同号")
    contract_line_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="合同明细行号")
    customer_name: Mapped[str] = mapped_column(String(120), nullable=False, comment="客户名称")
    product_name: Mapped[str] = mapped_column(String(120), nullable=False, comment="产品名称")
    declaration_no: Mapped[str] = mapped_column(String(40), nullable=False, comment="报关单号")
    declaration_line_no: Mapped[int] = mapped_column(Integer, nullable=False, comment="报关单行号")
    sales_invoice_no: Mapped[str] = mapped_column(String(40), nullable=True, comment="销售发票号")
    currency_code: Mapped[str] = mapped_column(String(10), default="USD", comment="币种")
    fx_rate_customs: Mapped[float] = mapped_column(Numeric(12, 6), default=0, comment="海关汇率")
    customs_fob_amount_doc: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="报关FOB原币金额")
    customs_fob_amount_cny: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="报关FOB人民币金额")
    rebate_tax_basis_amount_cny: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="退税税基金额")
    non_refundable_amount_cny: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="不可退税金额")
    rebate_rate: Mapped[float] = mapped_column(Numeric(8, 4), default=0, comment="退税率")
    rebate_tax_amount_cny: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="应退税额")
    rebate_batch_no: Mapped[str] = mapped_column(String(40), nullable=True, comment="退税申报批次号")
    source_system: Mapped[str] = mapped_column(String(30), default="关务/退税系统", comment="来源系统")
    doc_status: Mapped[str] = mapped_column(String(20), default="已申报", comment="单据状态")


class ReconExportContractDiscountLine(Base, TimestampMixin):
    """出口合同折扣 / 折让 / 返利明细"""
    __tablename__ = "recon_export_contract_discount_line"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    taxpayer_id: Mapped[str] = mapped_column(String(20), ForeignKey("enterprise_info.taxpayer_id"), nullable=False)
    contract_id: Mapped[str] = mapped_column(String(40), nullable=False, comment="合同号")
    contract_line_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="合同明细行号")
    discount_doc_no: Mapped[str] = mapped_column(String(40), nullable=False, comment="折扣单据号")
    discount_type_code: Mapped[str] = mapped_column(String(20), nullable=False, comment="折扣类型编码")
    discount_type_name: Mapped[str] = mapped_column(String(60), nullable=False, comment="折扣类型名称")
    discount_reason: Mapped[str] = mapped_column(Text, nullable=True, comment="折扣原因")
    book_period: Mapped[str] = mapped_column(String(7), nullable=False, comment="账面期间 YYYY-MM")
    rebate_period: Mapped[str] = mapped_column(String(7), nullable=True, comment="税基传递期间 YYYY-MM")
    effective_date: Mapped[str] = mapped_column(Date, nullable=False, comment="折扣生效日期")
    related_declaration_no: Mapped[str] = mapped_column(String(40), nullable=True, comment="关联报关单号")
    related_declaration_line_no: Mapped[int] = mapped_column(Integer, nullable=True, comment="关联报关单行号")
    related_invoice_no: Mapped[str] = mapped_column(String(40), nullable=True, comment="关联发票号")
    currency_code: Mapped[str] = mapped_column(String(10), default="USD", comment="币种")
    fx_rate_discount: Mapped[float] = mapped_column(Numeric(12, 6), default=0, comment="折扣汇率")
    discount_amount_doc: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="原币折扣金额")
    discount_amount_cny: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="人民币折扣金额")
    book_side_discount_amount_cny: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="账面侧折扣金额")
    tax_side_discount_amount_cny: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="税基侧折扣金额")
    affect_book_revenue_flag: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否影响账面收入")
    affect_tax_basis_flag: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否影响税基")
    allocation_method: Mapped[str] = mapped_column(String(40), default="按合同明细行", comment="分摊方式")
    allocation_scope: Mapped[str] = mapped_column(String(40), default="合同明细行", comment="分摊范围")
    sync_status: Mapped[str] = mapped_column(String(20), default="仅账面已处理", comment="同步状态")
    source_system: Mapped[str] = mapped_column(String(30), default="合同管理系统", comment="来源系统")
    doc_status: Mapped[str] = mapped_column(String(20), default="已审批", comment="单据状态")
