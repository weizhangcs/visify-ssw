import { SceneType } from '../types/constants';

export const generateMockRepository = (count = 300) => {
    const scenes = [];
    const relationships = [];
    const types = Object.values(SceneType);

    let lastMainPlotId = null;
    let currentTime = 0; // 时间轴游标

    for (let i = 0; i < count; i++) {
        const id = `scene-${i}`;

        // 模拟时长：5 到 15 秒之间
        const duration = Math.floor(Math.random() * 10) + 5;
        const startTime = currentTime;
        const endTime = currentTime + duration;
        currentTime = endTime; // 游标后移

        const isClusterError = i >= 20 && i <= 22;
        const isRandomError = !isClusterError && Math.random() < 0.05 && i > 5;
        const needsResequence = isClusterError || isRandomError;
        const isFunctionalAI = !needsResequence && Math.random() < 0.2 && i > 0;

        scenes.push({
            id,
            index: i,
            label: `SC-${i + 1}`,
            narrative_action: needsResequence
                ? `[待修正] 时序或逻辑存疑。`
                : (isFunctionalAI ? `[AI: Functional] 环境/过场。` : `[主线] 标准剧情推进 (Index: ${i})`),
            location: isFunctionalAI ? '空镜' : '实景',
            scene_type: isFunctionalAI ? SceneType.ESTABLISHING : types[i % types.length],
            logicRole: isFunctionalAI ? 'functional_attachment' : 'main_plot',
            needsResequence: needsResequence,

            // === 新增：物理时间戳 ===
            startTime: startTime,
            endTime: endTime,
            duration: duration
        });

        if (i > 0) {
            if (isFunctionalAI && lastMainPlotId) {
                relationships.push({ source: lastMainPlotId, target: id, type: 'attachment' });
            } else {
                if (lastMainPlotId) {
                    relationships.push({ source: lastMainPlotId, target: id, type: 'sequence' });
                }
                lastMainPlotId = id;
            }
        } else {
            lastMainPlotId = id;
        }
    }

    return { scenes, relationships };
};