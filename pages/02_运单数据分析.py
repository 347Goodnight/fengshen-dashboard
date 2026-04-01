import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from data_cleaner import clean_order_data

st.set_page_config(page_title="运单数据分析", layout="wide")
st.title("📦 运单数据分析")

# 初始化 session_state
if 'order_cleaned_data' not in st.session_state:
    st.session_state.order_cleaned_data = None
if 'order_report_date' not in st.session_state:
    st.session_state.order_report_date = None

# ---------- 顶部：上传和日期设置 ----------
col_upload, col_date, col_btn, col_clear = st.columns([2, 1, 1, 1])
with col_upload:
    uploaded_file = st.file_uploader("上传运单Excel文件", type=["xlsx", "xls"], key="upload_order")
with col_date:
    report_date = st.date_input("考勤日期", value=datetime.today())
with col_btn:
    process_btn = st.button("🚀 开始清洗", use_container_width=True)
with col_clear:
    if st.button("清除数据", use_container_width=True):
        st.session_state.order_cleaned_data = None
        st.rerun()

# 如果点击了按钮，并且有上传文件，则进行清洗并保存到 session_state
if process_btn and uploaded_file is not None:
    with st.spinner("正在读取文件..."):
        df_raw = pd.read_excel(uploaded_file)
    with st.spinner("正在清洗数据..."):
        try:
            df_cleaned = clean_order_data(df_raw, report_date)
            st.session_state.order_cleaned_data = df_cleaned
            st.session_state.order_report_date = report_date
            st.success("数据清洗完成！")
            st.rerun()
        except Exception as e:
            st.error(f"数据清洗失败：{e}")
            st.session_state.order_cleaned_data = None

