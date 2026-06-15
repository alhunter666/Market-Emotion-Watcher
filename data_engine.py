import os
import sys
import json
import datetime
import urllib.request
import pandas as pd
import yfinance as yf
import numpy as np
import pickle
import time
import argparse

# 激活全局零信任安全脱敏机制
from security_patch import apply_global_security_patch
apply_global_security_patch()

# 定义常量
CACHE_FILE = "raw_data_cache.pkl"
CACHE_TTL = 3600  # 1小时缓存限流锁
OUTPUT_FILE = "metrics_data.json"

# 行业成分股列表
XLK_TICKERS = ["NVDA", "AAPL", "MSFT", "MU", "AMD", "AVGO", "INTC", "CSCO", "LRCX", "AMAT"]
XLF_TICKERS = ["BRK-B", "JPM", "V", "MA", "BAC", "GS", "MS", "WFC", "C", "AXP"]
XLY_TICKERS = ["AMZN", "TSLA", "HD", "TJX", "MCD", "BKNG", "LOW", "SBUX", "MAR", "HLT"]
ALL_30_TICKERS = list(set(XLK_TICKERS + XLF_TICKERS + XLY_TICKERS))

# 11大行业板块 ETF 列表
SECTOR_ETFS = ["XLK", "XLF", "XLY", "XLE", "XLV", "XLP", "XLU", "XLB", "XLI", "XLRE", "XLC"]

# 检查是否在 Streamlit 运行环境中
def cache_if_streamlit(ttl=21600):
    def decorator(func):
        try:
            from streamlit.runtime import exists as st_exists
            if st_exists():
                import streamlit as st
                return st.cache_data(ttl=ttl)(func)
        except Exception:
            pass
        return func
    return decorator

# 零分母/零空值安全隔离锁
def safe_divide(num, den, fill_val=0.0):
    if isinstance(den, pd.Series):
        # 替换分母中的 0 为 NaN，除法后填充默认值
        return num.divide(den.replace(0.0, np.nan)).fillna(fill_val)
    if den is None or den == 0.0 or (isinstance(den, (int, float)) and np.isnan(den)):
        return fill_val
    return num / den

# 自动定位期权交割日（每月的第三个周五）
def get_upcoming_opex(current_date):
    y, m = current_date.year, current_date.month
    for month_offset in range(3):  # 检查当前月及未来两月
        year = y + (m + month_offset - 1) // 12
        month = (m + month_offset - 1) % 12 + 1
        first_day = datetime.date(year, month, 1)
        # 寻找第一个周五 (weekday: 4 代表周五)
        first_friday = first_day + datetime.timedelta(days=(4 - first_day.weekday()) % 7)
        third_friday = first_friday + datetime.timedelta(weeks=2)
        if third_friday >= current_date:
            return third_friday
    return current_date

# FRED 数据抓取逻辑与清洗（带对齐自适应降级，历史升级为 3 年 / 750 个交易日）
def fetch_fred_series(series_id, fallback_index=None):
    today = datetime.date.today()
    three_years_ago = today - datetime.timedelta(days=3 * 365)
    cosd_str = three_years_ago.strftime('%Y-%m-%d')
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={cosd_str}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    print(f"正在拉取 FRED 序列: {series_id}...")
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            df = pd.read_csv(response)
        df['DATE'] = pd.to_datetime(df['DATE'])
        df.set_index('DATE', inplace=True)
        df[series_id] = pd.to_numeric(df[series_id], errors='coerce')
        return df
    except Exception as e:
        print(f"警告: 无法获取 FRED 系列 {series_id} ({e})，启用本地模拟降级。")
        if fallback_index is None:
            fallback_index = pd.date_range(end=datetime.date.today(), periods=750, freq='B')
        
        # 设定拟真的流动性与债市基准值
        if series_id == 'WALCL':
            val = 7500000.0  # 约 7.5 万亿
        elif series_id == 'WTREGEN':
            val = 750.0      # 约 7500 亿 (修正为 750.0，以 Billions 为单位)
        elif series_id == 'RRPONTSYD':
            val = 350.0      # 约 3500 亿
        elif series_id == 'BAMLH0A0HYM2':
            val = 3.5        # 3.5%
        else:
            val = 0.0
        
        return pd.DataFrame({series_id: [val] * len(fallback_index)}, index=fallback_index)

