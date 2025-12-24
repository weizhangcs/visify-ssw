import React, { useEffect, useState, useRef } from 'react';
import { Form, Button, Empty, Tag, Divider, Tooltip, message } from 'antd';
import {
    DeleteOutlined,
    CheckCircleOutlined,
    RobotOutlined,
    UserOutlined,
    SaveOutlined,
    ClockCircleOutlined,
    EditOutlined,
    AuditOutlined,
    UndoOutlined // 新增撤销图标
} from '@ant-design/icons';
import dayjs from 'dayjs';
import _ from 'lodash'; // 引入 lodash 处理深拷贝
import './inspectors/inspector.css';

import SceneInspector from './inspectors/SceneInspector';
import HighlightInspector from './inspectors/HighlightInspector';
import DialogueInspector from './inspectors/DialogueInspector';
import CaptionInspector from './inspectors/CaptionInspector';

const Inspector = ({ action, track, onUpdate, onDelete, characterList }) => {
    // [核心] 本地草稿状态 (Buffered State)
    // 只有点击"确认"时，才把 draft 同步给 action (全局状态)
    const [draft, setDraft] = useState(null);
    const [isDirty, setIsDirty] = useState(false); // 是否有未保存的修改

    // 1. 初始化 / 切换片段时的重置逻辑
    useEffect(() => {
        if (action) {
            // 如果 draft 为空，或者 ID 变了（切到了别的片段），完全重置草稿
            if (!draft || draft.id !== action.id) {
                setDraft(_.cloneDeep(action));
                setIsDirty(false);
            }
                // 2. 特殊情况：处理外部时间轴拖拽 (Timeline Sync)
                // 如果 ID 没变，但外部传入的 start/end 变了（说明用户在拖拽时间轴），
            // 我们需要把新时间同步进 draft，但保留用户正在编辑的 data 内容。
            else if (action.start !== draft.start || action.end !== draft.end) {
                setDraft(prev => ({
                    ...prev,
                    start: action.start,
                    end: action.end
                }));
            }
        } else {
            setDraft(null);
            setIsDirty(false);
        }
    }, [action]); // 依赖 action 变化

    // 空状态渲染
    if (!draft || !track) {
        return (
            <div className="vss-inspector-panel h-full flex flex-col items-center justify-center bg-white text-gray-400">
                <Empty description="未选中任何片段" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                <span className="text-xs mt-2">点击时间轴上的色块进行编辑</span>
            </div>
        );
    }

    // --- 内部交互逻辑 (操作 Draft) ---

    // 修改字段 (Input/Select)
    const handleFieldChange = (field, value) => {
        setDraft(prev => {
            const newData = { ...prev.data, [field]: value };
            return { ...prev, data: newData };
        });
        setIsDirty(true);
    };

    // 修改时间 (Start/End Input)
    const handleTimeChange = (field, value) => {
        const val = parseFloat(value);
        if (!isNaN(val)) {
            setDraft(prev => ({ ...prev, [field]: val }));
            setIsDirty(true);
        }
    };

    // [核心功能] 取消 / 重置
    const handleCancel = () => {
        if (action) {
            // 用原始 action 覆盖 draft，实现回退
            setDraft(_.cloneDeep(action));
            setIsDirty(false);
            message.info("已撤销未保存的修改");
        }
    };

    // [核心功能] 确认审订 / 提交
    const handleConfirm = () => {
        const now = new Date().toISOString();

        // 构造提交数据
        const finalData = {
            ...draft.data,
            is_verified: true, // 标记为已审订
            origin: 'human',   // 标记为人工修改
            modified_at: now
        };

        // 触发父组件更新 (写入 DOM/Context)
        onUpdate({
            ...draft,
            data: finalData
        });

        setIsDirty(false); // 重置脏标记
        message.success("已保存并标记为审订通过");
    };

    // --- 下面是 UI 渲染逻辑 ---

    const containerClass = "vss-inspector-panel h-full bg-white border-l border-gray-200";

    // 注入给子组件的 Props
    const commonProps = {
        data: draft.data,   // 注意：传给子组件的是 draft.data
        track: draft,       // 包含 start/end
        characterList: characterList, // 角色列表
        onChange: handleFieldChange,
        onTrackChange: handleTimeChange,
        onConfirm: handleConfirm,
        // 传递 Cancel 逻辑给子组件
        onCancel: handleCancel,
        onDelete: () => onDelete(action.id),
        isDirty: isDirty // 可选：告诉子组件是否有修改（用于高亮保存按钮等）
    };

    // --- 路由分支 ---

    // 1. Scene 轨道 (全托管卡片)
    if (track.id === 'scenes') {
        return (
            <div className={`${containerClass} p-4 bg-gray-50`}>
                <SceneInspector {...commonProps} />
            </div>
        );
    }

    // 2. Highlight 轨道 (全托管卡片)
    if (track.id === 'highlights') {
        return (
            <div className={`${containerClass} p-4 bg-gray-50`}>
                <HighlightInspector {...commonProps} />
            </div>
        );
    }

    // 3. Dialogue 轨道 (全托管卡片)
    if (track.id === 'dialogues') {
        return (
            <div className={`${containerClass} p-4 bg-gray-50`}>
                <DialogueInspector {...commonProps} />
            </div>
        );
    }

    // 4. Caption 轨道 (全托管卡片)
    if (track.id === 'captions') {
        return (
            <div className={`${containerClass} p-4 bg-gray-50`}>
                <CaptionInspector {...commonProps} />
            </div>
        );
    }

    // --- 兜底 Legacy 模式 (防止未知轨道报错) ---
    return (
        <div className={containerClass}>
            <div className="p-4 text-gray-400">
                未知轨道类型: {track.id}
            </div>
        </div>
    );
};

export default Inspector;