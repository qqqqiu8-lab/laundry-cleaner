import streamlit as st
import pandas as pd
import re
import plotly.express as px
from io import BytesIO

# --- 1. 配置 ---
st.set_page_config(page_title="洗衣片分析-全功能看板", layout="wide")
st.title("📊 洗衣片市场分析看板 (大盘汇总+精准校正版)")

# --- 2. 核心配置 ---
CORRECTION_MAP = {
    "B091JHW9B6": 13.99, "B0FY6TTGBC": 12.79, "B0G3WPX1RW": 13.98,
    "B0D48FXQ3N": 14.99, "B0D8LJ1ZHG": 14.99, "B0B7LC848X": 16.98
}
TARGET_BRANDS = ["Earth Breeze", "SHEETS LAUNDRY CLUB", "Tru Earth", "Arm & Hammer", "Poesie", "THE CLEAN PEOPLE", "Binbata", "KIND LAUNDRY", "Cleancult", "Sudstainables", "CLEARALIF", "Soulink"]

def clean_currency(series):
    return pd.to_numeric(series.astype(str).str.replace(r'[$,￥¥,]', '', regex=True).str.strip(), errors='coerce').fillna(0)

def get_total_loads(row, asin_col, title_col):
    asin = str(row[asin_col]).strip().upper()
    title = str(row[title_col]).lower()
    if asin in ['B087CDX5VS', 'B097RDC9YF']: return 48
    if asin == 'B09LNSW6M4': return 72
    p1 = re.search(r'(\d+)\s*(?:-| )*(?:load|lds)', title)
    if p1: return int(p1.group(1))
    p2 = re.search(r'(\d+)\s*(?:-| )*(?:sheet)', title)
    if p2: return int(p2.group(1))
    p3 = re.search(r'(\d+)\s*(?:-| )*(?:count|ct|cnt|strip|piece|wash)', title)
    if p3: return int(p3.group(1))
    p4 = re.search(r'(\d+)\s*(?:-| )*(?:pack)', title)
    if p4: return int(p4.group(1))
    return None

uploaded_file = st.file_uploader("📥 上传原始 input.xlsx 文件", type=["xlsx"])

