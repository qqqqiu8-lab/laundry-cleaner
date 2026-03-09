import streamlit as st
import pandas as pd
import re
import plotly.express as px
from io import BytesIO

# --- 1. 配置 ---
st.set_page_config(page_title="Market Analysis", layout="wide")
st.title("📊 洗衣片市场分析 (极致清洗+重点品牌监控)")

# --- 2. 核心规则配置 ---
CORRECTION_MAP = {
    "B091JHW9B6": 13.99, "B0FY6TTGBC": 12.79, "B0G3WPX1RW": 13.98,
    "B0D48FXQ3N": 14.99, "B0D8LJ1ZHG": 14.99, "B0B7LC848X": 16.98
}
TARGET_BRANDS = ["Earth Breeze", "SHEETS LAUNDRY CLUB", "Tru Earth", "Arm & Hammer", "Poesie", "THE CLEAN PEOPLE", "Binbata", "KIND LAUNDRY", "Cleancult", "Sudstainables", "CLEARALIF", "Soulink"]

def clean_currency(series):
    return pd.to_numeric(series.astype(str).str.replace(r'[$,￥¥,]', '', regex=True).str.strip(), errors='coerce')

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

uploaded_file = st.file_uploader("📥 请上传 input.xlsx", type=["xlsx"])

