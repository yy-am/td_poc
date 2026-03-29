"""Mock数据生成器 — 生成28张表的全量测试数据

数据策略:
- 10家企业, 5个行业, 24个月(2023-01 ~ 2024-12)
- 含故意差异: 收入时间性差异、视同销售、折旧方法差异、坏账准备差异
- 1家异常企业(税负显著低于行业平均)
- 约29000+行数据
"""
import random
import math
from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import *

random.seed(42)

# ========== 企业基础数据定义 ==========
ENTERPRISES = [
    {"taxpayer_id": "91310000MA1FL8XX01", "name": "华兴科技有限公司", "industry": "6512", "industry_name": "软件和信息技术服务", "type": "一般纳税人", "capital": 5000, "base_rev": 5_000_000, "seasonal": [1.0, 0.9, 1.0, 1.1, 1.0, 0.95, 0.85, 0.9, 1.1, 1.15, 1.2, 1.3]},
    {"taxpayer_id": "91310000MA1FL8XX02", "name": "明达制造集团", "industry": "3311", "industry_name": "金属结构制造", "type": "一般纳税人", "capital": 20000, "base_rev": 12_000_000, "seasonal": [0.8, 0.7, 0.9, 1.0, 1.05, 1.1, 1.0, 0.95, 1.1, 1.2, 1.3, 1.4]},
    {"taxpayer_id": "91310000MA1FL8XX03", "name": "锦程贸易有限公司", "industry": "5211", "industry_name": "百货零售", "type": "一般纳税人", "capital": 3000, "base_rev": 8_000_000, "seasonal": [1.5, 1.3, 0.9, 0.8, 0.9, 1.0, 0.8, 0.85, 1.0, 1.1, 1.4, 1.5]},
    {"taxpayer_id": "91310000MA1FL8XX04", "name": "宏基建设工程公司", "industry": "4712", "industry_name": "房屋建筑工程", "type": "一般纳税人", "capital": 15000, "base_rev": 18_000_000, "seasonal": [0.6, 0.5, 0.8, 1.0, 1.1, 1.2, 1.1, 1.0, 1.2, 1.3, 1.1, 0.7]},
    {"taxpayer_id": "91310000MA1FL8XX05", "name": "瑞丰金融服务公司", "industry": "6620", "industry_name": "金融辅助服务", "type": "一般纳税人", "capital": 10000, "base_rev": 6_000_000, "seasonal": [1.0, 1.0, 1.1, 1.0, 0.95, 1.05, 1.0, 0.9, 1.0, 1.1, 1.0, 1.2]},
    {"taxpayer_id": "91310000MA1FL8XX06", "name": "绿源环保科技公司", "industry": "7721", "industry_name": "环境保护监测", "type": "一般纳税人", "capital": 8000, "base_rev": 4_500_000, "seasonal": [0.9, 0.85, 1.0, 1.05, 1.1, 1.15, 1.2, 1.1, 1.0, 0.95, 0.9, 0.85]},
    {"taxpayer_id": "91310000MA1FL8XX07", "name": "盛世传媒广告公司", "industry": "7311", "industry_name": "广告业", "type": "一般纳税人", "capital": 2000, "base_rev": 3_000_000, "seasonal": [0.7, 0.8, 0.9, 1.0, 1.0, 1.1, 0.9, 0.8, 1.1, 1.2, 1.3, 1.5]},
    {"taxpayer_id": "91310000MA1FL8XX08", "name": "天和医药科技公司", "industry": "2710", "industry_name": "化学药品制造", "type": "一般纳税人", "capital": 12000, "base_rev": 10_000_000, "seasonal": [1.0, 0.95, 1.05, 1.0, 1.0, 1.05, 1.1, 1.0, 0.95, 1.0, 1.05, 1.1]},
    # 此企业数据异常：税负率显著低于行业平均
    {"taxpayer_id": "91310000MA1FL8XX09", "name": "鑫隆商贸有限公司", "industry": "5211", "industry_name": "百货零售", "type": "一般纳税人", "capital": 1500, "base_rev": 9_000_000, "seasonal": [1.3, 1.2, 0.9, 0.85, 0.9, 0.95, 0.85, 0.9, 1.0, 1.1, 1.3, 1.4], "anomaly": True},
    {"taxpayer_id": "91310000MA1FL8XX10", "name": "卓越教育培训公司", "industry": "8291", "industry_name": "职业技能培训", "type": "一般纳税人", "capital": 1000, "base_rev": 2_500_000, "seasonal": [0.6, 0.7, 1.2, 1.0, 0.9, 0.8, 1.0, 0.9, 1.3, 1.2, 1.0, 0.8]},
]

