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


# --- 获取窗口对应的进程文件名 ---
def get_process_filename(hwnd):
    """
    通过窗口句柄获取对应的可执行文件名
    """
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi

        # 1. 获取 PID
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        # 2. 打开进程 (PROCESS_QUERY_INFORMATION | PROCESS_VM_READ)
        # 0x0400 | 0x0010
        hProcess = kernel32.OpenProcess(0x0410, False, pid)

        if hProcess:
            buf = ctypes.create_unicode_buffer(1024)
            # 3. 获取进程全路径
            if psapi.GetModuleFileNameExW(hProcess, 0, buf, 1024):
                full_path = buf.value
                kernel32.CloseHandle(hProcess)
                # 返回文件名
                return os.path.basename(full_path)
            kernel32.CloseHandle(hProcess)
    except Exception as e:
        print(f"获取进程名失败: {e}")
        pass
    return ""



def close_all_user_windows(whitelist_files=None):
    """
    尝试关闭所有可见的用户窗口 (清场模式)
    但排除白名单中的应用
    """
    if platform.system() != 'Windows':
        return

    if whitelist_files is None:
        whitelist_files = []

    # 转小写用于比对
    whitelist_lower = [f.lower() for f in whitelist_files]
    print(f"正在执行清场，白名单进程: {whitelist_lower}")

    try:
        user32 = ctypes.windll.user32
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_long)

        def enum_callback(hwnd, lParam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value

                    # 1. 系统核心
                    if title == "Program Manager": return True
                    # 2. 摸鱼神器自己
                    if "摸鱼神器" in title or "TouchFish" in title: return True
                    # 3. 获取进程名并检查白名单
                    proc_name = get_process_filename(hwnd).lower()

                    if proc_name and proc_name in whitelist_lower:
                        print(f"保留白名单应用: {proc_name} ({title})")
                        return True

                    # 执行关闭
                    print(f"正在关闭窗口: [{proc_name}] {title}")
                    user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
            return True

        user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
    except Exception as e:
        print(f"关闭窗口出错: {e}")



def trigger_protection(action_type, safe_app_path, fallback_url, whitelist_apps=None):
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
    elif action_type == 'kill_all':
        # 传入白名单
        close_all_user_windows(whitelist_apps)

    # 3. 打开安全应用
    app_opened = False
    if safe_app_path and os.path.exists(safe_app_path):
        try:
            print(f"正在全屏启动应用: {safe_app_path}")
            cmd = f'start /max "" "{safe_app_path}"'
            subprocess.run(cmd, shell=True)

            app_opened = True
        except Exception as e:
            print(f"打开应用失败: {e}")
            # 如果 start /max 失败，尝试回退到普通启动
            try:
                os.startfile(safe_app_path)
                app_opened = True
            except:
                pass

    # 如果没配置应用或打开失败，打开网页
    if not app_opened:
        print(f"打开备用链接: {fallback_url}")
        # 对于网页，我们也可以尝试用 start /max 启动默认浏览器
        try:
            cmd = f'start /max "" "{fallback_url}"'
            subprocess.run(cmd, shell=True)
        except:
            webbrowser.open(fallback_url)