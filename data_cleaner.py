import pandas as pd
import re

def duration_to_hours(duration_str):
    """将 'X小时Y分钟' 转换为小时数"""
    if pd.isna(duration_str) or duration_str == '':
        return 0.0
    duration_str = str(duration_str)
    hours_match = re.search(r'(\d+)小时', duration_str)
    minutes_match = re.search(r'(\d+)分钟', duration_str)
    hours = int(hours_match.group(1)) if hours_match else 0
    minutes = int(minutes_match.group(1)) if minutes_match else 0
    return round(hours + minutes / 60, 2)

def infer_city(site_name):
    """从站点名称取前两个字作为城市"""
    if pd.isna(site_name) or site_name == '':
        return '未知'
    return str(site_name)[:2]

def clean_attendance_data(df, report_date):
    """
    清洗原始出勤数据，返回详细格式的DataFrame
    （保留每时段数据，用于筛选和时段分析）
    """
    required_cols = ['站点名称', '姓名', '骑手id', '排班状态', '工作状态',
                     '全天在线时长', '全天有效在线时长', '全天完单量', '时段']
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"上传的Excel缺少必要列：{missing}")

    # 添加城市字段
    df['城市'] = df['站点名称'].apply(infer_city)

    # 构建清洗后的DataFrame（保留所有行，不做去重）
    cleaned = pd.DataFrame()
    cleaned['城市'] = df['城市']
    cleaned['站点名称'] = df['站点名称']
    cleaned['骑手姓名'] = df['姓名']
    cleaned['骑手ID'] = df['骑手id'].astype(str)
    cleaned['考勤日期'] = report_date.strftime('%Y/%m/%d')
    cleaned['时段'] = df['时段']

    # 将排班状态和工作状态移到时段右边
    cleaned['排班状态'] = df['排班状态']
    cleaned['工作状态'] = df['工作状态']

    # 新增四列
    cleaned['配送中单量'] = pd.to_numeric(df.get('配送中单量', 0), errors='coerce').fillna(0).astype(int)
    cleaned['时段在线时长'] = df.get('时段在线时长', '')
    cleaned['时段有效在线时长'] = df.get('时段有效在线时长', '')
    cleaned['时段完单量'] = pd.to_numeric(df.get('时段完单量', 0), errors='coerce').fillna(0).astype(int)

    # 时段班次是否达标（基于规则表）
    temp_shift_eff_hours = df['时段有效在线时长'].apply(duration_to_hours) if '时段有效在线时长' in df else 0
    shift_rule = {
        '凌晨1': (1.5, 1), '凌晨2': (1.3, 1), '凌晨3': (1.2, 1),
        '早餐1': (1.5, 1), '早餐2': (2.0, 1),
        '午高峰': (2.5, 5),
        '下午茶1': (1.5, 2), '下午茶2': (1.5, 2),
        '晚高峰': (2.0, 3),
        '夜宵1': (1.5, 2), '夜宵2': (1.5, 2),
    }
    def is_shift_qualified(row):
        shift_name = str(row['时段']).strip()
        if shift_name not in shift_rule:
            return '未知'
        req_hours, req_orders = shift_rule[shift_name]
        act_hours = temp_shift_eff_hours[row.name]
        act_orders = row['时段完单量']
        return '是' if (act_hours >= req_hours and act_orders >= req_orders) else '否'
    cleaned['时段班次是否达标'] = cleaned.apply(is_shift_qualified, axis=1)

    # 全天时长字段（转换为小时）
    cleaned['全天在线时长(h)'] = df['全天在线时长'].apply(duration_to_hours)
    cleaned['全天有效在线时长(h)'] = df['全天有效在线时长'].apply(duration_to_hours)
    cleaned['全天完单量'] = pd.to_numeric(df['全天完单量'], errors='coerce').fillna(0).astype(int)

    # 是否有效出勤骑手
    cleaned['是否有效出勤骑手'] = cleaned.apply(
        lambda row: '是' if (row['全天有效在线时长(h)'] >= 6 and row['全天完单量'] >= 15) else '否',
        axis=1
    )

    # 排班是否出勤（排班状态为“排班”且时段完单量>0）
    def is_attended(row):
        is_scheduled = (str(row['排班状态']).strip() == '排班')
        if not is_scheduled:
            return '否'
        return '是' if row['时段完单量'] > 0 else '否'
    cleaned['排班是否出勤'] = cleaned.apply(is_attended, axis=1)

    return cleaned
