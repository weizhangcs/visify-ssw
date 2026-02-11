import React from 'react';
import ReactDOM from 'react-dom/client';
import { AppProvider } from '@/shared/theme';
import VectorLab from '../features/vector/VectorLab';

const context = window.SERVER_CONTEXT || {};
const rootNode = document.getElementById('react-root-vector-lab');

if (rootNode) {
    const root = ReactDOM.createRoot(rootNode);
    root.render(
        <AppProvider>
            <VectorLab context={context} />
        </AppProvider>
    );
}