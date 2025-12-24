import React, { useEffect, useRef, useState } from 'react';
import { Modal, Button, Space, Typography } from 'antd';
import { PlayCircleOutlined, ReloadOutlined, LoadingOutlined } from '@ant-design/icons';
import Hls from 'hls.js';

const { Text } = Typography;

// 你的本地 Nginx 源地址
const LOCAL_SOURCE = "http://localhost:9999/media/transcoding_outputs/c2c81885-7eb4-46f2-9c92-d2018be28b74/265/hls/index.m3u8";

export default function VideoModal({ visible, onClose, scene }) {
    const videoRef = useRef(null);
    const hlsRef = useRef(null);
    const [loading, setLoading] = useState(true);

    // === 核心生命周期：加载视频 ===
    useEffect(() => {
        let hls = null;
        const video = videoRef.current;

        // 只有 Modal 显示且 DOM 就绪时执行
        if (visible && video && scene) {
            setLoading(true);

            if (Hls.isSupported()) {
                hls = new Hls({
                    enableWorker: true,    // 开启多线程加速
                    lowLatencyMode: true,  // 低延迟模式
                });
                hlsRef.current = hls;

                hls.loadSource(LOCAL_SOURCE);
                hls.attachMedia(video);

                // 1. 索引解析完成 -> 尝试播放
                hls.on(Hls.Events.MANIFEST_PARSED, () => {
                    setLoading(false);
                    // 跳转到片段起点
                    video.currentTime = scene.startTime;
                    video.play().catch((e) => {
                        console.warn("自动播放被浏览器拦截，需手动点击:", e);
                    });
                });

                // 2. 错误处理与自动恢复
                hls.on(Hls.Events.ERROR, (event, data) => {
                    if (data.fatal) {
                        switch (data.type) {
                            case Hls.ErrorTypes.MEDIA_ERROR:
                                console.log('[HLS] 尝试恢复媒体错误...');
                                hls.recoverMediaError();
                                break;
                            default:
                                console.error('[HLS] 无法恢复的错误:', data);
                                hls.destroy();
                                break;
                        }
                    }
                });

            } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
                // 兼容 Safari (Safari 原生支持 HLS)
                video.src = LOCAL_SOURCE;
                video.addEventListener('loadedmetadata', () => {
                    setLoading(false);
                    video.currentTime = scene.startTime;
                    video.play();
                });
            }
        }

        // === 清理：关闭 Modal 时立刻销毁 ===
        return () => {
            if (hls) {
                hls.destroy();
            }
            if (video) {
                video.pause();
                video.removeAttribute('src'); // 彻底释放
                video.load();
            }
        };
    }, [visible, scene]);

    // === 逻辑：片段播放控制 ===
    // 使用原生 onTimeUpdate 监听，性能最好
    const handleTimeUpdate = () => {
        const video = videoRef.current;
        if (video && scene && !video.paused) {
            // 如果超过了结束时间，暂停
            if (video.currentTime >= scene.endTime) {
                video.pause();
                // 可选：回到起点等待重播
                // video.currentTime = scene.startTime;
            }
        }
    };

    // 重播功能
    const handleReplay = () => {
        const video = videoRef.current;
        if (video && scene) {
            video.currentTime = scene.startTime;
            video.play();
        }
    };

    if (!scene) return null;

    return (
        <Modal
            title={
                <Space>
                    <PlayCircleOutlined />
                    <span>{scene.label}</span>
                    <Text type="secondary" style={{fontSize: 12}}>
                        ({formatTime(scene.startTime)} - {formatTime(scene.endTime)})
                    </Text>
                    {loading && <LoadingOutlined style={{color: '#1677ff'}} />}
                </Space>
            }
            open={visible}
            onCancel={onClose}
            footer={null}
            width={800} // 宽屏
            destroyOnClose={true} // 关闭销毁 DOM
            centered
            maskClosable={false} // 防止误触关闭
            forceRender={true}
        >
            <div style={{ background: '#000', width: '100%', aspectRatio: '16/9', position: 'relative' }}>
                <video
                    ref={videoRef}
                    controls
                    autoPlay // 辅助属性
                    onTimeUpdate={handleTimeUpdate} // 核心监听
                    style={{ width: '100%', height: '100%', display: 'block' }}
                    crossOrigin="anonymous"
                />

                {/* 如果需要自定义 Loading 遮罩，可以在这里盖一个 div */}
            </div>

            <div style={{ marginTop: 15, textAlign: 'center' }}>
                <Button
                    icon={<ReloadOutlined />}
                    onClick={handleReplay}
                    size="large"
                >
                    重播片段 (Replay Segment)
                </Button>
            </div>
        </Modal>
    );
}

// 辅助时间格式化
function formatTime(seconds) {
    if(seconds === undefined) return '00:00';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m.toString().padStart(2,'0')}:${s.toString().padStart(2,'0')}`;
}