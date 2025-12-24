import React from 'react';
import ReactDOM from 'react-dom/client';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import SceneWorkbench from './features/orchestration/SceneWorkbench';
// 引入 React Flow 样式
import '@xyflow/react/dist/style.css';

ReactDOM.createRoot(document.getElementById('app')).render(
    <React.StrictMode>
        <ConfigProvider locale={zhCN}>
            <SceneWorkbench />
        </ConfigProvider>
    </React.StrictMode>
);