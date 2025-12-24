import React, { useMemo } from 'react';
import { Select, Input } from 'antd';
import {
    StarOutlined,
    ClockCircleOutlined,
    SmileOutlined,
    FileTextOutlined,
    DeleteOutlined,
    CheckOutlined
} from '@ant-design/icons';
import VOCAB from '../../config/vocabularies.json';
import './inspector.css'; // 复用统一的样式系统

const { TextArea } = Input;

const HighlightInspector = ({
                                data,
                                track = {},
                                onChange,
                                onTrackChange,
                                onConfirm,
                                onCancel,
                                onDelete
                            }) => {

    // 解构数据
    const {
        type,
        mood,
        description
    } = data;

    const { start = 0, end = 0 } = track;

    // 自动计算时长
    const duration = useMemo(() => {
        if (end > start) return (end - start).toFixed(2);
        return '0.00';
    }, [start, end]);

    return (
        <div className="inspector-card">
            {/* --- 中间滚动区域 --- */}
            <div className="inspector-scroll-area">

                {/* Row 1: 类型 + 时间 (4:6 比例) */}
                <div style={{ display: 'grid', gridTemplateColumns: '4fr 6fr', gap: '12px' }}>

                    {/* A. 高光类型 */}
                    <div className="form-group">
                        <label className="form-label required">
                            <StarOutlined /> 高光类型
                        </label>
                        <Select
                            className="w-full"
                            value={type || 'Other'}
                            onChange={(val) => {
                                onChange('type', val);
                                // [保留原逻辑] 自动同步 Label，方便在时间轴上直观显示
                                onChange('label', val);
                            }}
                            options={VOCAB.highlight_types.map(opt => ({ label: opt.label, value: opt.value }))}
                        />
                    </div>

                    {/* B. 时间段控制 */}
                    <div className="form-group">
                        <label className="form-label">
                            <ClockCircleOutlined /> 时间段
                        </label>
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

                {/* Row 2: 情绪体验 */}
                <div className="form-group">
                    <label className="form-label">
                        <SmileOutlined /> 情绪体验
                    </label>
                    <Select
                        className="w-full"
                        value={mood || ''}
                        onChange={(val) => onChange('mood', val)}
                        options={[
                            { label: '-- 未选择 --', value: '' },
                            ...VOCAB.highlight_moods.map(opt => ({ label: opt.label, value: opt.value }))
                        ]}
                        placeholder="选择带来的情绪感受..."
                    />
                </div>

                {/* Row 3: 高光描述 */}
                <div className="form-group">
                    <label className="form-label">
                        <FileTextOutlined /> 高光描述
                    </label>
                    <TextArea
                        className="form-textarea"
                        value={description || ''}
                        onChange={(e) => onChange('description', e.target.value)}
                        placeholder="描述这一刻为何精彩..."
                        autoSize={{ minRows: 4, maxRows: 8 }}
                    />
                </div>
            </div>

            {/* --- 底部操作栏 --- */}
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

export default HighlightInspector;