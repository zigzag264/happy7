/**
 * 主应用逻辑 - 新UI版本
 */

// 全局状态
let appData = {
    lotteryHistory: null,
    aiPredictions: null,
    predictionsHistory: null,
    tokenUsage: { records: [] }
};

// 全局错误处理
window.onerror = function(msg, src, line, col, error) {
    console.error('全局JS错误:', msg, 'at', src + ':' + line + ':' + col);
    // 隐藏加载屏，避免白屏
    const ls = document.getElementById('loadingScreen');
    if (ls) ls.style.display = 'none';
    const ma = document.getElementById('mainApp');
    if (ma) ma.style.display = 'block';
    return true;
};

// 初始化应用
async function initApp() {
    try {
        // 加载数据（容错：单文件失败不阻塞整体）
        await loadAllData();

        // 渲染UI
        renderHeroBanner();
        renderModelFilters();
        renderModelsGrid();
        renderHistoryTab();

        // 设置事件监听
        setupEventListeners();
    } catch (error) {
        console.error('初始化失败:', error);
        showErrorInPage('数据加载异常: ' + error.message);
    } finally {
        // 无论成功还是失败，都隐藏加载屏并显示主界面
        hideLoadingScreen();
    }
}

// 在页面中显示错误信息（替代 alert）
function showErrorInPage(message) {
    const ma = document.getElementById('mainApp');
    if (!ma) return;
    // 移除已有错误提示
    document.getElementById('errorBanner')?.remove();
    const banner = document.createElement('div');
    banner.id = 'errorBanner';
    banner.style.cssText = 'position:fixed;top:80px;left:50%;transform:translateX(-50%);z-index:10000;background:#fee;color:#c00;border:1px solid #f88;border-radius:8px;padding:10px 20px;font-size:14px;max-width:90vw;box-shadow:0 4px 12px rgba(0,0,0,0.15)';
    banner.innerHTML = '⚠️ ' + message + '<button onclick="this.parentElement.remove()" style="margin-left:12px;cursor:pointer;background:none;border:none;color:#c00;font-size:16px">×</button>';
    ma.appendChild(banner);
    // 30秒后自动消失
    setTimeout(() => banner.remove(), 30000);
}

// 加载所有数据（容错：单个文件失败不影响其他数据）
async function loadAllData() {
    const results = await Promise.allSettled([
        DataLoader.loadLotteryHistory(),
        DataLoader.loadPredictions(),
        DataLoader.loadPredictionsHistory(),
        DataLoader.loadTokenUsage()
    ]);

    // 历史开奖数据（必需）
    if (results[0].status === 'fulfilled') {
        appData.lotteryHistory = results[0].value;
    } else {
        console.error('加载历史开奖数据失败:', results[0].reason);
        showErrorInPage('无法加载历史开奖数据，页面功能受限');
    }

    // AI 预测数据（必需）
    if (results[1].status === 'fulfilled') {
        appData.aiPredictions = results[1].value;
    } else {
        console.error('加载 AI 预测数据失败:', results[1].reason);
        showErrorInPage('无法加载 AI 预测数据');
    }

    // 历史预测对比（可选）
    if (results[2].status === 'fulfilled') {
        appData.predictionsHistory = results[2].value;
    } else {
        console.warn('加载历史预测数据失败:', results[2].reason);
        appData.predictionsHistory = { predictions_history: [] };
    }

    // Token 用量（可选）
    if (results[3].status === 'fulfilled') {
        appData.tokenUsage = results[3].value;
    } else {
        console.warn('加载 Token 用量数据失败:', results[3].reason);
        appData.tokenUsage = { records: [] };
    }
}