# 如果 session_state 中有数据，则显示
if st.session_state.order_cleaned_data is not None:
    df_cleaned = st.session_state.order_cleaned_data

    # ========== 筛选模块 ==========
    st.markdown('<div class="sticky-filter">', unsafe_allow_html=True)
    st.markdown("---")
    st.subheader("🔍 数据筛选")

    # 第一行：城市 + 站点
    row1_left, row1_right = st.columns(2)
    with row1_left:
        st.markdown("**选择城市**")
        all_cities = sorted(df_cleaned['城市'].astype(str).unique())
        cities_selected = st.multiselect(
            "城市",
            all_cities,
            default=all_cities,
            key="city_order",
            label_visibility="collapsed"
        )
    with row1_right:
        st.markdown("**选择站点**")
        site_options = sorted(
            df_cleaned[df_cleaned['城市'].isin(cities_selected)]['站点名称'].astype(str).unique()
        )
        sites_selected = st.multiselect(
            "站点",
            site_options,
            default=site_options,
            key="site_order",
            label_visibility="collapsed"
        )

    # 第二行：骑手搜索
    col_name, col_id = st.columns(2)
    with col_name:
        rider_name_search = st.text_input("骑手姓名包含", placeholder="输入关键字")
    with col_id:
        rider_id_search = st.text_input("骑手ID包含", placeholder="输入ID")

    st.markdown('</div>', unsafe_allow_html=True)

    # 应用筛选
    mask = (
        df_cleaned['城市'].isin(cities_selected) &
        df_cleaned['站点名称'].isin(sites_selected)
    )
    if rider_name_search:
        mask &= df_cleaned['骑手姓名'].str.contains(rider_name_search, na=False)
    if rider_id_search:
        mask &= df_cleaned['骑手ID'].astype(str).str.contains(rider_id_search, na=False)

    df_filtered = df_cleaned[mask]

    # 显示筛选结果数量
    st.info(f"当前筛选结果：{len(df_filtered)} 行")

    # 显示清洗后表格（百分比列格式化为 %）
    st.subheader("✅ 清洗后数据")
    st.dataframe(
        df_filtered,
        use_container_width=True,
        hide_index=True,
        column_config={
            "妥投率": st.column_config.NumberColumn("妥投率", format="%.2f%%"),
            "T8准时率": st.column_config.NumberColumn("T8准时率", format="%.2f%%")
        }
    )

    # ---------- 整体指标 ----------
    st.subheader("📈 整体指标")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        total_riders = len(df_filtered)
        st.metric("骑手数", total_riders)
    with col2:
        total_orders = df_filtered['推单量'].sum()
        st.metric("总推单量", f"{total_orders:,}")
    with col3:
        total_delivered = df_filtered['完单量'].sum()
        st.metric("总完单量", f"{total_delivered:,}")
    with col4:
        total_t8_overtime = df_filtered['T8超时单'].sum()
        total_t8_timely_rate = ((total_delivered - total_t8_overtime) / total_delivered * 100) if total_delivered > 0 else 0
        st.metric("总完单T8准时率", f"{total_t8_timely_rate:.2f}%")

    # ---------- 可视化分析（使用tabs切换）----------
    st.subheader("📊 可视化分析")
    tab1, tab2 = st.tabs(["站点T8准时率排行", "骑手T8准时率排行"])

    with tab1:
        # 站点T8准时率排行（低红高绿）
        site_stats = df_filtered.groupby('站点名称').agg({
            '完单量': 'sum',
            'T8超时单': 'sum'
        }).reset_index()
        site_stats['准时率'] = ((site_stats['完单量'] - site_stats['T8超时单']) / site_stats['完单量'] * 100).round(2)
        site_stats = site_stats.sort_values('准时率', ascending=True).head(10)  # 准时率最低的10个站点
        fig1 = px.bar(site_stats, x='准时率', y='站点名称', orientation='h',
                      title='站点T8准时率排行（倒序，低红高绿）',
                      labels={'准时率': '准时率 (%)', '站点名称': ''},
                      color='准时率', color_continuous_scale='RdYlGn',  # 低红高绿
                      text_auto='.2f')
        st.plotly_chart(fig1, use_container_width=True)

    with tab2:
        # 骑手T8准时率排行（竖向条形，带排序控件和数量选择）
        col_control1, col_control2 = st.columns(2)
        with col_control1:
            sort_order = st.selectbox("排序依据",
                                       ["准时率从低到高", "准时率从高到低",
                                        "T8超时单数量从多到少", "T8超时单数量从少到多"],
                                       key="rider_sort")
        with col_control2:
            top_n = st.slider("显示前几名", min_value=5, max_value=50, value=10, step=5, key="rider_top")

        # 根据排序获取数据
        if sort_order == "准时率从低到高":
            rider_stats = df_filtered[['骑手姓名', 'T8准时率', 'T8超时单']].sort_values('T8准时率', ascending=True).head(top_n)
        elif sort_order == "准时率从高到低":
            rider_stats = df_filtered[['骑手姓名', 'T8准时率', 'T8超时单']].sort_values('T8准时率', ascending=False).head(top_n)
        elif sort_order == "T8超时单数量从多到少":
            rider_stats = df_filtered[['骑手姓名', 'T8准时率', 'T8超时单']].sort_values('T8超时单', ascending=False).head(top_n)
        else:  # "T8超时单数量从少到多"
            rider_stats = df_filtered[['骑手姓名', 'T8准时率', 'T8超时单']].sort_values('T8超时单', ascending=True).head(top_n)

        # 竖向条形图：x为骑手姓名，y为准时率
        fig2 = px.bar(rider_stats, x='骑手姓名', y='T8准时率', orientation='v',
                      title=f'骑手T8准时率排行 ({sort_order})',
                      labels={'T8准时率': '准时率 (%)', '骑手姓名': ''},
                      color='T8准时率', color_continuous_scale='RdYlGn',  # 低红高绿
                      text_auto='.2f',
                      hover_data={'骑手姓名': True, 'T8准时率': ':.2f', 'T8超时单': True})
        fig2.update_traces(textposition='outside')
        fig2.update_layout(showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)

    # 下载按钮
    csv = df_filtered.to_csv(index=False).encode('utf-8-sig')
    st.download_button("📥 下载筛选后数据", csv, "order_analysis.csv")

else:
    st.info("请在上方上传运单Excel文件并点击“开始清洗”")