if uploaded_file:
    with st.spinner('🚀 正在处理数据...'):
        df = pd.read_excel(uploaded_file, sheet_name='Sheet1', dtype=str)
        cols = {'asin': 'ASIN', 'brand': '品牌', 'title': '商品标题', 'p_asin': '父ASIN', 'u': '月销量', 'w': '月销售额($)', 'p': '价格($)'}
        
        df['_num_w'] = clean_currency(df[cols['w']])
        df['_num_u'] = clean_currency(df[cols['u']])
        df['_num_p'] = clean_currency(df[cols['p']])
        df[cols['p_asin']] = df[cols['p_asin']].fillna("").astype(str).str.strip().str.upper()
        df[cols['asin']] = df[cols['asin']].fillna("").astype(str).str.strip().str.upper()

        # B. 极致清洗 (1-8步)
        t_ser = df[cols['title']].fillna("").str.lower()
        neg_words = ["color", "colour", "white", "oz", "softener", "dryer", "booster", "dispenser", "holder", "blaster", "paks", "ounce"]
        neg_mask = t_ser.apply(lambda x: any(word in x for word in neg_words))
        p_mask = t_ser.str.contains("powder")
        p_exc = t_ser.str.contains("powder sheet") | df[cols['asin']].isin(['B075JMVPQ3', 'B0929GD916', 'B0FXZTS6Y5'])
        df_f1 = df[~(neg_mask | (p_mask & ~p_exc))].copy()
        
        b_exc = ["amazon basics", "all", "gain", "tide", "clorox", "blueland"]
        df_f1 = df_f1[~df_f1[cols['brand']].fillna("").str.lower().str.strip().isin(b_exc)]
        df_f1 = df_f1.dropna(subset=['_num_u', '_num_w'])
        df_f1 = df_f1[df_f1[cols['title']].fillna("").str.lower().str.contains("strips|sheets")]
        
        df_f1 = df_f1.sort_values('_num_w', ascending=True)
        df_f1 = df_f1.drop_duplicates(subset=[cols['asin']], keep='first')
        df_f1 = df_f1.drop_duplicates(subset=[cols['p_asin']], keep='first')
        df_f1 = df_f1.drop_duplicates(subset=[cols['brand'], '_num_u', '_num_w'], keep='first')

        # C. 价格校准
        def calibrate_sales(row):
            pa = row[cols['p_asin']]
            if pa in CORRECTION_MAP:
                std_p = CORRECTION_MAP[pa]
                if round(row['_num_p'], 2) != round(std_p, 2):
                    return round(std_p * row['_num_u'], 2)
            return row['_num_w']
        
        df_f1['_final_w'] = df_f1.apply(calibrate_sales, axis=1)
        df_f1['Total_Loads'] = df_f1.apply(get_total_loads, args=(cols['asin'], cols['title']), axis=1)
        df_f1['Per_Load'] = df_f1['_num_p'] / df_f1['Total_Loads']

        # D. 表格生成
        s2 = pd.DataFrame({
            'ASIN': df_f1[cols['asin']], 'Brand': df_f1[cols['brand']], 'Title': df_f1[cols['title']],
            'Qty': df_f1['_num_u'], 'Sales': df_f1['_final_w'], 'Price': df_f1['_num_p'],
            'Loads': df_f1['Total_Loads'], 'PerLoad': df_f1['Per_Load'].round(3)
        })
        tw, tu = s2['Sales'].sum(), s2['Qty'].sum()

        # E. 看板布局
        st.markdown("### 📈 市场大盘汇总")
        k1, k2, k3 = st.columns(3)
        k1.metric("市场总额", f"${tw:,.2f}")
        k2.metric("市场总量", f"{tu:,.0f} Units")
        k3.metric("市场均价", f"${(tw/tu if tu else 0):.2f}")
        
        # 重点品牌看板
        st.markdown("---")
        st.markdown("### 🏆 重点品牌监控看板")
        br_res = []
        for b in TARGET_BRANDS:
            b_df = s2[s2['Brand'].str.lower().str.strip() == b.lower().strip()]
            bw = b_df['Sales'].sum()
            share = (bw / tw * 100) if tw > 0 else 0
            br_res.append({"Brand": b, "Sales": round(bw, 2), "Qty": b_df['Qty'].sum(), "Share%": round(share, 2)})
        
        s5_monitor = pd.DataFrame(br_res)
        c1, c2 = st.columns(2)
        with c1: st.plotly_chart(px.bar(s5_monitor.sort_values('Sales'), x='Sales', y='Brand', orientation='h', title='品牌销售额排名'), use_container_width=True)
        with c2: st.plotly_chart(px.pie(s5_monitor, values='Share%', names='Brand', title='品牌相对份额', hole=0.3), use_container_width=True)
        st.dataframe(s5_monitor.sort_values('Share%', ascending=False), use_container_width=True)

        # F. 导出逻辑
        p_b = s2['Price']
        s3 = pd.DataFrame([["<$10", len(s2[p_b<10]), s2[p_b<10]['Sales'].sum()], ["$10-14", len(s2[(p_b>=10)&(p_b<14)]), s2[(p_b>=10)&(p_b<14)]['Sales'].sum()], ["$14-20", len(s2[(p_b>=14)&(p_b<20)]), s2[(p_b>=14)&(p_b<20)]['Sales'].sum()], [">$20", len(s2[p_b>=20]), s2[p_b>=20]['Sales'].sum()]], columns=["Price_Range", "Count", "Sales"])
        
        lc = s2['PerLoad']
        s4 = pd.DataFrame([["<$0.1", len(s2[lc<0.1]), s2[lc<0.1]['Sales'].sum()], ["$0.1-0.2", len(s2[(lc>=0.1)&(lc<0.2)]), s2[(lc>=0.1)&(lc<0.2)]['Sales'].sum()], [">$0.2", len(s2[lc>=0.2]), s2[lc>=0.2]['Sales'].sum()]], columns=["Load_Range", "Count", "Sales"])

        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_f1.to_excel(writer, sheet_name='CleanData', index=False)
            s2.to_excel(writer, sheet_name='CoreData', index=False)
            s3.to_excel(writer, sheet_name='PriceAnalysis', index=False)
            s4.to_excel(writer, sheet_name='LoadAnalysis', index=False)
            s5_monitor.to_excel(writer, sheet_name='BrandSummary', index=False)
        
        st.success("✅ 处理完成")
        st.download_button(label="📥 下载深度分析报告", data=output.getvalue(), file_name="Market_Report.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
