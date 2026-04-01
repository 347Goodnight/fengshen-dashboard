import streamlit as st
import pandas as pd
import plotly.express as px
from data_cleaner import duration_to_hours

def compute_site_summary(df):
    """
    计算每个站点的各项指标。
    - 完单量、实际出勤骑手数、人效 基于“全天”时段去重骑手。
    - 排班出勤骑手数 基于所有时段（含全天和其他）按规则判断。
    - 其他排班/在线/背单指标 基于所有时段。
    """
    df = df.copy()

    # ==================== 第一部分：基于所有时段的骑手级聚合 ====================
    # 添加标志列
    df['is_scheduled'] = (df['排班状态'] == '排班')
    # 排班出勤标志：全天时段用全天完单量，非全天用时段完单量
    df['is_scheduled_attended'] = (
        (df['排班状态'] == '排班') &
        (
            ((df['时段'] == '全天') & (df['全天完单量'] > 0)) |
            ((df['时段'] != '全天') & (df['时段完单量'] > 0))
        )
    )
    df['is_online'] = df['工作状态'].str.contains('上班', na=False)
    df['is_break'] = df['工作状态'].str.contains('小休', na=False)
    df['is_offline'] = df['工作状态'].str.contains('下班', na=False)
    df['has_backorder'] = (df['配送中单量'] > 0)
    df['时段有效在线时长_h'] = df['时段有效在线时长'].apply(duration_to_hours)

    # 按站点+骑手ID聚合，取各标志的最大值（即只要任一记录满足就算）
    grouped_all = df.groupby(['站点名称', '骑手ID']).agg({
        'is_scheduled': 'max',
        'is_scheduled_attended': 'max',
        'is_online': 'max',
        'is_break': 'max',
        'is_offline': 'max',
        'has_backorder': 'max',
        '时段完单量': 'sum',
        '时段有效在线时长_h': 'sum',
    }).reset_index()

    # ==================== 第二部分：基于“全天”时段的唯一骑手数据 ====================
    df_all_day = df[df['时段'] == '全天'].copy()
    df_all_day_unique = df_all_day.drop_duplicates(subset=['站点名称', '骑手ID'], keep='first')

    # 按站点聚合全天指标
    all_day_site = df_all_day_unique.groupby('站点名称').agg(
        完单量=('全天完单量', 'sum'),
        实际出勤骑手数=('全天完单量', lambda x: (x > 0).sum())
    ).reset_index()
    all_day_site['人效'] = all_day_site.apply(
        lambda row: row['完单量'] / row['实际出勤骑手数'] if row['实际出勤骑手数'] > 0 else 0,
        axis=1
    )

    # ==================== 第三部分：基于所有时段计算其他站点指标 ====================
    site_other = grouped_all.groupby('站点名称').apply(lambda g: pd.Series({
        '排班应出勤骑手数': g['is_scheduled'].sum(),
        '排班出勤骑手数': g['is_scheduled_attended'].sum(),
        '排班在线骑手数': ((g['is_scheduled']) & (g['is_online'])).sum(),
        '排班背单骑手数': ((g['is_scheduled']) & (g['has_backorder'])).sum(),
        '排班下线且无备单骑手数': ((g['is_scheduled']) & (~g['is_online']) & (~g['has_backorder'])).sum(),
        '在线骑手数': g['is_online'].sum(),
        '背单骑手数': g['has_backorder'].sum(),
        '小休骑手数': g['is_break'].sum(),
        '小休且背单骑手数': ((g['is_break']) & (g['has_backorder'])).sum(),
    })).reset_index()

    # ==================== 第四部分：合并并计算排班出勤率 ====================
    site_summary = pd.merge(all_day_site, site_other, on='站点名称', how='outer').fillna(0)

    # 重新计算排班出勤率（使用新的排班出勤骑手数）
    site_summary['排班出勤率'] = site_summary.apply(
        lambda row: row['排班出勤骑手数'] / row['排班应出勤骑手数'] if row['排班应出勤骑手数'] > 0 else 0,
        axis=1
    )

    # 调整列顺序
    cols_order = [
        '站点名称', '完单量', '实际出勤骑手数', '人效',
        '排班应出勤骑手数', '排班出勤骑手数', '排班出勤率',
        '排班在线骑手数', '排班背单骑手数', '排班下线且无备单骑手数',
        '在线骑手数', '背单骑手数', '小休骑手数', '小休且背单骑手数'
    ]
    site_summary = site_summary[cols_order]

    # 格式化
    site_summary['完单量'] = site_summary['完单量'].astype(int)
    site_summary['实际出勤骑手数'] = site_summary['实际出勤骑手数'].astype(int)
    site_summary['人效'] = site_summary['人效'].round(2)
    site_summary['排班应出勤骑手数'] = site_summary['排班应出勤骑手数'].astype(int)
    site_summary['排班出勤骑手数'] = site_summary['排班出勤骑手数'].astype(int)
    site_summary['排班出勤率'] = site_summary['排班出勤率'].apply(lambda x: f"{x:.1%}")
    site_summary['排班在线骑手数'] = site_summary['排班在线骑手数'].astype(int)
    site_summary['排班背单骑手数'] = site_summary['排班背单骑手数'].astype(int)
    site_summary['排班下线且无备单骑手数'] = site_summary['排班下线且无备单骑手数'].astype(int)
    site_summary['在线骑手数'] = site_summary['在线骑手数'].astype(int)
    site_summary['背单骑手数'] = site_summary['背单骑手数'].astype(int)
    site_summary['小休骑手数'] = site_summary['小休骑手数'].astype(int)
    site_summary['小休且背单骑手数'] = site_summary['小休且背单骑手数'].astype(int)

    # 过滤无效站点（完单量为0且排班应出勤为0）
    site_summary = site_summary[
        ~((site_summary['完单量'] == 0) & (site_summary['排班应出勤骑手数'] == 0))
    ].reset_index(drop=True)

    return site_summary


