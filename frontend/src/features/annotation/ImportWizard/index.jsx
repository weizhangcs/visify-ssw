import React, { useState } from 'react';
import {
    Card, Upload, Select, Button, Typography,
    Divider, Alert, message, Input, Space, Form, Row, Col
} from 'antd';
import {
    PlusSquareOutlined,
    ImportOutlined,
    InboxOutlined,
    FileTextOutlined,
    ArrowLeftOutlined
} from '@ant-design/icons';

const { Title, Text, Paragraph } = Typography;
const { Dragger } = Upload;

const ImportWizard = ({ context }) => {
    // 1. 解构后端注入的 Context
    // assets: [{value: 'id', label: 'Title'}]
    // urls: { import_api: '...' }
    // csrfToken: '...'
    const { assets, urls, csrfToken } = context;

    const [mode, setMode] = useState(null); // null (未选) | 'create' | 'import'
    const [submitting, setSubmitting] = useState(false);

    // --- 提交导入逻辑 ---
    const handleImportSubmit = async (values) => {
        // 校验文件
        if (!values.file || values.file.length === 0) {
            message.error("请上传工程文件");
            return;
        }

        setSubmitting(true);
        const formData = new FormData();
        // Antd Upload 组件会将文件放在 fileList 或 file 属性中，这里我们取 originFileObj
        formData.append('import_file', values.file[0].originFileObj);
        formData.append('asset_id', values.asset_id);
        formData.append('name', values.name);

        try {
            const response = await fetch(urls.import_api, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': csrfToken
                }
            });
            const res = await response.json();

            if (res.success) {
                message.success("导入成功！正在跳转项目页...", 1.5, () => {
                    window.location.href = res.redirect_url;
                });
            } else {
                message.error(res.message || "导入失败，请检查文件格式。");
                setSubmitting(false);
            }
        } catch (e) {
            console.error(e);
            message.error("网络请求错误");
            setSubmitting(false);
        }
    };

    // --- 渲染：模式选择卡片 ---
    const renderModeSelection = () => (
        <div className="space-y-6">
            <div className="text-center mb-8">
                <Title level={3}>新建标注项目</Title>
                <Text type="secondary">请选择创建项目的方式</Text>
            </div>

            <Row gutter={[24, 24]}>
                {/* 选项 A: 新建空白项目 */}
                <Col span={12}>
                    <Card
                        hoverable
                        className={`h-full border-2 transition-all ${mode === 'create' ? 'border-blue-500 bg-blue-50' : 'border-gray-200'}`}
                        onClick={() => setMode('create')}
                    >
                        <div className="text-center py-6">
                            <PlusSquareOutlined className="text-4xl text-blue-500 mb-4" />
                            <Title level={5}>新建空白项目</Title>
                            <Paragraph type="secondary" className="mb-0 text-xs px-4">
                                从头开始。手动关联资产、配置编码参数，适用于全新的标注任务。
                            </Paragraph>
                        </div>
                    </Card>
                </Col>

                {/* 选项 B: 导入工程文件 */}
                <Col span={12}>
                    <Card
                        hoverable
                        className={`h-full border-2 transition-all ${mode === 'import' ? 'border-purple-500 bg-purple-50' : 'border-gray-200'}`}
                        onClick={() => setMode('import')}
                    >
                        <div className="text-center py-6">
                            <ImportOutlined className="text-4xl text-purple-500 mb-4" />
                            <Title level={5}>导入工程文件</Title>
                            <Paragraph type="secondary" className="mb-0 text-xs px-4">
                                从 JSON 文件恢复。自动关联新资产并重建任务进度，适用于数据迁移或备份恢复。
                            </Paragraph>
                        </div>
                    </Card>
                </Col>
            </Row>
        </div>
    );

    return (
        <div className="bg-gray-50 min-h-screen p-12 -m-6 flex justify-center items-start">
            <Card
                className="w-full max-w-3xl shadow-lg rounded-xl overflow-hidden"
                bodyStyle={{ padding: '40px' }}
            >
                {/* 1. 模式选择区 */}
                {renderModeSelection()}

                {/* 2. 动态内容区 (根据选择展示) */}
                {mode && (
                    <div className="mt-8 pt-8 border-t border-gray-100">

                        {/* 模式 A: 新建 -> 跳转原生 */}
                        {mode === 'create' && (
                            <div className="flex flex-col items-center gap-10">
                                <Alert
                                    message="即将跳转至基础配置页面"
                                    description="系统将引导您填写项目名称并选择关联资产。"
                                    type="info"
                                    showIcon
                                    className="text-left max-w-md w-full"
                                />
                                <Button
                                    type="primary"
                                    size="large"
                                    href="?mode=classic" // 关键：回跳 Django 原生逻辑
                                    icon={<PlusSquareOutlined />}
                                    className="px-8 h-12 text-lg"
                                >
                                    前往填写基础信息
                                </Button>
                            </div>
                        )}

                        {/* 模式 B: 导入 -> 显示表单 */}
                        {mode === 'import' && (
                            <Form
                                layout="vertical"
                                onFinish={handleImportSubmit}
                                initialValues={{ name: `Imported Project - ${new Date().toLocaleDateString()}` }}
                            >
                                <Alert
                                    message="重要提示"
                                    description="请确保选择的「目标资产」包含的媒体文件数量与导入工程中的任务数量一致。系统将尝试按顺序强制匹配。"
                                    type="warning"
                                    showIcon
                                    className="mb-6"
                                />

                                <Row gutter={24}>
                                    <Col span={12}>
                                        <Form.Item
                                            label="项目名称"
                                            name="name"
                                            rules={[{ required: true, message: '请输入项目名称' }]}
                                        >
                                            <Input size="large" prefix={<FileTextOutlined className="text-gray-400"/>} />
                                        </Form.Item>
                                    </Col>
                                    <Col span={12}>
                                        <Form.Item
                                            label="目标关联资产"
                                            name="asset_id"
                                            rules={[{ required: true, message: '请选择目标资产' }]}
                                            extra="导入的数据将嫁接到此资产上。"
                                        >
                                            <Select
                                                size="large"
                                                placeholder="搜索资产..."
                                                showSearch
                                                optionFilterProp="label"
                                                options={assets}
                                            />
                                        </Form.Item>
                                    </Col>
                                </Row>

                                <Form.Item
                                    label="工程文件 (JSON)"
                                    name="file"
                                    valuePropName="fileList"
                                    getValueFromEvent={(e) => (Array.isArray(e) ? e : e?.fileList)}
                                    rules={[{ required: true, message: '请上传文件' }]}
                                >
                                    <Dragger
                                        maxCount={1}
                                        accept=".json"
                                        beforeUpload={() => false} // 阻止自动上传
                                        className="bg-purple-50 border-purple-200"
                                    >
                                        <p className="ant-upload-drag-icon">
                                            <InboxOutlined className="text-purple-500" />
                                        </p>
                                        <p className="ant-upload-text">点击或拖拽 JSON 文件到此处</p>
                                        <p className="ant-upload-hint">支持格式: .json (由导出功能生成)</p>
                                    </Dragger>
                                </Form.Item>

                                <div className="flex justify-end gap-4 mt-8">
                                    <Button size="large" icon={<ArrowLeftOutlined />} onClick={() => window.history.back()}>
                                        取消
                                    </Button>
                                    <Button
                                        type="primary"
                                        htmlType="submit"
                                        size="large"
                                        loading={submitting}
                                        className="bg-purple-600 hover:bg-purple-500 border-none px-8"
                                        icon={<ImportOutlined />}
                                    >
                                        开始恢复
                                    </Button>
                                </div>
                            </Form>
                        )}
                    </div>
                )}
            </Card>
        </div>
    )
};

export default ImportWizard;