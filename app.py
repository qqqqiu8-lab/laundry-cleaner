import streamlit as st
import pandas as pd
import re
import plotly.express as px
from io import BytesIO

# --- 1. 网页配置 ---
st.set_page_config(page_title="洗衣片分析-高级看板", layout="wide")
st.title("📊 洗衣片市场深度看板 (高级交互版)")
st.markdown("---")

# --- 2. 核心配置区 (已改为全大写 CLEARALIF) ---
HEAD_BRANDS = {"earth breeze", "the clean people", "arm & hammer", "tru earth", "sheets laundry club"}
CORRECTION_MAP = {
    "B091JHW9B6": 13.99, "B0FY6TTGBC": 12.79, "B0G3WPX1RW": 13.98,
    "B0D48FXQ3N": 14.99, "B0D8LJ1ZHG": 14.99, "B0B7LC848X": 16.98
}
TARGET_BRANDS = [
    "Earth Breeze", "SHEETS LAUNDRY CLUB", "Tru Earth", "Arm & Hammer", 
    "Poesie", "THE CLEAN PEOPLE", "Binbata", "KIND LAUNDRY", "Cleancult", 
    "Sudstainables", "CLEARALIF"
]

def clean_currency(series):
    return pd.to_numeric(
        series.astype(str).str.replace(r'[$,￥¥,]', '', regex=True).str.strip(),
        errors='coerce'
    ).fillna(0)

# --- 3. 网页取数接口 ---
uploaded_file = st.file_uploader("📥 上传原始 input.xlsx 文件", type=["xlsx"])

if uploaded_file:
    with st.spinner('🚀 正在生成看板...'):
        df = pd.read_excel(uploaded_file, sheet_name='Sheet1', dtype=str)
        cols = {'asin': 'ASIN', 'brand': '品牌', 'title': '商品标题', 
                'p_asin': '父ASIN', 'u': '月销量', 'w': '月销售额($)', 'p': '价格($)'}

        df['_num_w'] = clean_currency(df[cols['w']])
        df['_num_u'] = clean_currency(df[cols['u']])
        df['_num_p'] = clean_currency(df[cols['p']])
        df[cols['p_asin']] = df[cols['p_asin']].fillna("").astype(str).str.strip().str.upper()

        t_ser = df[cols['title']].fillna("").str.lower()
        neg_mask = t_ser.str.contains("color|colour|white|oz|softener|dryer|booster|dispenser|holder|blaster|paks|ounce")
        p_mask = t_ser.str.contains("powder")
        p_exc = t_ser.str.contains("powder sheet") | df[cols['asin']].isin(['B075JMVPQ3', 'B0929GD916', 'B0FXZTS6Y5'])
        
        df_clean = df[~(neg_mask | (p_mask & ~p_exc))].copy()
        b_exc = ["amazon basics", "all", "gain", "tide", "clorox", "blueland"]
        df_clean = df_clean[~df_clean[cols['brand']].fillna("").str.lower().str.strip().isin(b_exc)]
        df_clean = df_clean[df_clean[cols['title']].fillna("").str.lower().str.contains("strips|sheets")]

        df_clean = df_clean.sort_values('_num_w', ascending=True)
        df_clean = df_clean.drop_duplicates(subset=[cols['asin']]).drop_duplicates(subset=[cols['p_asin']])
        df_clean = df_clean.drop_duplicates(subset=[cols['brand'], cols['u'], cols['w']])

        def get_correct_w(row):
            pa = row[cols['p_asin']]
            if pa in CORRECTION_MAP:
                return round(CORRECTION_MAP[pa] * row['_num_u'], 2)
            return row['_num_w']
        
        df_clean['_final_w'] = df_clean.apply(get_correct_w, axis=1)

        sheet2 = pd.DataFrame({
            'ASIN': df_clean[cols['asin']], '品牌': df_clean[cols['brand']],
            '月销量': df_clean['_num_u'], '月销售额($)': df_clean['_final_w'], '价格($)': df_clean['_num_p']
        })

        total_u, total_w = sheet2['月销量'].sum(), sheet2['月销售额($)'].sum()

        # --- 4. 可视化看板 ---
        m1, m2, m3 = st.columns(3)
        m1.metric("市场总销售额", f"${total_w:,.0f}")
        m2.metric("市场总销量", f"{total_u:,.0f} units")
        m3.metric("市场均价", f"${(total_w/total_u if total_u else 0):.2f}")

        col1, col2 = st.columns(2)
        with col1:
            p_col = sheet2['价格($)']
            p_data = pd.DataFrame({
                "价格区间": ["<$10", "$10-14", "$14-20", ">$20"],
                "销售额": [
                    sheet2[p_col < 10]['月销售额($)'].sum(),
                    sheet2[(p_col >= 10) & (p_col < 14)]['月销售额($)'].sum(),
                    sheet2[(p_col >= 14) & (p_col < 20)]['月销售额($)'].sum(),
                    sheet2[p_col >= 20]['月销售额($)'].sum()
                ]
            })
            fig_pie = px.pie(p_data, values='销售额', names='价格区间', title='价格分布占比', hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)

        with col2:
            brand_res = []
            for b in TARGET_BRANDS:
                b_df = sheet2[sheet2['品牌'].str.lower().str.strip() == b.lower().strip()]
                bw = b_df['月销售额($)'].sum()
                brand_res.append({'品牌': b, '销售额': bw})
            df_plot = pd.DataFrame(brand_res).sort_values('销售额', ascending=True)
            fig_bar = px.bar(df_plot, x='销售额', y='品牌', orientation='h', title='重点品牌对比', color='销售额')
            st.plotly_chart(fig_bar, use_container_width=True)

        # 品牌数据表展示
        st.subheader("📋 重点监控品牌详表")
        brand_final = []
        for b in TARGET_BRANDS:
            b_df = sheet2[sheet2['品牌'].str.lower().str.strip() == b.lower().strip()]
            bw, bu = b_df['月销售额($)'].sum(), b_df['月销量'].sum()
            brand_final.append({'品牌名': b, '总销量': bu, '总销售额': round(bw, 2), '占比%': f"{(bw/total_w*100):.2f}%" if total_w else "0%"})
        df_brand_table = pd.DataFrame(brand_final).sort_values('总销售额', ascending=False)
        st.dataframe(df_brand_table, use_container_width=True)

        # --- 5. 导出逻辑 ---
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_clean.to_excel(writer, sheet_name='Sheet1', index=False)
            sheet2.to_excel(writer, sheet_name='Sheet2', index=False)
            df_brand_table.to_excel(writer, sheet_name='品牌分析汇总', index=False)
        
        st.download_button("📥 下载完整报告", data=output.getvalue(), file_name="洗衣片市场分析报告.xlsx")
