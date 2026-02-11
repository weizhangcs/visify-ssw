import React, { useState } from 'react';
import { Card, Empty, List, Button, Input, Tag, Typography, Space, Divider, message, Spin, Row, Col } from 'antd';
import { 
    BulbOutlined, 
    SearchOutlined, 
    DatabaseOutlined, 
    CheckCircleOutlined, 
    SyncOutlined,
    PlayCircleOutlined
} from '@ant-design/icons';

const { Title, Text, Paragraph } = Typography;
const { Search } = Input;

const InferenceRag = () => {
    // 获取后端注入的数据
    const context = window.SERVER_CONTEXT || { jobs: [], urls: {} };
    const { jobs, urls } = context;

    const [selectedJobId, setSelectedJobId] = useState(jobs.length > 0 ? jobs[0].id : null);
    const [searchResults, setSearchResults] = useState(null);
    const [searching, setSearching] = useState(false);
    const [building, setBuilding] = useState(false);

    // 获取当前选中的 Job 对象
    const selectedJob = jobs.find(j => j.id === selectedJobId);

    // --- API 交互 ---

    const handleBuildIndex = async () => {
        if (!selectedJobId) return;
        setBuilding(true);
        try {
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
            const res = await fetch(urls.build_api, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({ job_id: selectedJobId })
            });
            const data = await res.json();
            if (data.status === 'success') {
                message.success("索引构建任务已启动，请稍后刷新页面查看状态");
            } else {
                message.error(data.message);
            }
        } catch (e) {
            message.error("请求失败");
        } finally {
            setBuilding(false);
        }
    };

    const handleSearch = async (value) => {
        if (!value.trim() || !selectedJobId) return;
        setSearching(true);
        setSearchResults(null);
        try {
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
            const res = await fetch(urls.search_api, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({ job_id: selectedJobId, query: value })
            });
            const data = await res.json();
            if (data.status === 'success') {
                setSearchResults(data.data);
            } else {
                message.error(data.message);
            }
        } catch (e) {
            message.error("搜索请求失败");
        } finally {
            setSearching(false);
        }
    };

    // --- 渲染辅助 ---
    
    const renderResultSection = (title, items, color) => {
        if (!items || items.length === 0) return null;
        return (
            <div className="mb-6">
                <Divider orientation="left" style={{borderColor: '#f0f0f0'}}>
                    <Tag color={color}>{title}</Tag>
                </Divider>
                <div className="space-y-3">
                    {items.map((item, idx) => (
                        <Card key={idx} size="small" bordered={false} className="bg-gray-50 shadow-sm hover:shadow-md transition-shadow">
                            <div className="flex justify-between items-start mb-1">
                                <Text type="secondary" className="text-xs">
                                    Time: {item.start?.toFixed(2)}s - {item.end?.toFixed(2)}s
                                </Text>
                                <Tag bordered={false} className="text-xs">Score: {item.score?.toFixed(4)}</Tag>
                            </div>
                            <Paragraph className="mb-0 text-sm text-gray-700">
                                {item.text_preview}
                            </Paragraph>
                        </Card>
                    ))}
                </div>
            </div>
        );
    };

    return (
        <div className="mt-6 flex gap-6 items-start">
            {/* 左侧：媒体列表 */}
            <Card title="媒体资源库" className="w-1/3 shadow-sm" bodyStyle={{padding: 0}}>
                <List
                    dataSource={jobs}
                    renderItem={item => (
                        <List.Item 
                            className={`cursor-pointer transition-colors hover:bg-gray-50 px-4 py-3 ${selectedJobId === item.id ? 'bg-purple-50 border-r-4 border-purple-500' : ''}`}
                            onClick={() => { setSelectedJobId(item.id); setSearchResults(null); }}
                        >
                            <List.Item.Meta
                                avatar={<PlayCircleOutlined className="text-lg text-gray-400 mt-1" />}
                                title={<span className="text-sm font-medium">{item.media_title}</span>}
                                description={
                                    <Space size="small" className="mt-1">
                                        {item.has_index ? 
                                            <Tag color="success" icon={<CheckCircleOutlined />}>索引就绪</Tag> : 
                                            <Tag color="default">未索引</Tag>
                                        }
                                    </Space>
                                }
                            />
                        </List.Item>
                    )}
                />
            </Card>

            {/* 右侧：交互区 */}
            <Card className="w-2/3 shadow-sm min-h-[500px]">
                {selectedJob ? (
                    <div>
                        <div className="flex justify-between items-center mb-6">
                            <div>
                                <Title level={4} style={{marginBottom: 4}}>{selectedJob.media_title}</Title>
                                <Text type="secondary">Job ID: {selectedJob.id}</Text>
                            </div>
                            <Button 
                                type={selectedJob.has_index ? "default" : "primary"}
                                icon={selectedJob.has_index ? <SyncOutlined /> : <DatabaseOutlined />} 
                                onClick={handleBuildIndex}
                                loading={building}
                            >
                                {selectedJob.has_index ? "重建索引" : "构建本地向量索引"}
                            </Button>
                        </div>

                        <div className="mb-8">
                            <Search
                                placeholder="输入自然语言查询，例如：'安然的故事' 或 '激烈的争吵场景'"
                                enterButton={<Button type="primary" icon={<SearchOutlined />}>语义检索</Button>}
                                size="large"
                                onSearch={handleSearch}
                                loading={searching}
                                disabled={!selectedJob.has_index}
                            />
                            {!selectedJob.has_index && <Text type="warning" className="text-xs mt-2 block">⚠️ 请先构建索引以启用搜索功能</Text>}
                        </div>

                        <div className="results-area">
                            {searchResults ? (
                                <>
                                    {renderResultSection("对话 (Dialogues)", searchResults.dialogue, "blue")}
                                    {renderResultSection("场景 (Scenes)", searchResults.scene, "orange")}
                                    {renderResultSection("切片 (Slices)", searchResults.slice, "purple")}
                                    {renderResultSection("画面 (Frames)", searchResults.frame, "cyan")}
                                    {Object.keys(searchResults).length === 0 && <Empty description="未找到相关内容" />}
                                </>
                            ) : (
                                !searching && <div className="text-center text-gray-400 mt-20">
                                    <BulbOutlined style={{fontSize: 48, marginBottom: 16, color: '#e5e7eb'}} />
                                    <p>输入关键词开始探索视频内容</p>
                                </div>
                            )}
                        </div>
                    </div>
                ) : (
                    <Empty description="请选择左侧媒体文件" className="mt-20" />
                )}
            </Card>
        </div>
    );
};

export default InferenceRag;