# 行业平均税负
INDUSTRY_BENCHMARKS = {
    "6512": {"avg_vat": 0.056, "avg_cit": 0.08},
    "3311": {"avg_vat": 0.035, "avg_cit": 0.06},
    "5211": {"avg_vat": 0.012, "avg_cit": 0.015},
    "4712": {"avg_vat": 0.032, "avg_cit": 0.04},
    "6620": {"avg_vat": 0.055, "avg_cit": 0.10},
    "7721": {"avg_vat": 0.048, "avg_cit": 0.07},
    "7311": {"avg_vat": 0.052, "avg_cit": 0.06},
    "2710": {"avg_vat": 0.065, "avg_cit": 0.09},
    "8291": {"avg_vat": 0.055, "avg_cit": 0.05},
}

# 会计科目表 — 核心科目
CHART_OF_ACCOUNTS = [
    ("1001", "库存现金", "资产", None, 1, False, "借"),
    ("1002", "银行存款", "资产", None, 1, False, "借"),
    ("1002.01", "银行存款-基本户", "资产", "1002", 2, True, "借"),
    ("1002.02", "银行存款-一般户", "资产", "1002", 2, True, "借"),
    ("1122", "应收账款", "资产", None, 1, True, "借"),
    ("1221", "其他应收款", "资产", None, 1, True, "借"),
    ("1401", "材料采购", "资产", None, 1, True, "借"),
    ("1403", "原材料", "资产", None, 1, True, "借"),
    ("1405", "库存商品", "资产", None, 1, True, "借"),
    ("1601", "固定资产", "资产", None, 1, False, "借"),
    ("1601.01", "固定资产-房屋建筑物", "资产", "1601", 2, True, "借"),
    ("1601.02", "固定资产-机器设备", "资产", "1601", 2, True, "借"),
    ("1601.03", "固定资产-电子设备", "资产", "1601", 2, True, "借"),
    ("1602", "累计折旧", "资产", None, 1, True, "贷"),
    ("1701", "无形资产", "资产", None, 1, True, "借"),
    ("2001", "短期借款", "负债", None, 1, True, "贷"),
    ("2202", "应付账款", "负债", None, 1, True, "贷"),
    ("2211", "应付职工薪酬", "负债", None, 1, True, "贷"),
    ("2221", "应交税费", "负债", None, 1, False, "贷"),
    ("2221.01", "应交税费-应交增值税", "负债", "2221", 2, False, "贷"),
    ("2221.01.01", "应交税费-应交增值税(销项税额)", "负债", "2221.01", 3, True, "贷"),
    ("2221.01.02", "应交税费-应交增值税(进项税额)", "负债", "2221.01", 3, True, "借"),
    ("2221.01.03", "应交税费-应交增值税(进项税额转出)", "负债", "2221.01", 3, True, "贷"),
    ("2221.02", "应交税费-应交企业所得税", "负债", "2221", 2, True, "贷"),
    ("2221.03", "应交税费-应交城市维护建设税", "负债", "2221", 2, True, "贷"),
    ("2221.04", "应交税费-应交教育费附加", "负债", "2221", 2, True, "贷"),
    ("2221.05", "应交税费-应交印花税", "负债", "2221", 2, True, "贷"),
    ("2221.06", "应交税费-应交房产税", "负债", "2221", 2, True, "贷"),
    ("2241", "其他应付款", "负债", None, 1, True, "贷"),
    ("4001", "实收资本", "权益", None, 1, True, "贷"),
    ("4101", "资本公积", "权益", None, 1, True, "贷"),
    ("4103", "盈余公积", "权益", None, 1, True, "贷"),
    ("4104", "未分配利润", "权益", None, 1, True, "贷"),
    ("6001", "主营业务收入", "收入", None, 1, True, "贷"),
    ("6051", "其他业务收入", "收入", None, 1, True, "贷"),
    ("6111", "投资收益", "收入", None, 1, True, "贷"),
    ("6301", "营业外收入", "收入", None, 1, True, "贷"),
    ("6401", "主营业务成本", "费用", None, 1, True, "借"),
    ("6402", "其他业务成本", "费用", None, 1, True, "借"),
    ("6403", "营业税金及附加", "费用", None, 1, True, "借"),
    ("6601", "销售费用", "费用", None, 1, True, "借"),
    ("6602", "管理费用", "费用", None, 1, True, "借"),
    ("6603", "财务费用", "费用", None, 1, True, "借"),
    ("6711", "营业外支出", "费用", None, 1, True, "借"),
    ("6801", "所得税费用", "费用", None, 1, True, "借"),
    ("1231", "坏账准备", "资产", None, 1, True, "贷"),
]


