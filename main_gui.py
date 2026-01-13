import tkinter as tk
from tkinter import ttk, filedialog, messagebox, Toplevel
import threading
import time
import os
import sys
import cv2
from PIL import Image, ImageTk

from settings_manager import SettingsManager
from modules.actions import trigger_protection
from modules.vision import VisionMonitor
from modules.audio import AudioMonitor


# --- 资源路径查找 ---
def get_resource_path(relative_path):
    """
    智能查找资源路径
    """
    # 1. 本地开发环境 (IDE运行)
    if not getattr(sys, 'frozen', False):
        # 在 IDE 中，使用当前脚本 (__file__) 所在的目录作为基准
        base_path = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_path, relative_path)

    # 2. 打包发布环境 (EXE运行)
    base_dir = os.path.dirname(sys.executable) # exe 所在目录

    # 路径A: 在 exe 同级目录下找
    path_root = os.path.join(base_dir, relative_path)
    if os.path.exists(path_root):
        return path_root

    # 路径B: 在 _internal 目录下找
    path_internal = os.path.join(base_dir, '_internal', relative_path)
    if os.path.exists(path_internal):
        return path_internal

    # 如果都找不到，默认返回 exe 同级目录
    return path_root


class CameraSelectionDialog:
    def __init__(self, parent, current_index=0, on_confirm=None):
        self.top = Toplevel(parent)
        self.top.title("选择摄像头")
        self.top.geometry("600x500")
        self.top.transient(parent)
        self.top.grab_set()

        self.on_confirm = on_confirm
        self.current_cam_index = current_index
        self.cap = None
        self.is_previewing = False

        self._init_ui()
        self._start_preview(self.current_cam_index)
        self.top.protocol("WM_DELETE_WINDOW", self.on_close)

    def _init_ui(self):
        ctrl_frame = ttk.Frame(self.top, padding=10)
        ctrl_frame.pack(fill='x')
        ttk.Label(ctrl_frame, text="检测到的设备:").pack(side='left')

        self.available_cams = [i for i in range(4)]
        self.combo_cam = ttk.Combobox(ctrl_frame, values=self.available_cams, state="readonly", width=5)
        self.combo_cam.set(self.current_cam_index)
        self.combo_cam.pack(side='left', padx=5)
        self.combo_cam.bind("<<ComboboxSelected>>", self._on_cam_change)

        ttk.Label(ctrl_frame, text="(切换后请稍等画面加载)").pack(side='left', padx=5)
        self.video_label = ttk.Label(self.top, text="正在加载摄像头...", anchor="center")
        self.video_label.pack(fill='both', expand=True, padx=10, pady=5)

        btn_frame = ttk.Frame(self.top, padding=10)
        btn_frame.pack(fill='x', side='bottom')
        ttk.Button(btn_frame, text="取消", command=self.on_close).pack(side='right', padx=5)
        ttk.Button(btn_frame, text="确认使用此设备", command=self.confirm_selection).pack(side='right', padx=5)

    def _on_cam_change(self, event):
        new_idx = int(self.combo_cam.get())
        if new_idx != self.current_cam_index:
            self._stop_preview()
            self._start_preview(new_idx)

    def _start_preview(self, index):
        self.current_cam_index = index
        try:
            self.cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
            if not self.cap.isOpened():
                self.video_label.config(text=f"无法打开摄像头 {index}", image='')
                return
            self.is_previewing = True
            self._update_frame()
        except Exception as e:
            self.video_label.config(text=f"初始化错误: {e}", image='')

    def _stop_preview(self):
        self.is_previewing = False
        if self.cap and self.cap.isOpened():
            self.cap.release()
        self.cap = None

    def _update_frame(self):
        if not self.is_previewing or not self.cap:
            return
        ret, frame = self.cap.read()
        if ret:
            cv2image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(cv2image)
            img_tk = ImageTk.PhotoImage(image=img.resize((560, 380)))
            self.video_label.imgtk = img_tk
            self.video_label.config(image=img_tk, text="")
        else:
            self.video_label.config(text="无法获取画面帧", image='')
        if self.is_previewing:
            self.top.after(30, self._update_frame)

    def confirm_selection(self):
        if self.on_confirm:
            self.on_confirm(self.current_cam_index)
        self.on_close()

    def on_close(self):
        self._stop_preview()
        self.top.destroy()


