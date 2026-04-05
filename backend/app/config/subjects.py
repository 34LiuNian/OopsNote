"""学科配置。"""

SUBJECTS = {
    "math": "数学",
    "physics": "物理",
    "chemistry": "化学",
    "english": "英语",
    "biology": "生物"
}

DEFAULT_SUBJECT = "math"

# 有效学科键（用于校验）
VALID_SUBJECT_KEYS = tuple(SUBJECTS.keys())
