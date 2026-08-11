# 大乐透 AI 预测系统 (Super Lotto AI Prediction)

基于 AI 模型的大乐透彩票预测与数据分析展示平台。展示 5 个大模型对大乐透开奖号码的预测，提供历史数据分析和命中率对比。

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
│   ├── predictions_history.json      # 历史预测对比
│   └── token_usage.json              # Token 用量统计
├── doc/
│   └── prompt2.0.md                  # AI Prompt 模板（大乐透版）
├── fetch_history/
│   └── fetch_lottery_history.py      # 爬虫脚本
├── generate_ai_prediction.py         # AI 预测自动生成
├── email_content_builder.py          # 邮件内容组装
├── email_daily_digest.py             # 每日邮件推送
├── email_smtp_utils.py               # SMTP 邮件工具
├── email_push_notify.py              # Push 触发邮件
├── test_prediction.py                # 预测格式测试
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

3. 生成 AI 预测：
   ```bash
   pip install openai
   python generate_ai_prediction.py
   ```

## 技术栈

- **前端**: HTML5, CSS3, Vanilla JS
- **后端**: Python (openai, requests, BeautifulSoup4)
- **自动化**: GitHub Actions
- **部署**: Vercel