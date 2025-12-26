// frontend/src/features/orchestration/components/VideoModal.jsx

import React, { useEffect, useRef, useState } from 'react';
import { Modal, Button, Space, Typography, Alert } from 'antd';
import { PlayCircleOutlined, ReloadOutlined, LoadingOutlined, WarningOutlined } from '@ant-design/icons';
import Hls from 'hls.js';

const { Text } = Typography;

export default function VideoModal({ visible, onClose, scene }) {
    const videoRef = useRef(null);
    const hlsRef = useRef(null);
    const [loading, setLoading] = useState(true);
    const [errorMsg, setErrorMsg] = useState(null);

    // === 核心生命周期：加载视频 ===
    useEffect(() => {
        let hls = null;
        const video = videoRef.current;

        setErrorMsg(null);

        // 只有 Modal 显示且 DOM 就绪时执行
        if (visible && video && scene) {
            setLoading(true);

            // [核心修正] 使用后端传递的 streamUrl
            const sourceUrl = scene.streamUrl;

            if (!sourceUrl) {
                setLoading(false);
                setErrorMsg("未找到流媒体地址 (streamUrl)，请检查转码任务是否完成。");
                return;
            }

            if (Hls.isSupported()) {
                hls = new Hls({
                    enableWorker: true,
                    lowLatencyMode: true,
                });
                hlsRef.current = hls;

                hls.loadSource(sourceUrl);
                hls.attachMedia(video);

                hls.on(Hls.Events.MANIFEST_PARSED, () => {
                    setLoading(false);
                    video.currentTime = scene.startTime;
                    video.play().catch((e) => {
                        console.warn("Autoplay blocked:", e);
                    });
                });

                hls.on(Hls.Events.ERROR, (event, data) => {
                    if (data.fatal) {
                        switch (data.type) {
                            case Hls.ErrorTypes.MEDIA_ERROR:
                                hls.recoverMediaError();
                                break;
                            default:
                                console.error('[HLS] Fatal Error:', data);
                                setErrorMsg(`播放错误: ${data.details}`);
                                hls.destroy();
                                break;
                        }
                    }
                });

            } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
                // Safari 原生支持
                video.src = sourceUrl;
                video.addEventListener('loadedmetadata', () => {
                    setLoading(false);
                    video.currentTime = scene.startTime;
                    video.play();
                });
            } else {
                setErrorMsg("您的浏览器不支持 HLS 播放。");
                setLoading(false);
            }
        }

        // === 清理 ===
        return () => {
            if (hls) {
                hls.destroy();
            }
            if (video) {
                video.pause();
                video.removeAttribute('src');
                video.load();
            }
        };
    }, [visible, scene]);

    // === 逻辑：片段播放控制 (Bound Check) ===
    const handleTimeUpdate = () => {
        const video = videoRef.current;
        if (video && scene && !video.paused) {
            if (video.currentTime >= scene.endTime) {
                video.pause();
            }
        }
    };

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
            width={800}
            destroyOnClose={true}
            centered
            maskClosable={false}
            forceRender={true}
        >
            <div style={{ background: '#000', width: '100%', aspectRatio: '16/9', position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>

                {errorMsg ? (
                    <Alert
                        message="播放失败"
                        description={errorMsg}
                        type="error"
                        showIcon
                        icon={<WarningOutlined />}
                        style={{ maxWidth: '80%' }}
                    />
                ) : (
                    <video
                        ref={videoRef}
                        controls
                        autoPlay
                        onTimeUpdate={handleTimeUpdate}
                        style={{ width: '100%', height: '100%', display: 'block' }}
                        crossOrigin="anonymous"
                    />
                )}
            </div>

            <div style={{ marginTop: 15, textAlign: 'center' }}>
                <Button
                    icon={<ReloadOutlined />}
                    onClick={handleReplay}
                    size="large"
                    disabled={!!errorMsg}
                >
                    重播片段 (Replay Segment)
                </Button>
            </div>
        </Modal>
    );
}

function formatTime(seconds) {
    if(seconds === undefined) return '00:00';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m.toString().padStart(2,'0')}:${s.toString().padStart(2,'0')}`;
}