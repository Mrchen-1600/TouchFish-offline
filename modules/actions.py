import os
import webbrowser
import platform
import ctypes
import pyautogui
import subprocess

# Windows 音量控制常量
VK_VOLUME_MUTE = 0xAD


def set_system_mute():
    """
    切换系统静音状态 (当前仅支持 Windows)
    """
    if platform.system() == 'Windows':
        print("执行: 系统静音")
        try:
            # 模拟按下和释放静音键
            ctypes.windll.user32.keybd_event(VK_VOLUME_MUTE, 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_VOLUME_MUTE, 0, 2, 0)
        except Exception as e:
            print(f"静音失败: {e}")


def trigger_protection(action_type, safe_app_path, fallback_url):
    """
    执行保护流程：
    1. 静音
    2. 最小化/关闭窗口
    3. 打开伪装应用
    """
    print(f"正在触发保护! 动作: {action_type}")

    # 1. 优先静音
    set_system_mute()

    # 2. 处理当前窗口
    if action_type == 'minimize':
        # Win+D 显示桌面 (最小化所有)
        pyautogui.hotkey('win', 'd')
    elif action_type == 'close':
        # Alt+F4 关闭当前聚焦窗口
        pyautogui.hotkey('alt', 'f4')

    # 3. 打开安全应用
    app_opened = False
    if safe_app_path and os.path.exists(safe_app_path):
        try:
            print(f"正在打开应用: {safe_app_path}")
            os.startfile(safe_app_path)
            app_opened = True
        except Exception as e:
            print(f"打开应用失败: {e}")

    # 如果没配置应用或打开失败，打开网页
    if not app_opened:
        print(f"打开备用链接: {fallback_url}")
        webbrowser.open(fallback_url)