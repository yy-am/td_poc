"""系统元数据模型 — 6张表"""
from sqlalchemy import String, Integer, Text, JSON, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from app.models.base import Base, TimestampMixin


class SysSemanticModel(Base, TimestampMixin):
    """语义模型注册表"""
    __tablename__ = "sys_semantic_model"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, comment="模型标识")
    label: Mapped[str] = mapped_column(String(200), nullable=False, comment="模型中文名")
    description: Mapped[str] = mapped_column(Text, nullable=True, comment="模型描述")
    source_table: Mapped[str] = mapped_column(String(100), nullable=False, comment="源物理表名")
    model_type: Mapped[str] = mapped_column(String(20), default="physical", comment="类型: physical/semantic/metric")
    yaml_definition: Mapped[str] = mapped_column(Text, nullable=True, comment="YAML定义")
    status: Mapped[str] = mapped_column(String(20), default="active", comment="状态: active/draft/archived")


class SysUserPreference(Base, TimestampMixin):
    """用户分析偏好"""
    __tablename__ = "sys_user_preference"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="用户ID")
    preference_type: Mapped[str] = mapped_column(String(30), nullable=False, comment="偏好类型")
    preference_key: Mapped[str] = mapped_column(String(100), nullable=False, comment="偏好键")
    preference_value: Mapped[str] = mapped_column(Text, nullable=False, comment="偏好值")
    usage_count: Mapped[int] = mapped_column(Integer, default=1, comment="使用次数")
    last_used_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="最后使用时间")


class DictIndustry(Base):
    """行业分类字典"""
    __tablename__ = "dict_industry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    industry_code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, comment="行业代码")
    industry_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="行业名称")
    parent_code: Mapped[str] = mapped_column(String(10), nullable=True, comment="上级行业代码")
    avg_vat_burden: Mapped[float] = mapped_column(default=0, comment="行业平均增值税税负率")
    avg_cit_rate: Mapped[float] = mapped_column(default=0, comment="行业平均所得税税率")


class DictTaxType(Base):
    """税种字典"""
    __tablename__ = "dict_tax_type"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tax_code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, comment="税种编码")
    tax_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="税种名称")
    standard_rate: Mapped[str] = mapped_column(String(50), nullable=True, comment="标准税率")
    description: Mapped[str] = mapped_column(Text, nullable=True, comment="说明")


class SysConversation(Base, TimestampMixin):
    """会话记录"""
    __tablename__ = "sys_conversation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, comment="会话ID")
    user_id: Mapped[str] = mapped_column(String(50), default="default", comment="用户ID")
    title: Mapped[str] = mapped_column(String(200), nullable=True, comment="会话标题")
    status: Mapped[str] = mapped_column(String(20), default="active", comment="状态")


class SysConversationMessage(Base):
    """会话消息"""
    __tablename__ = "sys_conversation_message"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(50), ForeignKey("sys_conversation.session_id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, comment="角色: user/assistant/system")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="消息内容")
    message_type: Mapped[str] = mapped_column(String(20), default="text", comment="类型: text/chart/table/thinking")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=True, comment="元数据JSON")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
