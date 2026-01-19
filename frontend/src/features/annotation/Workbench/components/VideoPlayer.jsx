import React, { forwardRef, useImperativeHandle, useRef, useEffect } from 'react';
import Hls from 'hls.js';

// [修改] 增加 subtitleUrl 属性, 增加 controls 属性 (默认为 true)
const VideoPlayer = forwardRef(({ url, playing, onProgress, onDuration, onReady, onPlay, onPause, subtitleUrl, controls = true }, ref) => {
    const videoRef = useRef(null);
    const lastLogTime = useRef(0);
    const retryCount = useRef(0); // [Fix] 引入重试计数器

    useImperativeHandle(ref, () => ({
        seekTo: (seconds) => {
            if (videoRef.current) {
                // console.log(`[VideoPlayer] 执行 Seek -> ${seconds}s`);
                videoRef.current.currentTime = seconds;
            }
        },
        getCurrentTime: () => {
            return videoRef.current ? videoRef.current.currentTime : 0;
        }
    }));

    useEffect(() => {
        const video = videoRef.current;
        if (!video || !url) return;

        let hls = null;
        const isHls = url.includes('.m3u8');

        if (isHls && Hls.isSupported()) {
            // [Fix] 集成 hls.js 以支持非 Safari 浏览器的 HLS 播放
            hls = new Hls({
                enableWorker: true,
                lowLatencyMode: true,
            });
            hls.loadSource(url);
            hls.attachMedia(video);
            hls.on(Hls.Events.MANIFEST_PARSED, () => {
                retryCount.current = 0; // [Fix] 加载成功后重置重试计数
                if (playing) video.play().catch(e => console.error("[VideoPlayer] HLS Play Error:", e));
            });

            // [Fix] 添加 HLS 错误监听，便于排查 NetworkError / MediaError
            hls.on(Hls.Events.ERROR, (event, data) => {
                if (data.fatal) {
                    console.error("[VideoPlayer] HLS Fatal Error:", data);
                    switch (data.type) {
                        case Hls.ErrorTypes.NETWORK_ERROR:
                            // [Fix] 增加重试限制，防止死循环
                            if (retryCount.current < 3) {
                                retryCount.current++;
                                console.warn(`[VideoPlayer] Network error, retrying (${retryCount.current}/3)...`);
                                hls.startLoad();
                            } else {
                                console.error("[VideoPlayer] Network recovery failed. Stopping.");
                                hls.destroy();
                            }
                            break;
                        case Hls.ErrorTypes.MEDIA_ERROR:
                            if (retryCount.current < 3) {
                                retryCount.current++;
                                console.warn(`[VideoPlayer] Media error, recovering (${retryCount.current}/3)...`);
                                hls.recoverMediaError();
                            } else {
                                console.error("[VideoPlayer] Media recovery failed. Stopping.");
                                hls.destroy();
                            }
                            break;
                        default:
                            hls.destroy();
                            break;
                    }
                }
            });
        } else {
            // 原生支持 (Safari) 或 普通 MP4
            video.src = url;
        }

        return () => {
            if (hls) {
                hls.destroy();
            }
        };
    }, [url]); // 仅当 URL 变化时重新加载

    useEffect(() => {
        const video = videoRef.current;
        if (!video) return;

        if (playing && video.paused) {
            video.play().catch(e => console.error("[VideoPlayer] Play Error:", e));
        } else if (!playing && !video.paused) {
            video.pause();
        }
    }, [playing]);

    // [新增] 监听字幕 URL 变化，强制开启显示
    // 因为原生 <track default> 只在挂载时生效，后续动态添加需要手动设置 mode
    useEffect(() => {
        const video = videoRef.current;
        if (video && subtitleUrl) {
            // 稍微延迟一下，确保 track 标签已被 React 渲染进 DOM
            setTimeout(() => {
                if (video.textTracks && video.textTracks.length > 0) {
                    // 设置最后一条轨道为显示 (showing)
                    // 注意：如果之前有轨道，可能需要先清理或遍历设置
                    const track = video.textTracks[video.textTracks.length - 1];
                    track.mode = 'showing';
                }
            }, 100);
        }
    }, [subtitleUrl]);

    return (
        <div className="w-full h-full bg-black flex items-center justify-center overflow-hidden">
            <video
                ref={videoRef}
                // src={url} // [Fix] 移除直接赋值，改由 useEffect 接管以支持 HLS
                className="w-full h-full object-contain"
                controls={controls}

                onPlay={() => { if (onPlay) onPlay(); }}
                onPause={() => { if (onPause) onPause(); }}
                onLoadedMetadata={() => {
                    if (onDuration && videoRef.current) onDuration(videoRef.current.duration);
                    if (onReady) onReady();
                }}
                onTimeUpdate={() => {
                    if (videoRef.current) {
                        const now = videoRef.current.currentTime;
                        if (Math.abs(now - lastLogTime.current) > 2) {
                            lastLogTime.current = now;
                        }
                        if (onProgress) {
                            onProgress({ playedSeconds: now });
                        }
                    }
                }}
                onError={(e) => console.error('[VideoPlayer] Native Error:', e)}
                crossOrigin="anonymous" // [建议] 如果视频和字幕跨域，加上这个更安全
            >
                {/* [新增] 动态渲染字幕轨 */}
                {subtitleUrl && (
                    <track
                        key={subtitleUrl} // key 变化强制 React 重新渲染标签
                        label="实时预览"
                        kind="subtitles"
                        srcLang="zh"
                        src={subtitleUrl}
                        default
                    />
                )}
            </video>
        </div>
    );
});

export default VideoPlayer;