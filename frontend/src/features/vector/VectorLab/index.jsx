import React, { useState } from 'react';
import { Card, Input, Select, Slider, Button, Row, Col, Empty, Spin, message, Typography, Checkbox, Divider } from 'antd';
import { SearchOutlined, RocketOutlined, ClearOutlined } from '@ant-design/icons';
import ResultCard from './components/ResultCard';
import VideoModal from './components/VideoModal';

const { Title, Text } = Typography;

const INDEX_OPTIONS = [
    { label: '对白 (Dialogue)', value: 'dialogue' },
    { label: '场景 (Scene)', value: 'scene' },
    { label: '切片 (Slice)', value: 'slice' },
    { label: '画面 (Frame)', value: 'frame' },
];

const VectorLab = ({ context }) => {
    const { assets = [] } = context; // [Fix] Add default value

    // State
    const [selectedAsset, setSelectedAsset] = useState(assets.length > 0 ? assets[0].id : null);
    const [selectedTypes, setSelectedTypes] = useState(['dialogue', 'scene', 'slice', 'frame']);
    const [query, setQuery] = useState('');
    const [topK, setTopK] = useState(10);
    const [results, setResults] = useState(null);
    const [loading, setLoading] = useState(false);

    // [新增] 播放弹窗状态
    const [playingItem, setPlayingItem] = useState(null);

    const handleSearch = async () => {
        if (!selectedAsset) {
            message.warning("请先选择资产");
            return;
        }
        if (!query.trim()) {
            message.warning("请输入查询内容");
            return;
        }
        if (selectedTypes.length === 0) {
            message.warning("请至少选择一种索引类型");
            return;
        }

        setLoading(true);
        setResults(null);

        try {
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
            const response = await fetch('/vector/api/search/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({
                    asset_id: selectedAsset,
                    query: query,
                    index_types: selectedTypes,
                    top_k: topK
                })
            });

            const data = await response.json();
            if (data.status === 'success') {
                setResults(data.data);
                if (data.data.length === 0) {
                    message.info("未找到匹配结果");
                }
            } else {
                message.error(data.message || "检索失败");
            }
        } catch (e) {
            console.error(e);
            message.error("网络请求错误");
        } finally {
            setLoading(false);
        }
    };

    const handleClear = () => {
        setQuery('');
        setResults(null);
    };

    return (
        <div className="p-6 max-w-7xl mx-auto">
            <div className="mb-8">
                <Title level={2} style={{ marginBottom: 0 }}>向量检索实验室</Title>
                <Text type="secondary">多模态混合检索验证环境 (Vector Search Lab)</Text>
            </div>

            <Row gutter={24}>
                {/* 左侧：控制面板 */}
                <Col xs={24} lg={8}>
                    <Card title="检索配置" className="shadow-sm sticky top-6">
                        <div className="space-y-6">
                            <div>
                                <div className="mb-2 font-medium">目标资产</div>
                                <Select
                                    className="w-full"
                                    placeholder="选择资产"
                                    options={assets.map(a => ({ label: a.title, value: a.id }))}
                                    value={selectedAsset}
                                    onChange={setSelectedAsset}
                                />
                            </div>

                            <div>
                                <div className="mb-2 font-medium">索引范围 (多选)</div>
                                <Checkbox.Group
                                    options={INDEX_OPTIONS}
                                    value={selectedTypes}
                                    onChange={setSelectedTypes}
                                    className="flex flex-col gap-2"
                                />
                            </div>

                            <div>
                                <div className="mb-2 font-medium flex justify-between">
                                    <span>召回数量 (Top K)</span>
                                    <span className="text-blue-600">{topK}</span>
                                </div>
                                <Slider min={1} max={50} value={topK} onChange={setTopK} />
                            </div>

                            <Divider />

                            <div>
                                <div className="mb-2 font-medium">查询语句</div>
                                <Input.TextArea
                                    rows={4}
                                    placeholder="输入自然语言，例如：'雨夜中的孤独背影' 或 '关于梦想的讨论'"
                                    value={query}
                                    onChange={e => setQuery(e.target.value)}
                                    onPressEnter={(e) => {
                                        if (!e.shiftKey) {
                                            e.preventDefault();
                                            handleSearch();
                                        }
                                    }}
                                />
                            </div>

                            <div className="flex gap-3">
                                <Button
                                    type="primary"
                                    icon={<RocketOutlined />}
                                    block
                                    size="large"
                                    onClick={handleSearch}
                                    loading={loading}
                                >
                                    开始检索
                                </Button>
                                <Button icon={<ClearOutlined />} size="large" onClick={handleClear} />
                            </div>
                        </div>
                    </Card>
                </Col>

                {/* 右侧：结果展示 */}
                <Col xs={24} lg={16}>
                    <div className="space-y-4">
                        {loading ? (
                            <div className="py-20 text-center bg-white rounded-lg shadow-sm">
                                <Spin size="large" tip="正在进行语义匹配..." />
                            </div>
                        ) : results ? (
                            <>
                                <div className="flex justify-between items-center mb-2">
                                    <Text strong>检索结果 ({results.length})</Text>
                                    <Text type="secondary" className="text-xs">按相似度排序</Text>
                                </div>
                                {results.length > 0 ? (
                                    results.map((item, idx) => (
                                        <ResultCard
                                            key={`${item.id}-${idx}`}
                                            item={item}
                                            rank={idx + 1}
                                            onPlay={() => setPlayingItem(item)} // [新增] 传递播放回调
                                        />
                                    ))
                                ) : (
                                    <Empty description="暂无匹配结果" className="bg-white p-10 rounded-lg shadow-sm" />
                                )}
                            </>
                        ) : (
                            <div className="py-20 text-center bg-white rounded-lg shadow-sm text-gray-400">
                                <SearchOutlined style={{ fontSize: 48, marginBottom: 16 }} />
                                <p>配置左侧参数并输入查询语句以开始</p>
                            </div>
                        )}
                    </div>
                </Col>
            </Row>

            {/* [新增] 视频播放弹窗 */}
            <VideoModal
                visible={!!playingItem}
                item={playingItem}
                onClose={() => setPlayingItem(null)}
            />
        </div>
    );
};

export default VectorLab;