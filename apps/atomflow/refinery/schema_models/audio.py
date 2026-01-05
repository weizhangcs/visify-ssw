from pydantic import BaseModel, Field


class AudioAnalysis(BaseModel):
    """
    [音频特征] 对白声学分析结果。
    通常由音频分析模型产出，用于辅助情感判断或角色识别。
    """

    gender: str = Field(default="Unknown", description="推测性别: Male | Female | Unknown")
    pitch_level: str = Field(default="Mid", description="音高等级: High | Mid | Low")
    speed_level: str = Field(default="Normal", description="语速等级: Fast | Normal | Slow")
    volume_level: str = Field(default="Normal", description="音量等级: Loud | Normal | Quiet")

    # 原始数值 (用于调试或更精细的聚类)
    avg_pitch_hz: float = Field(default=0.0, description="平均基频 (Hz)")
    chars_per_sec: float = Field(default=0.0, description="语速 (字/秒)")
    rms_energy: float = Field(default=0.0, description="能量均方根")


class AudioContent(BaseModel):
    """音频内容容器 (占位)"""

    pass
