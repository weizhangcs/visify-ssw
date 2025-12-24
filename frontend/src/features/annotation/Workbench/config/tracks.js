/**
 * 泳道 (Track) 定义与能力配置
 * 集中管理所有轨道的基础属性和交互权限
 */
export const TRACK_DEFINITIONS = {
    // 1. 场景轨 (复杂数据)
    scenes: {
        id: 'scenes',
        label: 'SCENES',
        color: '#d8b4fe', // Purple
        capabilities: {
            create: true,
            resize: true,
            move: true,
            split: false, // 禁止拆分
            merge: false  // 禁止合并
        },
        // 创建新片段时的默认数据
        // [升级] 对齐 V5.3 Schema 的初始数据结构
        factory: () => ({
            label: '新场景',
            location: 'Unknown',
            scene_type: 'unknown',
            camera_logic: '',
            reason: '',
            tags: [], // 预留标签数组
            character_dynamics: '',
            description: ''
        })
    },

    // 2. 高光轨 (复杂数据)
    highlights: {
        id: 'highlights',
        label: 'HIGHLIGHTS',
        color: '#fcd34d', // Amber
        capabilities: {
            create: true,
            resize: true,
            move: true,
            split: false,
            merge: false
        },
        factory: () => ({ label: 'Action', type: 'Action', description: '' })
    },

    // 3. 字幕轨 (简单数据)
    dialogues: {
        id: 'dialogues',
        label: 'DIALOG',
        color: '#bae7ff', // Blue
        capabilities: {
            create: true,
            resize: true,
            move: true,
            split: true,  // 允许拆分
            merge: true   // 允许合并
        },
        factory: () => ({ text: '新字幕', speaker: 'Unknown' })
    },

    // 4. 提词轨 (简单数据)
    captions: {
        id: 'captions',
        label: 'CAPTIONS',
        color: '#ffbb96', // Orange
        capabilities: {
            create: true,
            resize: true,
            move: true,
            split: true,
            merge: true
        },
        factory: () => ({ text: '新提词', category: 'other' })
    }
};

/**
 * 辅助函数：获取轨道能力
 */
export const getTrackConfig = (trackId) => TRACK_DEFINITIONS[trackId];

export const canTrackDo = (trackId, action) => {
    const config = TRACK_DEFINITIONS[trackId];
    return config?.capabilities?.[action] || false;
};