if uploaded_file:
    with st.spinner('🚀 正在执行精准脱水清洗与大盘汇总...'):
        df = pd.read_excel(uploaded_file, sheet_name='Sheet1', dtype=str)
        cols = {'asin': 'ASIN', 'brand': '品牌', 'title': '商品标题', 'p_asin': '父ASIN', 'u': '月销量', 'w': '月销售额($)', 'p': '价格($)'}
        
        # A. 预处理
        df['_num_w'] = clean_currency(df[cols['w']])
        df['_num_u'] = clean_currency(df[cols['u']])
        df['_num_p'] = clean_currency(df[cols['p']])
        df[cols['p_asin']] = df[cols['p_asin']].fillna("").astype(str).str.strip().str.upper()
        df[cols['asin']] = df[cols['asin']].fillna("").astype(str).str.strip().str.upper()

        # B. 基础清洗
        t_ser = df[cols['title']].fillna("").str.lower()
        neg_mask = t_ser.str.contains("color|colour|white|oz|softener|dryer|booster|dispenser|holder|blaster|paks|ounce")
        p_mask = t_ser.str.contains("powder")
        p_exc = t_ser.str.contains("powder sheet") | df[cols['asin']].isin(['B075JMVPQ3', 'B0929GD916', 'B0FXZTS6Y5'])
        df_clean = df[~(neg_mask | (p_mask & ~p_exc))].copy()
        df_clean = df_clean[df_clean[cols['title']].fillna("").str.lower().str.contains("strips|sheets")]
        
        # C. 查重：保留销售额最低 (脱水)
        df_clean = df_clean.sort_values('_num_w', ascending=True)
        df_clean = df_clean.drop_duplicates(subset=[cols['asin']], keep='first')
        df_clean = df_clean.drop_duplicates(subset=[cols['p_asin']], keep='first')
        
        # D. 按需校准
        def calibrate_sales(row):
            p_asin = row[cols['p_asin']]
            if p_asin in CORRECTION_MAP:
                standard_p = CORRECTION_MAP[p_asin]
                if round(row['_num_p'], 2) != round(standard_p, 2):
                    return round(standard_p * row['_num_u'], 2)
            return row['_num_w']
        
        df_clean['_final_w'] = df_clean.apply(calibrate_sales, axis=1)
        df_clean['Total_Loads'] = df_clean.apply(get_total_loads, args=(cols['asin'], cols['title']), axis=1)
        df_clean['Per_Load'] = df_clean['_num_p'] / df_clean['Total_Loads']

        # E. 数据汇总
        s2 = pd.DataFrame({
            'ASIN': df_clean[cols['asin']], '品牌': df_clean[cols['brand']], '商品标题': df_clean[cols['title']],
            '月销量': df_clean['_num_u'], '月销售额($)': df_clean['_final_w'], 
            '价格($)': df_clean['_num_p'], 'Total_Loads': df_clean['Total_Loads'], 
            'Load成本': df_clean['Per_Load'].round(3)
        })
        
        # 计算大盘指标
        total_wealth = s2['月销售额($)'].sum()
        total_units = s2['月销量'].sum()
        market_avg_price = total_wealth / total_units if total_units > 0 else 0

        # --- 🚀 3. 看板顶部 KPI 汇总 ---
        st.markdown("### 📈 市场大盘核心指标")
        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("市场总销售额", f"${total_wealth:,.2f}")
        kpi2.metric("市场总销量", f"{total_units:,.0f} Units")
        kpi3.metric("全市场均价", f"${market_avg_price:.2f}")
        st.markdown("---")

        # --- 4. 可视化图表 ---
        # Sheet 3 & 5 数据准备
        p_bins = s2['价格($)']
        s3 = pd.DataFrame([["<$10", len(s2[p_bins<10]), s2[p_bins<10]['月销售额($)'].sum()], ["$10-14", len(s2[(p_bins>=10)&(p_bins<14)]), s2[(p_bins>=10)&(p_bins<14)]['月销售额($)'].sum()], ["$14-20", len(s2[(p_bins>=14)&(p_bins<20)]), s2[(p_bins>=14)&(p_bins<20)]['月销售额($)'].sum()], [">$20", len(s2[p_bins>=20]), s2[p_bins>=20]['月销售额($)'].sum()]], columns=["价格带", "链接数", "月销售额"])
        
        brand_data = []
        for b in TARGET_BRANDS:
            b_df = s2[s2['品牌'].str.lower().str.strip() == b.lower().strip()]
            bw = b_df['月销售额($)'].sum()
            brand_data.append([b, len(b_df), b_df['月销量'].sum(), round(bw,2), f"{(bw/total_wealth*100):.2f}%" if total_wealth else "0%"])
        s5 = pd.DataFrame(brand_data, columns=["品牌名", "链接数", "总销量", "总销售额", "市占率%"])

        c1, c2 = st.columns(2)
        with c1: st.plotly_chart(px.pie(s3, values='月销售额', names='价格带', title='价格分布占比', hole=0.4), use_container_width=True)
        with c2: st.plotly_chart(px.bar(s5.sort_values('总销售额', ascending=True), x='总销售额', y='品牌名', orientation='h', title='核心品牌竞争力对比', color='总销售额'), use_container_width=True)
        
        # --- 5. 导出 ---
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_clean.to_excel(writer, sheet_name='Sheet1_脱水清洗', index=False)
            s2.to_excel(writer, sheet_name='Sheet2_核心指标', index=False)
            s3.to_excel(writer, sheet_name='Sheet3_价格带分析', index=False)
            s5.to_excel(writer, sheet_name='Sheet5_品牌分析', index=False)
        st.download_button("📥 下载精准脱水版报告", data=output.getvalue(), file_name="洗衣片深度分析报告.xlsx")
