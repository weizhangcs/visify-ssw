import { useState, useEffect, useMemo } from 'react';
import { message } from 'antd';
import _ from 'lodash';
import { transformToTracks, transformFromTracks } from '../utils/adapter';

export const useWorkbenchLogic = () => {
    const [tracks, setTracks] = useState([]);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [selectedActionId, setSelectedActionId] = useState(null);
    const [originalMeta, setOriginalMeta] = useState(null);
    //const [videoUrl, setVideoUrl] = useState(TEST_VIDEO_URL);

    // 1. 初始化数据
    useEffect(() => {
        const initData = async () => {
            setLoading(true);
            const serverData = window.SERVER_DATA || null;

            console.log("[Workbench] Init Data:", serverData);
            setOriginalMeta(serverData);
            try {
                const convertedTracks = transformToTracks(serverData);
                setTracks(convertedTracks);
                if (serverData.source_path && !serverData.source_path.includes('v2_demo.mp4')) {
                    setVideoUrl(serverData.source_path);
                }
            } catch (e) {
                console.error("Adapter Error:", e);
                message.error("数据转换失败");
            }
            setLoading(false);
        };
        initData();
    }, []);

    // 2. 选中上下文计算
    const selectedContext = useMemo(() => {
        if (!selectedActionId) return { action: null, track: null };
        for (const track of tracks) {
            const action = track.actions.find(a => a.id === selectedActionId);
            if (action) return { action, track };
        }
        return { action: null, track: null };
    }, [selectedActionId, tracks]);

    const isComplexType = ['scenes', 'highlights'].includes(selectedContext.track?.id);

    // 3. CRUD 操作封装
    const updateTracks = (newTracks) => setTracks(newTracks);

    const updateAction = (updatedAction) => {
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

    const deleteAction = (actionId) => {
        const newTracks = _.cloneDeep(tracks);
        for (const track of newTracks) {
            track.actions = track.actions.filter(a => a.id !== actionId);
        }
        setTracks(newTracks);
        setSelectedActionId(null);
        message.info('已删除');
    };

    const createClip = (trackId, start, end) => {
        const newTracks = _.cloneDeep(tracks);
        const track = newTracks.find(t => t.id === trackId);
        if (track) {
            const newId = `${trackId}-${Date.now()}`;
            let newData = { label: 'New Clip' };

            // 默认值工厂
            if (trackId === 'scenes') newData = { label: '新场景' };
            else if (trackId === 'highlights') newData = { label: 'Action', type: 'Action' };
            else if (trackId === 'dialogues') newData = { text: '新字幕', speaker: 'Unknown' };
            else if (trackId === 'captions') newData = { text: '新提词', category: 'General' };

            track.actions.push({ id: newId, start, end, data: newData });
            setTracks(newTracks);
            setSelectedActionId(newId);
            message.success('创建成功');
        }
    };

    const splitClip = (currentTime) => {
        if (!selectedActionId || isComplexType) return;

        let targetTrack, targetAction, tIdx, aIdx;
        tracks.forEach((t, i) => t.actions.forEach((a, j) => {
            if (a.id === selectedActionId) { targetTrack=t; targetAction=a; tIdx=i; aIdx=j; }
        }));

        if (!targetAction) return;
        if (currentTime <= targetAction.start + 0.1 || currentTime >= targetAction.end - 0.1) {
            message.warning('无法在边缘拆分');
            return;
        }

        const newTracks = _.cloneDeep(tracks);
        const track = newTracks[tIdx];
        const action = track.actions[aIdx];
        const originalEnd = action.end;

        action.end = currentTime;
        const newAction = { ..._.cloneDeep(action), id: `${targetTrack.id}-${Date.now()}`, start: currentTime, end: originalEnd };
        track.actions.push(newAction);

        setTracks(newTracks);
        setSelectedActionId(newAction.id);
        message.success('拆分成功');
    };

    const mergeClip = () => {
        if (!selectedActionId || isComplexType) return;
        // ... (原 merge 逻辑搬运)
        let tIdx, track, currentAction;
        const newTracks = _.cloneDeep(tracks);
        for(let i=0; i<newTracks.length; i++) {
            const a = newTracks[i].actions.find(act => act.id === selectedActionId);
            if(a) { tIdx=i; track=newTracks[i]; currentAction=a; break; }
        }
        if (!track) return;

        track.actions.sort((a, b) => a.start - b.start);
        const currentIndex = track.actions.findIndex(a => a.id === currentAction.id);
        const nextAction = track.actions[currentIndex + 1];

        if (!nextAction) { message.warning('后方无片段'); return; }

        // 简单校验
        if (track.id === 'dialogues' && currentAction.data.speaker !== nextAction.data.speaker) {
            message.error('角色不一致'); return;
        }

        currentAction.end = nextAction.end;
        currentAction.data.text = `${currentAction.data.text} ${nextAction.data.text}`;
        track.actions.splice(currentIndex + 1, 1);
        setTracks(newTracks);
        message.success('合并成功');
    };

    const saveData = async () => {
        if (!originalMeta) return;
        setSaving(true);
        try {
            const payload = transformFromTracks(tracks, originalMeta);
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
            const res = await fetch(window.location.href, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken, 'X-Requested-With': 'XMLHttpRequest' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (res.ok && data.status === 'success') message.success('保存成功');
            else message.error('保存失败');
        } catch (e) {
            console.error(e);
            message.error('网络错误');
        } finally {
            setSaving(false);
        }
    };

    return {
        tracks, loading, saving, videoUrl,
        selectedActionId, setSelectedActionId, selectedContext, isComplexType,
        updateTracks, updateAction, deleteAction, createClip, splitClip, mergeClip, saveData
    };
};