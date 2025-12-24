import React, { useState, useMemo } from 'react';
import { Typography, Input, Button, List, Badge, Divider, Card, InputNumber, Space, message, Tag } from 'antd';
import { AimOutlined, ClearOutlined, WarningOutlined, ImportOutlined, CompressOutlined } from '@ant-design/icons';

const { Text } = Typography;
const { Search } = Input;

export default function Sidebar({
                                    totalCount,
                                    todoList,
                                    currentLoadedCount,
                                    onLoadRange,
                                    onLoadSmartContext,
                                    onClearWorkspace
                                }) {
    const [rangeStart, setRangeStart] = useState(1);
    const [rangeEnd, setRangeEnd] = useState(20);
    const [searchVal, setSearchVal] = useState('');

    const handleRangeLoad = () => {
        const count = rangeEnd - rangeStart + 1;
        if (count > 20) {
            message.warning('为了减轻认知负担，单次装载请勿超过 20 个场景');
            return;
        }
        if (count <= 0) {
            message.error('结束序号必须大于开始序号');
            return;
        }
        onLoadRange(rangeStart - 1, rangeEnd);
    };

    // 连续性聚合算法 (保持不变)
    const groupedTodos = useMemo(() => {
        if (!todoList || todoList.length === 0) return [];
        const sorted = [...todoList].sort((a, b) => a.index - b.index);
        const groups = [];
        if (sorted.length === 0) return [];

        let currentGroup = { start: sorted[0], end: sorted[0], items: [sorted[0]] };

        for (let i = 1; i < sorted.length; i++) {
            const item = sorted[i];
            if (item.index === currentGroup.end.index + 1) {
                currentGroup.end = item;
                currentGroup.items.push(item);
            } else {
                groups.push(currentGroup);
                currentGroup = { start: item, end: item, items: [item] };
            }
        }
        groups.push(currentGroup);
        return groups;
    }, [todoList]);

    return (
        <div style={{ width: 300, borderRight: '1px solid #ddd', display: 'flex', flexDirection: 'column', height: '100%', background: '#fff' }}>

            {/* 1. 头部 & 统计 */}
            <div style={{ padding: 15, borderBottom: '1px solid #eee', background: '#fafafa' }}>
                <h3>🕹️ 编排控制台</h3>
                <Space split={<Divider type="vertical" />}>
                    <Text type="secondary" style={{fontSize: 12}}>总数: {totalCount}</Text>
                    <Badge status={currentLoadedCount > 0 ? "processing" : "default"} text={`视口: ${currentLoadedCount}`} />
                </Space>
            </div>

            {/* 2. 初始装载区 (Initial Loading) - 已改名 */}
            <div style={{ padding: 15, borderBottom: '1px solid #eee' }}>
                <Text strong style={{fontSize: 12}}>📖 初始装载区 (Max 20)</Text>
                <div style={{ marginTop: 8, display: 'flex', gap: 5 }}>
                    <InputNumber min={1} max={totalCount} value={rangeStart} onChange={setRangeStart} style={{flex:1}} size="small"/>
                    <span style={{lineHeight: '24px'}}>-</span>
                    <InputNumber min={1} max={totalCount} value={rangeEnd} onChange={setRangeEnd} style={{flex:1}} size="small"/>
                    <Button type="primary" size="small" icon={<ImportOutlined />} onClick={handleRangeLoad} />
                </div>
            </div>

            {/* 3. 精准返工 (Rework Tool) - 移到上方 */}
            <div style={{ padding: 15, borderBottom: '1px solid #eee', background: '#f9f9f9' }}>
                <div style={{display:'flex', justifyContent:'space-between', marginBottom: 5}}>
                    <Text style={{fontSize: 12}}>🔍 精准返工 (支持范围):</Text>
                    <Button type="link" size="small" danger onClick={onClearWorkspace} icon={<ClearOutlined />}>清空</Button>
                </div>
                <Search
                    placeholder="输入 39 或 39-41"
                    allowClear
                    enterButton={<AimOutlined />}
                    value={searchVal}
                    onChange={e => setSearchVal(e.target.value)}
                    onSearch={(val) => {
                        if(!val) return;
                        onLoadSmartContext(val);
                        setSearchVal('');
                    }}
                />
            </div>

            {/* 4. 待调整清单 (Smart Context) - 移到底部并自动填充剩余空间 */}
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                <div style={{ padding: '10px 15px 5px', background: '#fff' }}>
                    <Text type="warning" strong style={{fontSize: 12}}>
                        <WarningOutlined /> 待修正片段 ({groupedTodos.length} 组)
                    </Text>
                </div>

                {/* 这里使用 flex: 1 让列表占据剩余所有高度，并开启 overflowY: auto */}
                <div style={{ flex: 1, overflowY: 'auto', padding: '0 15px 10px' }}>
                    <List
                        dataSource={groupedTodos}
                        split={false}
                        renderItem={group => {
                            const isRange = group.items.length > 1;
                            const label = isRange
                                ? `SC ${group.start.index + 1} - ${group.end.index + 1}`
                                : group.start.label;

                            const queryPayload = isRange
                                ? `${group.start.index + 1}-${group.end.index + 1}`
                                : group.start.index;

                            return (
                                <Card
                                    size="small"
                                    hoverable
                                    style={{ marginBottom: 8, borderLeft: '3px solid #faad14', cursor: 'pointer' }}
                                    bodyStyle={{ padding: '8px 12px' }}
                                    onClick={() => onLoadSmartContext(queryPayload)}
                                >
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                        <Text strong style={{fontSize: 13}}>
                                            {isRange && <CompressOutlined style={{marginRight: 4}} />}
                                            {label}
                                        </Text>
                                        {isRange && <Tag color="orange" style={{margin:0}}>{group.items.length} 个片段</Tag>}
                                    </div>

                                    <div style={{ fontSize: 10, color: '#666', marginTop: 4 }} className="text-truncate">
                                        {isRange
                                            ? `[连续修正区] 包含 ${group.start.label} 至 ${group.end.label}`
                                            : group.start.narrative_action}
                                    </div>
                                </Card>
                            );
                        }}
                    />
                </div>
            </div>

        </div>
    );
}