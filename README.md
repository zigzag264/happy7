# 大乐透 AI 预测系统 (Super Lotto AI Prediction)

基于统计/机器学习模型的大乐透彩票预测与数据分析展示平台。展示 10 种统计/机器学习模型对大乐透开奖号码的预测，提供历史数据分析和命中率对比。

## 项目结构

```
happy7/
├── index.html                        # 主页面（3 个 Tab）
├── css/style.css                     # 样式
├── js/
│   ├── app.js                        # 主应用逻辑
│   ├── components.js                 # UI 组件（号码球、卡片）
│   └── data-loader.js                # 数据加载模块
├── data/
│   ├── lottery_history.json          # 历史开奖数据（前区 01-35, 后区 01-12）
│   ├── ai_predictions.json           # 当前 AI 预测
│   └── predictions_history.json      # 历史预测对比
├── strategies/
│   ├── base.py                       # 策略基类与工具函数
│   ├── runner.py                     # 策略模型运行入口
│   ├── markov_chain.py               # 马尔科夫链
│   ├── bayesian.py                   # 贝叶斯推断
│   ├── arima_model.py                # 时间序列 ARIMA
│   ├── monte_carlo.py                # 蒙特卡洛模拟
│   ├── ensemble_ml.py                # 随机森林集成
│   ├── lstm_model.py                 # LSTM 神经网络
│   ├── apriori.py                    # 关联规则 Apriori
│   ├── genetic_algorithm.py          # 遗传算法
│   ├── hmm_model.py                  # 隐马尔可夫 HMM
│   └── csp_model.py                  # 组合约束 CSP
├── fetch_history/
│   └── fetch_lottery_history.py      # 爬虫脚本
├── email_content_builder.py          # 邮件内容组装
├── email_daily_digest.py             # 每日邮件推送
├── email_smtp_utils.py               # SMTP 邮件工具
├── email_push_notify.py              # Push 触发邮件
├── test_prediction.py                # 预测格式测试
├── update_all.bat                    # 本地一键更新（Windows）
├── update_all.sh                     # 本地一键更新（Linux/Mac）
├── .github/workflows/                # 工作流配置
└── README.md
```

## 大乐透规则

- **前区号码**: 从 01-35 中选择 5 个号码（从小到大排序）
- **后区号码**: 从 01-12 中选择 2 个号码（从小到大排序）
- **开奖时间**: 每周一、三、六 21:25

## 快速开始

1. 启动本地服务器：
   ```bash
   start_server.bat  # Windows
   # 或
   python -m http.server 8000
   ```

2. 浏览器打开 `http://localhost:8000`

3. 运行统计/机器学习模型：
   ```bash
   python -m strategies.runner
   ```

## 数据更新

### 自动更新（GitHub Actions）

| 工作流 | 调度时间 | 说明 |
|--------|---------|------|
| 开奖数据抓取 | 每天 21:40 + 12:00 | 开奖后 15 分钟自动抓取 500彩票网最新数据 |
| 模型预测生成 | 每天 22:00 | 数据更新后自动运行 10 个统计/ML 模型 |
| 每日邮件推送 | 每天 08:30 + 18:00 | 定时发送当日预测汇总邮件 |
| 推送通知 | 每次 push 到 master | 代码/数据变更时发送邮件通知 |

也可在 GitHub 仓库 → Actions 页面手动触发 `workflow_dispatch`。

### 手动更新（本地）

在项目根目录运行一键更新脚本，自动完成「拉取代码 → 抓取数据 → 运行模型 → 提交推送」：

```bash
update_all.bat    # Windows
# 或
./update_all.sh   # Linux / Mac
```

脚本流程：
1. `git pull` — 拉取 GitHub 最新代码
2. `fetch_history/fetch_lottery_history.py` — 抓取最新开奖数据
3. `python -m strategies.runner` — 运行 10 个统计/ML 模型生成预测
4. `git add + commit + push` — 提交并推送变更（无变更时跳过）

### 本地与线上数据一致性

```
本地文件 ← git pull ← GitHub master ← Actions 自动 commit
   ↑                                        ↓
  HTTP服务器                            Vercel 自动部署
   ↓                                        ↓
  浏览器访问                               线上站点
```

- **本地查看**: 启动 `python -m http.server 8000`，浏览器访问 `http://localhost:8000`
- **线上查看**: Vercel 自动部署，push 后约 1 分钟生效
- **保持同步**: 本地运行 `update_all.bat/sh` 或 `git pull` 即可

## 技术栈

- **前端**: HTML5, CSS3, Vanilla JS
- **后端**: Python (requests, numpy, pandas, scikit-learn)
- **自动化**: GitHub Actions
- **部署**: Vercel
