import streamlit as st
import pandas as pd
import re
from io import BytesIO

# --- 1. 网页界面配置 (替代本地 print) ---
st.set_page_config(page_title="洗衣片分析-生产版", layout="wide")
st.title("🧺 洗衣片市场精准分析工具 (网页生产版)")
st.info("说明：已集成 16步清洗逻辑 + 物理价格校准 + Sheet 1-5 联动统计。")

# --- 2. 核心配置区 (完全保留你原始跑通的代码配置) ---
HEAD_BRANDS = {"earth breeze", "the clean people", "arm & hammer", "tru earth", "sheets laundry club"}
CORRECTION_MAP = {
    "B091JHW9B6": 13.99, "B0FY6TTGBC": 12.79, "B0G3WPX1RW": 13.98,
    "B0D48FXQ3N": 14.99, "B0D8LJ1ZHG": 14.99, "B0B7LC848X": 16.98
}
TARGET_BRANDS = [
    "Earth Breeze", "SHEETS LAUNDRY CLUB", "Tru Earth", "Arm & Hammer", 
    "Poesie", "THE CLEAN PEOPLE", "Binbata", "KIND LAUNDRY", "Cleancult", "Sudstainables"
]

def clean_currency(series):
    """保留你原始代码中的正则清理逻辑"""
    return pd.to_numeric(
        series.astype(str).str.replace(r'[$,￥¥,]', '', regex=True).str.strip(),
        errors='coerce'
    ).fillna(0)

# --- 3. 网页取数接口：从本地文件改为上传组件 ---
uploaded_file = st.file_uploader("👉 第一步：请上传原始 input.xlsx 文件", type=["xlsx"])

