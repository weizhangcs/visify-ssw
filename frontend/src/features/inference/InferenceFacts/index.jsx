import React, { useState, useMemo, useEffect } from 'react';
import { Table, Tag, Card, Typography, Empty, Space, Button, Alert, Checkbox, message, Slider, Row, Col, Tooltip, Divider } from 'antd';
import { BarsOutlined, SyncOutlined, ExperimentOutlined, FilterOutlined, SendOutlined, RocketOutlined } from '@ant-design/icons';

const { Text } = Typography;

const InferenceFacts = ({ context }) => {
    // 1. 解构后端传来的数据
    const { items, character_data, meta, urls } = context;
    const { all_characters, importance_scores, min_score, max_score } = character_data;

    // 状态
    const [selectedCharacters, setSelectedCharacters] = useState([]);
    const [scoreThreshold, setScoreThreshold] = useState(0);
    const [submitting, setSubmitting] = useState(false);

    // 初始化 Slider 阈值
    useEffect(() => {
        if (min_score !== scoreThreshold) {
            setScoreThreshold(min_score);
        }
    }, [min_score]);

    // 2. 核心计算：基于滑动条和得分，动态过滤出可选项
    const filteredCharacterOptions = useMemo(() => {
        return all_characters
            .filter(charName => {
                const score = importance_scores[charName] || 0;
                return score >= scoreThreshold;
            })
            .map(charName => ({
                label: charName,
                value: charName,
                score: importance_scores[charName] || 0,
            }));
    }, [all_characters, importance_scores, scoreThreshold]);

    // 联动更新选中状态
    useEffect(() => {
        setSelectedCharacters(prevSelected => {
            const availableNames = filteredCharacterOptions.map(opt => opt.value);
            return prevSelected.filter(name => availableNames.includes(name));
        });
    }, [filteredCharacterOptions]);

    // 全选状态计算
    const isAllSelected = selectedCharacters.length > 0 &&
        selectedCharacters.length === filteredCharacterOptions.length;

    // 全选/全不选逻辑
    const handleSelectAll = (e) => {
        const checked = e.target.checked;
        if (checked) {
            const allNames = filteredCharacterOptions.map(opt => opt.value);
            setSelectedCharacters(allNames);
        } else {
            setSelectedCharacters([]);
        }
    };

    // --- 提交逻辑 ---
    const handleSubmit = async () => {
        if (selectedCharacters.length === 0) {
            message.warning('请至少选择一个角色进行推理！');
            return;
        }

        setSubmitting(true);
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
        const formData = new FormData();
        selectedCharacters.forEach(char => formData.append('characters', char));
        formData.append('csrfmiddlewaretoken', csrfToken);

        try {
            const response = await fetch(urls.submit, {
                method: 'POST',
                body: formData,
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });

            if (response.redirected) {
                message.success('任务已发起，页面刷新中...', 1.5, () => {
                    window.location.href = response.url;
                });
            } else {
                if (!response.ok) throw new Error('提交失败');
                message.success('任务创建成功');
                setTimeout(() => window.location.reload(), 1000);
            }
        } catch (error) {
            console.error(error);
            message.error('请求失败，请检查网络或重试');
            setSubmitting(false);
        }
    };

    // [新增] RAG 部署处理函数
    const handleDeployRAG = async (ragUrl) => {
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
        const formData = new FormData();
        formData.append('csrfmiddlewaretoken', csrfToken);

        try {
            const response = await fetch(ragUrl, {
                method: 'POST',
                body: formData,
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });

            if (response.redirected) {
                message.success('知识图谱部署任务已启动，页面刷新中...', 1.5, () => {
                    window.location.href = response.url;
                });
            } else {
                if (!response.ok) throw new Error('部署请求失败');
                message.success('部署请求已发送');
                setTimeout(() => window.location.reload(), 1000);
            }
        } catch (error) {
            console.error(error);
            message.error('知识图谱部署失败');
        }
    };

    // --- 表格列定义 ---
    const columns = [
        {
            title: '任务ID',
            dataIndex: 'id',
            key: 'id',
            width: 100,
            render: (text) => <Text code>{text.slice(0, 8)}</Text>,
        },
        {
            // 1. 颜色和显示判断
            title: '类型',
            dataIndex: 'jobType',
            key: 'jobType',
            width: 140,
            render: (text, record) => {
                const isFacts = record.typeCode === 'FACTS'; // [核心修正 1] 使用 typeCode 判断
                const color = isFacts ? 'purple' : 'blue';
                return <Tag color={color}>{text || '未知类型'}</Tag>;
            }
        },
        {
            title: '状态',
            dataIndex: 'status',
            key: 'status',
            width: 120,
            render: (status, record) => {
                const colors = {
                    'COMPLETED': 'success',
                    'RUNNING': 'processing',
                    'FAILED': 'error',
                    'CREATED': 'default',
                    'PENDING': 'default'
                };
                // 确保 RAG 任务失败时能看到失败状态
                return <Tag color={colors[status] || 'default'}>{record.statusDisplay || status}</Tag>;
            }
        },
        {
            title: '输入参数',
            dataIndex: 'input',
            key: 'input',
            ellipsis: true,
            render: (input, record) => {
                // [核心修正 2] 使用 typeCode 判断
                if (record.typeCode === 'FACTS') {
                    const chars = input?.characters || [];
                    return chars.length > 0 ? (
                        <Tooltip title={chars.join(', ')}>
                            <Text>{chars.length} 个角色</Text>
                        </Tooltip>
                    ) : <Text type="secondary">--</Text>;
                } else if (record.typeCode === 'RAG_DEPLOYMENT') {
                    // RAG 部署任务的输入是源 FACTS Job ID
                    const sourceId = input?.source_facts_job_id; // 从 input.params 中获取
                    return sourceId ? (
                        <Tooltip title={`源 Job ID: ${sourceId}`}>
                            <Text type="secondary">源 Job: {sourceId.slice(0, 8)}</Text>
                        </Tooltip>
                    ) : <Text type="secondary">自动触发</Text>
                }
                return <Text type="secondary">N/A</Text>;
            }
        },
        {
            title: '创建时间',
            dataIndex: 'created',
            key: 'created',
            width: 160,
            className: 'text-gray-500 text-sm'
        },
        // [移除 RAG 操作列]
    ];

    return (
        <div className="space-y-6 mt-6">
            <Card
                title={<Space><ExperimentOutlined className="text-purple-600" /><span>发起新任务：角色选择与过滤</span></Space>}
                bordered={false}
                className="shadow-sm"
            >
                {!meta.metricsLoaded ? (
                    <Alert
                        type="warning"
                        showIcon
                        message="无法加载角色数据"
                        description={meta.errorMsg || "未找到可用的角色矩阵数据。请先返回“标注项目”完成角色矩阵计算。"}
                    />
                ) : (
                    <div>
                        <Row gutter={16} align="middle" className="mb-6 p-4 bg-gray-50 rounded-lg border border-gray-100">
                            <Col span={4}>
                                <Space className="font-medium text-gray-700">
                                    <FilterOutlined /> 最小重要度得分:
                                </Space>
                                <Text type="secondary" className="block text-xs mt-1">
                                    (范围: {min_score.toFixed(2)} - {max_score.toFixed(2)})
                                </Text>
                            </Col>
                            <Col span={14}>
                                <Slider
                                    min={min_score}
                                    max={max_score}
                                    step={0.01}
                                    onChange={setScoreThreshold}
                                    value={scoreThreshold}
                                    tooltip={{ formatter: (value) => `得分 ≥ ${value?.toFixed(2)}` }}
                                />
                            </Col>
                            <Col span={6}>
                                <Text type="secondary">当前筛选出: </Text>
                                <Tag color="blue">{filteredCharacterOptions.length} / {all_characters.length}</Tag>
                            </Col>
                        </Row>

                        <div className="mb-4">
                            <Text strong className="block mb-2">选择要提交推理的角色 (已过滤):</Text>
                            <Checkbox
                                onChange={handleSelectAll}
                                checked={isAllSelected}
                                indeterminate={selectedCharacters.length > 0 && !isAllSelected}
                                className="mb-3"
                            >
                                全选当前 {filteredCharacterOptions.length} 个角色
                            </Checkbox>
                            <Divider style={{ margin: '10px 0' }} />
                            <Checkbox.Group
                                options={filteredCharacterOptions}
                                value={selectedCharacters}
                                onChange={setSelectedCharacters}
                                className="flex flex-wrap gap-x-4"
                            />
                        </div>

                        <Button
                            type="primary"
                            icon={<SendOutlined />}
                            loading={submitting}
                            onClick={handleSubmit}
                            disabled={selectedCharacters.length === 0}
                            size="large"
                        >
                            {submitting ? '提交中...' : '启动云端推理'}
                        </Button>
                    </div>
                )}
            </Card>

            <Card
                title={<Space><BarsOutlined /><span>历史任务记录</span></Space>}
                bordered={false}
                className="shadow-sm"
                bodyStyle={{ padding: 0 }}
            >
                <Table
                    dataSource={items}
                    columns={columns}
                    rowKey="id"
                    pagination={{ pageSize: 5 }}
                />
            </Card>
        </div>
    );
};

// [修复] 必须添加此行
export default InferenceFacts;