def _rand(base, low=0.92, high=1.08):
    """在基础值附近随机波动"""
    return round(base * random.uniform(low, high), 2)


def _periods():
    """生成 2023-01 到 2024-12 的期间列表"""
    periods = []
    for year in [2023, 2024]:
        for month in range(1, 13):
            periods.append(f"{year}-{month:02d}")
    return periods


PERIODS = _periods()


async def generate_all_mock_data(session: AsyncSession):
    """主入口: 生成全部Mock数据"""
    print("Starting mock data generation...")

    # 1. 字典数据
    await _gen_dict_industry(session)
    await _gen_dict_tax_type(session)
    print("  [OK] dict data")

    # 2. 会计科目表
    await _gen_chart_of_accounts(session)
    print("  [OK] chart of accounts")

    # 3. 企业主数据
    await _gen_enterprises(session)
    await session.flush()
    print("  [OK] enterprise master data")

    # 4. 各企业每月业务数据
    for ent in ENTERPRISES:
        is_anomaly = ent.get("anomaly", False)
        await _gen_monthly_data(session, ent, is_anomaly)
        print(f"  [OK] {ent['name']} monthly business data")

    # 5. 折旧台账
    await _gen_depreciation_schedules(session)
    print("  [OK] depreciation schedules")

    # 6. 语义模型元数据
    await _gen_semantic_models(session)
    print("  [OK] semantic model metadata")

    await session.commit()
    print("Mock data generation completed!")


async def _gen_dict_industry(session: AsyncSession):
    industries = [
        DictIndustry(industry_code="6512", industry_name="软件和信息技术服务", parent_code="65", avg_vat_burden=0.056, avg_cit_rate=0.08),
        DictIndustry(industry_code="3311", industry_name="金属结构制造", parent_code="33", avg_vat_burden=0.035, avg_cit_rate=0.06),
        DictIndustry(industry_code="5211", industry_name="百货零售", parent_code="52", avg_vat_burden=0.012, avg_cit_rate=0.015),
        DictIndustry(industry_code="4712", industry_name="房屋建筑工程", parent_code="47", avg_vat_burden=0.032, avg_cit_rate=0.04),
        DictIndustry(industry_code="6620", industry_name="金融辅助服务", parent_code="66", avg_vat_burden=0.055, avg_cit_rate=0.10),
        DictIndustry(industry_code="7721", industry_name="环境保护监测", parent_code="77", avg_vat_burden=0.048, avg_cit_rate=0.07),
        DictIndustry(industry_code="7311", industry_name="广告业", parent_code="73", avg_vat_burden=0.052, avg_cit_rate=0.06),
        DictIndustry(industry_code="2710", industry_name="化学药品制造", parent_code="27", avg_vat_burden=0.065, avg_cit_rate=0.09),
        DictIndustry(industry_code="8291", industry_name="职业技能培训", parent_code="82", avg_vat_burden=0.055, avg_cit_rate=0.05),
    ]
    session.add_all(industries)


async def _gen_dict_tax_type(session: AsyncSession):
    types = [
        DictTaxType(tax_code="VAT", tax_name="增值税", standard_rate="13%/9%/6%", description="一般纳税人增值税"),
        DictTaxType(tax_code="CIT", tax_name="企业所得税", standard_rate="25%", description="企业所得税"),
        DictTaxType(tax_code="STAMP", tax_name="印花税", standard_rate="0.03%-0.1%", description="印花税"),
        DictTaxType(tax_code="PROPERTY", tax_name="房产税", standard_rate="1.2%/12%", description="房产税"),
        DictTaxType(tax_code="LAND", tax_name="城镇土地使用税", standard_rate="按面积", description="城镇土地使用税"),
        DictTaxType(tax_code="URBAN", tax_name="城市维护建设税", standard_rate="7%/5%/1%", description="城市维护建设税"),
        DictTaxType(tax_code="EDU", tax_name="教育费附加", standard_rate="3%", description="教育费附加"),
        DictTaxType(tax_code="LOCAL_EDU", tax_name="地方教育附加", standard_rate="2%", description="地方教育附加"),
    ]
    session.add_all(types)


async def _gen_chart_of_accounts(session: AsyncSession):
    accounts = []
    for code, name, atype, parent, level, is_leaf, direction in CHART_OF_ACCOUNTS:
        accounts.append(AcctChartOfAccounts(
            account_code=code, account_name=name, account_type=atype,
            parent_code=parent, level=level, is_leaf=is_leaf, direction=direction,
        ))
    session.add_all(accounts)


