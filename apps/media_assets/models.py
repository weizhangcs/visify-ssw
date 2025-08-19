# 文件路径: apps/media_assets/models.py
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
    COPYRIGHT_STATUS_CHOICES = (
        ('pending', '待定'),
        ('cleared', '已授权'),
        ('owned', '自有版权'),
        ('restricted', '受限'),
    )
    LANGUAGE_CHOICES = (
        ('zh-CN', '中文 (简体)'),
        ('en-US', '英语 (美国)'),
    )
    UPLOAD_STATUS_CHOICES = (
        ('pending', '等待文件上传'),
        ('uploading', '上传中'),
        ('completed', '上传完成'),
        ('failed', '上传失败'),
    )
    PROCESSING_STATUS_CHOICES = (
        ('pending', '等待处理'),
        ('processing', '处理中'),
        ('completed', '全部处理完成'),
        ('failed', '部分或全部失败'),
    )

    upload_status = models.CharField(
        max_length=20,
        choices=UPLOAD_STATUS_CHOICES,
        default='pending',
        verbose_name="文件上传状态"
    )
    processing_status = models.CharField(
        max_length=20,
        choices=PROCESSING_STATUS_CHOICES,
        default='pending',
        verbose_name="文件处理状态"
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
    label_studio_project_id = models.IntegerField(blank=True, null=True, verbose_name="Label Studio 项目ID")
    label_studio_export_file = models.FileField(
        upload_to='ls_exports/', blank=True, null=True, verbose_name="Label Studio 导出文件"
    )

    character_audit_report = models.FileField(
        upload_to='audit_reports/l1_character/', blank=True, null=True, verbose_name="角色名审计报告 (CSV)"
    )
    blueprint_validation_report = models.JSONField(
        blank=True, null=True, verbose_name="叙事蓝图验证报告"
    )
    final_blueprint_file = models.FileField(
        upload_to='blueprints/', blank=True, null=True, verbose_name="最终叙事蓝图 (JSON)"
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
        ('updated', '已更新'),
        ('failed', '失败'),
    )
    ANNOTATION_STATUS_CHOICES = (
        ('pending', '未开始'),
        ('in_progress', '进行中'),
        ('completed', '已完成'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    media = models.ForeignKey(Media, on_delete=models.CASCADE, related_name='assets', verbose_name="所属媒资")
    title = models.CharField(max_length=255, verbose_name="条目标题")
    sequence_number = models.PositiveIntegerField(default=1, verbose_name="序号")

    source_video = models.FileField(upload_to='source_files/', blank=True, null=True, verbose_name="源视频文件")
    source_subtitle = models.FileField(upload_to='source_files/', blank=True, null=True,
                                       verbose_name="源字幕文件 (SRT)")

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

    label_studio_task_id = models.IntegerField(blank=True, null=True, verbose_name="Label Studio 任务ID")

    processed_video_url = models.URLField(max_length=1024, blank=True, null=True, verbose_name="处理后视频URL (CDN)")
    source_subtitle_url = models.URLField(max_length=1024, blank=True, null=True,
                                          verbose_name="源字幕文件URL (CDN/Public)")
    l1_output_file = models.FileField(upload_to='l1_outputs/', blank=True, null=True, verbose_name="第一层产出 (.ass)")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    def get_subeditor_url(self):
        if not self.processed_video_url or not self.source_subtitle_url:
            return None

        # 默认使用源 SRT 文件
        subtitle_url = self.source_subtitle_url

        # 如果已有 L1 产出物（.ass 文件），则优先使用它
        if self.l1_output_file and hasattr(self.l1_output_file, 'url'):
            subtitle_url = self.l1_output_file.url

        # 如果最终没有可用的字幕文件URL，则无法生成链接
        if not subtitle_url:
            return None

        subeditor_base_url = settings.SUBEDITOR_PUBLIC_URL
        video_url = self.processed_video_url
        asset_id = str(self.id)

        # 将 srtUrl 参数用于传递 .ass 或 .srt 文件的地址
        return f"{subeditor_base_url}?videoUrl={video_url}&srtUrl={subtitle_url}&assetId={asset_id}"

    def get_label_studio_task_url(self):
        if not self.media.label_studio_project_id or not self.label_studio_task_id:
            return None
        project_id = self.media.label_studio_project_id
        task_id = self.label_studio_task_id
        return f"{settings.LABEL_STUDIO_PUBLIC_URL}/projects/{project_id}/data?tab={task_id}&task={task_id}"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_processing_status = self.processing_status
        self._original_l1_status = self.l1_status
        self._original_l2_l3_status = self.l2_l3_status
        self._original_source_video = self.source_video

    def save(self, *args, **kwargs):
        if self.processing_status != self._original_processing_status:
            self.processing_status_changed_at = timezone.now()
        if self.l1_status != self._original_l1_status:
            self.l1_status_changed_at = timezone.now()
        if self.l2_l3_status != self._original_l2_l3_status:
            self.l2_l3_status_changed_at = timezone.now()
        super().save(*args, **kwargs)
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