// 渲染Hero Banner
function renderHeroBanner() {
    if (!appData.lotteryHistory || !appData.aiPredictions) return;

    const nextDraw = appData.lotteryHistory.next_draw;

    // 更新期号
    const heroPeriodEl = document.getElementById('heroPeriod');
    if (heroPeriodEl) heroPeriodEl.textContent = nextDraw.next_period;

    // 更新日期显示
    const heroDateDisplayEl = document.getElementById('heroDateDisplay');
    if (heroDateDisplayEl) heroDateDisplayEl.textContent = nextDraw.next_date_display;

    // 更新开奖时间
    const heroDrawTimeEl = document.getElementById('heroDrawTime');
    if (heroDrawTimeEl) heroDrawTimeEl.textContent = `${nextDraw.draw_time} 开奖`;

    // 更新预测日期
    const heroPredictionDateEl = document.getElementById('heroPredictionDate');
    if (heroPredictionDateEl) heroPredictionDateEl.textContent = appData.aiPredictions.prediction_date;

    // 倒计时 (可选功能)
    const heroCountdownEl = document.getElementById('heroCountdown');
    if (heroCountdownEl) {
        const daysUntil = calculateDaysUntil(nextDraw.next_date);
        heroCountdownEl.textContent = daysUntil > 0 ? `距离开奖仅剩 ${daysUntil} 天` : '即将开奖';
    }
}

// 当前模型类型筛选
let currentModelFilter = 'all';

// 渲染模型类型筛选按钮
function renderModelFilters() {
    const container = document.getElementById('modelFilters');
    if (!container) return;

    const filters = [
        { key: 'all', label: '全部', count: appData.aiPredictions?.models?.length || 0 },
        { key: 'llm', label: 'LLM 大模型', count: 0 },
        { key: 'statistical', label: '统计模型', count: 0 },
        { key: 'ml', label: '机器学习', count: 0 },
        { key: 'deep', label: '深度学习', count: 0 },
    ];

    (appData.aiPredictions?.models || []).forEach(m => {
        const type = m.model_type || 'llm';
        const f = filters.find(x => x.key === type);
        if (f) f.count += 1;
    });

    container.innerHTML = filters.map(f => `
        <button class="filter-btn${f.key === currentModelFilter ? ' active' : ''}" data-filter="${f.key}">
            ${f.label} <span class="filter-count">${f.count}</span>
        </button>
    `).join('');

    container.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            currentModelFilter = btn.dataset.filter;
            renderModelFilters();
            renderModelsGrid();
        });
    });
}

// 获取筛选后的模型列表
function getFilteredModels() {
    const models = appData.aiPredictions?.models || [];
    if (currentModelFilter === 'all') return models;
    return models.filter(m => (m.model_type || 'llm') === currentModelFilter);
}

// 渲染模型网格
function renderModelsGrid() {
    if (!appData.aiPredictions) return;

    const modelsGridEl = document.getElementById('modelsGrid');
    if (!modelsGridEl) return;

    // 清空现有内容
    modelsGridEl.innerHTML = '';

    // 检测预测期号是否已开奖
    const targetPeriod = appData.aiPredictions.target_period;
    const latestDraw = appData.lotteryHistory?.data?.[0];
    let actualResult = null;

    if (latestDraw && parseInt(targetPeriod) <= parseInt(latestDraw.period)) {
        // 预测期号已开奖，查找对应的开奖结果
        actualResult = appData.lotteryHistory.data.find(draw => draw.period === targetPeriod);

        if (actualResult) {
            // 在网格前添加状态提示
            const statusBanner = createDrawnStatusBanner(actualResult);
            modelsGridEl.appendChild(statusBanner);
        }
    }

    // 渲染每个模型
    getFilteredModels().forEach(model => {
        const modelCard = Components.createModelCard(model, actualResult);
        modelsGridEl.appendChild(modelCard);
    });
}

// 创建已开奖状态横幅
function createDrawnStatusBanner(actualResult) {
    const banner = document.createElement('div');
    banner.className = 'drawn-status-banner';
    banner.innerHTML = `
        <div class="drawn-status-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                <polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
        </div>
        <div class="drawn-status-content">
            <h3 class="drawn-status-title">第 ${actualResult.period} 期已开奖</h3>
            <p class="drawn-status-subtitle">以下为预测命中情况对比</p>
        </div>
        <div class="drawn-status-balls">
            ${actualResult.front_balls.map(num => `<span class="mini-result-ball red">${num}</span>`).join('')}
            ${actualResult.back_balls.map(num => `<span class="mini-result-ball blue">${num}</span>`).join('')}
        </div>
    `;
    return banner;
}

// 渲染历史标签页
function renderHistoryTab() {
    renderHitRankings();
    renderGroupedRankings();
    renderTokenUsage();
    renderAccuracyCards();
}

