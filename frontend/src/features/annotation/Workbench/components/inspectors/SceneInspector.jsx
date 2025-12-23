// frontend/src/features/annotation/Workbench/components/inspectors/SceneInspector.jsx
import React from 'react';
import { Tag, Divider, Typography, Empty } from 'antd';
import {
    EnvironmentOutlined,
    VideoCameraOutlined,
    BulbOutlined,
    TagsOutlined
} from '@ant-design/icons';
import VOCAB from '../../config/vocabularies.json';

const { Text, Paragraph } = Typography;

const SceneInspector = ({ data, onChange }) => {
    // 提取新字段
    const {
        tags = [],
        camera_logic,
        reason,
        location,
        scene_type,
        label,
        description,
        character_dynamics
    } = data;

    return (
        <div className="scene-inspector-content">
            {/* A. 核心标题 (对应 narrative_action) */}
            <div className="form-group">
                <label className="form-label required">场景事件 / 标题</label>
                <input
                    type="text"
                    className="form-input"
                    placeholder="例如：主角在雨中重逢..."
                    value={label || ''}
                    onChange={(e) => onChange('label', e.target.value)}
                />
            </div>

            <div className="form-row">
                <div className="form-group">
                    <label className="form-label">
                        <VideoCameraOutlined /> 场景类型
                    </label>
                    <select
                        className="form-select"
                        value={scene_type || ''}
                        onChange={(e) => onChange('scene_type', e.target.value)}
                    >
                        <option value="">-- 未选择 --</option>
                        {VOCAB.scene_types.map(opt => (
                            <option key={opt.value} value={opt.value}>{opt.label}</option>
                        ))}
                    </select>
                </div>
                <div className="form-group">
                    <label className="form-label">
                        <EnvironmentOutlined /> 场景地点
                    </label>
                    <input
                        type="text"
                        className="form-input"
                        placeholder="例如：室内/办公室"
                        value={location || ''}
                        onChange={(e) => onChange('location', e.target.value)}
                    />
                </div>
            </div>

            <Divider style={{ margin: '16px 0' }} />

            {/* B. AI 视觉标签云 */}
            <div className="form-group">
                <label className="form-label">
                    <TagsOutlined /> 视觉与氛围标签 (AI)
                </label>
                <div style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: '6px',
                    padding: '10px',
                    backgroundColor: 'var(--insp-bg-body)',
                    borderRadius: 'var(--insp-input-radius)',
                    border: '1px dashed var(--insp-border-color)'
                }}>
                    {tags && tags.length > 0 ? (
                        tags.map((tag, idx) => (
                            <Tag key={idx} color="blue" style={{ margin: 0 }}>{tag}</Tag>
                        ))
                    ) : (
                        <Text type="secondary" italic>未识别到标签</Text>
                    )}
                </div>
            </div>

            {/* C. AI 推理洞察 (Camera Logic & Reason) */}
            <div className="form-group">
                <label className="form-label">
                    <BulbOutlined /> AI 剪辑与运镜建议
                </label>
                <div style={{
                    padding: '12px',
                    backgroundColor: '#f0f9ff',
                    borderLeft: '4px solid #3b82f6',
                    borderRadius: '4px',
                    fontSize: '13px',
                    lineHeight: '1.6',
                    color: '#1e40af'
                }}>
                    <div style={{ fontWeight: 600, marginBottom: '4px' }}>运镜逻辑:</div>
                    <Paragraph ellipsis={{ rows: 2, expandable: true, symbol: '展开' }} style={{ margin: 0 }}>
                        {camera_logic || '未提供分析'}
                    </Paragraph>

                    {reason && (
                        <>
                            <div style={{ fontWeight: 600, margin: '8px 0 4px 0', borderTop: '1px solid #bfdbfe', paddingTop: '8px' }}>
                                切分理由:
                            </div>
                            <div style={{ fontStyle: 'italic', color: '#1d4ed8' }}>{reason}</div>
                        </>
                    )}
                </div>
            </div>

            {/* D. 角色关系与描述 */}
            <div className="form-group">
                <label className="form-label">角色动态/关系</label>
                <input
                    type="text"
                    className="form-input"
                    value={character_dynamics || ''}
                    onChange={(e) => onChange('character_dynamics', e.target.value)}
                    placeholder="例如：对立、暧昧..."
                />
            </div>

            <div className="form-group">
                <label className="form-label">剧情备注 (手动)</label>
                <textarea
                    className="form-textarea"
                    placeholder="记录更多场景细节..."
                    value={description || ''}
                    onChange={(e) => onChange('description', e.target.value)}
                    style={{ minHeight: '100px' }}
                />
            </div>
        </div>
    );
};

export default SceneInspector;