async def _gen_enterprises(session: AsyncSession):
    for ent in ENTERPRISES:
        enterprise = EnterpriseInfo(
            taxpayer_id=ent["taxpayer_id"], enterprise_name=ent["name"],
            legal_representative=f"张{random.choice('明华强伟')}{random.choice('国一')}",
            industry_code=ent["industry"], industry_name=ent["industry_name"],
            registration_type=ent["type"], tax_authority="国家税务总局上海市税务局",
            registered_capital=ent["capital"],
            establishment_date=date(random.randint(2010, 2020), random.randint(1, 12), random.randint(1, 28)),
            status="正常",
        )
        session.add(enterprise)
        await session.flush()
        session.add(EnterpriseBankAccount(
            taxpayer_id=ent["taxpayer_id"], bank_name="中国工商银行上海分行",
            account_number=f"1001{random.randint(1000000000, 9999999999)}",
            account_type="基本户", is_primary=True,
        ))
        session.add(EnterpriseContact(
            taxpayer_id=ent["taxpayer_id"],
            address=f"上海市{random.choice(['浦东新区', '徐汇区', '黄浦区', '静安区', '杨浦区'])}某路{random.randint(100,999)}号",
            phone=f"021-{random.randint(50000000, 69999999)}",
            email=f"finance@{ent['name'][:2]}.com",
            financial_controller=f"李{random.choice('敏芳丽娟')}",
            tax_officer=f"王{random.choice('勇磊峰超')}",
        ))


