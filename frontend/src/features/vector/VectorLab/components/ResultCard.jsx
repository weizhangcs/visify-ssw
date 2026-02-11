import React, { useRef } from 'react';
import { Card, Tag, Typography, Image } from 'antd';
import { PlayCircleOutlined, PictureOutlined, MessageOutlined, VideoCameraOutlined } from '@ant-design/icons';
import VideoPlayer from '../../../annotation/Workbench/components/VideoPlayer';

const { Text, Paragraph } = Typography;

const TYPE_CONFIG = {
    dialogue: { color: 'blue', icon: <MessageOutlined />, label: '对话' },
    scene: { color: 'orange', icon: <VideoCameraOutlined />, label: '场景' },
    slice: { color: 'purple', icon: <PlayCircleOutlined />, label: '切片' },
    frame: { color: 'cyan', icon: <PictureOutlined />, label: '画面' },
};

const ResultCard = ({ item, rank, onPlay }) => { // [新增] 接收 onPlay
    const { type, score, start, end, text_preview, video_url, image_url, media_title, seq } = item;
    const config = TYPE_CONFIG[type] || { color: 'default', label: type };
    const playerRef = useRef(null);

    // 格式化时间
    const timeStr = end > 0
        ? `${start.toFixed(2)}s - ${end.toFixed(2)}s`
        : `${start.toFixed(2)}s`;

    return (
        <Card
            size="small"
            className="shadow-sm hover:shadow-md transition-shadow border-l-4"
            style={{ borderLeftColor: type === 'frame' ? '#13c2c2' : (type === 'dialogue' ? '#1890ff' : '#722ed1') }}
            bodyStyle={{ padding: '12px 16px' }}
        >
            <div className="flex gap-4">
                {/* 媒体展示区 (左侧) */}
                <div className="flex-shrink-0 w-48 bg-black rounded overflow-hidden flex items-center justify-center relative group">
                    {type === 'frame' && image_url ? (
                        <Image
                            src={image_url}
                            alt="Frame"
                            height={108}
                            width="100%"
                            className="object-contain"
                            preview={{ src: image_url }}
                        />
                    ) : (type === 'slice' || type === 'scene') && video_url ? (
                        <div
                            className="w-full h-[108px] relative cursor-pointer group"
                            onClick={onPlay} // [新增] 点击触发弹窗
                        >
                            {/* 复用 VideoPlayer，但禁用控制条，仅作为预览封面 */}
                            <VideoPlayer
                                ref={playerRef}
                                url={video_url}
                                playing={false}
                                controls={false} // [新增] 禁用原生控制条
                                onReady={() => {
                                    if (playerRef.current && start > 0) {
                                        playerRef.current.seekTo(start);
                                    }
                                }}
                            />

                            {/* [新增] 播放按钮遮罩 */}
                            <div className="absolute inset-0 flex items-center justify-center bg-black/20 group-hover:bg-black/40 transition-colors">
                                <PlayCircleOutlined className="text-white text-3xl opacity-80 group-hover:opacity-100 group-hover:scale-110 transition-all" />
                            </div>

                            {/* 遮罩提示时间 */}
                            <div className="absolute bottom-1 right-1 bg-black/60 text-white text-[10px] px-1 rounded pointer-events-none">
                                {timeStr}
                            </div>
                        </div>
                    ) : (
                        <div className="w-full h-[108px] flex flex-col items-center justify-center text-gray-500 bg-gray-100">
                            {config.icon}
                            <span className="text-xs mt-1">纯文本/无媒体</span>
                        </div>
                    )}
                </div>

                {/* 内容信息区 (右侧) */}
                <div className="flex-1 min-w-0">
                    <div className="flex justify-between items-start mb-2">
                        <div className="flex items-center gap-2">
                            <Tag color={config.color} icon={config.icon}>{config.label}</Tag>
                            <Text strong className="text-sm">#{rank}</Text>
                            <Text type="secondary" className="text-xs">Score: {score.toFixed(4)}</Text>
                        </div>
                        <Tag bordered={false} className="text-xs text-gray-400">
                            {media_title} (Seq: {seq})
                        </Tag>
                    </div>

                    <Paragraph
                        className="text-gray-700 text-sm mb-2"
                        ellipsis={{ rows: 3, expandable: true, symbol: '展开' }}
                    >
                        {text_preview}
                    </Paragraph>

                    <div className="flex gap-2 mt-auto">
                        {item.tags && item.tags.length > 0 && (
                            <div className="flex flex-wrap gap-1">
                                {item.tags.slice(0, 5).map((tag, i) => (
                                    <Tag key={i} bordered={false} className="text-[10px] bg-gray-100 text-gray-500 mr-0">
                                        #{tag}
                                    </Tag>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </Card>
    );
};

export default ResultCard;