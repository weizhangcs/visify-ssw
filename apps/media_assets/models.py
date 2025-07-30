import uuid
from django.db import models
from django.utils import timezone
from django.conf import settings


class Media(models.Model):
    """
    顶层媒资实体，代表一个完整的作品，如一部短剧或一部电影。
    对应您概念中的 'Asset' (逻辑资产)。
    """
    MEDIA_TYPE_CHOICES = (
        ('short_drama', '短剧'),
        ('movie', '电影'),
    )

    INGESTION_STATUS_CHOICES = (
        ('pending', '等待文件上传'),
        ('ingesting', '加载处理中'),
        ('completed', '加载完成'),
        ('failed', '加载失败'),
    )
    ingestion_status = models.CharField(
        max_length=20,
        choices=INGESTION_STATUS_CHOICES,
        default='pending',
        verbose_name="批量加载状态"
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, verbose_name="媒资标题")
    description = models.TextField(blank=True, null=True, verbose_name="描述")
    media_type = models.CharField(
        max_length=20,
        choices=MEDIA_TYPE_CHOICES,
        default='short_drama',
        verbose_name="媒资类型"
    )
    label_studio_project_id = models.IntegerField(blank=True, null=True, verbose_name="Label Studio 项目ID")
    label_studio_export_file = models.FileField(
        upload_to='ls_exports/', blank=True, null=True, verbose_name="Label Studio 导出文件"
    )
    blueprint_status = models.CharField(max_length=20, default='pending', verbose_name="叙事蓝图生成状态")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    def __str__(self):
        return self.title

    def get_label_studio_project_url(self):
        """返回此媒资在 Label Studio 中的项目主页 URL。"""
        if not self.label_studio_project_id:
            return None
        # 注意：这里我们使用公开的URL，因为它用于生成给用户点击的链接
        return f"{settings.LABEL_STUDIO_PUBLIC_URL}/projects/{self.label_studio_project_id}"

    class Meta:
        verbose_name = "媒资（作品）"
        verbose_name_plural = verbose_name
        ordering = ['-created_at']