async def _gen_monthly_data(session: AsyncSession, ent: dict, is_anomaly: bool):
    """为一家企业生成24个月的全部业务数据"""
    tid = ent["taxpayer_id"]
    base_rev = ent["base_rev"]
    seasonal = ent["seasonal"]
    industry = ent["industry"]
    bench = INDUSTRY_BENCHMARKS[industry]

    # VAT税率 (行业不同)
    vat_rate = {"6512": 0.06, "3311": 0.13, "5211": 0.13, "4712": 0.09,
                "6620": 0.06, "7721": 0.06, "7311": 0.06, "2710": 0.13, "8291": 0.06}[industry]
    cost_ratio = random.uniform(0.6, 0.8)

    quarterly_revenue = {2023: {1: 0, 2: 0, 3: 0, 4: 0}, 2024: {1: 0, 2: 0, 3: 0, 4: 0}}
    quarterly_cost = {2023: {1: 0, 2: 0, 3: 0, 4: 0}, 2024: {1: 0, 2: 0, 3: 0, 4: 0}}
    quarterly_profit = {2023: {1: 0, 2: 0, 3: 0, 4: 0}, 2024: {1: 0, 2: 0, 3: 0, 4: 0}}

    for i, period in enumerate(PERIODS):
        year = int(period[:4])
        month = int(period[5:])
        quarter = (month - 1) // 3 + 1
        s_factor = seasonal[month - 1]
        # 2024年整体增长5-15%
        growth = 1.0 if year == 2023 else random.uniform(1.05, 1.15)

        # === 会计账面收入 (真实值) ===
        acct_revenue = _rand(base_rev * s_factor * growth)
        acct_cost = _rand(acct_revenue * cost_ratio)
        acct_revenue_other = _rand(acct_revenue * 0.03, 0.5, 1.5)

        # === 增值税申报收入 (含差异) ===
        # 差异类型1: 时间性差异(开票与确认收入时间不同)
        timing_diff = _rand(acct_revenue * 0.03, -1, 1)
        # 差异类型2: 视同销售(部分企业有)
        deemed_sales = 0
        if ent["name"] in ["明达制造集团", "锦程贸易有限公司"] and month in [3, 6, 9, 12]:
            deemed_sales = _rand(acct_revenue * 0.02)
        # 异常企业: 隐瞒部分收入
        hidden = 0
        if is_anomaly:
            hidden = acct_revenue * random.uniform(0.05, 0.12)
        vat_revenue = round(acct_revenue + timing_diff + deemed_sales - hidden, 2)

        # 销项税 = VAT申报收入 * 税率
        output_tax = round(vat_revenue * vat_rate, 2)
        # 进项税 (成本对应)
        input_tax_ratio = random.uniform(0.75, 0.92) if not is_anomaly else random.uniform(0.88, 0.98)
        input_tax = round(output_tax * input_tax_ratio, 2)
        transferred_out = round(input_tax * random.uniform(0, 0.03), 2) if random.random() > 0.7 else 0
        vat_payable = round(output_tax - input_tax + transferred_out, 2)
        if vat_payable < 0:
            vat_payable = 0

        # === 增值税申报 ===
        session.add(TaxVatDeclaration(
            taxpayer_id=tid, tax_period=period,
            total_sales_amount=vat_revenue, taxable_sales_amount=vat_revenue,
            exempt_sales_amount=0, output_tax_amount=output_tax,
            input_tax_amount=input_tax, input_tax_transferred_out=transferred_out,
            tax_payable=vat_payable,
            declaration_date=date(year, month, 15) + timedelta(days=random.randint(0, 10)),
        ))

        # === 发票汇总 ===
        for inv_type, ratio in [("专用发票", 0.65), ("普通发票", 0.25), ("电子发票", 0.10)]:
            inv_amount = round(vat_revenue * ratio * random.uniform(0.9, 1.1), 2)
            inv_tax = round(inv_amount * vat_rate, 2)
            session.add(TaxVatInvoiceSummary(
                taxpayer_id=tid, tax_period=period, invoice_type=inv_type,
                invoice_count=random.randint(10, 200),
                total_amount=inv_amount, total_tax=inv_tax,
                total_amount_with_tax=round(inv_amount + inv_tax, 2),
            ))

        # === 利润表 ===
        tax_surcharges = round(vat_payable * 0.12, 2)  # 城建税+教附+地方教附
        selling_exp = _rand(acct_revenue * random.uniform(0.03, 0.08))
        admin_exp = _rand(acct_revenue * random.uniform(0.04, 0.10))
        finance_exp = _rand(acct_revenue * random.uniform(0.005, 0.02))
        invest_income = _rand(acct_revenue * 0.005, 0, 2) if random.random() > 0.7 else 0
        non_op_income = _rand(acct_revenue * 0.002, 0, 2) if random.random() > 0.8 else 0
        non_op_expense = _rand(acct_revenue * 0.001, 0, 2) if random.random() > 0.85 else 0
        profit_total = round(acct_revenue + acct_revenue_other - acct_cost - tax_surcharges
                             - selling_exp - admin_exp - finance_exp
                             + invest_income + non_op_income - non_op_expense, 2)
        cit_expense = round(max(profit_total * 0.25, 0), 2)
        net_profit = round(profit_total - cit_expense, 2)

        session.add(AcctIncomeStatement(
            taxpayer_id=tid, period=period,
            revenue_main=acct_revenue, revenue_other=acct_revenue_other,
            cost_main=acct_cost, cost_other=0, tax_surcharges=tax_surcharges,
            selling_expenses=selling_exp, admin_expenses=admin_exp, finance_expenses=finance_exp,
            investment_income=invest_income, non_operating_income=non_op_income,
            non_operating_expense=non_op_expense,
            profit_total=profit_total, income_tax_expense=cit_expense, net_profit=net_profit,
        ))

        # 累积季度数据
        quarterly_revenue[year][quarter] += acct_revenue + acct_revenue_other
        quarterly_cost[year][quarter] += acct_cost
        quarterly_profit[year][quarter] += profit_total

        # === 资产负债表 (简化) ===
        base_assets = acct_revenue * 3
        session.add(AcctBalanceSheet(
            taxpayer_id=tid, period=period,
            cash=_rand(base_assets * 0.15),
            receivables=_rand(base_assets * 0.20),
            inventory=_rand(base_assets * 0.15),
            fixed_assets=_rand(base_assets * 0.30),
            total_assets=_rand(base_assets),
            payables=_rand(base_assets * 0.15),
            tax_payable_bs=round(vat_payable + cit_expense * 0.3, 2),
            total_liabilities=_rand(base_assets * 0.45),
            paid_in_capital=ent["capital"] * 10000,
            retained_earnings=_rand(base_assets * 0.15),
            total_equity=_rand(base_assets * 0.55),
        ))

        # === 应交税费明细 ===
        for tax_t, accrued in [("增值税", vat_payable), ("企业所得税", cit_expense * 0.3),
                                ("城市维护建设税", vat_payable * 0.07), ("教育费附加", vat_payable * 0.03)]:
            paid = round(accrued * random.uniform(0.85, 1.0), 2)
            session.add(AcctTaxPayableDetail(
                taxpayer_id=tid, period=period, tax_type=tax_t,
                opening_balance=_rand(accrued * 0.1, 0, 0.3),
                accrued_amount=round(accrued, 2), paid_amount=paid,
                closing_balance=round(accrued - paid, 2),
            ))

        # === 其他税种 ===
        if month in [1, 4, 7, 10]:  # 季度申报
            session.add(TaxOtherTaxes(
                taxpayer_id=tid, tax_period=period, tax_type="城市维护建设税",
                tax_basis=round(vat_payable * 3, 2), tax_rate=0.07,
                tax_amount=round(vat_payable * 3 * 0.07, 2),
            ))
            session.add(TaxOtherTaxes(
                taxpayer_id=tid, tax_period=period, tax_type="印花税",
                tax_basis=round(acct_revenue * 3, 2), tax_rate=0.0003,
                tax_amount=round(acct_revenue * 3 * 0.0003, 2),
            ))

        # === 收入对比 ===
        cit_revenue = round(acct_revenue + acct_revenue_other + timing_diff * 0.5, 2)  # 所得税收入与增值税口径不同
        session.add(ReconRevenueComparison(
            taxpayer_id=tid, period=period,
            vat_declared_revenue=vat_revenue, cit_declared_revenue=cit_revenue,
            acct_book_revenue=round(acct_revenue + acct_revenue_other, 2),
            vat_vs_acct_diff=round(vat_revenue - acct_revenue - acct_revenue_other, 2),
            cit_vs_acct_diff=round(cit_revenue - acct_revenue - acct_revenue_other, 2),
            vat_vs_cit_diff=round(vat_revenue - cit_revenue, 2),
            diff_explanation="时间性差异" + ("+视同销售" if deemed_sales > 0 else "") + ("+收入异常" if hidden > 0 else ""),
        ))

        # === 税负分析 ===
        vat_burden = round(vat_payable / vat_revenue, 6) if vat_revenue > 0 else 0
        cit_eff_rate = round(cit_expense / (acct_revenue + acct_revenue_other), 6) if acct_revenue > 0 else 0
        session.add(ReconTaxBurdenAnalysis(
            taxpayer_id=tid, period=period, industry_code=industry,
            vat_burden_rate=vat_burden,
            cit_effective_rate=cit_eff_rate,
            total_tax_burden=round(vat_burden + cit_eff_rate, 6),
            industry_avg_vat_burden=bench["avg_vat"],
            industry_avg_cit_rate=bench["avg_cit"],
            deviation_vat=round(vat_burden - bench["avg_vat"], 6),
            deviation_cit=round(cit_eff_rate - bench["avg_cit"], 6),
        ))

        # === 调整追踪 ===
        # 每月产生1-3个差异项
        adj_items = [
            ("暂时性", "折旧方法差异", acct_revenue * 0.002),
            ("暂时性", "坏账准备差异", acct_revenue * 0.001),
            ("永久性", "业务招待费超限", admin_exp * 0.05),
        ]
        if deemed_sales > 0:
            adj_items.append(("永久性", "视同销售调整", deemed_sales))
        if non_op_expense > 0 and random.random() > 0.5:
            adj_items.append(("永久性", "罚款支出", non_op_expense * 0.3))

        for adj_type, category, base_amount in adj_items:
            acct_amt = _rand(base_amount)
            tax_amt = _rand(base_amount * random.uniform(0.5, 1.5))
            diff = round(acct_amt - tax_amt, 2)
            session.add(ReconAdjustmentTracking(
                taxpayer_id=tid, period=period,
                adjustment_type=adj_type, source_category=category,
                accounting_amount=acct_amt, tax_amount=tax_amt,
                difference=diff,
                deferred_tax_impact=round(diff * 0.25, 2) if adj_type == "暂时性" else 0,
            ))

        # === 风险指标 (异常企业标记高风险) ===
        if is_anomaly or (vat_burden < bench["avg_vat"] * 0.5):
            risk_level = "高" if is_anomaly else "中"
            session.add(TaxRiskIndicator(
                taxpayer_id=tid, tax_period=period,
                indicator_code="R001", indicator_name="增值税税负率偏低预警",
                indicator_value=vat_burden, threshold_value=bench["avg_vat"] * 0.6,
                risk_level=risk_level,
                alert_message=f"增值税税负率{vat_burden:.4%}，低于行业预警值{bench['avg_vat'] * 0.6:.4%}",
            ))
        # 随机添加一些低风险指标
        if random.random() > 0.8:
            session.add(TaxRiskIndicator(
                taxpayer_id=tid, tax_period=period,
                indicator_code="R002", indicator_name="进项税额变动率异常",
                indicator_value=random.uniform(-0.3, 0.3),
                threshold_value=0.2, risk_level="低",
                alert_message="进项税额变动幅度较大，建议关注",
            ))

        # === 交叉核验 ===
        rules = [
            ("CK001", "增值税申报收入≈发票合计", vat_revenue, vat_revenue * random.uniform(0.98, 1.02)),
            ("CK002", "利润表收入=主营+其他", acct_revenue + acct_revenue_other, acct_revenue + acct_revenue_other),
            ("CK003", "资产=负债+权益", 1.0, random.uniform(0.999, 1.001)),
        ]
        for code, name, expected, actual in rules:
            diff = round(actual - expected, 2)
            status = "通过" if abs(diff) < expected * 0.01 else ("预警" if abs(diff) < expected * 0.05 else "异常")
            session.add(ReconCrossCheckResult(
                taxpayer_id=tid, period=period,
                check_rule_code=code, check_rule_name=name,
                expected_value=round(expected, 2), actual_value=round(actual, 2),
                difference=diff, status=status,
                recommendation="" if status == "通过" else "请核实差异原因",
            ))

        # 每50条flush一次避免内存过大
        if i > 0 and i % 6 == 0:
            await session.flush()

    # === 所得税季度预缴 ===
    for year in [2023, 2024]:
        for q in range(1, 5):
            rev = quarterly_revenue[year][q]
            cost = quarterly_cost[year][q]
            profit = quarterly_profit[year][q]
            taxable = max(profit * random.uniform(1.0, 1.05), 0)
            tax_amt = round(taxable * 0.25, 2)
            prepaid = round(tax_amt * random.uniform(0.9, 1.0), 2)
            session.add(TaxCitQuarterly(
                taxpayer_id=tid, tax_year=year, quarter=q,
                revenue_total=round(rev, 2), cost_total=round(cost, 2),
                profit_total=round(profit, 2), taxable_income=round(taxable, 2),
                tax_rate=0.25, tax_payable=tax_amt, tax_prepaid=prepaid,
            ))

    # === 所得税年度汇算清缴 ===
    for year in [2023, 2024]:
        total_profit = sum(quarterly_profit[year].values())
        adj_increase = round(total_profit * random.uniform(0.02, 0.06), 2)
        adj_decrease = round(total_profit * random.uniform(0.005, 0.02), 2)
        taxable = round(max(total_profit + adj_increase - adj_decrease, 0), 2)
        tax_amt = round(taxable * 0.25, 2)
        prepaid = sum(round(quarterly_profit[year][q] * 0.25 * random.uniform(0.9, 1.0), 2) for q in range(1, 5))
        refund_or_due = round(tax_amt - prepaid, 2)

        annual = TaxCitAnnual(
            taxpayer_id=tid, tax_year=year,
            accounting_profit=round(total_profit, 2),
            tax_adjustments_increase=adj_increase,
            tax_adjustments_decrease=adj_decrease,
            taxable_income=taxable, tax_rate=0.25,
            tax_amount=tax_amt, tax_prepaid=round(prepaid, 2),
            tax_refund_or_due=refund_or_due,
        )
        session.add(annual)
        await session.flush()

        # 调整明细项
        adjustment_items = [
            ("A01", "职工福利费超限", 0.005, "调增"),
            ("A02", "业务招待费超限", 0.003, "调增"),
            ("A03", "广告费超限", 0.002, "调增"),
            ("A04", "折旧差异", 0.004, "调增"),
            ("A05", "坏账准备", 0.002, "调增"),
            ("A06", "研发费用加计扣除", 0.01, "调减"),
            ("A07", "免税收入", 0.003, "调减"),
        ]
        if ent["name"] in ["明达制造集团", "锦程贸易有限公司"]:
            adjustment_items.append(("A08", "视同销售调整", 0.002, "调增"))

        for code, name, ratio, direction in adjustment_items:
            acct_amt = round(abs(total_profit * ratio) * random.uniform(0.8, 1.2), 2)
            tax_amt_item = round(acct_amt * random.uniform(0.5, 1.5), 2)
            adj = round(abs(acct_amt - tax_amt_item), 2)
            session.add(TaxCitAdjustmentItem(
                annual_id=annual.id, taxpayer_id=tid, tax_year=year,
                item_code=code, item_name=name,
                accounting_amount=acct_amt, tax_amount=tax_amt_item,
                adjustment_amount=adj, adjustment_direction=direction,
            ))

    # 生成少量凭证数据 (每企业每月5条凭证)
    for i, period in enumerate(PERIODS):
        year = int(period[:4])
        month = int(period[5:])
        for j in range(5):
            entry = AcctJournalEntry(
                taxpayer_id=tid,
                entry_number=f"PZ-{period}-{j + 1:03d}",
                entry_date=date(year, month, random.randint(1, 28)),
                period=period,
                description=random.choice(["收入确认", "成本结转", "费用报销", "税费计提", "工资计提"]),
                created_by="系统",
                is_adjusted=(j == 4 and month == 12),
            )
            session.add(entry)
            await session.flush()

            # 每条凭证2-3行
            amount = _rand(base_rev * 0.1)
            session.add(AcctJournalLine(
                entry_id=entry.id, account_code="6001",
                debit_amount=0, credit_amount=amount, description="主营业务收入",
            ))
            session.add(AcctJournalLine(
                entry_id=entry.id, account_code="1122",
                debit_amount=amount, credit_amount=0, description="应收账款",
            ))
            tax_line_amt = round(amount * 0.06, 2)
            session.add(AcctJournalLine(
                entry_id=entry.id, account_code="2221.01.01",
                debit_amount=0, credit_amount=tax_line_amt, description="销项税额",
            ))

    # 总账余额 (每企业每月约10个科目)
    key_accounts = ["1002", "1122", "1405", "1601", "2202", "2221", "6001", "6401", "6602", "4104"]
    for period in PERIODS:
        for acc_code in key_accounts:
            opening = _rand(base_rev * 0.5, 0.1, 1.5)
            debit = _rand(base_rev * 0.3, 0.05, 1.0)
            credit = _rand(base_rev * 0.3, 0.05, 1.0)
            session.add(AcctGeneralLedger(
                taxpayer_id=tid, account_code=acc_code, period=period,
                opening_balance=opening, debit_total=debit, credit_total=credit,
                closing_balance=round(opening + debit - credit, 2),
            ))