class MonitorThread(threading.Thread):
    def __init__(self, settings, callback_trigger, callback_log, callback_finished):
        super().__init__()
        self.settings = settings
        self.callback_trigger = callback_trigger
        self.callback_log = callback_log
        self.callback_finished = callback_finished
        self.running = True
        self.paused = False

        self.stranger_counter = 0
        self.absence_counter = 0

    def run(self):
        try:
            self.callback_log("正在初始化 AI 引擎...")

            # --- 1. 初始化视觉 ---
            vision_mon = None
            try:
                cam_idx = int(self.settings.get('camera_index', 0))
                # 图片路径处理：优先检查绝对路径，其次检查资源路径
                raw_img_path = self.settings.get('user_image_path', "")

                # 找到用户设置的真实文件
                if raw_img_path:
                    if not os.path.exists(raw_img_path):
                        res_path = get_resource_path(raw_img_path)
                        if os.path.exists(res_path):
                            raw_img_path = res_path

                p_scale = float(self.settings.get('process_scale', 0.5))

                vision_mon = VisionMonitor(
                    user_image_path=raw_img_path,
                    tolerance=float(self.settings.get('tolerance', 0.6)),
                    camera_index=cam_idx,
                    process_scale=p_scale
                )
            except Exception as e:
                self.callback_log(f"视觉模块初始化异常: {e}")
                return

                # --- 2. 初始化音频 ---
            audio_mon = None
            try:
                model_path = get_resource_path("model")

                # 仅在打包环境 (frozen) 下尝试 Fallback 查找
                # 只有在打包成 exe 后，才有可能出现 _internal 这种结构
                if getattr(sys, 'frozen', False):
                    if not os.path.exists(model_path):
                        base = os.path.dirname(sys.executable)
                        fallback = os.path.join(base, '_internal', 'model')
                        if os.path.exists(fallback):
                            model_path = fallback

                self.callback_log(f"加载语音模型: {model_path}")

                audio_mon = AudioMonitor(
                    keywords_str=self.settings.get('voice_keywords', ""),
                    model_path=model_path
                )
            except Exception as e:
                self.callback_log(f"音频模块警告: {e}")
                self.callback_log("--> 提示: 请确认 'model' 文件夹存在于软件目录中。")

            # --- 3. 状态自检与启动 ---

            # 视觉状态检查
            vision_active = False
            if vision_mon.is_ready:
                self.callback_log(f"✔ 视觉监控就绪 (画质: {p_scale})")
                vision_active = True
            else:
                self.callback_log("❌ 视觉警告：未设置用户照片！")
                self.callback_log("--> 摄像头将【不会启动】。请先在'视觉识别'页浏览并选择您的照片。")

            # 音频状态检查
            audio_active = False
            if audio_mon:
                self.callback_log("✔ 语音监控：已就绪")
                audio_active = True

            if not vision_active and not audio_active:
                self.callback_log("⚠️ 警告：视觉和语音均未就绪，监控实际上在空转。")

            self.callback_log(">>> 监控循环已开始 <<<")

            while self.running:
                if self.paused:
                    time.sleep(1)
                    continue

                # --- 视觉检测 (仅当准备好时才执行) ---
                if vision_active and vision_mon:
                    # get_status 内部会尝试打开摄像头
                    status = vision_mon.get_status()

                    if status == 'stranger':
                        self.stranger_counter += 1
                        limit = int(self.settings.get('stranger_threshold', 3))
                        self.callback_log(f"检测到陌生人 ({self.stranger_counter}/{limit})")
                        if self.stranger_counter >= limit:
                            self.trigger("陌生人靠近")

                    elif status == 'absence':
                        self.absence_counter += 1
                        limit = int(self.settings.get('absence_threshold', 5))
                        self.callback_log(f"检测到离席 ({self.absence_counter}/{limit})")
                        if self.absence_counter >= limit:
                            self.trigger("用户离席")

                    elif status == 'safe':
                        self.stranger_counter = 0
                        self.absence_counter = 0

                # --- 音频检测 ---
                if audio_active and audio_mon and audio_mon.check_trigger():
                    self.trigger("语音关键词匹配")

                time.sleep(float(self.settings.get('sample_interval', 0.5)))

            # 清理
            if vision_mon: vision_mon.stop_camera()
            if audio_mon: audio_mon.stop()
            self.callback_log("监控已停止。")

        except Exception as e:
            self.callback_log(f"致命错误: {e}")
        finally:
            self.callback_finished()

    def trigger(self, reason):
        self.callback_log(f"!!! 触发保护: {reason} !!!")
        self.paused = True
        self.callback_trigger()
        self.callback_log("进入冷却模式 (10s)...")
        time.sleep(10)
        self.stranger_counter = 0
        self.absence_counter = 0
        self.paused = False
        self.callback_log("恢复监控。")

    def stop(self):
        self.running = False


class MainWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("摸鱼神器 - 离线版")
        self.root.geometry("850x900")

        # 加载图标
        try:
            icon_path = get_resource_path("logo.ico")
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except:
            pass

        self.manager = SettingsManager()
        self.settings = self.manager.settings
        self.monitor_thread = None
        self._setup_ui()

    def _setup_ui(self):
        style = ttk.Style()
        style.configure('TGroupBox', font=('Arial', 10, 'bold'))

        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.pack(fill='x')
        self.btn_toggle = ttk.Button(top_frame, text="启动监控", command=self.toggle_monitoring)
        self.btn_toggle.pack(side='left', fill='x', expand=True, padx=5)
        self.lbl_status = ttk.Label(top_frame, text="状态: 待机", foreground="gray")
        self.lbl_status.pack(side='right', padx=10)

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=10, pady=5)

        # Tab 1
        tab_action = ttk.Frame(notebook, padding=10)
        notebook.add(tab_action, text="触发动作")
        self._build_file_picker(tab_action, "安全应用 (伪装):", "safe_app_path", 0, "老板来时自动弹出的软件")
        self._build_entry(tab_action, "备用网址:", "fallback_url", 1, "找不到应用时打开的网页")
        ttk.Label(tab_action, text="窗口处理:").grid(row=4, column=0, sticky='w', pady=10)
        self.var_action_type = tk.StringVar(value=self.settings.get('action_type', 'minimize'))
        frame_radio = ttk.Frame(tab_action)
        frame_radio.grid(row=4, column=1, sticky='w')
        ttk.Radiobutton(frame_radio, text="最小化所有 (Win+D)", variable=self.var_action_type, value="minimize").pack(
            side='left')
        ttk.Radiobutton(frame_radio, text="关闭当前 (Alt+F4)", variable=self.var_action_type, value="close").pack(
            side='left')
        ttk.Label(tab_action, text="* 触发时将强制静音", foreground="red").grid(row=5, column=1, sticky='w')

        # Tab 2
        tab_vision = ttk.Frame(notebook, padding=10)
        notebook.add(tab_vision, text="视觉识别")

        # 文件选择器加过滤器
        self._build_file_picker(tab_vision, "我的照片:", "user_image_path", 0, "用于核验本人 (必须设置！)",
                                file_filter="image")

        ttk.Label(tab_vision, text="摄像头设备:").grid(row=3, column=0, sticky='nw', pady=(10, 0))
        cam_frame = ttk.Frame(tab_vision)
        cam_frame.grid(row=3, column=1, sticky='w', pady=(10, 0))
        self.var_camera_index = tk.IntVar(value=int(self.settings.get('camera_index', 0)))
        self.ent_camera_index = ttk.Entry(cam_frame, textvariable=self.var_camera_index, width=5, state='readonly')
        self.ent_camera_index.pack(side='left')
        ttk.Button(cam_frame, text="测试/选择摄像头", command=self.open_camera_picker).pack(side='left', padx=5)

        self._build_slider(tab_vision, "检测画质(缩放):", "process_scale", 4, 0.25, 1.0,
                           "越高越清晰但CPU占用越高，默认0.5", is_int=False)

        self._build_slider(tab_vision, "人脸容差:", "tolerance", 5, 0.3, 0.8, "越低越严格，默认0.6", is_int=False)
        self._build_slider(tab_vision, "陌生人触发阈值:", "stranger_threshold", 6, 1, 10, "连续检测帧数，默认1", is_int=True)
        self._build_slider(tab_vision, "离席触发阈值:", "absence_threshold", 7, 1, 20, "连续检测帧数，默认10", is_int=True)

        # Tab 3
        tab_audio = ttk.Frame(notebook, padding=10)
        notebook.add(tab_audio, text="语音监听")
        self._build_entry(tab_audio, "触发关键词:", "voice_keywords", 0, "英文逗号分隔，如: 老板,来了")
        ttk.Label(tab_audio, text="提示: 模型需位于 exe 同级或 _internal 文件夹中。", foreground="gray").grid(row=2,
                                                                                                             column=1,
                                                                                                             sticky='w',
                                                                                                             pady=10)

        log_frame = ttk.LabelFrame(self.root, text="运行日志", padding=10)
        log_frame.pack(fill='both', expand=True, padx=10, pady=10)
        self.log_text = tk.Text(log_frame, height=8, state='disabled', font=("Consolas", 9))
        self.log_text.pack(fill='both', expand=True)

        ttk.Button(self.root, text="保存配置", command=self.save_all).pack(side='bottom', pady=10)

    def open_camera_picker(self):
        if self.monitor_thread and self.monitor_thread.is_alive():
            messagebox.showwarning("提示", "请先停止监控，然后再测试摄像头。")
            return

        def on_selected(index):
            self.var_camera_index.set(index)
            self.log(f"已选择摄像头 ID: {index}")

        CameraSelectionDialog(self.root, self.var_camera_index.get(), on_selected)

    def _build_file_picker(self, parent, label, key, row, tooltip, file_filter="all"):
        ttk.Label(parent, text=label).grid(row=row * 3, column=0, sticky='nw', pady=(10, 0))
        entry = ttk.Entry(parent, width=40)
        entry.insert(0, str(self.settings.get(key, "")))
        entry.grid(row=row * 3, column=1, sticky='w', pady=(10, 0))

        def browse():
            if file_filter == "image":
                path = filedialog.askopenfilename(title="选择图片",
                                                  filetypes=[("图片", "*.jpg *.png *.jpeg"), ("所有", "*.*")])
            elif file_filter == "exe":
                path = filedialog.askopenfilename(title="选择程序", filetypes=[("程序", "*.exe"), ("所有", "*.*")])
            else:
                path = filedialog.askopenfilename() if 'path' in key else filedialog.askdirectory()

            if path:
                entry.delete(0, tk.END)
                entry.insert(0, path)

        ttk.Button(parent, text="浏览...", command=browse).grid(row=row * 3, column=2, padx=5, pady=(10, 0))
        ttk.Label(parent, text=tooltip, foreground="#666").grid(row=row * 3 + 1, column=1, sticky='w')
        setattr(self, f"ent_{key}", entry)

    def _build_entry(self, parent, label, key, row, tooltip):
        ttk.Label(parent, text=label).grid(row=row * 3, column=0, sticky='nw', pady=(10, 0))
        entry = ttk.Entry(parent, width=40)
        entry.insert(0, str(self.settings.get(key, "")))
        entry.grid(row=row * 3, column=1, sticky='w', pady=(10, 0))
        ttk.Label(parent, text=tooltip, foreground="#666").grid(row=row * 3 + 1, column=1, sticky='w')
        setattr(self, f"ent_{key}", entry)

    def _build_slider(self, parent, label, key, row, min_v, max_v, tooltip, is_int=False):
        ttk.Label(parent, text=label).grid(row=row * 3, column=0, sticky='nw', pady=(10, 0))
        curr_val = self.settings.get(key, min_v)
        var = tk.DoubleVar(value=curr_val)
        val_lbl = ttk.Label(parent, text=str(curr_val), width=5)

        def on_scroll(v):
            val = float(v)
            display_text = f"{int(val)}" if is_int else f"{val:.2f}"
            val_lbl.config(text=display_text)

        scale = ttk.Scale(parent, from_=min_v, to=max_v, variable=var, command=on_scroll)
        scale.grid(row=row * 3, column=1, sticky='ew', pady=(10, 0))
        val_lbl.grid(row=row * 3, column=2, padx=5, pady=(10, 0))
        ttk.Label(parent, text=tooltip, foreground="#666").grid(row=row * 3 + 1, column=1, sticky='w')
        setattr(self, f"var_{key}", var)

    def log(self, msg):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

    def save_all(self):
        new_conf = {
            "safe_app_path": self.ent_safe_app_path.get(),
            "fallback_url": self.ent_fallback_url.get(),
            "action_type": self.var_action_type.get(),
            "user_image_path": self.ent_user_image_path.get(),
            "voice_keywords": self.ent_voice_keywords.get(),
            "camera_index": self.var_camera_index.get(),
            "process_scale": round(self.var_process_scale.get(), 2),
            "tolerance": round(self.var_tolerance.get(), 2),
            "stranger_threshold": int(self.var_stranger_threshold.get()),
            "absence_threshold": int(self.var_absence_threshold.get()),
            "voice_energy_threshold": 300
        }
        if self.manager.save_settings(new_conf):
            self.settings = new_conf
            messagebox.showinfo("成功", "配置已保存")

    def toggle_monitoring(self):
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.stop()
            self.btn_toggle.config(state='disabled', text="正在停止...")
        else:
            self.save_all()
            self.monitor_thread = MonitorThread(
                self.settings,
                self.execute_protection,
                self.handle_log_from_thread,
                self.on_thread_finished
            )
            self.monitor_thread.start()
            self.btn_toggle.config(text="停止监控")
            self.lbl_status.config(text="状态: 运行中", foreground="green")

    def on_thread_finished(self):
        self.root.after(0, self._reset_ui_state)

    def _reset_ui_state(self):
        self.btn_toggle.config(state='normal', text="启动监控")
        self.lbl_status.config(text="状态: 已停止", foreground="red")

    def handle_log_from_thread(self, msg):
        self.root.after(0, lambda: self.log(msg))

    def execute_protection(self):
        self.root.after(0, lambda: trigger_protection(
            self.settings.get('action_type', 'minimize'),
            self.settings.get('safe_app_path'),
            self.settings.get('fallback_url')
        ))


if __name__ == "__main__":
    root = tk.Tk()
    app = MainWindow(root)
    root.mainloop()