// 渲染模型 Token 用量排行表
function renderTokenUsage() {
    const container = document.getElementById('tokenUsageContainer');
    if (!container) return;

    const records = (appData.tokenUsage && appData.tokenUsage.records) || [];
    if (!records.length) {
        container.innerHTML = '<div class="ranking-empty"><p>暂无 Token 用量数据</p></div>';
        return;
    }

    // 兼容旧格式：旧记录含 model_id 且无 period 字段，视为单条调用记录
    const isLegacy = records[0] && !('period' in records[0]) && 'model_id' in records[0];

    // 按模型聚合（新结构：records 按期聚合，每期含 models 对象）
    const stats = {};
    const addModel = (modelId, m, retries) => {
        const entry = stats[modelId] || {
            modelName: m.name || m.model_name || modelId,
            modelId: modelId,
            promptTokens: 0,
            completionTokens: 0,
            totalTokens: 0,
            elapsed: 0,
            calls: 0,
            periods: 0,
        };
        entry.promptTokens += m.prompt || m.prompt_tokens || 0;
        entry.completionTokens += m.completion || m.completion_tokens || 0;
        entry.totalTokens += m.total || m.total_tokens || 0;
        entry.elapsed += m.elapsed || m.elapsed_seconds || 0;
        entry.calls += retries || 1;
        entry.periods += 1;
        stats[modelId] = entry;
    };

    if (isLegacy) {
        records.forEach(r => addModel(r.model_id || r.model_name, r, 1));
    } else {
        records.forEach(period => {
            const models = period.models || {};
            Object.entries(models).forEach(([modelId, m]) => addModel(modelId, m, m.retries || 1));
        });
    }

    const arr = Object.values(stats).sort((a, b) => b.totalTokens - a.totalTokens);

    const fmt = (n) => n.toLocaleString('zh-CN');

    let rows = arr.map(m => `
        <tr>
            <td class="token-model">${m.modelName}</td>
            <td>${fmt(m.promptTokens)}</td>
            <td>${fmt(m.completionTokens)}</td>
            <td class="token-total">${fmt(m.totalTokens)}</td>
            <td>${m.elapsed.toFixed(1)}s</td>
            <td>${m.calls}</td>
            <td>${fmt(Math.round(m.totalTokens / m.periods))}</td>
        </tr>
    `).join('');

    const totalElapsed = arr.reduce((s, m) => s + m.elapsed, 0);

    container.innerHTML = `
        <div class="ranking-panel">
            <div class="ranking-header">
                <span class="ranking-title">Token 用量排行</span>
                <span class="ranking-sub">${records.length} 期数据 · 总耗时 ${totalElapsed.toFixed(1)}s</span>
            </div>
            <div class="token-table-wrap">
                <table class="ranking-table token-table">
                    <thead>
                        <tr>
                            <th>模型</th>
                            <th>总Prompt输入</th>
                            <th>总输出</th>
                            <th>总计</th>
                            <th>总耗时</th>
                            <th>调用次数</th>
                            <th>期均token</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
        </div>`;
}

// 命中排行：按时间窗口分组、按 模型+策略 命中优劣 取 Top5
function renderHitRankings() {
    const container = document.getElementById('rankingContainer');
    if (!container || !appData.predictionsHistory) return;
    container.innerHTML = '';

    const records = appData.predictionsHistory.predictions_history || [];
    if (!records.length) {
        container.innerHTML = '<div class="ranking-empty"><p>暂无命中回溯数据</p></div>';
        return;
    }

    // 时间窗口
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const thisYearStart = new Date(today.getFullYear(), 0, 1);
    const thisMonthStart = new Date(today.getFullYear(), today.getMonth(), 1);
    const lastMonthStart = new Date(today.getFullYear(), today.getMonth() - 1, 1);

    // 取最新一期的开奖日期（用作"最新一期"窗口）
    const latestDate = records[0]?.actual_result?.date || null;

    const windows = [
        { key: 'latest',   label: '最新一期', sub: latestDate || '—', filter: (d) => d === latestDate },
        { key: 'month',    label: '本月', sub: '本月',      filter: (d) => { const x = new Date(d); return x >= thisMonthStart && x < today; } },
        { key: 'lastMonth',label: '上月', sub: '上月',      filter: (d) => { const x = new Date(d); return x >= lastMonthStart && x < thisMonthStart; } },
        { key: 'year',     label: '本年', sub: `${today.getFullYear()} 年度`, filter: (d) => { const x = new Date(d); return x >= thisYearStart && x < today; } },
    ];

    windows.forEach(win => {
        const panel = buildRankingPanel(win.label, win.sub, records, win.filter);
        container.appendChild(panel);
    });
}

