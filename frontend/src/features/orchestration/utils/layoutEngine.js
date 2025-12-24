import dagre from 'dagre';

const NODE_WIDTH = 300;
const NODE_HEIGHT = 150;
const RANK_SEP = 50;
const NODE_SEP = 30;

export const getLayoutedElements = (nodes, edges) => {
    const dagreGraph = new dagre.graphlib.Graph();

    dagreGraph.setGraph({
        rankdir: 'LR',
        ranksep: RANK_SEP,
        nodesep: NODE_SEP
    });

    dagreGraph.setDefaultEdgeLabel(() => ({}));

    // 1. 注册节点
    nodes.forEach((node) => {
        // 简单的宽度计算：折叠时变窄
        const width = node.data.isCollapsed ? 180 : NODE_WIDTH;
        const height = node.data.isCollapsed ? 80 : NODE_HEIGHT;
        dagreGraph.setNode(node.id, { width, height });
    });

    // 2. 注册连线
    edges.forEach((edge) => {
        dagreGraph.setEdge(edge.source, edge.target);
    });

    // 3. 计算
    dagre.layout(dagreGraph);

    // 4. 回填坐标
    const layoutedNodes = nodes.map((node) => {
        const nodeWithPosition = dagreGraph.node(node.id);
        return {
            ...node,
            targetPosition: 'left',
            sourcePosition: 'right',
            position: {
                x: nodeWithPosition.x - nodeWithPosition.width / 2,
                y: nodeWithPosition.y - nodeWithPosition.height / 2,
            },
        };
    });

    return { nodes: layoutedNodes, edges };
};