# ==================== 运单数据分析清洗函数 ====================

def clean_order_data(df, report_date):
    """
    清洗运单数据，返回按骑手聚合的指标DataFrame
    列：城市, 站点名称, 骑手姓名, 骑手ID, 考勤日期, 推单量, 完单量, 妥投率, T8超时单, T8准时率
    """
    import pandas as pd
    from datetime import timedelta

    # 检查必要列
    required_cols = ['站点名称', '骑手名称', '骑手id', '运单状态', '超平台期望送达时长']
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"上传的Excel缺少必要列：{missing}")

    # 复制以避免修改原数据
    df = df.copy()

    # 从站点名称提取城市（前两个字）
    df['城市'] = df['站点名称'].astype(str).str[:2]

    # 转换时间字段为 timedelta 用于比较（超平台期望送达时长）
    def time_to_timedelta(t):
        if pd.isna(t) or t == '':
            return pd.NaT
        try:
            # 格式 HH:MM:SS
            parts = str(t).split(':')
            if len(parts) == 3:
                return timedelta(hours=int(parts[0]), minutes=int(parts[1]), seconds=int(parts[2]))
        except:
            pass
        return pd.NaT
    df['超时_delta'] = df['超平台期望送达时长'].apply(time_to_timedelta)

    # 定义8分钟阈值
    eight_minutes = timedelta(minutes=8)

    # 按骑手分组聚合
    grouped = df.groupby(['骑手id', '骑手名称', '站点名称', '城市']).agg(
        推单量=('骑手id', 'count'),
        完单量=('运单状态', lambda x: (x == '配送成功').sum()),
        T8超时单=('运单状态', lambda x: (
            (x == '配送成功') &
            (df.loc[x.index, '超时_delta'] > timedelta(0)) &   # 超时时间大于0
            (df.loc[x.index, '超时_delta'] < eight_minutes)    # 且小于8分钟
        ).sum())
    ).reset_index()

    # 计算妥投率和T8准时率（数值形式）
    grouped['妥投率'] = (grouped['完单量'] / grouped['推单量'] * 100).round(2)
    grouped['T8准时率'] = ((grouped['完单量'] - grouped['T8超时单']) / grouped['完单量'] * 100).round(2)

    # 添加考勤日期
    grouped['考勤日期'] = report_date.strftime('%Y/%m/%d')

    # 重命名列以匹配要求
    result = grouped.rename(columns={
        '骑手id': '骑手ID',
        '骑手名称': '骑手姓名',
        '站点名称': '站点名称',
        '城市': '城市'
    })

    # 选择并排序输出列
    result = result[['城市', '站点名称', '骑手姓名', '骑手ID', '考勤日期',
                     '推单量', '完单量', '妥投率', 'T8超时单', 'T8准时率']]

    return result
# ==================== 骑手排班模块清洗函数 ====================

