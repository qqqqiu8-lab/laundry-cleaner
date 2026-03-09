import streamlit as st
import pandas as pd
import re
import plotly.express as px
from io import BytesIO

# --- 1. 配置 ---
st.set_page_config(page_title="洗衣片分析-全功能看板", layout="wide")
st.title("📊 洗衣片市场深度看板 (逻辑对齐版)")

# --- 2. 核心配置 ---
HEAD_BRANDS = {"earth breeze", "the clean people", "arm & hammer", "tru earth", "sheets laundry club"}
CORRECTION_MAP = {"B091JHW9B6": 13.99, "B0FY6TTGBC": 12.79, "B0G3WPX1RW": 13.98, "B0D48FXQ3N": 14.99, "B0D8LJ1ZHG": 14.99, "B0B7LC848X": 16.98}
TARGET_BRANDS = ["Earth Breeze", "SHEETS LAUNDRY CLUB", "Tru Earth", "Arm & Hammer", "Poesie", "THE CLEAN PEOPLE", "Binbata", "KIND LAUNDRY", "Cleancult", "Sudstainables", "CLEARALIF", "Soulink"]

def clean_currency(series):
    return pd.to_numeric(series.astype(str).str.replace(r'[$,￥¥,]', '', regex=True).str.strip(), errors='coerce').fillna(0)

# --- 🚀 核心改进：严格执行你的 Total_Loads 提取规则 ---
def get_total_loads(row, asin_col, title_col):
    asin = str(row[asin_col]).strip().upper()
    title = str(row[title_col]).lower()
    
    # 规则 1：特定 ASIN 强制修正 (最高优先级)
    if asin in ['B087CDX5VS', 'B097RDC9YF']:
        return 48
    if asin == 'B09LNSW6M4':
        return 72
    
    # 规则 2：按优先级从标题提取数字
    # 优先级 1: load/loads/lds
    p1 = re.search(r'(\d+)\s*(?:-| )*(?:load|lds)', title)
    if p1: return int(p1.group(1))
    
    # 优先级 2: sheet/sheets
    p2 = re.search(r'(\d+)\s*(?:-| )*(?:sheet)', title)
    if p2: return int(p2.group(1))
    
    # 优先级 3: count/ct/cnt/strips/pieces/washes/wash
    p3 = re.search(r'(\d+)\s*(?:-| )*(?:count|ct|cnt|strip|piece|wash)', title)
    if p3: return int(p3.group(1))
    
    # 优先级 4: pack/packs
    p4 = re.search(r'(\d+)\s*(?:-| )*(?:pack)', title)
    if p4: return int(p4.group(1))
    
    # 无法提取则留空
    return None

uploaded_file = st.file_uploader("📥 请上传 input.xlsx 文件", type=["xlsx"])

