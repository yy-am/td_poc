"""企业基础数据模型 — 3张表"""
from sqlalchemy import String, Integer, Numeric, Date, Boolean, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin


class EnterpriseInfo(Base, TimestampMixin):
    """企业主数据"""
    __tablename__ = "enterprise_info"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    taxpayer_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, comment="纳税人识别号")
    enterprise_name: Mapped[str] = mapped_column(String(200), nullable=False, comment="企业名称")
    legal_representative: Mapped[str] = mapped_column(String(50), nullable=True, comment="法定代表人")
    industry_code: Mapped[str] = mapped_column(String(10), nullable=False, comment="行业代码")
    industry_name: Mapped[str] = mapped_column(String(100), nullable=True, comment="行业名称")
    registration_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="纳税人类型: 一般纳税人/小规模纳税人")
    tax_authority: Mapped[str] = mapped_column(String(100), nullable=True, comment="主管税务机关")
    registered_capital: Mapped[float] = mapped_column(Numeric(18, 2), nullable=True, comment="注册资本(万元)")
    establishment_date: Mapped[str] = mapped_column(Date, nullable=True, comment="成立日期")
    status: Mapped[str] = mapped_column(String(20), default="正常", comment="状态: 正常/注销/非正常")


class EnterpriseBankAccount(Base, TimestampMixin):
    """企业银行账户"""
    __tablename__ = "enterprise_bank_account"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    taxpayer_id: Mapped[str] = mapped_column(String(20), ForeignKey("enterprise_info.taxpayer_id"), nullable=False)
    bank_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="开户银行")
    account_number: Mapped[str] = mapped_column(String(30), nullable=False, comment="银行账号")
    account_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="账户类型: 基本户/一般户")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否主账户")


class EnterpriseContact(Base, TimestampMixin):
    """企业联系信息"""
    __tablename__ = "enterprise_contact"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    taxpayer_id: Mapped[str] = mapped_column(String(20), ForeignKey("enterprise_info.taxpayer_id"), nullable=False)
    address: Mapped[str] = mapped_column(String(300), nullable=True, comment="注册地址")
    phone: Mapped[str] = mapped_column(String(20), nullable=True, comment="联系电话")
    email: Mapped[str] = mapped_column(String(100), nullable=True, comment="电子邮箱")
    financial_controller: Mapped[str] = mapped_column(String(50), nullable=True, comment="财务负责人")
    tax_officer: Mapped[str] = mapped_column(String(50), nullable=True, comment="办税人")
