import React, { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { Card, Typography, Tag, Space, Badge, Button } from 'antd';
import { DownOutlined, UpOutlined, PlayCircleFilled } from '@ant-design/icons'; // 引入播放图标
import { SceneType, SceneTypeLabels, SceneTypeColors } from '../types/constants';

const { Paragraph, Text } = Typography;

const SceneCard = ({ data, id }) => {
    const { content, isCollapsed, logicRole, onPlay } = data; // 从 data 解构 onPlay
    const isFunctional = logicRole === 'functional_attachment';
    const bgColor = SceneTypeColors[content.scene_type];

    // 类型颜色映射 (保持不变)
    const typeColor = {
        [SceneType.DIALOGUE]: 'blue',
        [SceneType.ACTION]: 'orange',
        [SceneType.MONTAGE]: 'purple',
        [SceneType.ESTABLISHING]: 'green',
        [SceneType.EMOTIONAL]: 'magenta',
        [SceneType.UNKNOWN]: 'default',
    }[content.scene_type];

    return (
        <div style={{ position: 'relative' }}>
            <Handle type="target" position={Position.Left} id="in-seq" style={{ width: 10, height: 10, background: '#666' }} />
            <Handle type="target" position={Position.Top} id="in-attach" style={{ left: '50%', borderRadius: 0, width: 30, height: 8, background: '#faad14' }} />

            <Badge.Ribbon text={isFunctional ? "挂件" : null} color="gold" style={{ display: isFunctional ? 'block' : 'none' }}>
                <Card
                    size="small"
                    hoverable
                    style={{
                        width: isCollapsed ? 200 : 320,
                        transform: isFunctional ? 'scale(0.85)' : 'scale(1)',
                        opacity: isFunctional ? 0.9 : 1,
                        backgroundColor: bgColor,
                        transition: 'all 0.3s',
                        border: '1px solid #d9d9d9',
                    }}
                    title={
                        <Space>
                            <Tag color={typeColor} style={{ fontWeight: 'bold' }}>{SceneTypeLabels[content.scene_type]}</Tag>
                            <Text strong>{content.label}</Text>
                        </Space>
                    }
                    extra={
                        <Space>
                            {/* === 新增：播放按钮 === */}
                            <Button
                                type="text"
                                shape="circle"
                                icon={<PlayCircleFilled style={{ color: '#1677ff', fontSize: 18 }} />}
                                className="nodrag"
                                onClick={(e) => {
                                    e.stopPropagation();
                                    if (onPlay) onPlay(content); // 触发回调，传递当前场景数据
                                }}
                            />
                            <Button
                                type="text"
                                size="small"
                                icon={isCollapsed ? <DownOutlined /> : <UpOutlined />}
                                className="nodrag"
                                onClick={(e) => {
                                    // Toggle 逻辑 (保持不变，或通过父组件处理)
                                    console.log('Toggle', id);
                                }}
                            />
                        </Space>
                    }
                >
                    {/* 内容保持不变 */}
                    {!isCollapsed ? (
                        <>
                            <div style={{ marginBottom: 6 }}>
                                <Text type="secondary" style={{ fontSize: 12 }}>
                                    📍 {content.location} | ⏱ {formatTimeSimple(content.startTime)}-{formatTimeSimple(content.endTime)}
                                </Text>
                            </div>
                            <Paragraph ellipsis={{ rows: 3 }} style={{ marginBottom: 8, fontSize: 13, color: '#333' }}>
                                {content.narrative_action}
                            </Paragraph>
                            <Space size={[0, 4]} wrap>
                                {content.visual_mood_tags && content.visual_mood_tags.map(tag => (
                                    <Tag key={tag} bordered={false} style={{ fontSize: 10, background: 'rgba(255,255,255,0.6)' }}>#{tag}</Tag>
                                ))}
                            </Space>
                        </>
                    ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                            <Text ellipsis style={{ width: '100%', fontSize: 12 }}>{content.narrative_action}</Text>
                        </div>
                    )}
                </Card>
            </Badge.Ribbon>

            <Handle type="source" position={Position.Right} id="out-seq" style={{ width: 10, height: 10, background: '#666' }} />
            <Handle type="source" position={Position.Bottom} id="out-attach" style={{ left: '50%', borderRadius: 0, width: 30, height: 8, background: '#faad14' }} />
        </div>
    );
};

// 简单的分秒格式化
function formatTimeSimple(seconds) {
    if(seconds === undefined) return '00:00';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2,'0')}`;
}

export default memo(SceneCard);