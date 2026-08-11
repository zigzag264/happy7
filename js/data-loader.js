/**
 * 数据加载模块
 * 负责从 JSON 文件加载历史开奖数据和 AI 预测数据
 */

const DataLoader = {
    _cacheBust() {
        return '?v=' + Date.now();
    },

    /**
     * 加载历史开奖数据
     * @returns {Promise<Object>} 历史数据对象
     */
    async loadLotteryHistory() {
        try {
            const response = await fetch('./data/lottery_history.json' + this._cacheBust());
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            console.log('历史开奖数据加载成功', data);
            return data;
        } catch (error) {
            console.error('加载历史开奖数据失败:', error);
            throw error;
        }
    },

    /**
     * 加载 AI 预测数据
     * @returns {Promise<Object>} AI 预测数据对象
     */
    async loadPredictions() {
        try {
            const response = await fetch('./data/ai_predictions.json' + this._cacheBust());
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            console.log('AI 预测数据加载成功', data);
            return data;
        } catch (error) {
            console.error('加载 AI 预测数据失败:', error);
            throw error;
        }
    },

    /**
     * 加载历史预测对比数据
     * @returns {Promise<Object>} 历史预测对比数据对象
     */
    async loadPredictionsHistory() {
        try {
            const response = await fetch('./data/predictions_history.json' + this._cacheBust());
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            console.log('历史预测对比数据加载成功', data);
            return data;
        } catch (error) {
            console.error('加载历史预测对比数据失败:', error);
            throw error;
        }
    },

    /**
     * 加载 token 用量数据
     * @returns {Promise<Object>} token 用量数据对象
     */
    async loadTokenUsage() {
        try {
            const response = await fetch('./data/token_usage.json' + this._cacheBust());
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            console.log('Token 用量数据加载成功', data);
            return data;
        } catch (error) {
            console.warn('加载 token 用量数据失败，此为可选数据:', error);
            return { records: [] };
        }
    },

    /**
     * 加载所有数据
     * @returns {Promise<Object>} 包含所有数据的对象
     */
    async loadAllData() {
        try {
            const [lotteryData, predictionData, predictionsHistoryData, tokenUsageData] = await Promise.all([
                this.loadLotteryHistory(),
                this.loadPredictions(),
                this.loadPredictionsHistory(),
                this.loadTokenUsage()
            ]);

            return {
                lottery: lotteryData,
                predictions: predictionData,
                predictionsHistory: predictionsHistoryData,
                tokenUsage: tokenUsageData
            };
        } catch (error) {
            console.error('加载数据失败:', error);
            throw error;
        }
    }
};

// 导出到全局作用域
window.DataLoader = DataLoader;