if uploaded_file:
    with st.spinner('🚀 正在严格按照业务规则执行分析...'):
        df = pd.read_excel(uploaded_file, sheet_name='Sheet1', dtype=str)
        cols = {'asin': 'ASIN', 'brand': '品牌', 'title': '商品标题', 'p_asin': '父ASIN', 'u': '月销量', 'w': '月销售额($)', 'p': '价格($)'}
        
        # 数据清洗 (16步逻辑)
        df['_num_w'] = clean_currency(df[cols['w']])
        df['_num_u'] = clean_currency(df[cols['u']])
        df['_num_p'] = clean_currency(df[cols['p']])
        df[cols['p_asin']] = df[cols['p_asin']].fillna("").astype(str).str.strip().str.upper()

        t_ser = df[cols['title']].fillna("").str.lower()
        neg_mask = t_ser.str.contains("color|colour|white|oz|softener|dryer|booster|dispenser|holder|blaster|paks|ounce")
        p_mask = t_ser.str.contains("powder")
        p_exc = t_ser.str.contains("powder sheet") | df[cols['asin']].isin(['B075JMVPQ3', 'B0929GD916', 'B0FXZTS6Y5'])
        df_clean = df[~(neg_mask | (p_mask & ~p_exc))].copy()
        df_clean = df_clean[~df_clean[cols['brand']].fillna("").str.lower().str.strip().isin(["amazon basics", "all", "gain", "tide", "clorox", "blueland"])]
        df_clean = df_clean[df_clean[cols['title']].fillna("").str.lower().str.contains("strips|sheets")]
        df_clean = df_clean.sort_values('_num_w', ascending=True).drop_duplicates(subset=[cols['asin']]).drop_duplicates(subset=[cols['p_asin']])
        
        # 校准与计算
        def get_correct_w(row):
            pa = row[cols['p_asin']]
            return round(CORRECTION_MAP[pa] * row['_num_u'], 2) if pa in CORRECTION_MAP else row['_num_w']
        
        df_clean['_final_w'] = df_clean.apply(get_correct_w, axis=1)
        
        # 🚀 应用你最开始给的 Total_Loads 提取逻辑
        df_clean['Total_Loads'] = df_clean.apply(get_total_loads, args=(cols['asin'], cols['title']), axis=1)
        df_clean['Per_Load'] = df_clean['_num_p'] / df_clean['Total_Loads']

        # --- PHASE 3: 生成五大核心 Sheet ---
        # Sheet 2: 基础数据
        s2 = pd.DataFrame({
            'ASIN': df_clean[cols['asin']], '品牌': df_clean[cols['brand']], '商品标题': df_clean[cols['title']],
            '月销量': df_clean['_num_u'], '月销售额($)': df_clean['_final_w'], 
            '价格($)': df_clean['_num_p'], 'Total_Loads': df_clean['Total_Loads'], 
            'Load成本': df_clean['Per_Load'].round(3)
        })
        tw, tu = s2['月销售额($)'].sum(), s2['月销量'].sum()

        # Sheet 3: 价格带分析
        p_bins = s2['价格($)']
        s3 = pd.DataFrame([
            ["<$10", len(s2[p_bins<10]), s2[p_bins<10]['月销售额($)'].sum()],
            ["$10-14", len(s2[(p_bins>=10)&(p_bins<14)]), s2[(p_bins>=10)&(p_bins<14)]['月销售额($)'].sum()],
            ["$14-20", len(s2[(p_bins>=14)&(p_bins<20)]), s2[(p_bins>=14)&(p_bins<20)]['月销售额($)'].sum()],
            [">$20", len(s2[p_bins>=20]), s2[p_bins>=20]['月销售额($)'].sum()]
        ], columns=["价格带", "链接数", "月销售额"])
        s3['占比%'] = (s3['月销售额']/tw*100).round(2).astype(str)+'%'

        # Sheet 4: Load 成本分布
        l_bins = s2['Load成本']
        s4 = pd.DataFrame([
            ["<$0.1", len(s2[l_bins<0.1]), s2[l_bins<0.1]['月销售额($)'].sum()],
            ["$0.1-0.2", len(s2[(l_bins>=0.1)&(l_bins<0.2)]), s2[(l_bins>=0.1)&(l_bins<0.2)]['月销售额($)'].sum()],
            [">$0.2", len(s2[l_bins>=0.2]), s2[l_bins>=0.2]['月销售额($)'].sum()]
        ], columns=["Load成本段", "链接数", "月销售额"])
        s4['占比%'] = (s4['月销售额']/tw*100).round(2).astype(str)+'%'

        # Sheet 5: 品牌分析
        brand_data = []
        for b in TARGET_BRANDS:
            b_df = s2[s2['品牌'].str.lower().str.strip() == b.lower().strip()]
            bw = b_df['月销售额($)'].sum()
            avg_l = b_df[b_df['Load成本']>0]['Load成本'].mean()
            brand_data.append([b, len(b_df), b_df['月销量'].sum(), round(bw,2), f"{(bw/tw*100):.2f}%" if tw else "0%", f"${avg_l:.3f}" if avg_l else "N/A"])
        s5 = pd.DataFrame(brand_data, columns=["品牌名", "链接数", "总销量", "总销售额", "市占率%", "平均Load成本"])

        # --- 4. 看板展示 ---
        st.subheader("📊 实时市场洞察")
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(px.pie(s3, values='月销售额', names='价格带', title='价格带占比(Sheet3)', hole=0.4), use_container_width=True)
        with c2:
            st.plotly_chart(px.bar(s5, x='总销售额', y='品牌名', orientation='h', title='品牌规模对比(Sheet5)', color='总销售额'), use_container_width=True)
        
        st.subheader("📋 品牌竞争力详表")
        st.dataframe(s5, use_container_width=True)

        # --- 5. 导出 ---
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_clean.to_excel(writer, sheet_name='Sheet1_清洗结果', index=False)
            s2.to_excel(writer, sheet_name='Sheet2_核心指标', index=False)
            s3.to_excel(writer, sheet_name='Sheet3_价格带分析', index=False)
            s4.to_excel(writer, sheet_name='Sheet4_Load分析', index=False)
            s5.to_excel(writer, sheet_name='Sheet5_品牌分析汇总', index=False)
        
        st.success("✅ 分析完成！")
        st.download_button("📥 下载完整 5-Sheet 联动报告", data=output.getvalue(), file_name="洗衣片深度分析报告_对齐规则版.xlsx")