class Asset(models.Model):
    """
    资产条目实体，代表组成 Media 的具体单元，如一集短剧。
    这是所有工作流处理的核心单元。
    对应您概念中的 'Item' (实体条目)。
    """
    PROCESSING_STATUS_CHOICES = (
        ('pending', '待处理'),
        ('processing', '处理中'),
        ('completed', '已完成'),
        ('failed', '失败'),
    )
    ANNOTATION_STATUS_CHOICES = (
        ('pending', '未开始'),
        ('in_progress', '进行中'),
        ('completed', '已完成'),
    )
    COPYRIGHT_STATUS_CHOICES = (
        ('pending', '待定'),
        ('cleared', '已授权'),
        ('owned', '自有版权'),
        ('restricted', '受限'),
    )
    LANGUAGE_CHOICES = (
        ('zh-CN', '中文 (简体)'),
        ('en-US', '英语 (美国)'),
        # 未来可以根据需要在这里添加更多语言选项
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    media = models.ForeignKey(Media, on_delete=models.CASCADE, related_name='assets', verbose_name="所属媒资")

    title = models.CharField(max_length=255, verbose_name="条目标题")
    sequence_number = models.PositiveIntegerField(default=1, verbose_name="序号")

    language = models.CharField(
        max_length=10,
        choices=LANGUAGE_CHOICES,
        default='zh-CN',
        verbose_name="语言"
    )

    copyright_status = models.CharField(
        max_length=20,
        choices=COPYRIGHT_STATUS_CHOICES,
        default='pending',
        verbose_name="版权状态"
    )

    # 输入文件
    source_video = models.FileField(upload_to='source_files/', blank=True, null=True, verbose_name="源视频文件")
    source_subtitle = models.FileField(upload_to='source_files/', blank=True, null=True,
                                       verbose_name="源字幕文件 (SRT)")

    # --- 工作流状态与时间戳 ---
    processing_status = models.CharField(
        max_length=20, choices=PROCESSING_STATUS_CHOICES, default='pending', verbose_name="物理文件处理状态"
    )
    processing_status_changed_at = models.DateTimeField(null=True, blank=True, verbose_name="物理状态变更时间")

    l1_status = models.CharField(
        max_length=20, choices=ANNOTATION_STATUS_CHOICES, default='pending', verbose_name="第一层标注状态-字幕"
    )
    l1_status_changed_at = models.DateTimeField(null=True, blank=True, verbose_name="L1状态变更时间")

    l2_l3_status = models.CharField(
        max_length=20, choices=ANNOTATION_STATUS_CHOICES, default='pending', verbose_name="第二/三层标注状态-打标"
    )
    l2_l3_status_changed_at = models.DateTimeField(null=True, blank=True, verbose_name="L2/L3状态变更时间")

    # 外部集成 ID
    label_studio_task_id = models.IntegerField(blank=True, null=True, verbose_name="Label Studio 任务ID")

    # 流程产出物
    processed_video_url = models.URLField(max_length=1024, blank=True, null=True, verbose_name="处理后视频URL (CDN)")
    source_subtitle_url = models.URLField(max_length=1024, blank=True, null=True,
                                          verbose_name="源字幕文件URL (CDN/Public)")
    l1_output_file = models.FileField(upload_to='l1_outputs/', blank=True, null=True, verbose_name="第一层产出 (.ass)")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    def get_subeditor_url(self):
        """返回此资产条目在 SubEditor 中的编辑页面 URL。"""
        if not self.processed_video_url or not self.source_subtitle_url:
            return None

        subeditor_base_url = settings.SUBEDITOR_PUBLIC_URL
        video_url = self.processed_video_url
        srt_url = self.source_subtitle_url
        asset_id = str(self.id)

        return f"{subeditor_base_url}?videoUrl={video_url}&srtUrl={srt_url}&assetId={asset_id}"

    def get_label_studio_task_url(self):
        """返回此资产条目在 Label Studio 中的具体任务 URL。"""
        if not self.media.label_studio_project_id or not self.label_studio_task_id:
            return None

        project_id = self.media.label_studio_project_id
        task_id = self.label_studio_task_id

        # 注意：这里我们使用公开的URL
        return f"{settings.LABEL_STUDIO_PUBLIC_URL}/projects/{project_id}/data?tab={task_id}&task={task_id}"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 记录初始状态值
        self._original_processing_status = self.processing_status
        self._original_l1_status = self.l1_status
        self._original_l2_l3_status = self.l2_l3_status
        self._original_source_video = self.source_video

    def save(self, *args, **kwargs):

        # 检查状态字段是否发生变化，如果变化则更新对应的时间戳
        if self.processing_status != self._original_processing_status:
            self.processing_status_changed_at = timezone.now()
        if self.l1_status != self._original_l1_status:
            self.l1_status_changed_at = timezone.now()
        if self.l2_l3_status != self._original_l2_l3_status:
            self.l2_l3_status_changed_at = timezone.now()

        from .tasks import process_media_asset

        super().save(*args, **kwargs)

        # --- 触发异步任务 ---
        # --- 优化后的异步任务触发逻辑 ---
        # 只要源视频文件发生了变化（比如从无到有），就触发任务
        if self.source_video and self._original_source_video != self.source_video:
            print(f"检测到视频文件变化，触发异步任务来处理 Asset: {self.id}")
            process_media_asset.delay(str(self.id))

        # 保存后，更新初始状态值为当前值，为下一次 save 调用做准备
        self._original_processing_status = self.processing_status
        self._original_l1_status = self.l1_status
        self._original_l2_l3_status = self.l2_l3_status
        self._original_source_video = self.source_video

    def __str__(self):
        return f"{self.media.title} - {self.sequence_number:02d} - {self.title}"

    class Meta:
        verbose_name = "资产条目（剧集）"
        verbose_name_plural = verbose_name
        ordering = ['media', 'sequence_number']