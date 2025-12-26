// frontend/src/entries/scene_orchestration.jsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
// 引入 React Flow 样式
import '@xyflow/react/dist/style.css';
import SceneWorkbench from '../features/orchestration/SceneWorkbench';

// 获取后端注入的上下文
const context = window.SERVER_CONTEXT || {};
const rootNode = document.getElementById('react-root-orchestration');

if (rootNode) {
    const root = ReactDOM.createRoot(rootNode);
    root.render(
        <ConfigProvider
            locale={zhCN}
            theme={{
                token: {
                    colorPrimary: '#722ed1', // Purple-700 (对齐 Annotation 风格)
                    borderRadius: 6,
                },
            }}
        >
            <SceneWorkbench context={context} />
        </ConfigProvider>
    );
}