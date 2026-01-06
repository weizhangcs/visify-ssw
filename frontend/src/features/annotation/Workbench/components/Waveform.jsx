import React, { useEffect, useRef, useState } from 'react';
import WaveSurfer from 'wavesurfer.js';

const Waveform = ({ url, waveformUrl, waveformData, scale, height = 60 }) => {
    const containerRef = useRef(null);
    const wavesurfer = useRef(null);
    const [isReady, setIsReady] = useState(false);

    useEffect(() => {
        if (!containerRef.current || !url) return;

        // 防止重复初始化
        if (wavesurfer.current) {
            wavesurfer.current.destroy();
        }

        const ws = WaveSurfer.create({
            container: containerRef.current,
            waveColor: '#6b7280',
            progressColor: '#6b7280',
            cursorWidth: 0,
            height: height,
            normalize: true,
            minPxPerSec: scale,
            fillParent: true,
            interact: false,
            scrollbar: false,
            hideScrollbar: true,
            // [关键 1] 显式指定 backend 为 MediaElement，兼容性更好
            backend: 'MediaElement',
        });

        // 绑定事件
        ws.on('ready', () => setIsReady(true));
        ws.on('error', (e) => console.warn('[Waveform] Warn:', e));

        // [关键 2] 核心加载逻辑分支
        const initWaveform = async () => {
            // 策略 0: 直接传入了波形数据 (Array)
            if (waveformData && Array.isArray(waveformData) && waveformData.length > 0) {
                ws.load(url, [waveformData]);
                console.log('[Waveform] Loaded using direct waveformData');
                return;
            }

            // 策略 A: 如果有预生成的波形数据 (JSON)，优先使用
            if (waveformUrl) {
                try {
                    const response = await fetch(waveformUrl);
                    if (!response.ok) throw new Error("Failed to fetch waveform json");

                    const json = await response.json();

                    // Python 脚本生成的 JSON 结构通常是: { data: [...] } (单声道)
                    // WaveSurfer load 方法的第二个参数是 peaks
                    // peaks 格式: Array<Float> (单声道) 或 Array<Array<Float>> (立体声)
                    const peaks = json.data;

                    if (peaks && peaks.length > 0) {
                        // [核心技巧] 传入 peaks 数据
                        // 即使 url 是 m3u8，只要提供了 peaks，WaveSurfer 就会立即渲染图形，
                        // 而不会阻塞等待音频解码。即便底层 audio 加载失败，波形依然可见。
                        ws.load(url, [peaks]);
                        console.log('[Waveform] Loaded using JSON peaks');
                        return;
                    }
                } catch (e) {
                    console.error("[Waveform] JSON Load Failed, falling back to decode:", e);
                }
            }

            // 策略 B: 没有 JSON 或加载失败，尝试直接解码 (如果 url 是 HLS，这里会失败)
            try {
                ws.load(url);
            } catch (e) {
                console.error("[Waveform] Direct Load Failed:", e);
            }
        };

        initWaveform();
        wavesurfer.current = ws;

        return () => {
            if (wavesurfer.current) {
                try {
                    wavesurfer.current.destroy();
                } catch (e) {}
                wavesurfer.current = null;
            }
        };
    }, [url, waveformUrl, waveformData]); // [修正] 依赖列表中加入 waveformData

    // 响应缩放
    useEffect(() => {
        if (wavesurfer.current && isReady && scale) {
            try {
                wavesurfer.current.zoom(scale);
            } catch (e) {
                // Ignore
            }
        }
    }, [scale, isReady]);

    return (
        <div
            ref={containerRef}
            className="w-full relative pointer-events-none"
            style={{ height }}
        />
    );
};

export default Waveform;