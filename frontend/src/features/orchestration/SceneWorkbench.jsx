import React, { useCallback, useMemo, useState, useEffect } from 'react';
import {
    ReactFlow, Background, Controls, MiniMap, useNodesState, useEdgesState, addEdge,
    MarkerType, Panel, ReactFlowProvider, useReactFlow
} from '@xyflow/react';
import { Button, message, Spin, Result, Tag } from 'antd';
import { ReloadOutlined, SaveOutlined, ArrowLeftOutlined, ForkOutlined } from '@ant-design/icons';

import SceneCard from './components/SceneCard';
import Sidebar from './components/Sidebar';
import VideoModal from './components/VideoModal';
import { getLayoutedElements } from './utils/layoutEngine';

// === V3.1 常量定义 ===
const NODE_TYPE = {
    EVENT: 'event',
    FUNCTIONAL: 'functional'
};

const EDGE_RELATION = {
    CONTINUE: 'continue',
    FORK: 'fork',
    MERGE: 'merge',
    ATTACH: 'attach'
};

function WorkbenchContent({ context }) {
    // React Flow 状态
    const [nodes, setNodes, onNodesChange] = useNodesState([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState([]);
    const { fitView } = useReactFlow();

    // === V3.1 数据仓库 ===
    const [repoScenes, setRepoScenes] = useState([]);     // 物理场景列表 (SceneNodes)
    const [repoTimelines, setRepoTimelines] = useState([]); // [New] 逻辑因果链
    const [repoEdges, setRepoEdges] = useState([]);       // 逻辑连线

    // UI 状态
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState(null);
    const [playingScene, setPlayingScene] = useState(null);

    const { urls, csrfToken } = context;

    // =========================================================================
    // 1. 初始化加载 (Load V3.1 Data)
    // =========================================================================
    useEffect(() => {
        const fetchData = async () => {
            if (!urls?.load_data) return;
            try {
                setLoading(true);
                const res = await fetch(urls.load_data);
                const json = await res.json();

                if (json.status === 'success') {
                    const { scenes, graph } = json.data;

                    // 1. 物理场景按 index 排序
                    const sortedScenes = scenes.sort((a, b) => a.index - b.index);
                    setRepoScenes(sortedScenes);

                    // 2. 加载 V3.1 图谱数据
                    if (graph) {
                        setRepoTimelines(graph.timelines || []);
                        setRepoEdges(graph.edges || []);
                    }

                    message.success(`已加载: ${scenes.length} 个场景, ${graph?.timelines?.length || 0} 条逻辑链`);
                } else {
                    setError(json.message);
                }
            } catch (e) {
                console.error(e);
                setError("无法连接到服务器");
            } finally {
                setLoading(false);
            }
        };
        fetchData();
    }, [urls]);

    // =========================================================================
    // 2. 视图投影 (Repository -> Viewport)
    // =========================================================================
    const nodeTypes = useMemo(() => ({ sceneCard: SceneCard }), []);

    const handlePlay = useCallback((sceneContent) => {
        setPlayingScene(sceneContent);
    }, []);

    const loadToViewport = useCallback((targetScenes, currentNodes = []) => {
        const existingIds = new Set(currentNodes.map(n => n.id));
        const newNodes = [...currentNodes];

        // 1. 实例化节点
        targetScenes.forEach(scene => {
            if (existingIds.has(scene.id)) return;

            // 查找该节点所属的 Timeline 信息 (用于染色或分组)
            const timeline = repoTimelines.find(t => t.id === scene.timeline_id);
            const timelineColor = timeline ? timeline.color : '#999';

            newNodes.push({
                id: scene.id, // UUID
                type: 'sceneCard',
                position: { x: 0, y: 0 },
                data: {
                    content: scene,
                    isCollapsed: true,
                    // [V3.1] 传递新的属性
                    nodeType: scene.node_type || NODE_TYPE.EVENT,
                    timelineId: scene.timeline_id,
                    timelineColor: timelineColor,
                    onPlay: handlePlay,
                },
            });
        });

        // 2. 实例化连线
        const visibleNodeIds = new Set(newNodes.map(n => n.id));

        const visibleEdges = repoEdges.filter(edge => {
            return visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target);
        }).map(edge => {
            const relation = edge.relation || EDGE_RELATION.CONTINUE;

            // 根据关系类型定义样式
            let style = { strokeWidth: 2, stroke: '#b1b1b7' }; // Default: Continue (Grey)
            let animated = false;
            let type = 'smoothstep';

            if (relation === EDGE_RELATION.ATTACH) {
                style = { stroke: '#faad14', strokeDasharray: '5,5' }; // Attach (Orange Dashed)
                type = 'step'; // 阶梯线
            } else if (relation === EDGE_RELATION.FORK) {
                style = { stroke: '#1890ff', strokeWidth: 2 }; // Fork (Blue)
                type = 'default'; // 贝塞尔曲线
            } else if (relation === EDGE_RELATION.MERGE) {
                style = { stroke: '#722ed1', strokeWidth: 2 }; // Merge (Purple)
            }

            return {
                id: `edge-${edge.source}-${edge.target}`,
                source: edge.source,
                target: edge.target,
                // 手柄映射：Attach 用专用手柄，其他用 Sequence 手柄
                sourceHandle: relation === EDGE_RELATION.ATTACH ? 'out-attach' : 'out-seq',
                targetHandle: relation === EDGE_RELATION.ATTACH ? 'in-attach' : 'in-seq',
                type: type,
                animated: animated,
                style: style,
                markerEnd: { type: MarkerType.ArrowClosed },
                data: { relation } // 存储关系元数据
            };
        });

        return { nodes: newNodes, edges: visibleEdges };
    }, [handlePlay, repoEdges, repoTimelines]);

    // =========================================================================
    // 3. 交互动作 (Actions)
    // =========================================================================

    // Sidebar 加载逻辑 (保持不变，基于 Index 计算)
    const handleLoadRange = (startIdx, endIdx) => {
        const targets = repoScenes.slice(startIdx, endIdx);
        if (targets.length === 0) { message.warning("无数据"); return; }

        const { nodes: nextNodes, edges: nextEdges } = loadToViewport(targets, []);
        const layouted = getLayoutedElements(nextNodes, nextEdges);
        setNodes([...layouted.nodes]);
        setEdges([...layouted.edges]);
        setTimeout(() => fitView({ duration: 800 }), 100);
    };

    // 智能上下文逻辑 (略，保持上一版基于 Index 的查找逻辑)
    const handleLoadSmartContext = (query) => {
        // ... (保持上一版的 Index 查找与 Smart Anchor 逻辑不变) ...
        // 为节省篇幅，此处省略，请复用上一版代码，
        // 唯一区别是 loadToViewport 现在会读取新的 timeline_id
        message.info("请复用上一版的智能加载逻辑");
    };

    const handleClear = () => { setNodes([]); setEdges([]); };

    // [V3.1] 保存逻辑
    const handleSaveGraph = async () => {
        setSaving(true);
        try {
            // 1. 收集节点状态
            const currentNodesData = nodes.map(n => ({
                id: n.id,
                node_type: n.data.nodeType, // V3.1 Attribute
                timeline_id: n.data.timelineId // V3.1 Attribute
            }));

            // 2. 收集连线
            const currentEdgesData = edges.map(e => ({
                source: e.source,
                target: e.target,
                relation: e.data?.relation || EDGE_RELATION.CONTINUE
            }));

            // 3. 合并逻辑 (用视口数据更新仓库数据)
            // 简易策略：视口内的覆盖，视口外的保留
            const visibleNodeIds = new Set(nodes.map(n => n.id));
            const edgesToKeep = repoEdges.filter(e => !visibleNodeIds.has(e.source) && !visibleNodeIds.has(e.target));
            const newRepoEdges = [...edgesToKeep, ...currentEdgesData];

            // 更新节点状态 (Type / Timeline)
            const newRepoScenes = repoScenes.map(s => {
                const nodeInView = nodes.find(n => n.id === s.id);
                if (nodeInView) {
                    return {
                        ...s,
                        node_type: nodeInView.data.nodeType,
                        timeline_id: nodeInView.data.timelineId
                    };
                }
                return s;
            });

            // 4. 构造 Payload (OrchestrationGraph V3.1)
            const graphPayload = {
                version: "3.1",
                timelines: repoTimelines, // 目前前端暂不支持创建新 Timeline，原样回传
                nodes: newRepoScenes.map(s => ({
                    id: s.id,
                    node_type: s.node_type || NODE_TYPE.EVENT,
                    timeline_id: s.timeline_id
                })),
                edges: newRepoEdges
            };

            setRepoScenes(newRepoScenes);
            setRepoEdges(newRepoEdges);

            // [DEBUG PROBE] 打印即将发送的 JSON 字符串
            console.log("--------------- DEBUG PAYLOAD START ---------------");
            console.log(JSON.stringify(graphPayload, null, 2));
            console.log("--------------- DEBUG PAYLOAD END   ---------------");

            const res = await fetch(urls.save_data, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                body: JSON.stringify(graphPayload)
            });
            const json = await res.json();

            if (json.status === 'success') message.success("保存成功 (V3.1)");
            else message.error(`保存失败: ${json.message}`);

        } catch (e) {
            console.error(e);
            message.error("保存异常");
        } finally {
            setSaving(false);
        }
    };

    // [V3.1] 连线处理逻辑
    const onConnect = useCallback((params) => {
        const sourceNode = nodes.find(n => n.id === params.source);
        const targetNode = nodes.find(n => n.id === params.target);

        if (!sourceNode || !targetNode) return;

        let relation = EDGE_RELATION.CONTINUE; // Default

        // 判定逻辑 1: 是否挂载
        if (params.sourceHandle === 'out-attach') {
            relation = EDGE_RELATION.ATTACH;
        }
        // 判定逻辑 2: 跨 Timeline (即分叉)
        else if (sourceNode.data.timelineId !== targetNode.data.timelineId) {
            relation = EDGE_RELATION.FORK;
        }

        const newEdge = {
            ...params,
            data: { relation }, // 存储业务关系
            type: relation === EDGE_RELATION.ATTACH ? 'step' : 'smoothstep',
            animated: relation === EDGE_RELATION.ATTACH,
            style: relation === EDGE_RELATION.ATTACH ? { stroke: '#faad14', strokeDasharray: '5,5' }
                : relation === EDGE_RELATION.FORK ? { stroke: '#1890ff' }
                    : { stroke: '#b1b1b7', strokeWidth: 2 },
            markerEnd: relation === EDGE_RELATION.ATTACH ? undefined : { type: MarkerType.ArrowClosed },
        };

        setEdges((eds) => addEdge(newEdge, eds));

        // 如果是 Attach，自动将目标节点标记为 Functional
        if (relation === EDGE_RELATION.ATTACH) {
            setNodes((nds) => nds.map(n => {
                if (n.id === params.target) {
                    return {
                        ...n,
                        data: { ...n.data, nodeType: NODE_TYPE.FUNCTIONAL }
                    };
                }
                return n;
            }));
        }

    }, [nodes, setEdges, setNodes]);

    // =========================================================================
    // 4. 渲染
    // =========================================================================
    if (loading) return <div className="flex h-screen w-full items-center justify-center bg-gray-50"><Spin size="large" tip="加载逻辑分析图谱..." /></div>;
    if (error) return <div className="flex h-screen w-full items-center justify-center bg-gray-50"><Result status="500" title="Error" subTitle={error} /></div>;

    return (
        <div style={{ width: '100%', height: '100%', display: 'flex' }}>
            <Sidebar
                totalCount={repoScenes.length}
                todoList={repoScenes.filter(s => s.needsResequence)}
                currentLoadedCount={nodes.length}
                onLoadRange={handleLoadRange}
                onLoadSmartContext={handleLoadSmartContext} // 请确保Sidebar传递的是 query 字符串或数字
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
                    <MiniMap
                        nodeColor={(n) => {
                            // MiniMap 颜色逻辑：Functional=Grey, Event=TimelineColor
                            if (n.data.nodeType === NODE_TYPE.FUNCTIONAL) return '#d9d9d9';
                            return n.data.timelineColor || '#1890ff';
                        }}
                    />

                    <Panel position="top-right" className="flex gap-2">
                        {/* 这里展示当前存在的 Logic Timelines */}
                        <div style={{ background: 'rgba(255,255,255,0.8)', padding: '4px 8px', borderRadius: 4, display: 'flex', gap: 4, marginRight: 10 }}>
                            {repoTimelines.map(t => (
                                <Tag key={t.id} color={t.color}>{t.name}</Tag>
                            ))}
                        </div>

                        <Button icon={<ReloadOutlined />} onClick={() => {
                            const layouted = getLayoutedElements(nodes, edges);
                            setNodes([...layouted.nodes]);
                            setEdges([...layouted.edges]);
                        }}>整理布局</Button>
                        <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSaveGraph}>保存分析</Button>
                        <Button icon={<ArrowLeftOutlined />} href={urls?.back}>退出</Button>
                    </Panel>
                </ReactFlow>
                <VideoModal visible={!!playingScene} scene={playingScene} onClose={() => setPlayingScene(null)} />
            </div>
        </div>
    );
}

export default function SceneWorkbench({ context }) {
    return (
        <div style={{ width: '100vw', height: '100vh', background: '#fff' }}>
            <ReactFlowProvider>
                <WorkbenchContent context={context} />
            </ReactFlowProvider>
        </div>
    );
}