import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
    plugins: [react()],
    build: {
        // 1. 修改输出目录：指向项目根目录下的 static_build
        outDir: '../static_build',

        // 2. 每次构建清空该目录
        emptyOutDir: true,

        rollupOptions: {
            input: {
                // 建议：Key 命名带上模块前缀，清晰明了
                'media-batch-upload': path.resolve(__dirname, 'src/entries/media_batch_upload.jsx'),
                'annotation-import-wizard': path.resolve(__dirname, 'src/entries/annotation_import_wizard.jsx'),
                'annotation-dashboard': path.resolve(__dirname, 'src/entries/annotation_dashboard.jsx'),
                'creative-director': path.resolve(__dirname, 'src/entries/creative_director.jsx'),
                'inference-facts': path.resolve(__dirname, 'src/entries/inference_facts.jsx'),
                'inference-rag': path.resolve(__dirname, 'src/entries/inference_rag.jsx'),
                'annotation-workbench': path.resolve(__dirname, 'src/entries/annotation_workbench.jsx'),
                // [新增] 场景编排入口
                'scene-orchestration': path.resolve(__dirname, 'src/entries/scene_orchestration.jsx'),
            },
            output: {
                entryFileNames: 'js/bundles/[name].js',
                chunkFileNames: 'js/chunks/[name]-[hash].js',
                assetFileNames: (assetInfo) => {
                    if (assetInfo.name && assetInfo.name.endsWith('.css')) {
                        return 'css/bundles/[name][extname]';
                    }
                    return 'assets/[name]-[hash][extname]';
                },
            },
        },
        sourcemap: true,
        minify: false,
    },
    resolve: {
        alias: {
            '@': path.resolve(__dirname, 'src'),
        },
    },
});