// 构建单个时间窗口排行面板
function buildRankingPanel(title, sub, records, dateFilter) {
    // 按模型聚合（去掉策略分组）
    const stats = {};  // key = model_name
    let hasLatest = false;

    records.forEach(rec => {
        const isLatest = !hasLatest && records.indexOf(rec) === 0;
        if (isLatest) hasLatest = true;
        const adate = rec.actual_result?.date;
        if (!adate || !dateFilter(adate)) return;
        (rec.models || []).forEach(model => {
            const key = model.model_name;
            if (!key) return;
            const entry = stats[key] || {
                modelName: model.model_name,
                totalHits: 0,
                bestHit: 0,
                games: 0,
                frontTotal: 0,
                backHits: 0,
                currentHits: 0,
                hitNumbers: '',
            };
            let bestPred = null;
            let allFrontHits = new Set();
            let allBackHits = new Set();
            (model.predictions || []).forEach(pred => {
                const hr = pred.hit_result;
                if (!hr) return;
                entry.totalHits += hr.total_hits || 0;
                entry.games += 1;
                entry.frontTotal += hr.front_hit_count || 0;
                entry.backHits += hr.back_hit_count || 0;
                if (hr.total_hits > entry.bestHit) entry.bestHit = hr.total_hits;
                if (isLatest) {
                    (hr.front_hits || []).forEach(n => allFrontHits.add(n));
                    (hr.back_hits || []).forEach(n => allBackHits.add(n));
                    if (!bestPred || (hr.total_hits || 0) > (bestPred.hit_result?.total_hits || 0)) {
                        bestPred = pred;
                    }
                }
            });
            if (isLatest) {
                entry.currentHits = bestPred ? (bestPred.hit_result?.total_hits || 0) : 0;
                const parts = [];
                if (allFrontHits.size) parts.push('前:' + [...allFrontHits].sort().join(' '));
                if (allBackHits.size) parts.push('后:' + [...allBackHits].sort().join(' '));
                entry.hitNumbers = parts.join(' ') || '—';
            }
            stats[key] = entry;
        });
    });

    const panel = document.createElement('div');
    panel.className = 'ranking-panel';

    // 标题
    const header = document.createElement('div');
    header.className = 'ranking-header';
    header.innerHTML = '<span class="ranking-title">' + title + '</span>'
        + '<span class="ranking-sub">' + sub + '</span>';
    panel.appendChild(header);

    const arr = Object.values(stats);
    if (!arr.length) {
        const empty = document.createElement('div');
        empty.className = 'ranking-empty';
        empty.innerHTML = '<p>该时段暂无命中数据</p>';
        panel.appendChild(empty);
        return panel;
    }

    const isLatest = title === '最新一期';
    let top10;
    if (isLatest) {
        // 最新一期：按 后区命中 → 本期命中数 排序
        arr.sort((a, b) => {
            const aBack = a.hitNumbers.includes('后:') ? 1 : 0;
            const bBack = b.hitNumbers.includes('后:') ? 1 : 0;
            return bBack - aBack || b.currentHits - a.currentHits;
        });
        top10 = arr.slice(0, 10);
    } else {
        // 本月/上月/本年：按 总球数 → 累计后区 排序
        arr.sort((a, b) => b.totalHits - a.totalHits || b.backHits - a.backHits);
        top10 = arr.slice(0, 10);
    }

    // 表格
    const table = document.createElement('table');
    table.className = 'ranking-table';
    const thead = document.createElement('thead');
    if (isLatest) {
        thead.innerHTML = '<tr>'
            + '<th>#</th><th>模型</th>'
            + '<th>本期命中</th><th>命中前区</th><th>后区</th>'
            + '</tr>';
    } else {
        thead.innerHTML = '<tr>'
            + '<th>#</th><th>模型</th>'
            + '<th>历史最多</th><th>累计前区</th><th>累计后区</th><th>总球数</th>'
            + '<th>期数</th></tr>';
    }
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    top10.forEach((e, i) => {
        const tr = document.createElement('tr');
        const rankClass = i === 0 ? ' rank-1' : i === 1 ? ' rank-2' : i === 2 ? ' rank-3' : '';
        const bestTag = e.bestHit >= 5 ? 'excellent' : e.bestHit >= 3 ? 'good' : '';
        if (isLatest) {
            // 从 "前:03 07 12 后:02" 格式中提取前区和后区
            const s = e.hitNumbers || '—';
            const frontMatch = s.match(/前:(.+?)(?: 后:|$)/);
            const backMatch = s.match(/后:(.+)/);
            const frontHits = frontMatch ? frontMatch[1].trim() : '—';
            const backHits = backMatch ? backMatch[1].trim() : '—';
            tr.innerHTML =
                '<td class="rank-num' + rankClass + '">' + (i + 1) + '</td>' +
                '<td class="rank-model">' + escHtml(e.modelName) + '</td>' +
                '<td class="rank-current">' + e.currentHits + ' 球</td>' +
                '<td class="rank-hits">' + escHtml(frontHits) + '</td>' +
                '<td class="rank-blue">' + escHtml(backHits) + '</td>';
        } else {
            tr.innerHTML =
                '<td class="rank-num' + rankClass + '">' + (i + 1) + '</td>' +
                '<td class="rank-model">' + escHtml(e.modelName) + '</td>' +
                '<td class="rank-best ' + bestTag + '">' + e.bestHit + ' 球</td>' +
                '<td class="rank-total">' + e.frontTotal + ' 球</td>' +
                '<td class="rank-blue">' + e.backHits + ' 球</td>' +
                '<td class="rank-total">' + e.totalHits + ' 球</td>' +
                '<td class="rank-games">' + e.games + '</td>';
        }
        tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    panel.appendChild(table);

    return panel;
}

// 策略 / 模型 分组统计（新增，不替换原有排行）
function renderGroupedRankings() {
    const container = document.getElementById('groupedRankingContainer');
    if (!container || !appData.predictionsHistory) return;
    container.innerHTML = '';

    const records = appData.predictionsHistory.predictions_history || [];
    if (!records.length) {
        container.innerHTML = '<div class="ranking-empty"><p>暂无命中回溯数据</p></div>';
        return;
    }

    // 收集所有 模型+策略 的命中汇总
    const stats = {};   // key = 分组键
    records.forEach(rec => {
        (rec.models || []).forEach(model => {
            (model.predictions || []).forEach(pred => {
                const hr = pred.hit_result;
                if (!hr) return;
                const modelKey = model.model_name || '—';
                const stratKey = pred.strategy || '—';
                [[modelKey, 'model'], [stratKey, 'strategy']].forEach(([name, type]) => {
                    const key = type + '|' + name;
                    const entry = stats[key] || {
                        type: type,
                        name: name,
                        maxHits: 0,
                        frontTotal: 0,
                        backHits: 0,
                        totalHits: 0,
                        games: 0,
                    };
                    entry.frontTotal += hr.front_hit_count || 0;
                    entry.backHits += hr.back_hit_count || 0;
                    entry.totalHits += hr.total_hits || 0;
                    entry.games += 1;
                    if ((hr.total_hits || 0) > entry.maxHits) entry.maxHits = hr.total_hits || 0;
                    stats[key] = entry;
                });
            });
        });
    });

    // 按 总球数 降序排序
    const arr = Object.values(stats).sort((a, b) => b.totalHits - a.totalHits || b.backHits - a.backHits);

    const modelPanel = buildGroupedPanel('模型分组', '按 AI 模型统计命中（全部历史）', arr.filter(e => e.type === 'model'));

    if (modelPanel) container.appendChild(modelPanel);
}

// 构建分组统计面板
function buildGroupedPanel(title, sub, entries) {
    const panel = document.createElement('div');
    panel.className = 'ranking-panel';

    const header = document.createElement('div');
    header.className = 'ranking-header';
    header.innerHTML = '<span class="ranking-title">' + title + '</span>'
        + '<span class="ranking-sub">' + sub + '</span>';
    panel.appendChild(header);

    if (!entries.length) {
        const empty = document.createElement('div');
        empty.className = 'ranking-empty';
        empty.innerHTML = '<p>暂无命中数据</p>';
        panel.appendChild(empty);
        return panel;
    }

    const table = document.createElement('table');
    table.className = 'ranking-table';
    const thead = document.createElement('thead');
    thead.innerHTML = '<tr>'
        + '<th>#</th><th>名称</th>'
        + '<th>历史最大单期球数</th><th>历史总前区</th><th>历史总后区</th><th>总球数</th>'
        + '<th>期数</th></tr>';
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    entries.forEach((e, i) => {
        const tr = document.createElement('tr');
        const rankClass = i === 0 ? ' rank-1' : i === 1 ? ' rank-2' : i === 2 ? ' rank-3' : '';
        const bestTag = e.maxHits >= 5 ? 'excellent' : e.maxHits >= 3 ? 'good' : '';
        tr.innerHTML =
            '<td class="rank-num' + rankClass + '">' + (i + 1) + '</td>' +
            '<td class="rank-model">' + escHtml(e.name) + '</td>' +
            '<td class="rank-best ' + bestTag + '">' + e.maxHits + ' 球</td>' +
            '<td class="rank-total">' + e.frontTotal + ' 球</td>' +
            '<td class="rank-blue">' + e.backHits + ' 球</td>' +
            '<td class="rank-total">' + e.totalHits + ' 球</td>' +
            '<td class="rank-games">' + e.games + ' 期</td>';
        tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    panel.appendChild(table);

    return panel;
}

// HTML 转义
function escHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

// 渲染准确度卡片
function renderAccuracyCards() {
    if (!appData.predictionsHistory) return;

    const containerEl = document.getElementById('accuracyCardsContainer');
    if (!containerEl) return;

    // 清空现有内容
    containerEl.innerHTML = '';

    // 渲染每个记录
    appData.predictionsHistory.predictions_history.forEach(record => {
        const card = Components.createAccuracyCard(record);
        containerEl.appendChild(card);
    });
}

// 渲染历史表格
function renderHistoryTable() {
    if (!appData.lotteryHistory) return;

    const tbodyEl = document.getElementById('historyTableBody');
    if (!tbodyEl) return;
    tbodyEl.innerHTML = '';

    const table = tbodyEl.parentElement;           // <table>
    const scrollWrap = table.parentElement;        // .history-table-scroll
    const container = scrollWrap.parentElement;    // .history-table-container

    const allRows = appData.lotteryHistory.data;
    const total = allRows.length;
    const shown = Math.min(3, total);

    for (let i = 0; i < shown; i++) {
        tbodyEl.appendChild(Components.createHistoryTableRow(allRows[i]));
    }

    if (total <= shown) return;

    const remaining = total - shown;

    // 隐藏行：先插入一个 <tbody> 到表格末尾、初始隐藏
    const hiddenTbody = document.createElement('tbody');
    hiddenTbody.id = 'historyHiddenRows';
    hiddenTbody.style.display = 'none';
    for (let i = shown; i < total; i++) {
        hiddenTbody.appendChild(Components.createHistoryTableRow(allRows[i]));
    }
    table.appendChild(hiddenTbody);

    // 展开/折叠按钮：插入到 .history-table-container 中、表格之后
    const toggle = document.createElement('div');
    toggle.id = 'historyToggle';
    toggle.className = 'history-toggle';
    toggle.innerHTML = '<span>展开查看全部 ' + remaining + ' 期</span>'
        + '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>';

    container.appendChild(toggle);

    toggle.addEventListener('click', function () {
        if (hiddenTbody.style.display === 'none') {
            hiddenTbody.style.display = '';
            toggle.innerHTML = '<span>收起</span>'
                + '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="18 15 12 9 6 15"/></svg>';
        } else {
            hiddenTbody.style.display = 'none';
            toggle.innerHTML = '<span>展开查看全部 ' + remaining + ' 期</span>'
                + '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>';
        }
    });
}

// 渲染统计卡片
function renderStatisticsCards() {
    if (!appData.lotteryHistory) return;

    // 计算前区频率（01-35）
    const frontFrequency = {};
    for (let i = 1; i <= 35; i++) {
        frontFrequency[i.toString().padStart(2, '0')] = 0;
    }

    // 计算后区频率（01-12）
    const backFrequency = {};
    for (let i = 1; i <= 12; i++) {
        backFrequency[i.toString().padStart(2, '0')] = 0;
    }

    // 计算和值
    let totalSum = 0;

    appData.lotteryHistory.data.forEach(draw => {
        // 前区
        draw.front_balls.forEach(ball => {
            frontFrequency[ball] = (frontFrequency[ball] || 0) + 1;
        });
        // 后区
        draw.back_balls.forEach(ball => {
            backFrequency[ball] = (backFrequency[ball] || 0) + 1;
        });
        // 和值（前区5个号码之和）
        const sum = draw.front_balls.reduce((acc, ball) => acc + parseInt(ball), 0);
        totalSum += sum;
    });

    // 找出最热前区
    const hottestFront = Object.entries(frontFrequency).sort((a, b) => b[1] - a[1])[0];

    // 找出最热后区
    const hottestBack = Object.entries(backFrequency).sort((a, b) => b[1] - a[1])[0];

    // 平均和值
    const avgSum = Math.round(totalSum / appData.lotteryHistory.data.length);

    // 更新UI
    const totalDrawsEl = document.getElementById('statTotalDraws');
    if (totalDrawsEl) totalDrawsEl.textContent = `${appData.lotteryHistory.data.length} 期`;

    const hottestFrontEl = document.getElementById('statHottestFront');
    if (hottestFrontEl) hottestFrontEl.textContent = `${hottestFront[0]} (${hottestFront[1]}次)`;

    const hottestBackEl = document.getElementById('statHottestBack');
    if (hottestBackEl) hottestBackEl.textContent = `${hottestBack[0]} (${hottestBack[1]}次)`;

    const avgSumEl = document.getElementById('statAvgSum');
    if (avgSumEl) avgSumEl.textContent = avgSum;
}

// 设置事件监听
function setupEventListeners() {
    // Tab切换 - 桌面端
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', () => handleTabSwitch(item.dataset.tab, navItems));
    });

    // Tab切换 - 移动端
    const mobileNavItems = document.querySelectorAll('.mobile-nav-item');
    mobileNavItems.forEach(item => {
        item.addEventListener('click', () => handleTabSwitch(item.dataset.tab, mobileNavItems));
    });

    }

// 处理Tab切换
function handleTabSwitch(tabName, navItems) {
    // 更新导航项状态
    navItems.forEach(item => {
        if (item.dataset.tab === tabName) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });

    // 同步桌面端和移动端状态
    const allNavItems = document.querySelectorAll('.nav-item, .mobile-nav-item');
    allNavItems.forEach(item => {
        if (item.dataset.tab === tabName) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });

    // 切换Tab内容
    const tabContents = document.querySelectorAll('.tab-content');
    tabContents.forEach(content => {
        if (content.dataset.tab === tabName) {
            content.classList.add('active');
        } else {
            content.classList.remove('active');
        }
    });

    // 如果切换到分析Tab，渲染所有图表
    if (tabName === 'analysis') {
            setTimeout(() => {
                renderStatisticsCards();
                renderHistoryTable();
                renderAccuracyCards();
            }, 100);
    }

    if (tabName === 'ranking') {
        setTimeout(() => renderHitRankings(), 50);
    }
    }

// 隐藏加载屏幕
function hideLoadingScreen() {
    const loadingScreen = document.getElementById('loadingScreen');
    const mainApp = document.getElementById('mainApp');

    if (loadingScreen) {
        loadingScreen.style.display = 'none';
    }

    if (mainApp) {
        mainApp.style.display = 'block';
    }
}

// 计算距离目标日期的天数
function calculateDaysUntil(targetDateStr) {
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const targetDate = new Date(targetDateStr);
    targetDate.setHours(0, 0, 0, 0);

    const diffTime = targetDate - today;
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

    return diffDays;
}

// 页面加载完成后初始化
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initApp);
} else {
    initApp();
}
