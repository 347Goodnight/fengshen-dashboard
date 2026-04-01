import streamlit as st
import pandas as pd
from datetime import datetime
from data_cleaner import clean_attendance_data
from visualizations import show_dashboard

st.set_page_config(page_title="实时出勤监控", layout="wide")
st.title("📊 实时出勤监控")

# 初始化 session_state
if 'cleaned_data' not in st.session_state:
    st.session_state.cleaned_data = None
if 'report_date' not in st.session_state:
    st.session_state.report_date = None

# ---------- 顶部：上传和日期设置 ----------
col_upload, col_date, col_btn, col_clear = st.columns([2, 1, 1, 1])
with col_upload:
    uploaded_file = st.file_uploader("上传Excel文件", type=["xlsx", "xls"], key="upload_attendance")
with col_date:
    report_date = st.date_input("考勤日期", value=datetime.today())
with col_btn:
    process_btn = st.button("🚀 开始清洗", use_container_width=True)
with col_clear:
    if st.button("清除数据", use_container_width=True):
        st.session_state.cleaned_data = None
        st.rerun()

# 如果点击了按钮，并且有上传文件，则进行清洗并保存到 session_state
if process_btn and uploaded_file is not None:
    with st.spinner("正在读取文件..."):
        df_raw = pd.read_excel(uploaded_file)
    with st.spinner("正在清洗数据..."):
        try:
            df_cleaned = clean_attendance_data(df_raw, report_date)
            st.session_state.cleaned_data = df_cleaned
            st.session_state.report_date = report_date
            st.success("数据清洗完成！")
            st.rerun()
        except Exception as e:
            st.error(f"数据清洗失败：{e}")
            st.session_state.cleaned_data = None


# ================== 普通下拉多选框（带状态保持） ==================
def multiselect_simple(label, options, key):
    """
    生成一个普通的下拉多选框，自动保持选择状态，并过滤无效选项
    """
    if key in st.session_state:
        # 过滤掉不在当前选项中的值（防止选项变化后出现无效选项）
        st.session_state[key] = [v for v in st.session_state[key] if v in options]
    else:
        # 第一次运行时默认全选
        st.session_state[key] = options[:]

    # 下拉多选框，隐藏内置标签（因为外层已有标题）
    selected = st.multiselect(label, options, key=key, label_visibility="collapsed")
    return selected


# ===========================================================

# 如果 session_state 中有数据，则显示筛选界面
if st.session_state.cleaned_data is not None:
    df_cleaned = st.session_state.cleaned_data

    # ========== 固定筛选模块开始 ==========
    st.markdown('<div class="sticky-filter">', unsafe_allow_html=True)
    st.markdown("---")
    st.subheader("🔍 数据筛选")

    # 第一行：城市 + 站点
    row1_left, row1_right = st.columns(2)
    with row1_left:
        st.markdown("**选择城市**")
        all_cities = sorted(df_cleaned['城市'].astype(str).unique())
        cities_selected = multiselect_simple("城市", all_cities, "city_selector")

    with row1_right:
        st.markdown("**选择站点**")
        # 根据所选城市过滤站点
        site_options = sorted(df_cleaned[df_cleaned['城市'].isin(cities_selected)]['站点名称'].astype(str).unique())
        sites_selected = multiselect_simple("站点", site_options, "site_selector")

    # 第二行：时段 + 排班状态 + 工作状态
    row2_left, row2_mid, row2_right = st.columns(3)
    with row2_left:
        st.markdown("**选择时段**")
        period_options = sorted(df_cleaned['时段'].astype(str).unique())
        periods_selected = multiselect_simple("时段", period_options, "period_selector")
    with row2_mid:
        st.markdown("**排班状态**")
        schedule_options = sorted(df_cleaned['排班状态'].astype(str).unique())
        schedule_status_selected = multiselect_simple("排班状态", schedule_options, "schedule_selector")
    with row2_right:
        st.markdown("**工作状态**")
        work_options = sorted(df_cleaned['工作状态'].astype(str).unique())
        work_status_selected = multiselect_simple("工作状态", work_options, "work_selector")

    # 第三行：骑手搜索
    col_name, col_id = st.columns(2)
    with col_name:
        rider_name_search = st.text_input("骑手姓名包含", placeholder="输入关键字")
    with col_id:
        rider_id_search = st.text_input("骑手ID包含", placeholder="输入ID")

    st.markdown('</div>', unsafe_allow_html=True)
    # ========== 固定筛选模块结束 ==========

    # 应用筛选
    mask = (
            df_cleaned['城市'].isin(cities_selected) &
            df_cleaned['站点名称'].isin(sites_selected) &
            df_cleaned['时段'].isin(periods_selected) &
            df_cleaned['排班状态'].isin(schedule_status_selected) &
            df_cleaned['工作状态'].isin(work_status_selected)
    )
    if rider_name_search:
        mask &= df_cleaned['骑手姓名'].str.contains(rider_name_search, na=False)
    if rider_id_search:
        mask &= df_cleaned['骑手ID'].str.contains(rider_id_search, na=False)

    df_filtered = df_cleaned[mask]

    # 显示筛选结果数量
    st.info(f"当前筛选结果：{len(df_filtered)} 行")

    # 显示清洗后表格（带筛选）
    st.subheader("✅ 清洗后数据")
    st.dataframe(df_filtered, use_container_width=True, hide_index=True)

    # 调用可视化模块
    show_dashboard(df_filtered)

    # 下载按钮
    csv = df_filtered.to_csv(index=False).encode('utf-8-sig')
    st.download_button("📥 下载筛选后数据", csv, "filtered_attendance.csv")

else:
    st.info("请在上方上传Excel文件并点击“开始清洗”")