async def _gen_depreciation_schedules(session: AsyncSession):
    """折旧台账 — 部分企业会计与税法采用不同方法"""
    asset_templates = [
        ("房屋", "房屋建筑物", 2_000_000, 240, "直线法", 240, "直线法"),
        ("生产设备A", "机器设备", 500_000, 120, "直线法", 60, "加速折旧"),
        ("生产设备B", "机器设备", 300_000, 120, "直线法", 120, "直线法"),
        ("电脑及办公设备", "电子设备", 50_000, 60, "直线法", 36, "加速折旧"),
        ("服务器", "电子设备", 200_000, 60, "直线法", 36, "加速折旧"),
    ]

    for ent in ENTERPRISES:
        for idx, (name, cat, value, acct_life, acct_method, tax_life, tax_method) in enumerate(asset_templates):
            value_rand = _rand(value)
            acct_dep = round(value_rand / acct_life, 2) if acct_life > 0 else 0
            tax_dep = round(value_rand / tax_life, 2) if tax_life > 0 else 0
            session.add(AcctDepreciationSchedule(
                taxpayer_id=ent["taxpayer_id"],
                asset_id=f"FA-{ent['taxpayer_id'][-2:]}-{idx + 1:03d}",
                asset_name=name, category=cat,
                original_value=value_rand,
                acct_useful_life=acct_life, acct_method=acct_method,
                acct_depreciation_monthly=acct_dep,
                tax_useful_life=tax_life, tax_method=tax_method,
                tax_depreciation_monthly=tax_dep,
                difference_monthly=round(acct_dep - tax_dep, 2),
            ))


