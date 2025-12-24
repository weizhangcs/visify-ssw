import React, { useCallback, useMemo, useState } from 'react';
import {
    ReactFlow, Background, Controls, MiniMap, useNodesState, useEdgesState, addEdge,
    MarkerType, Panel, ReactFlowProvider, useReactFlow
} from '@xyflow/react';
import { Button, message, notification } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';

import SceneCard from './components/SceneCard';
import Sidebar from './components/Sidebar';
import VideoModal from './components/VideoModal';
import { generateMockRepository } from './utils/mockData';
import { getLayoutedElements } from './utils/layoutEngine';

const REPO = generateMockRepository(300);
const TODO_LIST = REPO.scenes.filter(s => s.needsResequence);

function WorkbenchContent() {
    const [nodes, setNodes, onNodesChange] = useNodesState([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState([]);
    const { fitView } = useReactFlow();

    // === 新增：播放器状态 ===
    const [playingScene, setPlayingScene] = useState(null); // 当前播放的场景对象

    const handlePlay = useCallback((scene) => {
        console.log('Play Request:', scene);
        setPlayingScene(scene); // 触发 Modal 打开
    }, []);

    const nodeTypes = useMemo(() => ({ sceneCard: SceneCard }), []);

    // === 核心：转换器 ===
    const transformToGraph = useCallback((targetScenes, existingNodes = []) => {
        const existingIds = new Set(existingNodes.map(n => n.id));
        const newNodes = [...existingNodes];

        targetScenes.forEach(scene => {
            if (existingIds.has(scene.id)) return;
            newNodes.push({
                id: scene.id,
                type: 'sceneCard',
                position: { x: 0, y: 0 },
                data: {
                    content: scene,
                    isCollapsed: true,
                    logicRole: scene.logicRole,
                    onPlay: handlePlay,
                },
            });
        });

        // 计算连线 (仅显示双方都在场内的线)
        const visibleNodeIds = new Set(newNodes.map(n => n.id));
        const visibleEdges = [];
        REPO.relationships.forEach(rel => {
            if (visibleNodeIds.has(rel.source) && visibleNodeIds.has(rel.target)) {
                const isAttach = rel.type === 'attachment';
                visibleEdges.push({
                    id: isAttach ? `att-${rel.source}-${rel.target}` : `seq-${rel.source}-${rel.target}`,
                    source: rel.source,
                    target: rel.target,
                    sourceHandle: isAttach ? 'out-attach' : 'out-seq',
                    targetHandle: isAttach ? 'in-attach' : 'in-seq',
                    type: isAttach ? 'step' : 'smoothstep',
                    animated: isAttach,
                    style: isAttach ? { stroke: '#faad14', strokeDasharray: '5,5' } : { stroke: '#b1b1b7', strokeWidth: 2 },
                    markerEnd: isAttach ? undefined : { type: MarkerType.ArrowClosed },
                    label: isAttach ? 'AI' : undefined,
                    labelStyle: { fill: '#faad14', fontSize: 10 }
                });
            }
        });

        return { nodes: newNodes, edges: visibleEdges };
    }, [handlePlay]); // 依赖 handlePlay

    // === 辅助：寻找稳定锚点 (Find Stable Anchor) ===
    const findStableAnchor = (startIndex, direction) => {
        let curr = startIndex + direction;
        // 防止死循环，最大查找 50 个
        let steps = 0;
        while(curr >= 0 && curr < REPO.scenes.length && steps < 50) {
            const scene = REPO.scenes[curr];
            // 稳定条件：是主剧情节点 且 没有被标记为待修改
            if (scene.logicRole === 'main_plot' && !scene.needsResequence) {
                return curr;
            }
            curr += direction;
            steps++;
        }
        return curr; // 到了边界
    };

    // === Action 1: 纯物理范围加载 (Main Stage) ===
    const handleLoadRange = (startIdx, endIdx) => {
        // 这里不做智能扩展，用户要什么给什么 (遵守 Max 20 约束)
        const targets = REPO.scenes.slice(startIdx, endIdx);
        const { nodes: nextNodes, edges: nextEdges } = transformToGraph(targets, []); // 替换模式

        const layouted = getLayoutedElements(nextNodes, nextEdges);
        setNodes([...layouted.nodes]);
        setEdges([...layouted.edges]);

        setTimeout(() => fitView({ duration: 800 }), 100);
    };

    // === Action 2: 智能上下文加载 (Fixing Tool) ===
    const handleLoadSmartContext = (query) => {
        let targetIndices = [];

        // A. 解析输入 (可能是数字索引，可能是 ID，可能是范围字符串 "39-41")
        if (typeof query === 'number') {
            targetIndices = [query];
        } else if (typeof query === 'string') {
            // 尝试解析范围 "39-41"
            const rangeMatch = query.match(/^(\d+)-(\d+)$/);
            if (rangeMatch) {
                const start = parseInt(rangeMatch[1]) - 1; // 转为 0-based index
                const end = parseInt(rangeMatch[2]);
                for(let i = start; i < end; i++) targetIndices.push(i);
            } else if (query.match(/^\d+$/)) {
                // 纯数字字符串
                targetIndices.push(parseInt(query) - 1);
            } else {
                // 尝试 ID 匹配
                const s = REPO.scenes.find(x => x.id === query || x.label === query);
                if(s) targetIndices.push(s.index);
            }
        }

        if (targetIndices.length === 0 || targetIndices[0] < 0) {
            message.error('无法定位目标场景');
            return;
        }

        // B. 计算智能边界
        // 找出这组目标里 最小 和 最大 的索引
        const minTarget = Math.min(...targetIndices);
        const maxTarget = Math.max(...targetIndices);

        // 向前找稳定锚点
        const startAnchor = findStableAnchor(minTarget, -1);
        // 向后找稳定锚点
        const endAnchor = findStableAnchor(maxTarget, 1);

        // C. 提取数据 (包含两端的稳定锚点)
        // slice 是左闭右开，所以 endAnchor 要 +1，但考虑到 endAnchor 本身也要包含，且 slice 的 end 参数
        const loadStart = Math.max(0, startAnchor);
        const loadEnd = Math.min(REPO.scenes.length, endAnchor + 1);

        const contextScenes = REPO.scenes.slice(loadStart, loadEnd);

        // 追加模式 (append)
        const { nodes: nextNodes, edges: nextEdges } = transformToGraph(contextScenes, nodes);

        const layouted = getLayoutedElements(nextNodes, nextEdges);
        setNodes([...layouted.nodes]);
        setEdges([...layouted.edges]);

        const count = loadEnd - loadStart;
        message.success(`智能装载: 检测到 ${targetIndices.length} 个目标，自动关联上下文共 ${count} 个场景`);
        setTimeout(() => fitView({ duration: 800 }), 100);
    };

    const handleClear = () => {
        setNodes([]);
        setEdges([]);
    };

    const onConnect = useCallback((params) => {
        setEdges((eds) => addEdge({ ...params, type: 'smoothstep' }, eds));
    }, [setEdges]);

    return (
        <div style={{ width: '100%', height: '100%', display: 'flex' }}>
            <Sidebar
                totalCount={REPO.scenes.length}
                todoList={TODO_LIST}
                currentLoadedCount={nodes.length}
                onLoadRange={handleLoadRange}
                onLoadSmartContext={handleLoadSmartContext}
                onClearWorkspace={handleClear}
            />
            <div style={{ flex: 1, position: 'relative', borderLeft: '1px solid #ddd' }}>
                <ReactFlow
                    nodes={nodes}
                    edges={edges}
                    onNodesChange={onNodesChange}
                    onEdgesChange={onEdgesChange}
                    onConnect={onConnect}
                    nodeTypes={nodeTypes}
                    fitView
                    minZoom={0.1}
                >
                    <Background color="#f0f2f5" gap={20} />
                    <Controls />
                    <MiniMap nodeColor={(n) => n.data.logicRole === 'functional_attachment' ? '#faad14' : '#1677ff'} />

                    {nodes.length === 0 && (
                        <div style={{ position: 'absolute', top: '40%', left: '50%', transform: 'translate(-50%, -50%)', color: '#999', textAlign: 'center' }}>
                            <h3>✨ 工作台就绪</h3>
                            <p>装载主线范围，或点击待修正项开始工作</p>
                        </div>
                    )}

                    <Panel position="top-right">
                        <Button icon={<ReloadOutlined />} onClick={() => {
                            const layouted = getLayoutedElements(nodes, edges);
                            setNodes([...layouted.nodes]);
                            setEdges([...layouted.edges]);
                        }}>整理布局</Button>
                    </Panel>
                </ReactFlow>

                {/* === 全局播放器 Modal === */}
                <VideoModal
                    visible={!!playingScene}
                    scene={playingScene}
                    onClose={() => setPlayingScene(null)}
                />
            </div>
        </div>
    );
}

export default function SceneWorkbench() {
    return (
        <div style={{ width: '100vw', height: '100vh', background: '#fff' }}>
            <ReactFlowProvider>
                <WorkbenchContent />
            </ReactFlowProvider>
        </div>
    );
}