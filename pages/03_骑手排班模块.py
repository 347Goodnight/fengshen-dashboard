import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
from data_cleaner import clean_schedule_data

st.set_page_config(page_title="骑手排班模块", layout="wide")
st.title("📅 骑手排班模块")

# 初始化 session_state
if 'schedule_cleaned_data' not in st.session_state:
    st.session_state.schedule_cleaned_data = None
if 'schedule_report_date' not in st.session_state:
    st.session_state.schedule_report_date = None

# ---------- 顶部：上传和日期设置 ----------
col_upload, col_date, col_btn, col_clear = st.columns([2, 1, 1, 1])
with col_upload:
    uploaded_file = st.file_uploader("上传排班Excel文件", type=["xlsx", "xls"], key="upload_schedule")
with col_date:
    report_date = st.date_input("考勤日期", value=datetime.today())
with col_btn:
    process_btn = st.button("🚀 开始清洗", use_container_width=True)
with col_clear:
    if st.button("清除数据", use_container_width=True):
        st.session_state.schedule_cleaned_data = None
        st.rerun()

# 如果点击了按钮，并且有上传文件，则进行清洗并保存到 session_state
if process_btn and uploaded_file is not None:
    with st.spinner("正在读取文件..."):
        df_raw = pd.read_excel(uploaded_file)
    with st.spinner("正在清洗数据..."):
        try:
            df_cleaned = clean_schedule_data(df_raw, report_date)
            st.session_state.schedule_cleaned_data = df_cleaned
            st.session_state.schedule_report_date = report_date
            st.success("数据清洗完成！")
            st.rerun()
        except Exception as e:
            st.error(f"数据清洗失败：{e}")
            st.session_state.schedule_cleaned_data = None

