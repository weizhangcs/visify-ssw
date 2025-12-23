import React, { useRef, useState, useEffect, useMemo, useCallback } from 'react';
import { Tooltip } from 'antd';
import _ from 'lodash';
import Waveform from './Waveform';
import '../style.css';
import { canTrackDo } from '../config/tracks';

const TRACK_HEIGHT = 60;
const HEADER_HEIGHT = 30;
const WAVEFORM_HEIGHT = 60;

// [优化] 使用 React.memo 封装片段，防止游标移动时频繁重绘非选中片段
const TimelineClip = React.memo(({ action, scale, isSelected, isDragging, trackId, onMouseDown, canResize }) => {
    return (
        <Tooltip title={isDragging ? '' : (action.data.label || action.data.text)}>
            <div
                className={`timeline-clip ${isDragging ? 'dragging' : ''}`}
                style={{
                    left: action.start * scale,
                    width: (action.end - action.start) * scale,
                    backgroundColor: isSelected ? '#fbbf24' : (action.color || '#6366f1'),
                    cursor: isDragging ? 'grabbing' : 'grab',
                    border: isSelected ? '2px solid #ffffff' : '1px solid rgba(255, 255, 255, 0.2)',
                    boxShadow: isSelected ? '0 0 12px rgba(251, 191, 36, 0.8)' : 'none',
                    zIndex: isSelected ? 10 : 1
                }}
                onMouseDown={(e) => onMouseDown(e, trackId, action, 'move')}
            >
                {canResize && (
                    <div
                        className="timeline-clip-handle timeline-clip-handle-left"
                        onMouseDown={(e) => onMouseDown(e, trackId, action, 'left')}
                    />
                )}
                <div className="timeline-clip-content">
                    {action.data.label || action.data.text}
                </div>
                {canResize && (
                    <div
                        className="timeline-clip-handle timeline-clip-handle-right"
                        onMouseDown={(e) => onMouseDown(e, trackId, action, 'right')}
                    />
                )}
            </div>
        </Tooltip>
    );
});

const getRulerStep = (scale) => {
    const minSpacing = 60;
    const steps = [0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 300, 600];
    for (const step of steps) {
        if (step * scale >= minSpacing) return step;
    }
    return 600;
};