def show_dashboard(df):
    """主看板"""

    # ---------- 加载外部CSS样式 ----------
    try:
        with open("style.css", "r", encoding="utf-8") as f:
            css_content = f.read()
        st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        # 如果找不到CSS文件，忽略（或可输出警告）
        pass

    # 获取原始全量数据（用于不受时段筛选影响的指标和图表）
    original_df = st.session_state.get('cleaned_data', df)

    # ---------- 整体指标 ----------
    st.subheader("📈 整体指标")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("总记录数", len(df))  # 当前筛选后的记录数
    with col2:
        st.metric("总完单量", f"{df['全天完单量'].sum():,}")  # 当前筛选后的总完单量
    with col3:
        # 排班应出勤骑手数：基于原始全量数据，时段为“全天”且排班状态为“排班”的骑手ID去重
        scheduled_riders = original_df[(original_df['时段'] == '全天') & (original_df['排班状态'] == '排班')]['骑手ID'].nunique()
        st.metric("排班应出勤骑手数", scheduled_riders)
    with col4:
        # 实际出勤骑手数：基于原始全量数据，时段为“全天”且全天完单量大于0的骑手ID去重
        actual_attendance = original_df[(original_df['时段'] == '全天') & (original_df['全天完单量'] > 0)]['骑手ID'].nunique()
        st.metric("实际出勤骑手数", actual_attendance)

    # ---------- 站点明细表格（基于原始全量数据，不受筛选影响）----------
    st.markdown("---")
    st.subheader("📍 站点明细数据")
    site_df = compute_site_summary(original_df)
    st.dataframe(site_df, use_container_width=True, hide_index=True)

    # ---------- 可视化分析（新增出勤异常监控标签）----------
    st.subheader("📊 可视化分析")
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "站点完单排行", "出勤状况", "骑手考勤明细", "时段对比分析", "出勤异常监控"
    ])

    # 站点完单排行（基于当前筛选，但过滤掉完单量为0的站点）
    with tab1:
        site_orders = df.groupby('站点名称')['全天完单量'].sum().reset_index()
        site_orders = site_orders[site_orders['全天完单量'] > 0]  # 过滤完单量为0的站点
        site_orders = site_orders.sort_values('全天完单量', ascending=False)
        if not site_orders.empty:
            fig1 = px.bar(site_orders, x='站点名称', y='全天完单量', title="各站点完单总量",
                          color='全天完单量', color_continuous_scale='Blues')
            st.plotly_chart(fig1, use_container_width=True)
        else:
            st.info("当前筛选条件下无完单量大于0的站点")

    # 出勤状况（基于原始全量数据，不受时段筛选影响）
    with tab2:
        st.write("排班人员出勤概况")
        all_day_df = original_df[original_df['时段'] == '全天'].copy()
        all_day_unique = all_day_df.drop_duplicates(subset=['骑手ID'], keep='first')
        scheduled_count = len(all_day_unique[all_day_unique['排班状态'] == '排班'])
        attended_count = len(all_day_unique[(all_day_unique['排班状态'] == '排班') & (all_day_unique['全天完单量'] > 0)])
        not_attended_count = scheduled_count - attended_count

        if scheduled_count > 0:
            pie_data = pd.DataFrame({
                '状态': ['排班出勤', '排班未出勤'],
                '人数': [attended_count, not_attended_count]
            })
            fig3 = px.pie(pie_data, values='人数', names='状态', title='排班人员出勤比例',
                          color='状态', color_discrete_map={'排班出勤': '#2ca02c', '排班未出勤': '#d62728'})
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("暂无排班人员")

    # 骑手考勤明细（基于原始全量数据，不受时段筛选影响）
    with tab3:
        st.write("骑手考勤明细（基于全天时段）")
        all_day_unique = original_df[original_df['时段'] == '全天'].drop_duplicates(subset=['骑手ID'], keep='first').copy()
        if not all_day_unique.empty:
            rider_detail = all_day_unique[['骑手ID', '骑手姓名', '站点名称', '全天完单量', '全天有效在线时长(h)', '排班状态']]
            sort_by = st.selectbox("排序依据", ['全天完单量', '全天有效在线时长(h)'], key='rider_detail_sort')
            top_n = st.slider("显示前几名", 5, 50, 10, key='rider_detail_top')
            sorted_df = rider_detail.sort_values(by=sort_by, ascending=False).head(top_n)
            # 柱状图展示完单量
            fig = px.bar(sorted_df, x='骑手姓名', y='全天完单量', color='站点名称',
                         title=f"骑手完单量排行 (前{top_n})",
                         labels={'全天完单量': '完单量', '骑手姓名': '骑手'},
                         text_auto=True)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("无全天时段数据")

    # 时段对比分析（基于当前筛选）
    with tab4:
        st.write("各时段平均指标对比")
        period_stats = df.groupby('时段').agg({
            '时段完单量': 'mean',
            '时段有效在线时长': lambda x: x.apply(duration_to_hours).mean()
        }).reset_index()
        period_stats.columns = ['时段', '平均时段完单量', '平均时段有效在线时长(h)']
        # 过滤掉平均完单量为0的时段（可选）
        period_stats = period_stats[period_stats['平均时段完单量'] > 0]
        if not period_stats.empty:
            fig6 = px.bar(period_stats, x='时段', y='平均时段完单量', title="各时段平均完单量")
            st.plotly_chart(fig6, use_container_width=True)
            fig7 = px.bar(period_stats, x='时段', y='平均时段有效在线时长(h)', title="各时段平均有效在线时长")
            st.plotly_chart(fig7, use_container_width=True)
        else:
            st.info("当前筛选条件下无完单量数据")

    # 出勤异常监控（基于当前筛选数据，添加颜色标记）
    with tab5:
        st.subheader("出勤异常监控")
        # 筛选排班且下线（工作状态包含“下班”）
        abnormal_df = df.copy()
        abnormal_df = abnormal_df[(abnormal_df['排班状态'] == '排班') & (abnormal_df['工作状态'].str.contains('下班', na=False))]
        if not abnormal_df.empty:
            # 按骑手聚合，判断是否有背单（配送中单量 > 0）
            abnormal_grouped = abnormal_df.groupby(['骑手ID', '骑手姓名', '站点名称', '城市']).agg(
                有背单=('配送中单量', lambda x: (x > 0).any())
            ).reset_index()
            # 生成异常行为描述
            abnormal_grouped['异常行为描述'] = abnormal_grouped['有背单'].apply(
                lambda x: '排班下线配送中' if x else '排班下线且不在配送中'
            )
            # 添加颜色标记列
            abnormal_grouped['标记'] = abnormal_grouped['有背单'].apply(
                lambda x: '🟡' if x else '🔴'
            )
            # 选择输出列
            display_cols = ['城市', '站点名称', '骑手姓名', '骑手ID', '异常行为描述', '标记']
            st.dataframe(abnormal_grouped[display_cols], use_container_width=True, hide_index=True)
        else:
            st.info("无出勤异常数据")