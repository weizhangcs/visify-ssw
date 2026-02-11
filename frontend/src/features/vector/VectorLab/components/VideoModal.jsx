import React, { useRef, useEffect } from 'react';
import { Modal } from 'antd';
import VideoPlayer from '../../../annotation/Workbench/components/VideoPlayer';

const VideoModal = ({ visible, onClose, item }) => {
    const playerRef = useRef(null);

    // 当 Modal 打开且 item 变化时，自动跳转到起始时间
    useEffect(() => {
        if (visible && item && playerRef.current) {
            // 稍微延迟以确保 VideoPlayer 加载完成
            // 注意：VideoPlayer 内部也有 onReady 逻辑，这里作为补充或重置
        }
    }, [visible, item]);

    if (!item) return null;

    const { video_url, start, end, text_preview } = item;
    const title = `播放片段 (${start.toFixed(2)}s - ${end.toFixed(2)}s)`;

    return (
        <Modal
            open={visible}
            onCancel={onClose}
            footer={null}
            width={800}
            destroyOnClose
            centered
            title={title}
            styles={{ body: { padding: 0 } }}
        >
            <div style={{ height: '450px', background: '#000', position: 'relative' }}>
                <VideoPlayer
                    ref={playerRef}
                    url={video_url}
                    playing={true}
                    controls={true}
                    onReady={() => {
                        if (playerRef.current && start > 0) {
                            playerRef.current.seekTo(start);
                        }
                    }}
                />
            </div>
            <div className="p-4 bg-gray-50 text-gray-700 border-t">
                <div className="font-medium mb-1">相关文本:</div>
                <div className="text-sm">{text_preview}</div>
            </div>
        </Modal>
    );
};

export default VideoModal;