if uploaded_file:
    with st.spinner('🚀 正在执行核心算法，请稍候...'):
        # --- 读取上传的文件流 ---
        df = pd.read_excel(uploaded_file, sheet_name='Sheet1', dtype=str)
        cols = {'a': df.columns[0], 'asin': 'ASIN', 'brand': '品牌', 'title': '商品标题', 
                'p_asin': '父ASIN', 'u': '月销量', 'w': '月销售额($)', 'p': '价格($)'}

        # --- Phase 1: 预处理与严格去重 (核心逻辑完全不变) ---
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

        # --- Phase 2: 物理校准销售额 (核心逻辑完全不变) ---
        def get_correct_w(row):
            pa = row[cols['p_asin']]
            if pa in CORRECTION_MAP:
                return round(CORRECTION_MAP[pa] * row['_num_u'], 2)
            return row['_num_w']
        
        df_clean['_final_w'] = df_clean.apply(get_correct_w, axis=1)

        sheet2 = pd.DataFrame({
            '#': df_clean[cols['a']], 'ASIN': df_clean[cols['asin']], '品牌': df_clean[cols['brand']],
            '商品标题': df_clean[cols['title']], '月销量': df_clean['_num_u'],
            '月销售额($)': df_clean['_final_w'], '价格($)': df_clean['_num_p']
        })

        def get_loads(row):
            a, t = str(row['ASIN']), str(row['商品标题']).lower()
            if a in ["B087CDX5VS", "B097RDC9YF"]: return 48.0
            if a == "B09LNSW6M4": return 72.0
            for p_reg in [r"(\d+)\s*[-]?\s*(load|lds)", r"(\d+)\s*[-]?\s*sheet", r"(\d+)\s*[-]?\s*(count|ct|cnt|strip|piece|wash)"]:
                m = re.search(p_reg, t)
                if m: return float(m.group(1))
            return None
        sheet2['Total_Loads'] = sheet2.apply(get_loads, axis=1)
        sheet2['Cost_per_Load'] = (sheet2['价格($)'] / sheet2['Total_Loads']).round(2)

        # --- Phase 3 & 4: 联动统计 (核心逻辑完全不变) ---
        total_u, total_w = sheet2['月销量'].sum(), sheet2['月销售额($)'].sum()
        is_head = sheet2['品牌'].str.lower().str.strip().isin(HEAD_BRANDS)

        def calc_stats(mask, no_head=False):
            target = sheet2[mask].copy()
            if no_head: target = target[~is_head]
            u, w = target['月销量'].sum(), target['月销售额($)'].sum()
            return [u, u/total_u if total_u else 0, w, w/total_w if total_w else 0]

        p_col = sheet2['价格($)']
        s3_r1, s3_r2, s3_r3, s3_r5 = calc_stats(p_col < 10), calc_stats((p_col >= 10) & (p_col < 14)), calc_stats((p_col >= 14) & (p_col < 20)), calc_stats(p_col >= 20)
        s3_r4_nohead = calc_stats((p_col >= 14) & (p_col < 20), True)
        s3_data = {
            '<10销量': s3_r1[0], '<10占比': f"{s3_r1[1]:.2%}", '<10销售额': s3_r1[2], '<10额占比': f"{s3_r1[3]:.2%}",
            '10-14销量': s3_r2[0], '10-14占比': f"{s3_r2[1]:.2%}", '10-14销售额': s3_r2[2], '10-14额占比': f"{s3_r2[3]:.2%}",
            '14-20销量': s3_r3[0], '14-20占比': f"{s3_r3[1]:.2%}", '14-20销售额': s3_r3[2], '14-20额占比': f"{s3_r3[3]:.2%}",
            '14-20非头部销量': s3_r4_nohead[0], '14-20非头部销售额': s3_r4_nohead[2],
            '20销量': s3_r5[0], '20占比': f"{s3_r5[1]:.2%}", '20销售额': s3_r5[2], '20额占比': f"{s3_r5[3]:.2%}",
            '验算总量': s3_r1[0]+s3_r2[0]+s3_r3[0]+s3_r5[0], '总销量': total_u
        }

        c_col = sheet2['Cost_per_Load']
        s4_r1, s4_r2, s4_r3 = calc_stats(c_col < 0.1), calc_stats((c_col >= 0.1) & (c_col < 0.175)), calc_stats(c_col >= 0.175)
        s4_r4_nohead = calc_stats(c_col >= 0.175, True)
        s4_data = {
            'CPL<0.1销量': s4_r1[0], '占比1': f"{s4_r1[1]:.2%}", '销售额1': s4_r1[2], '额占比1': f"{s4_r1[3]:.2%}",
            '0.1-0.175销量': s4_r2[0], '占比2': f"{s4_r2[1]:.2%}", '销售额2': s4_r2[2], '额占比2': f"{s4_r2[3]:.2%}",
            'CPL>0.175销量': s4_r3[0], '占比3': f"{s4_r3[1]:.2%}", '销售额3': s4_r3[2], '额占比3': f"{s4_r3[3]:.2%}",
            '非头部>0.175销量': s4_r4_nohead[0], '非头部额': s4_r4_nohead[2]
        }

        # Phase 5: 品牌汇总
        brand_res = []
        for b in TARGET_BRANDS:
            b_df = sheet2[sheet2['品牌'].str.lower().str.strip() == b.lower().strip()]
            bw, bu = b_df['月销售额($)'].sum(), b_df['月销量'].sum()
            brand_res.append({'品牌名': b, '有效链接数': len(b_df), '总销量': bu, '总销售额': round(bw, 2), '市场份额%': f"{(bw/total_w*100):.2f}%" if total_w else "0%"})
        df_brand = pd.DataFrame(brand_res).sort_values('总销售额', ascending=False)

        # --- 4. 导出逻辑：改为内存流下载 ---
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_clean.to_excel(writer, sheet_name='Sheet1', index=False)
            sheet2.to_excel(writer, sheet_name='Sheet2', index=False)
            pd.DataFrame([s3_data]).to_excel(writer, sheet_name='Sheet3', index=False)
            pd.DataFrame([s4_data]).to_excel(writer, sheet_name='Sheet4', index=False)
            df_brand.to_excel(writer, sheet_name='品牌分析汇总', index=False)
        
        # --- 5. 网页端下载按钮 ---
        st.success(f"🎉 处理完成！分母已锁定为: ${total_w:,.2f}")
        st.download_button(
            label="📥 第二步：点击下载全联动分析报告",
            data=output.getvalue(),
            file_name="洗衣片精准分析报告_网页版.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