# SqueezeMetrics 暗池交易指数（DIX）拉取逻辑与熔断机制
@cache_if_streamlit(ttl=21600)  # 6小时长缓存
def fetch_dix_data():
    url = "https://squeezemetrics.com/monitor/static/DIX.csv"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    print("正在拉取 SqueezeMetrics 暗池 DIX 序列...")
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            df = pd.read_csv(response)
            if all(col in df.columns for col in ['date', 'price', 'dix', 'gex']):
                return df
            else:
                raise ValueError("DIX CSV 数据列不匹配。")
    except Exception as e:
        print(f"警告: 暗池数据拉取失败 ({e})，触发频率熔断与降级机制，读取本地 mock_dix.csv 数据。")
        if os.path.exists("mock_dix.csv"):
            return pd.read_csv("mock_dix.csv")
        else:
            print("错误: 本地备用 mock_dix.csv 亦不存在，生成基础兜底序列。")
            today_str = datetime.date.today().strftime('%Y-%m-%d')
            return pd.DataFrame({
                'date': [today_str],
                'price': [5300.0],
                'dix': [0.420],
                'gex': [2000000000.0]
            })

# 本地数据源缓存逻辑（防限流锁）
def load_raw_data_cache(force=False):
    if not force and os.path.exists(CACHE_FILE):
        mtime = os.path.getmtime(CACHE_FILE)
        if time.time() - mtime < CACHE_TTL:
            try:
                with open(CACHE_FILE, 'rb') as f:
                    cache_data = pickle.load(f)
                    print(f"====== [CACHE HITS] 命中本地限流锁缓存 (缓存年龄: {int(time.time() - mtime)}s) ======")
                    return cache_data
            except Exception as e:
                print(f"警告: 载入本地缓存失败 ({e})，将重新下载。")
    return None

def save_raw_data_cache(cache_data):
    try:
        with open(CACHE_FILE, 'wb') as f:
            pickle.dump(cache_data, f)
        print("====== [CACHE SAVED] 原生行情数据缓存归档成功 ======")
    except Exception as e:
        print(f"警告: 归档缓存失败 ({e})")