async def _gen_semantic_models(session: AsyncSession):
    """生成语义模型元数据"""
    models = [
        ("vat_declaration", "增值税申报数据", "tax_vat_declaration", "physical"),
        ("vat_invoice_summary", "发票汇总数据", "tax_vat_invoice_summary", "physical"),
        ("cit_quarterly", "所得税季度预缴", "tax_cit_quarterly", "physical"),
        ("cit_annual", "所得税年度汇算", "tax_cit_annual", "physical"),
        ("cit_adjustments", "纳税调整明细", "tax_cit_adjustment_items", "physical"),
        ("other_taxes", "其他税种申报", "tax_other_taxes", "physical"),
        ("risk_indicators", "税务风险指标", "tax_risk_indicators", "physical"),
        ("income_statement", "利润表", "acct_income_statement", "physical"),
        ("balance_sheet", "资产负债表", "acct_balance_sheet", "physical"),
        ("journal_entries", "会计凭证", "acct_journal_entry", "physical"),
        ("general_ledger", "总账余额", "acct_general_ledger", "physical"),
        ("tax_payable_detail", "应交税费明细", "acct_tax_payable_detail", "physical"),
        ("depreciation", "折旧台账", "acct_depreciation_schedule", "physical"),
        ("revenue_comparison", "收入对比分析", "recon_revenue_comparison", "semantic"),
        ("tax_burden_analysis", "税负分析", "recon_tax_burden_analysis", "semantic"),
        ("adjustment_tracking", "差异调整追踪", "recon_adjustment_tracking", "semantic"),
        ("cross_check", "交叉核验结果", "recon_cross_check_result", "semantic"),
        ("enterprise_master", "企业主数据", "enterprise_info", "physical"),
        ("enterprise_tax_overview", "企业税务总览", "enterprise_info", "semantic"),
        ("reconciliation_dashboard", "对账分析看板", "recon_revenue_comparison", "metric"),
    ]
    for name, label, table, mtype in models:
        session.add(SysSemanticModel(
            name=name, label=label, description=f"{label}语义模型",
            source_table=table, model_type=mtype, status="active",
        ))
