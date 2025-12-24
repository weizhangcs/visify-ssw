export const SceneType = {
    DIALOGUE: 'dialogue',
    ACTION: 'action',
    MONTAGE: 'montage',
    ESTABLISHING: 'establishing',
    EMOTIONAL: 'emotional',
    UNKNOWN: 'unknown',
};

// 新增：中文显性标签映射
export const SceneTypeLabels = {
    [SceneType.DIALOGUE]: '对话场',
    [SceneType.ACTION]: '动作场',
    [SceneType.MONTAGE]: '蒙太奇',
    [SceneType.ESTABLISHING]: '建立/空镜',
    [SceneType.EMOTIONAL]: '情绪场',
    [SceneType.UNKNOWN]: '待定',
};

// 新增：背景色映射（辅助识别）
export const SceneTypeColors = {
    [SceneType.DIALOGUE]: '#e6f4ff', // 浅蓝
    [SceneType.ACTION]: '#fff7e6',   // 浅橙
    [SceneType.MONTAGE]: '#f9f0ff',  // 浅紫
    [SceneType.ESTABLISHING]: '#f6ffed', // 浅绿
    [SceneType.EMOTIONAL]: '#fff0f6', // 浅粉
    [SceneType.UNKNOWN]: '#f5f5f5',   // 浅灰
};