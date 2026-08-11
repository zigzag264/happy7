/**
 * UI 组件模块 - 新UI版本
 * 负责生成和渲染各种 UI 组件
 */

const Components = {
    /**
     * 创建号码球元素
     * @param {string} number - 号码
     * @param {string} color - 颜色 ('red' 或 'blue')
     * @param {string} size - 大小 ('sm', 'md', 'lg')
     * @param {boolean} isHit - 是否命中
     * @returns {HTMLElement} 号码球元素
     */
    createLotteryBall(number, color, size = 'md', isHit = false) {
        const ball = document.createElement('div');
        ball.className = `lottery-ball ${color} size-${size}${isHit ? ' hit' : ''}`;
        ball.innerHTML = `<span>${number}</span>`;
        return ball;
    },

    /**
     * 创建球分隔符
     * @returns {HTMLElement} 分隔符元素
     */
    createBallDivider() {
        const divider = document.createElement('div');
        divider.className = 'ball-divider';
        return divider;
    },

    /**
     * 获取模型头部样式类名
     * @param {string} modelName - 模型名称
     * @returns {string} CSS 类名
     */
    getModelHeaderClass(modelName) {
        if (modelName.includes('DeepSeek')) return 'model-header-deepseek';
        if (modelName.includes('Qwen')) return 'model-header-qwen';
        if (modelName.includes('Tongyi')) return 'model-header-tongyi';
        if (modelName.includes('Kimi')) return 'model-header-kimi';
        return 'model-header-deepseek';
    },

    /**
     * 创建模型预测卡片
     * @param {Object} model - 模型数据
     * @param {Object} actualResult - 实际开奖结果（可选）
     * @returns {HTMLElement} 模型卡片元素
     */
    createModelCard(model, actualResult = null) {
        const card = document.createElement('div');
        card.className = 'model-card';

        const headerClass = this.getModelHeaderClass(model.model_name);

        // 清理 model_id 以生成有效的 DOM ID（移除特殊字符）
        const safeModelId = model.model_id.replace(/[^a-zA-Z0-9-_]/g, '-');

        // 计算最佳命中（如果已开奖）
        let bestHitCount = 0;
        let bestGroupId = null;
        if (actualResult) {
            model.predictions.forEach(prediction => {
                const hitResult = this.compareNumbers(prediction, actualResult);
                if (hitResult && hitResult.totalHits > bestHitCount) {
                    bestHitCount = hitResult.totalHits;
                    bestGroupId = prediction.group_id;
                }
            });
        }

        card.innerHTML = `
            <div class="model-card-header ${headerClass}">
                <div class="model-card-header-left">
                    <div class="model-icon-box">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/><path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/><path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4"/><path d="M17.599 6.5a3 3 0 0 0 .399-1.375"/><path d="M6.003 5.125A3 3 0 0 0 6.401 6.5"/><path d="M3.477 10.896a4 4 0 0 1 .585-.396"/><path d="M19.938 10.5a4 4 0 0 1 .585.396"/><path d="M6 18a4 4 0 0 1-1.967-.516"/><path d="M19.967 17.484A4 4 0 0 1 18 18"/>
                        </svg>
                    </div>
                    <div class="model-name-wrapper">
                        <h3>${model.model_name}</h3>
                        <div class="model-id">
                            <span class="model-id-dot"></span>
                            <span>Model: ${model.model_id}</span>
                        </div>
                    </div>
                </div>
                <div class="model-card-header-right">
                    ${actualResult && bestHitCount > 0 ? `
                        <div class="model-best-hit-badge">
                            <svg viewBox="0 0 24 24" fill="currentColor">
                                <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>
                            </svg>
                            <span>最佳 ${bestHitCount} 中</span>
                        </div>
                    ` : ''}
                    <div class="model-card-ticket-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                            <path d="M2 9a3 3 0 0 1 0 6v2a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-2a3 3 0 0 1 0-6V7a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2Z"/><path d="M13 5v2"/><path d="M13 17v2"/><path d="M13 11v2"/>
                        </svg>
                    </div>
                </div>
            </div>
            <div class="model-card-content">
                <div class="strategy-group" id="strategies-${safeModelId}"></div>
            </div>
        `;

        // 添加策略行
        const strategiesContainer = card.querySelector(`#strategies-${safeModelId}`);
        model.predictions.forEach((prediction, index) => {
            const isBest = actualResult && prediction.group_id === bestGroupId;
            strategiesContainer.appendChild(this.createStrategyRow(prediction, index === model.predictions.length - 1, actualResult, isBest));
        });

        return card;
    },

    /**
     * 创建策略行
     * @param {Object} prediction - 预测数据
     * @param {boolean} isLast - 是否是最后一个
     * @param {Object} actualResult - 实际开奖结果（可选）
     * @param {boolean} isBest - 是否是最佳预测组
     * @returns {HTMLElement} 策略行元素
     */
    createStrategyRow(prediction, isLast = false, actualResult = null, isBest = false) {
        const row = document.createElement('div');
        row.className = 'strategy-row';

        // 计算命中结果（如果已开奖）
        let hitResult = null;
        if (actualResult) {
            hitResult = this.compareNumbers(prediction, actualResult);
        }

        // 创建头部
        const header = document.createElement('div');
        header.className = 'strategy-header';
        header.innerHTML = `
            <div class="strategy-label-row">
                <div class="strategy-group-badge${isBest ? ' best' : ''}">${isBest ? '★ ' : ''}G-${prediction.group_id}</div>
                <span class="strategy-name">${prediction.strategy}</span>
                ${hitResult ? `
                    <div class="strategy-hit-stats">
                        <span class="hit-stat red">${hitResult.frontHitCount}前</span>
                        <span class="hit-stat ${hitResult.backHitCount > 0 ? 'blue' : 'miss'}">${hitResult.backHitCount}后</span>
                    </div>
                ` : ''}
            </div>
        `;
        row.appendChild(header);

        // 创建球容器
        const ballsContainer = document.createElement('div');
        ballsContainer.className = 'strategy-balls';

        prediction.front_balls.forEach(num => {
            const isHit = hitResult?.frontHits?.includes(num);
            ballsContainer.appendChild(this.createLotteryBall(num, 'red', 'md', isHit));
        });

        ballsContainer.appendChild(this.createBallDivider());

        prediction.back_balls.forEach(num => {
            const isHit = hitResult?.backHits?.includes(num);
            ballsContainer.appendChild(this.createLotteryBall(num, 'blue', 'md', isHit));
        });

        row.appendChild(ballsContainer);

        // 创建描述
        const desc = document.createElement('p');
        desc.className = 'strategy-description';
        desc.textContent = prediction.description;
        row.appendChild(desc);

        // 添加分隔符 (最后一个除外)
        if (!isLast) {
            const separator = document.createElement('div');
            separator.className = 'strategy-separator';
            row.appendChild(separator);
        }

        return row;
    },

    /**
     * 创建准确度卡片 (历史预测对比)
     * @param {Object} record - 历史记录
     * @returns {HTMLElement} 准确度卡片元素
     */
    createAccuracyCard(record) {
        const card = document.createElement('div');
        card.className = 'accuracy-card';

        const result = record.actual_result;
        if (!result) return card;

        // 卡片头部
        const header = document.createElement('div');
        header.className = 'accuracy-card-header';
        header.innerHTML = `
            <div class="accuracy-header-left">
                <div class="accuracy-trophy-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/><path d="M4 22h16"/><path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22"/><path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22"/><path d="M18 2H6v7a6 6 0 0 0 12 0V2Z"/>
                    </svg>
                </div>
                <div>
                    <h4 class="accuracy-header-title">第 ${result.period} 期</h4>
                    <span class="accuracy-header-subtitle">命中回溯报告</span>
                </div>
            </div>
            <span class="accuracy-header-date">${result.date}</span>
        `;
        card.appendChild(header);

        // 实际开奖结果
        const actualSection = document.createElement('div');
        actualSection.className = 'actual-result-section';
        actualSection.innerHTML = `
            <div class="actual-result-label">
                <div class="actual-result-bar"></div>
                <p class="actual-result-text">开奖号码 Official Draw</p>
            </div>
        `;

        const actualBalls = document.createElement('div');
        actualBalls.className = 'actual-result-balls';
        result.front_balls.forEach(num => {
            actualBalls.appendChild(this.createLotteryBall(num, 'red', 'md'));
        });
        actualBalls.appendChild(this.createBallDivider());
        result.back_balls.forEach(num => {
            actualBalls.appendChild(this.createLotteryBall(num, 'blue', 'md'));
        });
        actualSection.appendChild(actualBalls);

        card.appendChild(actualSection);

        // 模型命中列表
        const hitsList = document.createElement('div');
        hitsList.className = 'model-hits-list';

        record.models.forEach((model, index) => {
            hitsList.appendChild(this.createModelHitItem(model, index + 1, index === record.models.length - 1));
        });

        card.appendChild(hitsList);

        return card;
    },

    /**
     * 创建模型命中项
     * @param {Object} model - 模型数据
     * @param {number} index - 索引
     * @param {boolean} isLast - 是否最后一个
     * @returns {HTMLElement} 模型命中项元素
     */
    createModelHitItem(model, index, isLast = false) {
        const item = document.createElement('div');
        item.className = 'model-hit-item';

        // 计算最佳命中数
        const bestHit = Math.max(...model.predictions.map(p => p.hit_result?.total_hits || 0));

        // 清理 model_id 以生成有效的 DOM ID
        const safeModelId = model.model_id.replace(/[^a-zA-Z0-9-_]/g, '-');

        item.innerHTML = `
            ${!isLast ? '<div class="model-hit-connector"></div>' : ''}
            <div class="model-hit-row">
                <div class="model-hit-number">${index}</div>
                <div class="model-hit-content">
                    <div class="model-hit-header">
                        <h4 class="model-hit-name">${model.model_name}</h4>
                        ${bestHit >= 4 ? `
                        <span class="high-hit-badge">
                            <svg viewBox="0 0 24 24" fill="currentColor">
                                <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>
                            </svg>
                            高命中: ${bestHit}
                        </span>` : ''}
                    </div>
                    <div class="prediction-groups" id="groups-${safeModelId}"></div>
                </div>
            </div>
        `;

        // 添加预测组
        const groupsContainer = item.querySelector(`#groups-${safeModelId}`);
        model.predictions.forEach(prediction => {
            groupsContainer.appendChild(this.createPredictionGroupRow(prediction));
        });

        return item;
    },

    /**
     * 创建预测组行
     * @param {Object} prediction - 预测数据
     * @returns {HTMLElement} 预测组行元素
     */
    createPredictionGroupRow(prediction) {
        const row = document.createElement('div');
        const totalHits = prediction.hit_result?.total_hits || 0;
        const isWinning = totalHits >= 3;

        row.className = `prediction-group-row${isWinning ? ' winning' : ''}`;

        // 球容器
        const ballsContainer = document.createElement('div');
        ballsContainer.className = 'prediction-group-balls';
        ballsContainer.innerHTML = `
            <span class="prediction-group-strategy">${prediction.strategy.substring(0, 8)}${prediction.strategy.length > 8 ? '..' : ''}</span>
        `;

        const ballsList = document.createElement('div');
        ballsList.className = 'prediction-group-balls-list';

        prediction.front_balls.forEach(num => {
            const isHit = prediction.hit_result?.front_hits?.includes(num);
            const miniBall = document.createElement('div');
            miniBall.className = `mini-ball${isHit ? ' hit' : ''}`;
            miniBall.textContent = num;
            ballsList.appendChild(miniBall);
        });

        prediction.back_balls.forEach(num => {
            const isHit = prediction.hit_result?.back_hits?.includes(num);
            const miniBall = document.createElement('div');
            miniBall.className = `mini-ball blue${isHit ? ' hit' : ''}`;
            miniBall.textContent = num;
            ballsList.appendChild(miniBall);
        });

        ballsContainer.appendChild(ballsList);
        row.appendChild(ballsContainer);

        // 统计信息
        const stats = document.createElement('div');
        stats.className = 'prediction-group-stats';

        const frontHitCount = prediction.hit_result?.front_hit_count || 0;
        const backHitCount = prediction.hit_result?.back_hit_count || 0;

        stats.innerHTML = `
            <div class="stat-item">
                <span class="stat-value ${frontHitCount > 0 ? 'has-hit' : 'no-hit'}">${frontHitCount}</span>
                <span class="stat-label">前</span>
            </div>
            <div class="stat-divider"></div>
            <div class="stat-item">
                <span class="stat-value ${backHitCount > 0 ? 'blue-hit' : 'no-hit'}">${backHitCount}</span>
                <span class="stat-label">后</span>
            </div>
        `;
        row.appendChild(stats);

        return row;
    },

    /**
     * 创建历史表格行
     * @param {Object} draw - 开奖数据
     * @returns {HTMLElement} 表格行元素
     */
    createHistoryTableRow(draw) {
        const row = document.createElement('tr');

        // 期号
        const periodCell = document.createElement('td');
        periodCell.className = 'period-cell';
        periodCell.textContent = draw.period;
        row.appendChild(periodCell);

        // 日期
        const dateCell = document.createElement('td');
        dateCell.className = 'date-cell';
        dateCell.textContent = draw.date;
        row.appendChild(dateCell);

        // 开奖号码
        const ballsCell = document.createElement('td');
        const ballsContainer = document.createElement('div');
        ballsContainer.className = 'balls-cell';

        draw.front_balls.forEach(num => {
            ballsContainer.appendChild(this.createLotteryBall(num, 'red', 'sm'));
        });

        const divider = document.createElement('div');
        divider.style.width = '8px';
        ballsContainer.appendChild(divider);

        draw.back_balls.forEach(num => {
            ballsContainer.appendChild(this.createLotteryBall(num, 'blue', 'sm'));
        });

        ballsCell.appendChild(ballsContainer);
        row.appendChild(ballsCell);

        return row;
    },

    /**
     * 比较预测号码与实际开奖结果
     * @param {Object} prediction - 预测数据
     * @param {Object} actualResult - 实际开奖结果
     * @returns {Object} 命中信息
     */
    compareNumbers(prediction, actualResult) {
        if (!actualResult) {
            return null;
        }

        const frontHits = prediction.front_balls.filter(ball =>
            actualResult.front_balls.includes(ball)
        );

        const backHits = prediction.back_balls.filter(ball =>
            actualResult.back_balls.includes(ball)
        );

        return {
            frontHits: frontHits,
            frontHitCount: frontHits.length,
            backHits: backHits,
            backHitCount: backHits.length,
            totalHits: frontHits.length + backHits.length
        };
    }
};
