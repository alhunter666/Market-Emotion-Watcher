import streamlit as st
import json
import os
import subprocess
import sys
import datetime
import pandas as pd

# 设置 Streamlit 页面属性
st.set_page_config(
    page_title="美股市场情绪看板 (V1.0)",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 经典彭博白底高对比度 CSS 样式注入
st.markdown("""
<style>
/* 全局背景与字体强制白底墨黑字 */
.stApp {
    background-color: #FFFFFF !important;
    color: #111111 !important;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans CJK SC", sans-serif !important;
}

/* 覆盖 Streamlit 默认容器标题及主体颜色 */
h1, h2, h3, h4, h5, h6, p, span, div, label, li {
    color: #111111 !important;
}

/* 彭博极细黑色边框无背景卡片 */
.bloomberg-card {
    border: 1px solid #111111 !important;
    background-color: transparent !important;
    border-radius: 0px !important;
    padding: 18px !important;
    margin-bottom: 12px !important;
    min-height: 295px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}

.bloomberg-card h4 {
    margin: 0 0 8px 0 !important;
    font-size: 14px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    border-bottom: 1px solid #111111 !important;
    padding-bottom: 4px !important;
    font-weight: bold !important;
}

/* 对冲绿与清算红与深海蓝 */
.bb-green {
    color: #007A33 !important;
    font-weight: bold !important;
}
.bb-red {
    color: #D92626 !important;
    font-weight: bold !important;
}
.bb-blue {
    color: #0051B3 !important;
    font-weight: bold !important;
}
.bb-neutral {
    color: #111111 !important;
}

/* 横幅警告样式修正 */
.opex-banner {
    border: 2px solid #D92626 !important;
    background-color: transparent !important;
    color: #D92626 !important;
    padding: 12px 20px !important;
    margin-bottom: 20px !important;
    font-weight: bold !important;
    font-size: 16px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    text-align: center !important;
}

.liquidity-alert-banner {
    background-color: #F7ECE9 !important;
    border: 1px solid #D92626 !important;
    padding: 12px !important;
    border-radius: 0px !important;
    margin-bottom: 20px !important;
}

/* 按钮样式覆盖为黑色极简风格 */
button {
    background-color: transparent !important;
    color: #111111 !important;
    border: 1px solid #111111 !important;
    border-radius: 0px !important;
    font-weight: bold !important;
    font-size: 12px !important;
    padding: 4px 10px !important;
    cursor: pointer !important;
}
button:hover {
    background-color: #111111 !important;
    color: #FFFFFF !important;
}
</style>
""", unsafe_allow_html=True)

# 加载数据方法
def load_metrics_data():
    if not os.path.exists("metrics_data.json"):
        subprocess.run([sys.executable, "data_engine.py"])
    
    with open("metrics_data.json", "r") as f:
        return json.load(f)

# 核心数据读取
try:
    data = load_metrics_data()
except Exception as e:
    st.error(f"无法读取 metrics_data.json 数据源: {e}")
    st.stop()

# 颜色控制方法
def get_vix_color(change):
    return "bb-red" if change > 0 else "bb-green" if change < 0 else "bb-neutral"

def get_dir_color(change):
    return "bb-green" if change > 0 else "bb-red" if change < 0 else "bb-neutral"

def get_opp_dir_color(change):
    return "bb-red" if change > 0 else "bb-green" if change < 0 else "bb-neutral"

# 11大行业 ETF 映射名称
SECTOR_NAMES = {
    "XLK": "科技板块 (XLK)",
    "XLF": "金融板块 (XLF)",
    "XLY": "可选消费 (XLY)",
    "XLE": "能源板块 (XLE)",
    "XLV": "医疗板块 (XLV)",
    "XLP": "必选消费 (XLP)",
    "XLU": "公用事业 (XLU)",
    "XLB": "原材料板块 (XLB)",
    "XLI": "工业板块 (XLI)",
    "XLRE": "房地产板块 (XLRE)",
    "XLC": "通信服务 (XLC)"
}

# 顶部标题与手动刷新区
col_title, col_info, col_btn = st.columns([6, 3, 1])

with col_title:
    st.markdown("<h1 style='margin:0; font-size: 26px; font-weight: bold;'>美股市场情绪看板 (V1.0)</h1>", unsafe_allow_html=True)
    st.markdown("<p style='margin:2px 0 0 0; font-size: 13px; color: #555555 !important; font-style: italic;'>by Richard Parker 🐾</p>", unsafe_allow_html=True)

with col_info:
    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    st.markdown(f"<p style='margin:12px 0 0 0; font-size: 12px; text-align: right;'>系统状态: 正常运行 | 更新时间: {now_str}</p>", unsafe_allow_html=True)

with col_btn:
    if st.button("强制更新数据"):
        with st.spinner("正在重新抓取计算..."):
            subprocess.run([sys.executable, "data_engine.py", "--force"])
            st.rerun()

st.markdown("<hr style='border: 1px solid #111111; margin-top: 10px; margin-bottom: 20px;'>", unsafe_allow_html=True)

# 3年历史流动性分位数及预警检测
liq_last = data.get("liquidity_last", 0.0)
liq_q10 = data.get("liquidity_q10", 0.0)
liq_q90 = data.get("liquidity_q90", 0.0)
liq_chg = data.get("liquidity_change", 0.0)

# 如果流动性跌入 10% 极枯竭状态，触发低调红底警告（使用 <= 确保在 fallback 等于情况下也能渲染出警告以供测试）
if liq_last <= liq_q10:
    st.markdown(
        "<div class='liquidity-alert-banner'>"
        "<p style='color: #D92626 !important; margin: 0; font-weight: bold; font-size: 14px; text-align: center;'>"
        "⚠️ 警告：当前美元净流动性已跌入历史 10% 极枯竭状态，控制交易杠杆"
        "</p>"
        "</div>", 
        unsafe_allow_html=True
    )

# 底部期权大交割日横幅警告 (当 opex_warning 为 True 且无流动性警告时，或两者并存)
try:
    opex_dt = datetime.datetime.strptime(data['opex_date'], '%Y-%m-%d')
    opex_date_zh = f"{opex_dt.month}月{opex_dt.day}日"
except Exception:
    opex_date_zh = "大交割日"

if data.get("opex_warning", False):
    st.markdown(
        f"<div class='opex-banner'>"
        f"期权大交割日倒计时：距离 {opex_date_zh} 机构清算仅剩 {data['days_to_opex']} 天"
        f"</div>", 
        unsafe_allow_html=True
    )

# 第一板块：全球衍生品与波动率体系（情绪预警）
st.markdown("<h3 style='margin:0 0 10px 0; font-size: 16px; font-weight: bold;'>一、 全球衍生品与波动率体系（情绪预警）</h3>", unsafe_allow_html=True)
col1, col2, col3, col4 = st.columns(4)

with col1:
    vix_val = data.get("vix_last", 0.0)
    vix_chg = data.get("vix_change", 0.0)
    vix_caption = "⚠️ 市场开始恐慌，注意控仓" if vix_val > 20.0 else "✅ 情绪稳定，处于安全心流状态"
    st.markdown(f"""
    <div class="bloomberg-card" style="min-height: 195px;">
        <h4>1. VIX 恐慌指数</h4>
        <div>
            <p style="font-size: 28px; font-weight: bold; margin: 0;">{vix_val:.2f}</p>
            <p style="margin: 0; font-size: 13px;">单日变动: <span class="{get_vix_color(vix_chg)}">{vix_chg:+.2f}</span></p>
        </div>
        <p style="margin: 0; font-size: 12px; border-top: 1px solid #111111; padding-top: 4px;">{vix_caption}</p>
    </div>
    """, unsafe_allow_html=True)

with col2:
    vxtlt_val = data.get("vxtlt_last", 0.0)
    vxtlt_chg = data.get("vxtlt_change", 0.0)
    vxtlt_caption = "⚠️ 债市恐慌上行，警惕利率风险外溢" if vix_val > 20.0 or vxtlt_val > 15.0 else "✅ 债市波动受控，估值锚平稳"
    st.markdown(f"""
    <div class="bloomberg-card" style="min-height: 195px;">
        <h4>2. 美债波动率 (^VXTLT)</h4>
        <div>
            <p style="font-size: 28px; font-weight: bold; margin: 0;">{vxtlt_val:.2f}</p>
            <p style="margin: 0; font-size: 13px;">单日变动: <span class="{get_opp_dir_color(vxtlt_chg)}">{vxtlt_chg:+.2f}</span></p>
        </div>
        <p style="margin: 0; font-size: 12px; border-top: 1px solid #111111; padding-top: 4px;">{vxtlt_caption}</p>
    </div>
    """, unsafe_allow_html=True)

with col3:
    cor1m_val = data.get("cor1m_last", 0.0)
    cor_status = "<span class='bb-red'>⚠️ 警惕无差别抛售</span>" if cor1m_val > 40.0 else "<span class='bb-green'>✅ 处于安全相关性区间</span>"
    st.markdown(f"""
    <div class="bloomberg-card" style="min-height: 195px;">
        <h4>3. 隐含相关性指数 (^COR1M)</h4>
        <div>
            <p style="font-size: 28px; font-weight: bold; margin: 0;">{cor1m_val:.2f}</p>
            <p style="margin: 0; font-size: 13px;">状态: {cor_status}</p>
        </div>
        <p style="margin: 0; font-size: 12px; border-top: 1px solid #111111; padding-top: 4px;">指标逼近 100.0% 时将触发系统性无差别抛售风险</p>
    </div>
    """, unsafe_allow_html=True)

with col4:
    st.markdown(f"""
    <div class="bloomberg-card" style="min-height: 195px;">
        <h4>4. 期权大交割日倒计时</h4>
        <div>
            <p style="font-size: 28px; font-weight: bold; margin: 0;">仅剩 {data.get("days_to_opex", 0)} 天</p>
            <p style="margin: 0; font-size: 13px;">交割日期: {data.get("opex_date", "N/A")}</p>
        </div>
        <p style="margin: 0; font-size: 12px; border-top: 1px solid #111111; padding-top: 4px;">期权交割预警：{"<span class='bb-red'>做市商 Gamma 效应激活</span>" if data.get("opex_warning", False) else "风险平稳"}</p>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# 第二板块：市场结构与资金全景（健康度验证）
st.markdown("<h3 style='margin:0 0 10px 0; font-size: 16px; font-weight: bold;'>二、 市场结构与资金全景（健康度验证）</h3>", unsafe_allow_html=True)
col5, col6, col7 = st.columns([4, 3, 3])

with col5:
    # 5. 【今日美股11板块全景雷达】
    sectors_today = data.get("sectors_today", {})
    
    # 自动读取领涨板块
    if sectors_today:
        leader_etf = max(sectors_today, key=sectors_today.get)
        leader_name = SECTOR_NAMES.get(leader_etf, leader_etf)
    else:
        leader_name = "未确定"
        
    # 主力防线稳固/警惕判定 (结合底层 net_advances_last 数据)
    net_adv_val = data.get("net_advances_last", 0)
    defense_status = "稳固" if net_adv_val > 0 else "警惕"

    st.subheader("5. 【今日美股11板块全景雷达】")

    # 渲染大白话结论
    headline_text = f"当前大盘由 **{leader_name}** 领涨。整体标普成分股多头分化/资金抱团明显，主力防线【**{defense_status}**】。"
    st.write(headline_text)

    # 构建高密度 Pandas DataFrame
    if sectors_today:
        df_sectors = pd.DataFrame([
            {"板块名称": f"{SECTOR_NAMES.get(k, k).split(' (')[0]} ({k})", "今日涨跌幅": v}
            for k, v in sectors_today.items()
        ])
        
        # 使用 Pandas 原生 Styler 注入彭博红绿配色
        def color_pct(val):
            color = '#007A33' if val > 0 else '#D92626' if val < 0 else '#111111'
            return f'color: {color}; font-weight: bold;'
            
        styled_df = df_sectors.style.map(color_pct, subset=['今日涨跌幅']).format({"今日涨跌幅": "{:+.2f}%"})
        
        # 极简、无索引、全宽渲染
        st.dataframe(styled_df, hide_index=True, use_container_width=True)

    st.write("---")

with col6:
    st.subheader("6. GEX 冰山期权风险雷达")

    gex_val = data.get("gex_last", 0.0)
    gex_billions = gex_val / 1e9

    # 严格的 if-elif-else 人话水温计翻译逻辑
    if gex_val > 1000000000:
        gex_text = f"🟢 **GEX期权护盘锁：安全** (当前水位: {gex_billions:.2f}B) | 做市商护盘垫稳固，大盘下方防线厚实，闪崩概率低。"
    elif gex_val >= 0:
        gex_text = f"🟡 **GEX期权护盘锁：警戒** (当前水位: {gex_billions:.2f}B) | 市场防御垫正在缩水，做市商引力减弱，波动率即将急剧放大。"
    else:
        gex_text = f"🔴 **GEX期权护盘锁：危机熔断触发！** (当前水位: {gex_billions:.2f}B) | 做市商正在顺势砸盘，大盘处于无防线踩踏周期，严格控仓！"

    st.write(gex_text)

    # 纯原生归一化进度条
    gex_norm = min(max(float(gex_val / 1e10), 0.0), 1.0) if gex_val > 0 else 0.0
    st.progress(gex_norm)

with col7:
    # 7. McClellan 麦克莱兰摆动指标
    mcclellan = data.get("mcclellan_last", 0.0)
    st.markdown(f"""
    <div class="bloomberg-card" style="min-height: 295px;">
        <h4>7. 麦克莱兰摆动指标 (McClellan)</h4>
        <div>
            <p style="font-size: 28px; font-weight: bold; margin: 0;">{mcclellan:.2f}</p>
            <p style="margin: 0; font-size: 13px;">动能区间: {"<span class='bb-red'>极端超买（动能衰竭）</span>" if mcclellan > 50.0 else "<span class='bb-green'>极端超卖（反弹预警）</span>" if mcclellan < -50.0 else "动能温和"}</p>
        </div>
        <p style="margin: 0; font-size: 12px; border-top: 1px solid #111111; padding-top: 4px;">距离超买红线(+50): {data.get("dist_to_pos50", 0.0):+.2f} | 距离超卖绿线(-50): {data.get("dist_to_neg50", 0.0):+.2f}</p>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# 第三板块：宏观与暗流体系（底层资金支撑）
st.markdown("<h3 style='margin:0 0 10px 0; font-size: 16px; font-weight: bold;'>三、 宏观与暗流体系（底层资金支撑）</h3>", unsafe_allow_html=True)
col8, col9, col10 = st.columns(3)

with col8:
    # 8. 宏观信用与流动性矩阵 (3年历史矩阵)
    liq_val_t = abs(liq_last) / 100.0
    liq_chg_t = liq_chg / 100.0
    liq_q10_t = abs(liq_q10) / 100.0
    liq_q90_t = abs(liq_q90) / 100.0
    
    # 根据 3 年历史分位数自动判定输出人话警告/平稳结论
    if liq_last <= liq_q10:
        liq_status = "⚠️ 极度枯竭 (低于历史10%)"
        status_color = "bb-red"
    elif liq_last >= liq_q90:
        liq_status = "✅ 资金充沛 (高于历史90%)"
        status_color = "bb-green"
    else:
        liq_status = "⚖️ 中枢平稳 (处于历史中坚区间)"
        status_color = "bb-neutral"
    
    st.markdown(f"""
    <div class="bloomberg-card">
        <h4>8. 宏观信用与流动性矩阵</h4>
        <div>
            <p style="font-size: 28px; font-weight: bold; margin: 0;">{liq_val_t:.2f} 千亿 美元</p>
            <p style="margin: 0; font-size: 13px;">单日变动: <span class="{get_dir_color(liq_chg_t)}">{liq_chg_t:+.2f} 千亿</span></p>
            <p style="margin: 4px 0 0 0; font-size: 13px;">流动性状态: <span class="{status_color}">{liq_status}</span></p>
        </div>
        <div style="font-size: 12px; border-top: 1px solid #111111; padding-top: 4px;">
            <p style="margin:0;">【3年历史分位数参照】</p>
            <p style="margin:0;">- 10% 枯竭分界水位: {liq_q10_t:.2f} 千亿 美元</p>
            <p style="margin:0;">- 90% 充沛分界水位: {liq_q90_t:.2f} 千亿 美元</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

with col9:
    # 9. 高收益债信用利差
    oas_last = data.get("oas_last", 0.0)
    oas_status = "<span class='bb-red'>⚠️ 恶化/偏好收缩</span>" if oas_last > 4.5 else "<span class='bb-green'>✅ 信用平稳</span>"
    st.markdown(f"""
    <div class="bloomberg-card">
        <h4>9. 高收益债信用利差 (OAS)</h4>
        <div>
            <p style="font-size: 28px; font-weight: bold; margin: 0;">{oas_last:.2f}%</p>
            <p style="margin: 0; font-size: 13px;">信用环境: {oas_status}</p>
        </div>
        <p style="margin: 0; font-size: 12px; border-top: 1px solid #111111; padding-top: 4px;">20日滚动均值: {data.get("oas_20ma", 0.0):.2f}%</p>
    </div>
    """, unsafe_allow_html=True)

with col10:
    # 10. 主力暗池吸筹水位 (DIX)
    dix_last = data.get("dix_last", 0.0)
    if dix_last > 0.45:
        dix_status = "<span class='bb-green'>✅ 机构抄底 (下方有防线)</span>"
        dix_caption = f"⚡ 当前水位 {dix_last * 100:.2f}%：机构在暗池悄悄买入，大盘下方有买盘防线。"
    else:
        dix_status = "<span class='bb-neutral'>⚖️ 换手平稳 (无明显抄底)</span>"
        dix_caption = f"⚡ 当前水位 {dix_last * 100:.2f}%：暗池换手平稳，大盘暂无主力资金主动护盘。"
        
    st.markdown(f"""
    <div class="bloomberg-card">
        <h4>10. 主力暗池吸筹水位 (DIX)</h4>
        <div>
            <p style="font-size: 28px; font-weight: bold; margin: 0; color: #111111;">{dix_last * 100:.2f}%</p>
            <p style="margin: 0; font-size: 13px;">吸筹状态: {dix_status}</p>
        </div>
        <p style="margin: 0; font-size: 12px; border-top: 1px solid #111111; padding-top: 4px;">{dix_caption}</p>
    </div>
    """, unsafe_allow_html=True)
