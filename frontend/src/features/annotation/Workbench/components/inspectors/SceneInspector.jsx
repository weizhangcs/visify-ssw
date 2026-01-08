import React, { useMemo } from 'react';
import { Select, Input, Tooltip } from 'antd';
import {
    EnvironmentOutlined,
    VideoCameraOutlined,
    TagsOutlined,
    AimOutlined,
    FileTextOutlined,
    InfoCircleOutlined,
    EditOutlined,
    ClockCircleOutlined,
    CheckOutlined,
    DeleteOutlined,
    TeamOutlined
} from '@ant-design/icons';
import VOCAB from '../../config/vocabularies.json';
import './inspector.css';

const { TextArea } = Input;

const SceneInspector = ({
                            data,
                            track = {},
                            onChange,
                            onTrackChange,
                            onConfirm,
                            onDelete,
                            onCancel,
                        }) => {

    const {
        narrative_action,
        visual_mood_tags = [],
        scene_type,
        location,
        camera_logic,
        reason,
        description,
        character_dynamics
    } = data;

    const { start = 0, end = 0 } = track;

    const duration = useMemo(() => {
        if (end > start) return (end - start).toFixed(2);
        return '0.00';
    }, [start, end]);

    return (
        <div className="inspector-card">

            <div className="inspector-scroll-area">

                {/* Row 1: 类型 + 时间 */}
                <div style={{ display: 'grid', gridTemplateColumns: '4fr 6fr', gap: '12px' }}>
                    <div className="form-group">
                        <label className="form-label"><VideoCameraOutlined /> 类型</label>
                        <Select
                            className="w-full"
                            value={scene_type || 'unknown'}
                            onChange={(val) => onChange('scene_type', val)}
                            options={VOCAB.scene_types.map(opt => ({ label: opt.label, value: opt.value }))}
                            size="middle"
                        />
                    </div>

                    <div className="form-group">
                        <label className="form-label"><ClockCircleOutlined /> 时间段</label>
                        <div className="time-input-container">
                            <input
                                value={start.toFixed(2)}
                                onChange={(e) => onTrackChange && onTrackChange('start', e.target.value)}
                                disabled={!onTrackChange}
                            />
                            <span className="time-arrow">→</span>
                            <input
                                value={end.toFixed(2)}
                                onChange={(e) => onTrackChange && onTrackChange('end', e.target.value)}
                                disabled={!onTrackChange}
                            />
                            <span className="duration-badge">{duration}s</span>
                        </div>
                    </div>
                </div>

                {/* Row 2: 地点 */}
                <div className="form-group">
                    <label className="form-label"><EnvironmentOutlined /> 地点</label>
                    <Input
                        value={location || ''}
                        onChange={(e) => onChange('location', e.target.value)}
                        placeholder="场景发生的具体地点..."
                    />
                </div>

                {/* Row 3: 核心叙事 */}
                <div className="form-group">
                    <label className="form-label required" style={{ color: '#334155' }}>
                        <FileTextOutlined /> 核心叙事
                    </label>
                    <TextArea
                        value={narrative_action || ''}
                        onChange={(e) => onChange('narrative_action', e.target.value)}
                        placeholder="描述核心剧情动作..."
                        autoSize={{ minRows: 3, maxRows: 6 }}
                        className="form-textarea"
                    />
                </div>

                {/* Row 3.5: 角色张力 */}
                <div className="form-group">
                    <label className="form-label"><TeamOutlined /> 角色张力</label>
                    <TextArea
                        value={character_dynamics || ''}
                        onChange={(e) => onChange('character_dynamics', e.target.value)}
                        placeholder="描述角色间的互动关系与张力..."
                        autoSize={{ minRows: 2, maxRows: 4 }}
                    />
                </div>

                {/* Row 4: 视觉氛围 */}
                <div className="form-group">
                    <label className="form-label"><TagsOutlined /> 视觉氛围</label>
                    <Select
                        mode="tags"
                        style={{ width: '100%' }}
                        placeholder="输入标签并回车..."
                        value={visual_mood_tags}
                        onChange={(newTags) => onChange('visual_mood_tags', newTags)}
                        options={VOCAB.scene_moods.map(m => ({ label: m.label, value: m.value }))}
                        tokenSeparators={[',', ' ']}
                        maxTagCount="responsive"
                    />
                </div>

                {/* Row 5: 运镜逻辑 & AI依据 */}
                <div className="flex gap-3">
                    <div className="form-group flex-1">
                        <label className="form-label"><AimOutlined /> 运镜逻辑</label>
                        <TextArea
                            value={camera_logic || ''}
                            onChange={(e) => onChange('camera_logic', e.target.value)}
                            placeholder="例如: Fast cuts..."
                            autoSize={{ minRows: 3, maxRows: 5 }}
                            style={{ backgroundColor: '#f8fafc' }}
                        />
                    </div>

                    {reason && (
                        <div className="form-group flex-1">
                            <label className="form-label" style={{ color: '#94a3b8' }}>
                                <InfoCircleOutlined /> AI 依据
                            </label>
                            {/* 使用 CSS 类名 */}
                            <div className="readonly-box">
                                {reason}
                            </div>
                        </div>
                    )}
                </div>

                {/* Row 6: 其他备注 */}
                <div className="form-group">
                    <label className="form-label"><EditOutlined /> 其他备注</label>
                    <TextArea
                        value={description || ''}
                        onChange={(e) => onChange('description', e.target.value)}
                        placeholder="仅供内部参考..."
                        autoSize={{ minRows: 2, maxRows: 4 }}
                        style={{ fontSize: '12px', color: '#64748b' }}
                    />
                </div>
            </div>

            {/* --- Footer --- */}
            <div className="inspector-footer">
                <button
                    className="btn-ghost-danger"
                    onClick={onDelete}
                    title="删除此片段"
                >
                    <DeleteOutlined /> 删除
                </button>

                <div className="footer-actions-right">
                    <button className="btn-secondary"
                            onClick={onCancel}>
                        取消
                    </button>
                    <button
                        className="btn-primary"
                        onClick={onConfirm}
                    >
                        <CheckOutlined /> 确认审订
                    </button>
                </div>
            </div>
        </div>
    );
};

export default SceneInspector;