import React, { memo, useState } from 'react';
import { Input } from 'antd';
import { useReactFlow } from '@xyflow/react';

const GroupNode = ({ id, data, selected }) => {
    // 使用 useReactFlow 来更新节点数据
    const { setNodes } = useReactFlow();

    const onChange = (e) => {
        const newVal = e.target.value;
        // 实时更新 React Flow 数据模型
        setNodes((nds) =>
            nds.map((node) => {
                if (node.id === id) {
                    return {
                        ...node,
                        data: { ...node.data, label: newVal },
                    };
                }
                return node;
            })
        );
    };

    return (
        <div
            style={{
                width: '100%',
                height: '100%',
                backgroundColor: 'rgba(240, 240, 240, 0.4)', // 稍微透明一点
                border: selected ? '2px dashed #1677ff' : '2px dashed #ccc',
                borderRadius: 12,
                padding: 10,
                paddingTop: 40, // 留出标题位置
                position: 'relative',
                minWidth: 300,
                minHeight: 200,
            }}
        >
            {/* === 需求 5: 场景组可编辑命名 === */}
            <div style={{ position: 'absolute', top: -15, left: 10, width: 200 }}>
                <Input
                    size="small"
                    value={data.label}
                    onChange={onChange}
                    className="nodrag" // 关键：允许输入时禁止拖拽节点
                    style={{
                        fontWeight: 'bold',
                        color: '#1677ff',
                        borderColor: '#91caff',
                        background: '#e6f4ff',
                        boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
                    }}
                />
            </div>
        </div>
    );
};

export default memo(GroupNode);