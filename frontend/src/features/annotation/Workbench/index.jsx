import React, { useState, useRef, useMemo, useEffect } from 'react';
import { Typography, Space, Button, message, Spin, Slider, Tooltip as AntTooltip } from 'antd';
import { PlayCircleOutlined, PauseCircleOutlined, SaveOutlined, ArrowLeftOutlined, PlusOutlined, ScissorOutlined, MergeCellsOutlined, FileTextOutlined } from '@ant-design/icons';
import _ from 'lodash';
import VideoPlayer from './components/VideoPlayer';
import SimpleTimeline from './components/SimpleTimeline';
import Inspector from './components/Inspector';
import { transformToTracks, transformFromTracks } from './utils/adapter';
import { generateVTT } from './utils/vtt';
import { TRACK_DEFINITIONS, canTrackDo, getTrackConfig } from './config/tracks';
import './style.css';

const { Title } = Typography;

const AnnotationWorkbench = () => {
    // --- 状态定义 ---
    const [playing, setPlaying] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [tracks, setTracks] = useState([]);
    const [loading, setLoading] = useState(true);
    const [selectedActionId, setSelectedActionId] = useState(null);
    const [scale, setScale] = useState(20);

    const [originalMeta, setOriginalMeta] = useState(null);
    const [saving, setSaving] = useState(false);
    const [showSubtitle, setShowSubtitle] = useState(false); // VTT 开关

    const videoRef = useRef(null);

    // --- 初始化加载 ---
    useEffect(() => {
        const initData = async () => {
            setLoading(true);
            const serverData = window.SERVER_DATA || null;
            console.log("[Workbench] Init Data:", serverData);

            if (serverData) {
                setOriginalMeta(serverData);
                try {
                    const convertedTracks = transformToTracks(serverData);
                    setTracks(convertedTracks);
                    if (serverData.duration) setDuration(serverData.duration);
                } catch (e) {
                    console.error("[Workbench] Adapter Error:", e);
                    message.error("数据转换失败");
                }
            } else {
                message.warning("未检测到后端数据，使用空模板");
                const emptyTracks = Object.values(TRACK_DEFINITIONS).map(def => ({
                    id: def.id,
                    name: def.label,
                    color: def.color,
                    actions: []
                }));
                setTracks(emptyTracks);
            }
            setLoading(false);
        };
        initData();
    }, []);

    // VTT URL 计算
    const subtitleUrl = useMemo(() => {
        if (!showSubtitle) return null;
        return generateVTT(tracks);
    }, [tracks, showSubtitle]);

    // --- 辅助计算 ---
    const selectedContext = useMemo(() => {
        if (!selectedActionId) return { action: null, track: null };
        for (const track of tracks) {
            const action = track.actions.find(a => a.id === selectedActionId);
            if (action) return { action, track };
        }
        return { action: null, track: null };
    }, [selectedActionId, tracks]);

    const currentTrackId = selectedContext.track?.id;
    const canSplit = currentTrackId && canTrackDo(currentTrackId, 'split');
    const canMerge = currentTrackId && canTrackDo(currentTrackId, 'merge');

    // --- 基础交互 ---
    const handleProgress = (state) => setCurrentTime(state.playedSeconds);

    const handleSeek = (time) => {
        setCurrentTime(time);
        if (playing) setPlaying(false);
        if (videoRef.current) videoRef.current.seekTo(time);
    };

    const handleTrackUpdate = (newTracks) => setTracks(newTracks);

    const handleActionUpdate = (updatedAction) => {
        const newTracks = _.cloneDeep(tracks);
        for (const track of newTracks) {
            const idx = track.actions.findIndex(a => a.id === updatedAction.id);
            if (idx !== -1) {
                track.actions[idx] = updatedAction;
                break;
            }
        }
        setTracks(newTracks);
    };

    const handleActionDelete = (actionId) => {
        const newTracks = _.cloneDeep(tracks);
        for (const track of newTracks) {
            track.actions = track.actions.filter(a => a.id !== actionId);
        }
        setTracks(newTracks);
        setSelectedActionId(null);
        message.info('片段已删除');
    };

    // --- [新增] 选中相邻片段 (Keyboard Navigation) ---
    const handleSelectNeighbor = (direction) => {
        if (!selectedActionId) return;

        // 1. 找到当前所在的轨道和片段
        let targetTrack = null;
        let currentAction = null;

        for (const track of tracks) {
            const action = track.actions.find(a => a.id === selectedActionId);
            if (action) {
                targetTrack = track;
                currentAction = action;
                break;
            }
        }

        if (!targetTrack || !currentAction) return;

        // 2. 确保按时间排序 (处理可能的乱序数据)
        const sortedActions = _.sortBy(targetTrack.actions, 'start');
        const currentIndex = sortedActions.findIndex(a => a.id === currentAction.id);

        // 3. 计算目标索引
        let targetIndex = -1;
        if (direction === 'after') { // Next (A)
            targetIndex = currentIndex + 1;
        } else { // Before (B)
            targetIndex = currentIndex - 1;
        }

        // 4. 执行跳转
        if (targetIndex >= 0 && targetIndex < sortedActions.length) {
            const targetAction = sortedActions[targetIndex];

            // 选中目标
            setSelectedActionId(targetAction.id);

            // [UX] 同时将时间轴游标跳到目标片段开始处，方便即时预览内容
            handleSeek(targetAction.start);
        } else {
            message.info(direction === 'after' ? '已经是最后一个片段' : '已经是第一个片段');
        }
    };

    const handleCreateClip = (trackId, start, end) => {
        if (!canTrackDo(trackId, 'create')) return;

        const newTracks = _.cloneDeep(tracks);
        const track = newTracks.find(t => t.id === trackId);

        if (track) {
            const trackConfig = getTrackConfig(trackId);
            const newId = `${trackId}-${Date.now()}`;
            const newData = trackConfig && trackConfig.factory ? trackConfig.factory() : { label: 'New Clip' };

            const newAction = {
                id: newId,
                start: start,
                end: end,
                data: newData
            };

            track.actions.push(newAction);
            setTracks(newTracks);
            setSelectedActionId(newId);

            if (trackId === 'scenes') message.success('场景创建成功');
        }
    };

    const handleSplitClip = () => {
        if (!selectedActionId) return;

        let targetTrack = null, targetAction = null, trackIndex = -1, actionIndex = -1;
        tracks.forEach((t, tIdx) => {
            t.actions.forEach((a, aIdx) => {
                if (a.id === selectedActionId) {
                    targetTrack = t; targetAction = a; trackIndex = tIdx; actionIndex = aIdx;
                }
            });
        });

        if (!targetAction) return;
        if (!canTrackDo(targetTrack.id, 'split')) {
            message.warning('该轨道不支持拆分操作');
            return;
        }
        if (currentTime <= targetAction.start + 0.1 || currentTime >= targetAction.end - 0.1) {
            message.warning('游标未在片段中间，无法拆分');
            return;
        }

        const newTracks = _.cloneDeep(tracks);
        const track = newTracks[trackIndex];
        const action = track.actions[actionIndex];

        const originalEnd = action.end;
        action.end = currentTime;

        const newId = `${targetTrack.id}-${Date.now()}-split`;
        const newAction = {
            ..._.cloneDeep(action),
            id: newId,
            start: currentTime,
            end: originalEnd
        };

        track.actions.push(newAction);
        setTracks(newTracks);
        setSelectedActionId(newId);
        message.success('拆分成功');
    };

    const handleMergeClip = () => {
        if (!selectedActionId) return;

        let trackIndex = -1, track = null, currentAction = null;
        const newTracks = _.cloneDeep(tracks);

        for (let i = 0; i < newTracks.length; i++) {
            const t = newTracks[i];
            const a = t.actions.find(act => act.id === selectedActionId);
            if (a) {
                trackIndex = i; track = t; currentAction = a; break;
            }
        }

        if (!currentAction) return;
        if (!canTrackDo(track.id, 'merge')) {
            message.warning('该轨道不支持合并操作');
            return;
        }

        track.actions.sort((a, b) => a.start - b.start);
        const currentIndex = track.actions.findIndex(a => a.id === currentAction.id);

        if (currentIndex >= track.actions.length - 1) {
            message.warning('后方无片段，无法合并');
            return;
        }

        const nextAction = track.actions[currentIndex + 1];

        if (track.id === 'dialogues' && currentAction.data.speaker !== nextAction.data.speaker) {
            message.error(`角色不一致，禁止合并`);
            return;
        }

        currentAction.end = nextAction.end;
        if (['dialogues', 'captions'].includes(track.id)) {
            currentAction.data.text = `${currentAction.data.text} ${nextAction.data.text}`;
        }

        track.actions.splice(currentIndex + 1, 1);
        setTracks(newTracks);
        message.success('合并成功');
    };

    const togglePlay = () => setPlaying(!playing);

    const handleSave = async () => {
        if (!originalMeta) {
            message.error("原始数据丢失，无法保存");
            return;
        }

        setSaving(true);
        try {
            const payload = transformFromTracks(tracks, originalMeta);
            console.log("[Workbench] Saving Payload:", payload);

            const csrfToken = window.CONTEXT?.csrfToken || document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
            const saveUrl = window.CONTEXT?.saveEndpoint;

            if (!saveUrl) {
                throw new Error("Save endpoint not found in window.CONTEXT");
            }

            const response = await fetch(saveUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken,
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                const text = await response.text();
                throw new Error(`Server Error (${response.status}): ${text.substring(0, 100)}...`);
            }

            const resData = await response.json();

            if (resData.status === 'success') {
                message.success('保存成功');
                setOriginalMeta(payload);
            } else {
                message.error(`保存失败: ${resData.message || '未知错误'}`);
            }

        } catch (e) {
            console.error(e);
            message.error(`保存请求异常: ${e.message}`);
        } finally {
            setSaving(false);
        }
    };

    const handleGoBack = () => {
        const returnUrl = window.CONTEXT?.returnUrl;
        if (returnUrl) {
            window.location.href = returnUrl;
        } else {
            window.history.back();
        }
    };

    // --- 键盘快捷键监听 ---
    useEffect(() => {
        const handleKeyDown = (e) => {
            // 输入状态下禁用快捷键
            if (['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;

            switch(e.code) {
                case 'Space':
                    e.preventDefault();
                    setPlaying(prev => !prev);
                    break;
                case 'Backspace':
                case 'Delete':
                    if (selectedActionId) {
                        e.preventDefault();
                        handleActionDelete(selectedActionId);
                    }
                    break;
                case 'KeyS':
                    e.preventDefault();
                    handleSplitClip();
                    break;
                case 'KeyM':
                    e.preventDefault();
                    handleMergeClip();
                    break;
                // [新增] A键: 选中下一个 (After)
                case 'KeyA':
                    e.preventDefault();
                    handleSelectNeighbor('after');
                    break;
                // [新增] B键: 选中上一个 (Before)
                case 'KeyB':
                    e.preventDefault();
                    handleSelectNeighbor('before');
                    break;
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [selectedActionId, currentTime, tracks]); // 依赖项包含 selectedActionId 确保能找到当前位置

    return (
        <div className="wb-container">
            <header className="wb-header">
                <div className="wb-header-left">
                    <Button
                        icon={<ArrowLeftOutlined />}
                        type="text"
                        onClick={handleGoBack}
                        title="返回项目列表"
                    />
                    <div>
                        <Title level={4} style={{ margin: 0 }}>Annotation Workbench</Title>
                        <span className="wb-version-tag">v1.3.0</span>
                    </div>
                </div>

                <div className="wb-player-controls">
                    <div className="wb-control-group">
                        <Button
                            type="text"
                            shape="circle"
                            icon={playing ? <PauseCircleOutlined style={{ fontSize: 24, color: '#9333ea' }}/> : <PlayCircleOutlined style={{ fontSize: 24 }}/>}
                            onClick={togglePlay}
                        />

                        <AntTooltip title={showSubtitle ? "隐藏原片字幕" : "显示原片字幕 (CC)"}>
                            <Button
                                type={showSubtitle ? "primary" : "text"}
                                shape="circle"
                                size="small"
                                icon={<FileTextOutlined style={{ fontSize: 16 }} />}
                                onClick={() => setShowSubtitle(!showSubtitle)}
                                style={showSubtitle ? { backgroundColor: '#9333ea' } : { color: '#6b7280' }}
                            />
                        </AntTooltip>

                        <span className="wb-time-display">
                            {currentTime.toFixed(2)}s
                        </span>
                    </div>
                </div>

                <Space size="middle">
                    <span className="wb-save-hint">
                        暂存后请记得点击此处提交 👉
                    </span>

                    <Button
                        type="primary"
                        icon={<SaveOutlined />}
                        onClick={handleSave}
                        loading={saving}
                        title="将当前所有暂存的修改写入后端存储"
                    >
                        提交本次标注成果
                    </Button>
                </Space>
            </header>

            <div className="wb-body">
                <div className="wb-stage-pane">
                    <div className="wb-video-area">
                        <VideoPlayer
                            ref={videoRef}
                            url={originalMeta?.source_path}
                            playing={playing}
                            onProgress={handleProgress}
                            onDuration={setDuration}
                            onPlay={() => setPlaying(true)}
                            onPause={() => setPlaying(false)}
                            subtitleUrl={subtitleUrl}
                        />
                    </div>
                    <div className="wb-inspector-area">
                        <Inspector
                            action={selectedContext?.action}
                            track={selectedContext?.track}
                            onUpdate={handleActionUpdate}
                            onDelete={handleActionDelete}
                            characterList={originalMeta?.character_list || []}
                        />
                    </div>
                </div>

                <div className="wb-timeline-pane">
                    <div className="wb-timeline-toolbar">
                        <div className="wb-toolbar-actions">
                            <AntTooltip title={!canSplit ? "此轨道不支持拆分" : "快捷键: S"}>
                                <Button size="small" icon={<ScissorOutlined />} onClick={handleSplitClip} disabled={!selectedActionId || !canSplit}>拆分</Button>
                            </AntTooltip>
                            <AntTooltip title={!canMerge ? "此轨道不支持合并" : "快捷键: M"}>
                                <Button size="small" icon={<MergeCellsOutlined />} onClick={handleMergeClip} disabled={!selectedActionId || !canMerge}>合并</Button>
                            </AntTooltip>
                        </div>

                        <span className="wb-toolbar-hint">
                            快捷键: [A] 下一个片段 | [B] 上一个片段 | [S] 拆分 | [M] 合并
                        </span>

                        <div className="wb-toolbar-slider">
                            <Slider min={1} max={100} value={scale} onChange={setScale} style={{ flex: 1 }} tooltip={{ formatter: (v) => `${v} px/s` }} />
                        </div>
                    </div>

                    <div className="wb-timeline-body">
                        <SimpleTimeline
                            tracks={tracks}
                            currentTime={currentTime}
                            duration={duration || 60}
                            onSeek={handleSeek}
                            onUpdate={handleTrackUpdate}
                            selectedActionId={selectedActionId}
                            onSelect={(action) => setSelectedActionId(action ? action.id : null)}
                            scale={scale}
                            onScaleChange={setScale}
                            videoUrl={originalMeta?.source_path}
                            onCreate={handleCreateClip}
                            waveformUrl={originalMeta?.waveform_url}
                            waveformData={originalMeta?.waveform_data}
                        />
                    </div>
                </div>
            </div>

            <div style={{ display: 'none' }}></div>
        </div>
    );
};

export default AnnotationWorkbench;