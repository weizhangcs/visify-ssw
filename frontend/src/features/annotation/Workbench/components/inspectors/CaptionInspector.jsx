import React, { useMemo } from 'react';
import { Input, Select } from 'antd';
import {
    FontSizeOutlined,
    ClockCircleOutlined,
    TagOutlined,
    DeleteOutlined,
    CheckOutlined
} from '@ant-design/icons';
import VOCAB from '../../config/vocabularies.json';
import './inspector.css';

const { TextArea } = Input;

const CaptionInspector = ({
                              data,
                              track = {},
                              onChange,
                              onTrackChange,
                              onConfirm,
                              onCancel,
                              onDelete
                          }) => {

    const { category = 'other', text } = data;
    const { start = 0, end = 0 } = track;

    const duration = useMemo(() => {
        if (end > start) return (end - start).toFixed(2);
        return '0.00';
    }, [start, end]);

    return (
        <div className="inspector-card">
            <div className="inspector-scroll-area">

                {/* Row 1: 分类 + 时间 */}
                <div style={{ display: 'grid', gridTemplateColumns: '4fr 6fr', gap: '12px' }}>
                    {/* [修改] 提词分类改为 Select */}
                    <div className="form-group">
                        <label className="form-label"><TagOutlined /> 提词分类</label>
                        <Select
                            className="w-full"
                            value={category}
                            onChange={(val) => onChange('category', val)}
                            options={VOCAB.caption_categories.map(opt => ({
                                label: opt.label,
                                value: opt.value
                            }))}
                            placeholder="选择分类"
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

                {/* Row 2: OCR 内容 */}
                <div className="form-group">
                    <label className="form-label required">
                        <FontSizeOutlined /> 提词内容
                    </label>
                    <TextArea
                        className="form-textarea"
                        value={text || ''}
                        onChange={(e) => onChange('text', e.target.value)}
                        placeholder="画面上的文字内容..."
                        autoSize={{ minRows: 4, maxRows: 8 }}
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

export default CaptionInspector;