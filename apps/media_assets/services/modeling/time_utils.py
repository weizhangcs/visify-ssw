# time_utils.py

class TimeConverter:
    """
    一个处理时间格式转换的公共工具类。
    """
    @staticmethod
    def ass_time_to_seconds(time_str: str) -> float:
        """将Aegisub的时间格式 (H:MM:SS.ss) 转换为总秒数（浮点数）。"""
        if not isinstance(time_str, str): return 0.0
        parts = time_str.split(':')
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s)
        elif len(parts) == 2:
            m, s = parts
            return int(m) * 60 + float(s)
        elif len(parts) == 1:
            return float(parts[0])
        return 0.0

    @staticmethod
    def ls_time_to_seconds(seconds_float: float) -> float:
        """一个直通函数，用于统一接口，处理来自Label Studio的浮点数秒数。"""
        return seconds_float if seconds_float is not None else 0.0

    @staticmethod
    def seconds_to_final_format(seconds: float) -> str:
        """将总秒数（浮点数）转换为最终输出的HH:MM:SS.mmm格式字符串。"""
        if seconds is None:
            return "00:00:00.000"
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"