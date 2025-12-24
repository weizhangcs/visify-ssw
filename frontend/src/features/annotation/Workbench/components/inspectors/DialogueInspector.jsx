import React, { useMemo } from 'react';
import { Input, Tag, Typography } from 'antd';
import {
    UserOutlined,
    ClockCircleOutlined,
    FileTextOutlined,
    SoundOutlined,
    DeleteOutlined,
    CheckOutlined,
    TeamOutlined
} from '@ant-design/icons';
import './inspector.css';

const { TextArea } = Input;
const { Text } = Typography;

const DialogueInspector = ({
                               data,
                               track = {},
                               characterList = [], // [新增] 接收角色列表
                               onChange,
                               onTrackChange,
                               onConfirm,
                               onCancel,
                               onDelete
                           }) => {

    const { speaker, text, original_text } = data;
    const { start = 0, end = 0 } = track;

    const duration = useMemo(() => {
        if (end > start) return (end - start).toFixed(2);
        return '0.00';
    }, [start, end]);

    // 处理点击角色 Tag
    const handleCharacterClick = (name) => {
        onChange('speaker', name);
    };

    return (
        <div className="inspector-card">
            <div className="inspector-scroll-area">

                {/* Row 1: 角色 + 时间 (4:6) */}
                <div style={{ display: 'grid', gridTemplateColumns: '4fr 6fr', gap: '12px' }}>
                    <div className="form-group">
                        <label className="form-label"><UserOutlined /> 角色 (Speaker)</label>
                        <Input
                            value={speaker || ''}
                            onChange={(e) => onChange('speaker', e.target.value)}
                            placeholder="Unknown"
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

                {/* [新增] 角色云 (全剧角色列表) */}
                <div className="form-group">
                    <label className="form-label">
                        <TeamOutlined /> 快速选择角色
                    </label>
                    <div style={{
                        display: 'flex',
                        flexWrap: 'wrap',
                        gap: '6px',
                        padding: '10px',
                        backgroundColor: '#f8fafc',
                        border: '1px solid #e2e8f0',
                        borderRadius: '6px',
                        maxHeight: '120px',
                        overflowY: 'auto'
                    }} className="custom-scrollbar">
                        {characterList && characterList.length > 0 ? (
                            characterList.map((name, idx) => (
                                <Tag
                                    key={idx}
                                    color={speaker === name ? "blue" : "default"}
                                    style={{
                                        cursor: 'pointer',
                                        margin: 0,
                                        userSelect: 'none',
                                        fontSize: '12px'
                                    }}
                                    onClick={() => handleCharacterClick(name)}
                                >
                                    {name}
                                </Tag>
                            ))
                        ) : (
                            <Text type="secondary" style={{ fontSize: '12px' }}>
                                暂无角色数据，请先运行角色识别任务。
                            </Text>
                        )}
                    </div>
                </div>

                {/* Row 2: 原始 ASR (只读参考) */}
                {original_text && (
                    <div className="form-group">
                        <label className="form-label" style={{ color: '#94a3b8' }}>
                            <SoundOutlined /> 原始识别 (ASR Source)
                        </label>
                        <div className="readonly-box" style={{ fontFamily: 'monospace', fontSize: '12px' }}>
                            {original_text}
                        </div>
                    </div>
                )}

                {/* Row 3: 字幕修订 (核心) */}
                <div className="form-group">
                    <label className="form-label required">
                        <FileTextOutlined /> 字幕内容 (Subtitle)
                    </label>
                    <TextArea
                        className="form-textarea"
                        value={text || ''}
                        onChange={(e) => onChange('text', e.target.value)}
                        placeholder="输入对话内容..."
                        autoSize={{ minRows: 3, maxRows: 6 }}
                    />
                </div>
            </div>

            {/* Footer */}
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

export default DialogueInspector;