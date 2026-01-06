import React, { useRef, useState, useEffect, useMemo, useCallback } from 'react';
import { Tooltip } from 'antd';
import _ from 'lodash';
import Waveform from './Waveform';
import '../style.css';
import { canTrackDo } from '../config/tracks';

const TRACK_HEIGHT = 60;
const HEADER_HEIGHT = 30;
const WAVEFORM_HEIGHT = 60;

// [优化] 使用 React.memo 封装片段
const TimelineClip = React.memo(({ action, scale, isSelected, isDragging, trackId, onMouseDown, canResize, trackColor }) => {

    // --- 颜色状态联动逻辑 ---
    const { is_verified, origin } = action.data || {};

    const isModified = origin === 'human';
    const isVerified = is_verified === true;

    // 状态颜色定义
    const COLOR_SELECTED = '#fbbf24'; // 黄色 (选中)
    const COLOR_VERIFIED = '#22c55e'; // 绿色 (已审订)
    const COLOR_MODIFIED = '#3b82f6'; // 蓝色 (已修改/人工)
    const COLOR_DEFAULT  = '#a855f7'; // 紫色 (AI默认/未动)

    let backgroundColor = COLOR_DEFAULT;

    if (isSelected) {
        backgroundColor = COLOR_SELECTED;
    } else if (isVerified) {
        backgroundColor = COLOR_VERIFIED;
    } else if (isModified) {
        backgroundColor = COLOR_MODIFIED;
    }

    let borderColor = 'rgba(255, 255, 255, 0.3)';
    if (isSelected) borderColor = '#ffffff';
    else if (isVerified || isModified) borderColor = 'rgba(255, 255, 255, 0.8)';

    return (
        <Tooltip title={isDragging ? '' : (action.data.label || action.data.text)}>
            <div
                className={`timeline-clip ${isDragging ? 'dragging' : ''}`}
                style={{
                    left: action.start * scale,
                    width: (action.end - action.start) * scale,
                    backgroundColor: backgroundColor,
                    cursor: isDragging ? 'grabbing' : 'grab',
                    border: isSelected ? '2px solid #ffffff' : `1px solid ${borderColor}`,
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
                            waveformUrl,
                            waveformData
                        }) => {
    const containerRef = useRef(null);
    const [scrollLeft, setScrollLeft] = useState(0);
    const [viewportWidth, setViewportWidth] = useState(0);
    const totalWidth = Math.max(duration * scale, 1000);

    const [draggingAction, setDraggingAction] = useState(null);
    const [creatingAction, setCreatingAction] = useState(null);

    // 1. 监听容器尺寸
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

    // =========================================================================
    // [核心修复] 缩放时以游标为中心 (Zoom Anchor on Cursor)
    // =========================================================================
    useEffect(() => {
        if (containerRef.current && viewportWidth > 0) {
            // 计算游标在当前缩放比例下的绝对位置 (px)
            const cursorPixelPos = currentTime * scale;

            // 计算让游标居中所需的 scrollLeft
            // 目标位置 = 游标位置 - 视口一半
            const targetScrollLeft = Math.max(0, cursorPixelPos - viewportWidth / 2);

            // 直接操作 DOM 滚动，既快又准
            containerRef.current.scrollLeft = targetScrollLeft;

            // 同步 React 状态 (虽然 onScroll 也会触发，但这里主动设置更稳)
            setScrollLeft(targetScrollLeft);
        }
        // 注意：依赖项只有 [scale]，这意味着只有缩放发生时才执行居中
        // 如果把 currentTime 放进去，播放时画面会一直跟着跑 (自动滚屏)，那是另一个功能
    }, [scale]);


    const handleScroll = useCallback((e) => {
        setScrollLeft(e.target.scrollLeft);
    }, []);

    const viewRange = useMemo(() => {
        const buffer = 100 / scale;
        return {
            start: Math.max(0, scrollLeft / scale - buffer),
            end: (scrollLeft + viewportWidth) / scale + buffer
        };
    }, [scrollLeft, viewportWidth, scale]);

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

    // 全局鼠标事件监听 (Drag & Create Logic)
    useEffect(() => {
        if (!draggingAction && !creatingAction) return;

        const handleMouseMove = (e) => {
            // A. 处理拖拽
            if (draggingAction) {
                const deltaX = e.clientX - draggingAction.startX;
                const deltaTime = deltaX / scale;
                const { trackId, actionId, originalStart, originalEnd, type } = draggingAction;

                const newTracks = _.cloneDeep(tracks);
                const track = newTracks.find(t => t.id === trackId);
                const action = track.actions.find(a => a.id === actionId);

                if (action) {
                    if (type === 'move') {
                        const duration = originalEnd - originalStart;
                        action.start = Math.max(0, originalStart + deltaTime);
                        action.end = action.start + duration;
                    } else if (type === 'left') {
                        action.start = Math.min(Math.max(0, originalStart + deltaTime), originalEnd - 0.1);
                    } else if (type === 'right') {
                        action.end = Math.max(originalStart + 0.1, originalEnd + deltaTime);
                    }

                    if (!action.data) action.data = {};
                    action.data.origin = 'human';
                    action.data.is_verified = false;

                    onUpdate(newTracks);
                }
            }

            // B. 处理创建
            if (creatingAction) {
                // ...
            }
        };

        const handleMouseUp = (e) => {
            if (draggingAction) {
                setDraggingAction(null);
            }
            if (creatingAction) {
                const { trackId, startX, startAbsoluteX } = creatingAction;
                const endX = e.clientX;
                const diff = Math.abs(endX - startX);

                if (diff > 5) {
                    const rect = containerRef.current.getBoundingClientRect();
                    const currentAbsoluteX = e.clientX - rect.left + scrollLeft;

                    const startTime = Math.min(startAbsoluteX, currentAbsoluteX) / scale;
                    const endTime = Math.max(startAbsoluteX, currentAbsoluteX) / scale;

                    if (endTime - startTime > 0.1) {
                        onCreate(trackId, startTime, endTime);
                    }
                }
                setCreatingAction(null);
            }
        };

        window.addEventListener('mousemove', handleMouseMove);
        window.addEventListener('mouseup', handleMouseUp);

        return () => {
            window.removeEventListener('mousemove', handleMouseMove);
            window.removeEventListener('mouseup', handleMouseUp);
        };
    }, [draggingAction, creatingAction, tracks, scale, onUpdate, onCreate, scrollLeft]);


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
                    <Waveform url={videoUrl} waveformUrl={waveformUrl} waveformData={waveformData} scale={scale} height={WAVEFORM_HEIGHT} />
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
                                    setCreatingAction({ trackId: track.id, startX: e.clientX, startAbsoluteX: absX });
                                    if (onSelect) onSelect(null);
                                }
                            }}
                        >
                            <div className="timeline-track-bg" />
                            <div className="timeline-track-label sticky left-0 z-20 w-24 bg-gray-800/60 backdrop-blur-sm px-2 border-r border-gray-700 h-full flex items-center text-[10px] text-gray-400">
                                {track.name}
                            </div>

                            {track.actions
                                .filter(action => action.end > viewRange.start && action.start < viewRange.end)
                                .map(action => (
                                    <TimelineClip
                                        key={action.id}
                                        action={action}
                                        scale={scale}
                                        trackId={track.id}
                                        trackColor={track.color}
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

                {/* 4. 游标 */}
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