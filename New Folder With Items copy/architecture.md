# 量化系统技术架构书 (architecture.md)

## 架构设计原则
- **严格解耦**：底层数据引擎逻辑与前端展示外衣（Streamlit 极简看板）完全分离开来。底层作为独立的计算与采集模块运行，生成标准格式的 JSON 数据，前端 Streamlit 模块仅进行该数据读取与交互式 UI 渲染，杜绝前后端逻辑交叉污染。
- **前端渲染规范大重构**：彻底废弃不稳定的 HTML/CSS 注入。为保证与 Streamlit 纯白底色（Bloomberg Light）的完美兼容，所有数据展示必须强制降级使用 Streamlit 原生组件（如 st.metric 与 st.progress，且 5 号板块列表废弃 st.metric 网格，全面采用原生 Pandas Styler 结合 st.dataframe 进行高密度、高对比度渲染），确保渲染的绝对确定性与极简美学。

## 4原子数据流向节点（四象映射）

### 1. **[Node 1: Trigger]**
- **调度与触发器**：负责以定时任务（Cron Job）或手动触发方式周期性激活整个数据抓取与计算链条。

### 2. **[Node 2: Transform - 3年异构时序融合与11核心行业ETF数据链路]**
- **3年异构时序融合**：
  - 统一拉取过去 3 年历史（750+ 个交易日）的数据序列。鉴于 yfinance（交易日轴）与 FRED API（自然日/周报轴，通过 `&cosd=` 限制拉取过去 3 年）时间序列不同步，强制使用 `ffill().fillna(0)` 对齐合并，消除索引错位与计算崩溃。
- **11核心行业 ETF 数据链路**：
  - 直接抓取 11 个行业核心 ETF（XLK, XLF, XLY, XLE, XLV, XLP, XLU, XLB, XLI, XLRE, XLC）的当天收盘价并计算百分比变动。在前端展示上，彻底废弃不稳定的 HTML/CSS 注入，强制降级使用 Streamlit 原生的 `st.metric` 排布网格，保障渲染的绝对确定性。

### 3. **[Node 3: Core Logic - GEX 冰山计算与 3 年流动性矩阵节点]**
- **GEX 冰山计算节点**：
  - 读取做市商绝对 Gamma 暴露风险水位（gex_last），在技术架构上正式废弃 `st.bar_chart` 柱状图及 HTML/CSS 进度条注入，全面改为使用原生的 `st.progress` 进度条进行 0.0 到 1.0 的归一化水位渲染。
- **3年滚动分位数计算**：
  - 针对美元净流动性（WALCL/1000 - WTREGEN - RRPONTSYD）进行 3 年历史滚动分位数计算：
    - 3 年滚动 10% 极度枯竭水位：`rolling(window=750, min_periods=1).quantile(0.10)`
    - 3 年滚动 90% 极度充沛水位：`rolling(window=750, min_periods=1).quantile(0.90)`
- **防零防空隔离锁（Zero-Division Patch）**：
  - 所有除法与摆动指标计算中强制使用 `safe_divide`，提供除数为零或空值的安全兜底防御。
- **缓存大坝**：
  - 暗池数据抓取配有 `@st.cache_data(ttl=21600)` 长缓存与降级机制，普通行情抓取配有一小时 TTL 缓存锁。

### 4. **[Node 4: Output]**
- **标准 JSON 持久化落地**：将 Node 3 计算出的全部指标（包含最新流动性、10%与90%分位数、11行业涨跌幅、GEX 水位等）序列化输出到 `metrics_data.json`。

## 防御性工程大坝
- 全局日志流通过安全网关重定向，杜绝内存堆栈变量及敏感 Token 裸奔。任何非预期的输出字符流，在向控制台或文件写入时，都会自动调用零信任脱敏规则。