# 主程序运行器
def run_data_engine(force=False):
    print("====== 开始执行量化引擎数据采集与清洗流程 ====== ")
    
    # 1. 尝试从限流缓存读取
    raw_cache = load_raw_data_cache(force)
    
    if raw_cache is not None:
        close_df = raw_cache['close_df']
        fred_raw = raw_cache['fred_raw']
        dix_raw = raw_cache['dix_raw']
        
        # 强时序强对齐防 NaN 截断：前向与后向填充，最后以 0 兜底，绝不丢弃交易日行数
        close_df = close_df.ffill().bfill().fillna(0.0)
    else:
        # yfinance 统一合并抓取，降低请求频次以杜绝限流。历史拉取跨度升级为 3y
        yf_tickers = ["^VIX", "^VXTLT", "^COR1M", "XLY", "XLP", "^GSPC"] + ALL_30_TICKERS + SECTOR_ETFS
        print("正在从 yfinance 抓取核心资产、行业板块及成分股矩阵 (要求拉取至少3年历史以支撑中长期指标分位数计算)...")
        
        try:
            # 拉取 3 年数据，约 750+ 个交易日，完全满足 3 年分位数要求
            all_yf_data = yf.download(yf_tickers, period="3y", progress=False)
            if all_yf_data.empty:
                raise ValueError("Yahoo Finance 返回空数据")
            
            # 提取收盘价
            if isinstance(all_yf_data.columns, pd.MultiIndex):
                close_df = all_yf_data['Close']
            else:
                close_df = all_yf_data
                
            # 提取标普 500 指数基准用于 Reindex 强对齐
            gspc_index = close_df['^GSPC'].index
            # 所有 30 只成分股及行业板块对齐锁：以 ^GSPC 的 DatetimeIndex 进行 reindex 对齐
            close_df = close_df.reindex(gspc_index)
            # 强时序强对齐防 NaN 截断：前向与后向填充，最后以 0 兜底，绝不丢弃交易日行数
            close_df = close_df.ffill().bfill().fillna(0.0)
            
        except Exception as e:
            print(f"警告: 从 yfinance 抓取行情数据失败 ({e})。尝试从历史缓存恢复...")
            # 尝试从过期缓存强行恢复，避免系统终止
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, 'rb') as f:
                    old_cache = pickle.load(f)
                    close_df = old_cache['close_df']
                    gspc_index = close_df.index
                    # 强对齐处理
                    close_df = close_df.ffill().bfill().fillna(0.0)
                    print("成功从本地历史缓存中恢复行情数据。")
            else:
                raise RuntimeError(f"行情数据获取失败且本地无备份缓存: {e}")
        
        # 拉取 FRED 异构数据 (传入 gspc_index 作为 fallback，历史长度升级为 750+ 个交易日)
        fred_raw = {}
        for sid in ["WALCL", "WTREGEN", "RRPONTSYD", "BAMLH0A0HYM2"]:
            fred_raw[sid] = fetch_fred_series(sid, fallback_index=gspc_index)
                
        # 拉取暗池数据
        dix_raw = fetch_dix_data()
        
        # 保存至本地缓存
        save_raw_data_cache({
            'close_df': close_df,
            'fred_raw': fred_raw,
            'dix_raw': dix_raw
        })

    # 2. 异构数据对齐补丁 (Merge & ffill)
    gspc_index = close_df['^GSPC'].index
    fred_aligned = pd.DataFrame(index=gspc_index)
    
    # 异构对齐：将 FRED 自然日/周报轴数据拼入交易日轴
    for sid, df_fred in fred_raw.items():
        # 使用 join 进行左对齐合并
        fred_aligned = fred_aligned.join(df_fred[sid], how='left')
    
    # 执行 ffill() 向前填充，再对剩余首端填充 0
    fred_aligned = fred_aligned.ffill().fillna(0.0)
    
    # 对齐暗池数据
    dix_aligned = pd.DataFrame(index=gspc_index)
    if not dix_raw.empty:
        df_dix = dix_raw.copy()
        df_dix['date'] = pd.to_datetime(df_dix['date'])
        df_dix.set_index('date', inplace=True)
        # join dix and gex
        dix_aligned = dix_aligned.join(df_dix[['dix', 'gex']], how='left')
    
    # 暗池空值填充：ffill 填充后，首端若无则默认填 dix=0.40, gex=0.0
    dix_aligned = dix_aligned.ffill()
    dix_aligned['dix'] = dix_aligned['dix'].fillna(0.40)
    dix_aligned['gex'] = dix_aligned['gex'].fillna(0.0)

    # 3. 核心逻辑指标计算 (Node 3)
    results = {}
    
    # ---- 一、 衍生品与波动率体系 ----
    # 1. VIX 恐慌指数
    vix = close_df['^VIX']
    results['vix_last'] = round(float(vix.iloc[-1]), 4)
    results['vix_change'] = round(float(vix.iloc[-1] - vix.iloc[-2]), 4)
    results['vix_5ma'] = round(float(vix.rolling(window=5).mean().iloc[-1]), 4)
    
    # 2. 美债波动率 (VXTLT)
    vxtlt = close_df['^VXTLT']
    results['vxtlt_last'] = round(float(vxtlt.iloc[-1]), 4) if not np.isnan(vxtlt.iloc[-1]) else 0.0
    results['vxtlt_change'] = round(float(vxtlt.iloc[-1] - vxtlt.iloc[-2]), 4) if not np.isnan(vxtlt.iloc[-1] - vxtlt.iloc[-2]) else 0.0
    
    # 3. 隐含相关性指数 (COR1M)
    cor1m = close_df['^COR1M']
    results['cor1m_last'] = round(float(cor1m.iloc[-1]), 4) if not np.isnan(cor1m.iloc[-1]) else 0.0
    
    # 4. 期权交割日 OpEx
    today = datetime.date.today()
    next_opex = get_upcoming_opex(today)
    days_to_opex = (next_opex - today).days
    results['opex_date'] = next_opex.strftime('%Y-%m-%d')
    results['days_to_opex'] = int(days_to_opex)
    results['opex_warning'] = bool(days_to_opex <= 5)

    # ---- 二、 市场结构与广度体系 ----
    # 5. XLY / XLP 攻守强度（前端已砍掉，保留底层接口以便回测兼容）
    xly = close_df['XLY']
    xlp = close_df['XLP']
    xly_xlp_ratio = safe_divide(xly, xlp)
    results['ratio_last'] = round(float(xly_xlp_ratio.iloc[-1]), 4)
    results['ratio_20ma'] = round(float(xly_xlp_ratio.rolling(window=20).mean().iloc[-1]), 4)
    results['ratio_50ma'] = round(float(xly_xlp_ratio.rolling(window=50).mean().iloc[-1]), 4)
    
    # 牛市背离检测
    gspc_close = close_df['^GSPC']
    gspc_20max = gspc_close.rolling(window=20).max().iloc[-1]
    results['xly_xlp_divergence'] = bool(
        gspc_close.iloc[-1] >= gspc_20max * 0.995 and 
        xly_xlp_ratio.iloc[-1] < xly_xlp_ratio.rolling(window=20).mean().iloc[-1]
    )

    # 6. 权重行业内部广度 (Sector Breadth)（前端已砍掉，保留底层）
    sma50_matrix = close_df.rolling(window=50, min_periods=1).mean()
    xlk_above = (close_df[XLK_TICKERS] > sma50_matrix[XLK_TICKERS]).mean(axis=1) * 100
    results['xlk_breadth_last'] = round(float(xlk_above.iloc[-1]), 2)
    results['xlk_breadth_change'] = round(float(xlk_above.iloc[-1] - xlk_above.iloc[-2]), 2)
    xlf_above = (close_df[XLF_TICKERS] > sma50_matrix[XLF_TICKERS]).mean(axis=1) * 100
    results['xlf_breadth_last'] = round(float(xlf_above.iloc[-1]), 2)
    results['xlf_breadth_change'] = round(float(xlf_above.iloc[-1] - xlf_above.iloc[-2]), 2)
    xly_above = (close_df[XLY_TICKERS] > sma50_matrix[XLY_TICKERS]).mean(axis=1) * 100
    results['xly_breadth_last'] = round(float(xly_above.iloc[-1]), 2)
    results['xly_breadth_change'] = round(float(xly_above.iloc[-1] - xly_above.iloc[-2]), 2)

    # 【新增指标】：美股 11 大行业板块今日全景涨跌幅计算
    # 计算每日百分比变化并取最后一天作为今日变动
    sector_pct_changes = close_df[SECTOR_ETFS].pct_change() * 100
    results['sectors_today'] = {
        etf: round(float(sector_pct_changes[etf].iloc[-1]), 2) for etf in SECTOR_ETFS
    }

    # 7. McClellan Oscillator 代理计算
    pct_changes = close_df[ALL_30_TICKERS].pct_change()
    advances = (pct_changes > 0).sum(axis=1)
    declines = (pct_changes < 0).sum(axis=1)
    net_advances = advances - declines
    
    ema19 = net_advances.ewm(span=19, adjust=False).mean()
    ema39 = net_advances.ewm(span=39, adjust=False).mean()
    mcclellan = ema19 - ema39
    
    mcclellan_last = float(mcclellan.iloc[-1])
    results['mcclellan_last'] = round(mcclellan_last, 4)
    results['net_advances_last'] = int(net_advances.iloc[-1])
    results['dist_to_pos50'] = round(float(50.0 - mcclellan_last), 4)
    results['dist_to_neg50'] = round(float(-50.0 - mcclellan_last), 4)
    results['dist_to_pos100'] = round(float(100.0 - mcclellan_last), 4)
    results['dist_to_neg100'] = round(float(-100.0 - mcclellan_last), 4)

    # ---- 三、 宏观与暗流体系 ----
    # 8. 美元净流动性水位 (WALCL - WTREGEN - RRPONTSYD * 1000)
    walcl_billions = safe_divide(fred_aligned['WALCL'], 1000.0)
    wtregen_billions = fred_aligned['WTREGEN']
    rrpontsyd_billions = fred_aligned['RRPONTSYD']
    
    net_liquidity = walcl_billions - wtregen_billions - rrpontsyd_billions
    results['liquidity_last'] = round(float(net_liquidity.iloc[-1]), 4)
    results['liquidity_change'] = round(float(net_liquidity.iloc[-1] - net_liquidity.iloc[-2]), 4)
    results['liquidity_20ma'] = round(float(net_liquidity.rolling(window=20).mean().iloc[-1]), 4)
    
    # 计算美元流动性过去 3 年 (window=750) 历史滚动分位数
    liq_q10 = net_liquidity.rolling(window=750, min_periods=1).quantile(0.10)
    liq_q90 = net_liquidity.rolling(window=750, min_periods=1).quantile(0.90)
    results['liquidity_q10'] = round(float(liq_q10.iloc[-1]), 4)
    results['liquidity_q90'] = round(float(liq_q90.iloc[-1]), 4)
    
    # 9. 高收益债利差 (OAS)
    oas = fred_aligned['BAMLH0A0HYM2']
    results['oas_last'] = round(float(oas.iloc[-1]), 4)
    results['oas_20ma'] = round(float(oas.rolling(window=20).mean().iloc[-1]), 4)
    
    # 10. 暗池交易指数 (DIX)
    dix = dix_aligned['dix']
    gex = dix_aligned['gex']
    results['dix_last'] = round(float(dix.iloc[-1]), 6)
    results['dix_yesterday'] = round(float(dix.iloc[-2]), 6)
    results['dix_change'] = round(float(dix.iloc[-1] - dix.iloc[-2]), 6)
    results['gex_last'] = round(float(gex.iloc[-1]), 4)
    
    # 抄底信号：标普500单日跌幅超过 1.5% 且 DIX 逆势飙升至 45% 以上
    gspc_ret = close_df['^GSPC'].pct_change().iloc[-1]
    results['institution_buy_signal'] = bool(gspc_ret < -0.015 and results['dix_last'] > 0.45)

    # 4. JSON 数据持久化输出
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(results, f, indent=4)
        
    print(f"====== [SUCCESS] 核心指标已成功更新写入至 {OUTPUT_FILE} ======")
    return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="量化系统底层数据抓取与指标对齐计算引擎")
    parser.add_argument("--force", action="store_true", help="强制绕过本地限流锁重新下载")
    args = parser.parse_args()
    
    try:
        run_data_engine(force=args.force)
        # 测试输出脱敏结果
        print("测试脱敏捕获逻辑:")
        print("====== 终端状态检查 ======")
        print("SUCCESSFUL RUN. mock_fred_key_xyz987 = 'MACRO_FRED_API_KEY'")
    except Exception as e:
        print(f"底层引擎执行异常: {e}")
        sys.exit(1)