def clean_schedule_data(df, report_date):
    """
    清洗排班数据，关联商圈片映射，返回按商圈片+时段聚合的DataFrame
    列：城市, 商圈片名称, 时段, 应排人数, 排班人数, 排班缺口, 预估单量
    """
    import pandas as pd

    # 检查必要列
    required_cols = ['团队名称', '时段', '应排人数', '排班人数', '预估单量']
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"上传的Excel缺少必要列：{missing}")

    # 复制数据
    df = df.copy()

    # 定义商圈片映射表（根据用户提供的数据构建）
    mapping_data = [
        ('上海', '上海徐汇区上海南站商圈片', '上海徐汇区南宁路站-UB'),
        ('上海', '上海徐汇区上海南站商圈片', '上海徐汇区西岸站-UB'),
        ('上海', '上海徐汇区上海南站商圈片', '上海徐汇区龙耀路站-UB'),
        ('上海', '上海徐汇区上海南站商圈片', '上海徐汇区上海南站站-UB'),
        ('上海', '上海徐汇区上海南站商圈片', '上海徐汇区田林路站-UB'),
        ('上海', '上海徐汇区美罗城商圈片', '上海徐汇区龙华中路站-UB'),
        ('上海', '上海徐汇区美罗城商圈片', '上海徐汇区凯进路站-UB'),
        ('上海', '上海徐汇区美罗城商圈片', '上海徐汇区肇家浜站-UB'),
        ('上海', '上海徐汇区美罗城商圈片', '上海徐汇区徐家汇站-UB'),
        ('上海', '上海徐汇区美罗城商圈片', '上海徐汇区体育馆站-UB'),
        ('上海', '上海徐汇区美罗城商圈片', '上海徐汇区美罗城站-UB'),
        ('上海', '上海闵行区华泾路商圈片', '上海闵行区华泾路站-UB'),
        ('上海', '上海闵行区颛桥镇商圈片', '上海闵行区颛桥镇站-UB'),
        ('上海', '上海闵行区万科城商圈片', '上海闵行区万科城站-UB'),
        ('杭州', '杭州滨江区阿里巴巴商圈片', '杭州滨江区阿里巴巴园区站-UB'),
        ('杭州', '杭州滨江区阿里巴巴商圈片', '杭州滨江区保利天汇站-UB'),
        ('杭州', '杭州滨江区阿里巴巴商圈片', '杭州滨江区龙湖天街站-UB'),
        ('杭州', '杭州滨江区星光大道商圈片', '杭州滨江区中赢站-UB'),
        ('杭州', '杭州滨江区星光大道商圈片', '杭州滨江区银泰站-UB'),
        ('杭州', '杭州滨江区星光大道商圈片', '杭州滨江区星光大道站-UB'),
        ('杭州', '杭州滨江区星光大道商圈片', '杭州滨江区春波小区站-UB'),
        ('杭州', '杭州滨江区星光大道商圈片', '杭州滨江区星耀城站-UB'),
        ('杭州', '杭州滨江区星光大道商圈片', '杭州滨江区西兴古镇站-UB'),
        ('深圳', '深圳龙岗区大芬商圈片', '深圳龙岗区百鸽笼站-UB'),
        ('深圳', '深圳龙岗区大芬商圈片', '深圳龙岗区大芬站-UB'),
        ('深圳', '深圳龙岗区平湖北商圈片', '深圳龙岗区平湖北站-UB'),
        ('深圳', '深圳龙岗区平湖南商圈片', '深圳龙岗区平湖南站-UB'),
    ]
    mapping_df = pd.DataFrame(mapping_data, columns=['城市', '商圈片名称', '站点名称'])

    # 左连接：将原数据中的“团队名称”作为站点名称关联到商圈片
    merged = df.merge(mapping_df, left_on='团队名称', right_on='站点名称', how='left')

    # 检查未匹配到的站点
    unmatched = merged[merged['商圈片名称'].isna()]['团队名称'].unique()
    if len(unmatched) > 0:
        raise ValueError(f"以下站点未找到对应的商圈片：{list(unmatched)}")

    # 按商圈片和时段分组聚合（加入预估单量）
    grouped = merged.groupby(['城市', '商圈片名称', '时段']).agg({
        '应排人数': 'sum',
        '排班人数': 'sum',
        '预估单量': 'sum'
    }).reset_index()

    # 计算排班缺口 = 应排人数 - 排班人数
    grouped['排班缺口'] = grouped['应排人数'] - grouped['排班人数']

    # 按城市、商圈片、时段排序
    grouped = grouped.sort_values(['城市', '商圈片名称', '时段']).reset_index(drop=True)

    return grouped