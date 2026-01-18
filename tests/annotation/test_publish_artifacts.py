import os
import sys
import unittest
import uuid
from pathlib import Path

import django

# 1. 环境初始化 (解决 ModuleNotFoundError 和 AppRegistryNotReady)
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "visify_ssw.settings")
django.setup()

from apps.atomflow.refinery.models import Material  # noqa: E402
from apps.common.schemas.annotation.workbench import DataOrigin  # noqa: E402
from apps.common.schemas.annotation.workbench import DialogueContent  # noqa: E402
from apps.common.schemas.annotation.workbench import DialogueItem  # noqa: E402
from apps.common.schemas.annotation.workbench import ItemContext  # noqa: E402
from apps.common.schemas.annotation.workbench import MediaAnnotation  # noqa: E402
from apps.common.schemas.annotation.workbench import SceneContent  # noqa: E402
from apps.common.schemas.annotation.workbench import SceneItem  # noqa: E402; noqa: E402

# 2. 业务导入
from apps.media_assets.models import Asset, Media  # noqa: E402
from apps.workflow.annotation.jobs import AnnotationJob  # noqa: E402
from apps.workflow.annotation.projects import AnnotationProject  # noqa: E402
from apps.workflow.annotation.services.annotation_service import AnnotationService  # noqa: E402


class AnnotationPublishTest(unittest.TestCase):
    """
    测试 AnnotationJob 的数据发布逻辑 (publish_job_artifacts)。
    验证：
    1. Workbench 数据 (job.data) 是否正确拆解并存入冗余字段 (dialogues, scenes)。
    2. Refinery 数据 (Material) 是否正确复制 (frames, slices)。
    3. UUID 是否在整个过程中保持一致 (Identity Preservation)。
    """

    def setUp(self):
        # 1. 准备基础数据 (Asset, Media, Project, Job)
        # 注意：这里假设 Asset 和 Media 只需要 title 即可创建，根据实际模型可能需要调整
        self.asset = Asset.objects.create(title="Test Asset")
        self.media = Media.objects.create(asset=self.asset, title="Test Media", duration=100.0, sequence_number=1)
        self.project = AnnotationProject.objects.create(asset=self.asset, name="Test Project")
        self.job = AnnotationJob.objects.create(project=self.project, media=self.media, status="PROCESSING")

        # 2. 准备 Refinery Material (模拟上游产出)
        # 这些数据应该被复制到 Job 的 frames 和 slices 字段中
        self.material = Material.objects.create(media=self.media)
        self.material.frames = [
            {"id": str(uuid.uuid4()), "timestamp": 1.5, "path": "frames/f1.jpg", "digest": "abc"},
            {"id": str(uuid.uuid4()), "timestamp": 5.5, "path": "frames/f2.jpg", "digest": "def"},
        ]
        self.material.slices = [
            {"id": str(uuid.uuid4()), "start_time": 0.0, "end_time": 10.0, "type": "visual_segment"}
        ]
        self.material.save()

    def test_publish_job_artifacts(self):
        print("\n[Test] Starting test_publish_job_artifacts...")

        # 3. 模拟前端保存的标注数据 (job.data)
        # 构造符合 Schema 的数据对象
        dialogue_id = str(uuid.uuid4())
        scene_id = str(uuid.uuid4())

        anno_data = MediaAnnotation(
            media_id=str(self.media.id),
            file_name=self.media.title,
            source_path="/media/test.mp4",
            sequence_number=1,
            duration=100.0,
            dialogues=[
                DialogueItem(
                    start=1.0,
                    end=5.0,
                    content=DialogueContent(text="Hello World", speaker="Alice"),
                    # 模拟前端回传的 Context，包含 Refinery 生成的 ID
                    context=ItemContext(id=dialogue_id, origin=DataOrigin.HUMAN, is_verified=True),
                )
            ],
            scenes=[
                SceneItem(
                    start=0.0,
                    end=10.0,
                    content=SceneContent(narrative_action="Intro scene", label="Scene 1", visual_mood_tags=["Bright"]),
                    context=ItemContext(id=scene_id, origin=DataOrigin.AI_CV),
                )
            ],
            captions=[],
            highlights=[],
        )

        # 保存到数据库 (模拟前端 Save API 的行为)
        self.job.data = anno_data.model_dump(mode="json", exclude_none=True)
        self.job.save()

        # 4. 执行发布逻辑 (核心测试目标)
        AnnotationService.publish_job_artifacts(self.job)

        # 5. 验证结果
        # [Fix] django-fsm protected=True 禁止直接修改 status 字段，导致 refresh_from_db 失败
        # 必须重新从数据库获取对象
        self.job = AnnotationJob.objects.get(pk=self.job.pk)

        # A. 验证 Dialogues (来自 job.data)
        self.assertTrue(len(self.job.dialogues) > 0, "Dialogues should not be empty")
        d_item = self.job.dialogues[0]
        self.assertEqual(d_item["id"], dialogue_id, "Dialogue ID should be preserved")
        self.assertEqual(d_item["content"], "Hello World")
        self.assertEqual(d_item["speaker"], "Alice")
        print(f"✅ Dialogues verified. ID: {d_item['id']}")

        # B. 验证 Scenes (来自 job.data)
        self.assertTrue(len(self.job.scenes) > 0, "Scenes should not be empty")
        s_item = self.job.scenes[0]
        self.assertEqual(s_item["id"], scene_id, "Scene ID should be preserved")
        self.assertEqual(s_item["content"]["narrative_action"], "Intro scene")
        print(f"✅ Scenes verified. ID: {s_item['id']}")

        # C. 验证 Frames (来自 Material 的快照复制)
        self.assertEqual(len(self.job.frames), 2, "Frames should be copied from Material")
        self.assertEqual(self.job.frames[0]["path"], "frames/f1.jpg")
        print(f"✅ Frames copied from Material. Count: {len(self.job.frames)}")

        # D. 验证 Slices (来自 Material 的快照复制)
        self.assertEqual(len(self.job.slices), 1, "Slices should be copied from Material")
        self.assertEqual(self.job.slices[0]["type"], "visual_segment")
        print(f"✅ Slices copied from Material. Count: {len(self.job.slices)}")


if __name__ == "__main__":
    unittest.main()