const SimpleTimeline = ({
                            currentTime = 0,
                            duration = 600,
                            tracks = [],
                            scale = 20,
                            onSeek,
                            onUpdate,
                            onScaleChange,
                            selectedActionId,
                            onSelect,
                            onCreate,
                            videoUrl,
                            waveformUrl
                        }) => {
    const containerRef = useRef(null);
    const [scrollLeft, setScrollLeft] = useState(0);
    const [viewportWidth, setViewportWidth] = useState(0);
    const totalWidth = Math.max(duration * scale, 1000);

    const [draggingAction, setDraggingAction] = useState(null);
    const [creatingAction, setCreatingAction] = useState(null);

    // [优化] 监听容器尺寸和滚动，用于视口裁剪
    useEffect(() => {
        if (!containerRef.current) return;
        const resizeObserver = new ResizeObserver(entries => {
            for (let entry of entries) {
                setViewportWidth(entry.contentRect.width);
            }
        });
        resizeObserver.observe(containerRef.current);
        return () => resizeObserver.disconnect();
    }, []);

    const handleScroll = useCallback((e) => {
        setScrollLeft(e.target.scrollLeft);
    }, []);

    // [优化] 计算当前可见的时间范围 (视口裁剪核心)
    const viewRange = useMemo(() => {
        const buffer = 100 / scale; // 增加 100px 的缓冲区
        return {
            start: Math.max(0, scrollLeft / scale - buffer),
            end: (scrollLeft + viewportWidth) / scale + buffer
        };
    }, [scrollLeft, viewportWidth, scale]);

    // --- 交互逻辑保持不变，但使用 useCallback 优化 ---
    const handleClipMouseDown = useCallback((e, trackId, action, type) => {
        e.stopPropagation();
        e.preventDefault();
        if (type !== 'move' && !canTrackDo(trackId, 'resize')) return;
        if (type === 'move' && !canTrackDo(trackId, 'move')) return;

        setDraggingAction({
            trackId,
            actionId: action.id,
            startX: e.clientX,
            originalStart: action.start,
            originalEnd: action.end,
            type
        });
        if (type === 'move' && onSelect) onSelect(action);
    }, [onSelect]);

    //

    return (
        <div
            ref={containerRef}
            className="timeline-container custom-scrollbar"
            onScroll={handleScroll}
        >
            <div className="timeline-inner-wrapper" style={{ width: totalWidth }}>

                {/* 1. 标尺 */}
                <div
                    className="timeline-ruler"
                    style={{ height: HEADER_HEIGHT }}
                    onMouseDown={(e) => {
                        const rect = containerRef.current.getBoundingClientRect();
                        onSeek((e.clientX - rect.left + scrollLeft) / scale);
                    }}
                >
                    {/* 标尺刻度渲染优化：只渲染可见部分的刻度可进一步优化，此处暂略 */}
                    {Array.from({ length: Math.ceil(duration / getRulerStep(scale)) + 1 }).map((_, i) => {
                        const time = i * getRulerStep(scale);
                        const left = time * scale;
                        if (left < scrollLeft - 100 || left > scrollLeft + viewportWidth + 100) return null;
                        return (
                            <div key={i} className="timeline-tick" style={{ left }}>
                                {time}s
                            </div>
                        );
                    })}
                </div>

                {/* 2. 波形图 */}
                <div className="border-b border-gray-700 bg-gray-900/50 relative" style={{ height: WAVEFORM_HEIGHT }}>
                    <div className="sticky left-0 z-20 w-24 h-full flex items-center px-2 bg-gray-800/80 border-r border-gray-700 text-xs text-gray-400 font-bold backdrop-blur-sm">
                        AUDIO
                    </div>
                    <Waveform url={videoUrl} waveformUrl={waveformUrl} scale={scale} height={WAVEFORM_HEIGHT} />
                </div>

                {/* 3. 轨道区域 */}
                <div className="timeline-track-area">
                    {tracks.map(track => (
                        <div
                            key={track.id}
                            className="timeline-track"
                            style={{ height: TRACK_HEIGHT }}
                            onMouseDown={(e) => {
                                if (e.target === e.currentTarget || e.target.className === 'timeline-track-bg') {
                                    const rect = containerRef.current.getBoundingClientRect();
                                    const absX = e.clientX - rect.left + scrollLeft;
                                    setCreatingAction({ trackId: track.id, startX: e.clientX, startAbsoluteX: absX, currentX: e.clientX });
                                    onSelect(null);
                                }
                            }}
                        >
                            <div className="timeline-track-bg" />
                            <div className="timeline-track-label sticky left-0 z-20 w-24 bg-gray-800/60 backdrop-blur-sm px-2 border-r border-gray-700 h-full flex items-center text-[10px] text-gray-400">
                                {track.name}
                            </div>

                            {/* [优化核心] 过滤掉不在视口内的片段 */}
                            {track.actions
                                .filter(action => action.end > viewRange.start && action.start < viewRange.end)
                                .map(action => (
                                    <TimelineClip
                                        key={action.id}
                                        action={action}
                                        scale={scale}
                                        trackId={track.id}
                                        isSelected={selectedActionId === action.id}
                                        isDragging={draggingAction?.actionId === action.id}
                                        onMouseDown={handleClipMouseDown}
                                        canResize={canTrackDo(track.id, 'resize')}
                                    />
                                ))
                            }
                        </div>
                    ))}
                </div>

                {/* 4. 游标 (使用 transform 优化性能) */}
                <div
                    className="timeline-cursor"
                    style={{
                        transform: `translateX(${currentTime * scale}px)`,
                        left: 0
                    }}
                >
                    <div className="timeline-cursor-head" />
                    <div className="w-px h-full bg-red-500" />
                </div>
            </div>
        </div>
    );
};

export default SimpleTimeline;