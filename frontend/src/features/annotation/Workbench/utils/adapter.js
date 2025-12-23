import { TRACK_DEFINITIONS } from '../config/tracks';

// 定义工程字段集合 (属于 Context 的字段)
const CONTEXT_FIELDS = ['id', 'is_verified', 'origin', 'ai_meta', 'modified_at'];

/**
 * [前端适配器] Backend Schema -> Timeline Tracks (入站)
 */
export const transformToTracks = (annotationData) => {
    if (!annotationData) return [];

    const {
        scenes = [],
        dialogues = [],
        captions = [],
        highlights = []
    } = annotationData;

    const createTrack = (key, dataItems, effectId) => {
        const config = TRACK_DEFINITIONS[key];
        if (!config) return null;

        return {
            id: config.id,
            name: config.label,
            color: config.color,
            actions: dataItems.map((item, index) => {
                // 1. 提取嵌套结构
                const content = item.content || {};
                const context = item.context || {};

                // 2. 强力打平并标准化字段
                const flatData = {
                    ...content,
                    ...context,
                };

                // [关键修正] 统一 Dialogues 的显示文本字段
                // 确保 Timeline 轨道上能看到文字
                const displayLabel = flatData.label || flatData.text || flatData.content || `Clip ${index + 1}`;

                return {
                    // [关键修正] 确保 ID 绝对唯一，防止 React 渲染失效
                    id: context.id || item.id || `${key}-${index}-${Date.now()}`,
                    start: item.start,
                    end: item.end,
                    effectId: effectId,
                    data: {
                        ...flatData,
                        label: displayLabel // 注入统一的 label 供 UI 显示
                    }
                };
            })
        };
    };

    return [
        createTrack('scenes', scenes, 'scene'),
        createTrack('highlights', highlights, 'highlight'),
        createTrack('dialogues', dialogues, 'subtitle'),
        createTrack('captions', captions, 'caption')
    ].filter(Boolean);
};

/**
 * [反向转换器] Timeline Tracks -> Backend JSON (用于保存/出站)
 */
export const transformFromTracks = (tracks, originalMeta) => {
    const reconstructItem = (action, trackType) => {
        const flatData = action.data || {};
        const content = {};
        const context = {};

        // 核心逻辑：分流字段
        Object.keys(flatData).forEach(key => {
            if (CONTEXT_FIELDS.includes(key)) {
                context[key] = flatData[key];
            } else {
                content[key] = flatData[key];
            }
        });

        // 确保 context.id 始终存在
        context.id = action.id;

        // --- 针对不同轨道的后端 Schema 适配 (对齐 Pydantic) ---

        // 1. Captions (提词器): 后端 content 字段对应前端 text
        if (trackType === 'captions') {
            content.content = flatData.text || flatData.content || "";
            delete content.text;
        }

        // 2. Dialogues (对白): 确保 text 存在
        if (trackType === 'dialogues') {
            content.text = flatData.text || "";
        }

        // 3. Scenes: 保持原有结构即可，parsers.py 会处理剩下的
        if (trackType === 'scenes') {
            // 确保 label 对应后端 narrative_action (如果在后端需要这个映射)
        }

        return {
            start: action.start,
            end: action.end,
            content: content,
            context: context
        };
    };

    const getActionsByTrackId = (id) => {
        const track = tracks.find(t => t.id === id);
        return track ? track.actions.map(a => reconstructItem(a, id)) : [];
    };

    return {
        ...originalMeta,
        updated_at: new Date().toISOString(),
        scenes: getActionsByTrackId('scenes'),
        dialogues: getActionsByTrackId('dialogues'),
        captions: getActionsByTrackId('captions'),
        highlights: getActionsByTrackId('highlights')
    };
};