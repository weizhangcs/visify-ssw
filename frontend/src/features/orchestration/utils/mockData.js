// frontend/src/features/orchestration/utils/mockData.js

import { SceneType } from '../types/constants';

// [Hardcoded Data] 模拟真实数据的快照
const REAL_DATA_SNAPSHOT = {
    scenes: [
        {
            id: "scene_1", // 简化 ID，方便肉眼 debug
            index: 0,
            label: "SC-1",
            narrative_action: "Daniel Atlas performs a complex card trick.",
            location: "Dark Room",
            scene_type: SceneType.DIALOGUE,
            visual_mood_tags: ["intense", "magic"],
            logicRole: "main_plot",
            needsResequence: false,
            startTime: 100,
            endTime: 120,
            duration: 20,
            streamUrl: "http://localhost:9999/test.m3u8"
        },
        {
            id: "scene_2",
            index: 1,
            label: "SC-2",
            narrative_action: "Transitioning to New York City.",
            location: "New York",
            scene_type: SceneType.ESTABLISHING,
            visual_mood_tags: ["urban", "bright"],
            logicRole: "main_plot",
            needsResequence: false,
            startTime: 120,
            endTime: 140,
            duration: 20,
            streamUrl: "http://localhost:9999/test.m3u8"
        }
    ],
    // 显式定义连线
    relationships: [
        {
            source: "scene_1",
            target: "scene_2",
            type: "sequence"
        }
    ]
};

export const generateMockRepository = (count = 300) => {
    // 直接返回硬编码的快照，忽略 count 参数，确保测试环境绝对受控
    return {
        scenes: REAL_DATA_SNAPSHOT.scenes,
        relationships: REAL_DATA_SNAPSHOT.relationships
    };
};