# 如果 session_state 中有数据，则显示
if st.session_state.schedule_cleaned_data is not None:
    df_cleaned = st.session_state.schedule_cleaned_data

    # ========== 筛选模块 ==========
    st.markdown('<div class="sticky-filter">', unsafe_allow_html=True)
    st.markdown("---")
    st.subheader("🔍 数据筛选")

    # 第一行：城市 + 商圈片
    row1_left, row1_right = st.columns(2)
    with row1_left:
        st.markdown("**选择城市**")
        all_cities = sorted(df_cleaned['城市'].astype(str).unique())
        cities_selected = st.multiselect(
            "城市",
            all_cities,
            default=all_cities,
            key="city_schedule",
            label_visibility="collapsed"
        )
    with row1_right:
        st.markdown("**选择商圈片**")
        district_options = sorted(
            df_cleaned[df_cleaned['城市'].isin(cities_selected)]['商圈片名称'].astype(str).unique()
        )
        districts_selected = st.multiselect(
            "商圈片",
            district_options,
            default=district_options,
            key="district_schedule",
            label_visibility="collapsed"
        )

    # 第二行：时段筛选（可选）
    col_period, _ = st.columns(2)
    with col_period:
        st.markdown("**选择时段**")
        all_periods = sorted(df_cleaned['时段'].astype(str).unique())
        periods_selected = st.multiselect(
            "时段",
            all_periods,
            default=all_periods,
            key="period_schedule",
            label_visibility="collapsed"
        )

    st.markdown('</div>', unsafe_allow_html=True)

    # 应用筛选（用于表格和图表）
    mask = (
        df_cleaned['城市'].isin(cities_selected) &
        df_cleaned['商圈片名称'].isin(districts_selected) &
        df_cleaned['时段'].isin(periods_selected)
    )
    df_filtered = df_cleaned[mask].copy()

    # 将数值列转为整数
    for col in ['应排人数', '排班人数', '排班缺口', '预估单量']:
        df_filtered[col] = df_filtered[col].astype(int)

    # ---------- 宽表透视（含预估单量）----------
    st.markdown("---")
    st.subheader("📋 排班数据概览")

    date_str = st.session_state.schedule_report_date.strftime('%Y/%m/%d')
    st.markdown(f"**日期：{date_str}**")

    # 定义固定时段顺序
    periods_order = ['全天', '早餐1', '早餐2', '午高峰', '下午茶1', '下午茶2', '晚高峰', '夜宵1', '夜宵2']

    if not df_filtered.empty:
        # 透视：行 = [城市, 商圈片名称]，列 = 时段，值 = 四个指标
        df_pivot = pd.pivot_table(
            df_filtered,
            index=['城市', '商圈片名称'],
            columns='时段',
            values=['应排人数', '排班人数', '排班缺口', '预估单量'],
            fill_value=0,
            aggfunc='sum'
        )

        # 构建多层列名：先指标，再时段
        indicators = ['应排人数', '排班人数', '排班缺口', '预估单量']
        new_columns = []
        for indicator in indicators:
            for period in periods_order:
                if (indicator, period) in df_pivot.columns:
                    new_columns.append((indicator, period))
                else:
                    df_pivot[(indicator, period)] = 0
                    new_columns.append((indicator, period))
        df_pivot = df_pivot[new_columns]
        df_pivot = df_pivot.reset_index()
        columns = [('城市', ''), ('商圈片名称', '')] + new_columns
        df_pivot.columns = pd.MultiIndex.from_tuples(columns)

        # 将数值转为整数
        for col in new_columns:
            df_pivot[col] = df_pivot[col].astype(int)

        # 条件格式：对排班缺口列应用颜色
        def highlight_gap(val):
            if val > 0:
                return 'background-color: #FFB6C1'  # 浅红色（缺人）
            elif val < 0:
                return 'background-color: #90EE90'  # 浅绿色（人多）
            else:
                return ''  # 等于0无背景色

        gap_cols = [col for col in df_pivot.columns if col[0] == '排班缺口']
        styled_df = df_pivot.style.applymap(highlight_gap, subset=gap_cols)

        st.dataframe(
            styled_df,
            use_container_width=True,
            height=500
        )
    else:
        st.warning("当前筛选条件下无数据")

    # ---------- 可视化分析：商圈片时段排班概览 ----------
    st.markdown("---")
    st.subheader("📊 商圈片时段排班分析")

    if not df_filtered.empty:
        selected_district = st.selectbox("选择商圈片", options=df_filtered['商圈片名称'].unique())

        district_data = df_filtered[df_filtered['商圈片名称'] == selected_district].copy()
        district_data['时段'] = pd.Categorical(district_data['时段'], categories=periods_order, ordered=True)
        district_data = district_data.sort_values('时段')

        if not district_data.empty:
            fig = make_subplots(specs=[[{"secondary_y": True}]])

            # 准备灰色柱的文本和颜色
            texts = []
            colors = []
            for gap in district_data['排班缺口']:
                if gap > 0:
                    texts.append(f"缺{gap}人")
                    colors.append('red')
                elif gap < 0:
                    texts.append(f"多{-gap}人")
                    colors.append('blue')
                else:
                    texts.append('')
                    colors.append('rgba(0,0,0,0)')  # 透明

            # 应排人数柱状图（灰色）
            fig.add_trace(
                go.Bar(
                    x=district_data['时段'],
                    y=district_data['应排人数'],
                    name='应排人数',
                    marker_color='lightgray',
                    text=texts,
                    textposition='outside',
                    textfont=dict(color=colors, size=12),
                ),
                secondary_y=False,
            )

            # 实排人数柱状图（蓝色）
            fig.add_trace(
                go.Bar(
                    x=district_data['时段'],
                    y=district_data['排班人数'],
                    name='实排人数',
                    marker_color='steelblue',
                ),
                secondary_y=False,
            )

            # 预估单量折线图（绿色）
            fig.add_trace(
                go.Scatter(
                    x=district_data['时段'],
                    y=district_data['预估单量'],
                    name='预估单量',
                    mode='lines+markers',
                    line=dict(color='green', width=3),
                    marker=dict(size=8),
                ),
                secondary_y=True,
            )

            fig.update_xaxes(title_text="时段")
            fig.update_yaxes(title_text="人数", secondary_y=False)
            fig.update_yaxes(title_text="预估单量", secondary_y=True)

            fig.update_layout(
                title=f"{selected_district} 各时段排班概览",
                barmode='group',
                hovermode='x unified'
            )

            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("该商圈片无时段数据")
    else:
        st.warning("请先筛选数据")

    # ---------- 整体指标（仅基于全天时段，受城市和商圈片筛选影响）----------
    st.subheader("📈 整体指标")

    # 计算全天数据（受城市和商圈片筛选影响，但不受时段筛选影响）
    all_day_data = df_cleaned[
        (df_cleaned['时段'] == '全天') &
        (df_cleaned['城市'].isin(cities_selected)) &
        (df_cleaned['商圈片名称'].isin(districts_selected))
    ]
    total_should = int(all_day_data['应排人数'].sum()) if not all_day_data.empty else 0
    total_actual = int(all_day_data['排班人数'].sum()) if not all_day_data.empty else 0
    total_gap = int(all_day_data['排班缺口'].sum()) if not all_day_data.empty else 0

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("总应排人数", f"{total_should:,}")
    with col2:
        st.metric("总排班人数", f"{total_actual:,}")
    with col3:
        st.metric("总排班缺口", f"{total_gap:,}")

    # 下载按钮
    if not df_filtered.empty:
        csv = df_filtered.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 下载筛选后数据", csv, "schedule_analysis.csv")
    else:
        st.info("无数据可下载")

else:
    st.info("请在上方上传排班Excel文件并点击“开始清洗”")