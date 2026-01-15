import json
import os
import sys

# --- 获取真实的基础路径 ---
def get_base_path():
    """获取应用程序运行的真实目录"""
    if not getattr(sys, 'frozen', False):
        # 使用当前文件所在目录
        return os.path.dirname(os.path.abspath(__file__))
    else:
        # 2. 打包发布环境 (EXE运行)
        return os.path.dirname(sys.executable)

BASE_DIR = get_base_path()
SETTINGS_FILE = os.path.join(BASE_DIR, 'settings.json')

DEFAULT_SETTINGS = {
    # 动作设置
    "safe_app_path": "C:\\Windows\\System32\\notepad.exe",  # 默认记事本
    "fallback_url": "https://www.google.com", # 默认谷歌浏览器
    "action_type": "minimize",  # 'minimize' 或 'close'

    # 白名单：即使选择关闭所有，包含这些名字的窗口也不会关
    "whitelist_apps": [
        "winword.exe",
        "excel.exe",
        "powerpnt.exe",
        "pycharm64.exe",
        "code.exe"
    ],

    # 视觉设置
    "user_image_path": "default_user.jpg",
    "camera_index": 0,
    "tolerance": 0.6,  # 人脸识别阈值，越低越严格 (0.1 - 1.0)
    "stranger_threshold": 1,  # 陌生人连续判定帧数 (对应灵敏度)
    "absence_threshold": 10,  # 离席连续判定帧数 (对应灵敏度)
    "process_scale": 0.5,  # 图像处理缩放比例 (0.25 - 1.0)
    # 语音设置
    "voice_keywords": "老板,来了",
    "voice_energy_threshold": 300,  # 麦克风能量门限 (杂音过滤)

    # 全局采样
    "sample_interval": 0.2,  # 检测间隔(秒)
    # 冷却时间(秒)
    "cooldown_time": 10,
}


class SettingsManager:
    def __init__(self):
        self.settings = self.load_settings()

    def load_settings(self):
        """加载配置，若文件损坏或不存在则恢复默认"""
        if not os.path.exists(SETTINGS_FILE):
            return DEFAULT_SETTINGS.copy()

        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

                # 自动补全缺失的字段
                needs_save = False

                # 合并默认配置，防止新版本缺少字段
                for key, val in DEFAULT_SETTINGS.items():
                    if key not in data:
                        data[key] = val
                        needs_save = True

                # 如果补全了字段，保存，方便下次读取
                if needs_save:
                    self.save_settings(data)
                return data
        except Exception as e:
            print(f"配置文件加载失败，使用默认配置: {e}")
            return DEFAULT_SETTINGS.copy()

    def save_settings(self, new_settings):
        """保存配置到磁盘"""
        try:
            self.settings.update(new_settings)
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"配置文件保存失败: {e}")
            return False

    def get(self, key):
        return self.settings.get(key, DEFAULT_SETTINGS.get(key))