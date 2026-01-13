import os
import queue
import json
import threading
import pyaudio
from vosk import Model, KaldiRecognizer


class AudioMonitor:
    def __init__(self, keywords_str, model_path="model", energy_threshold=None):
        """
        初始化音频监控 (本地离线版)
        :param keywords_str: 英文逗号分隔的关键词字符串
        :param model_path: 本地模型路径
        """
        # 处理关键词
        self.keywords = [k.strip().lower() for k in keywords_str.split(',') if k.strip()]

        # 线程控制
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        self.triggered_keyword = None

        print(f"[Audio] 正在初始化，模型路径: {model_path}")
        # 检查模型路径
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"找不到模型根目录: {model_path}")

        # 检查关键子目录是否存在
        # Vosk/Kaldi 标准结构通常包含: conf, graph, am 和 ivector
        # 只要 final.mdl 不在正确的位置，底层 C++ 就会报错
        required_subdirs = ['conf', 'graph', 'am', 'ivector']
        missing = [d for d in required_subdirs if not os.path.exists(os.path.join(model_path, d))]

        if missing:
            print(f"[Audio Error] 模型文件夹结构不完整！缺少子目录: {missing}")
            print(f"当前目录内容: {os.listdir(model_path)}")
            raise ValueError(f"模型损坏，缺少 {missing}")

        # 检查 am/final.mdl 是否存在
        am_path = os.path.join(model_path, 'am', 'final.mdl')
        if not os.path.exists(am_path) and not os.path.exists(os.path.join(model_path, 'final.mdl')):
            print("[Audio Warning] 警告：未检测到 final.mdl 文件，模型加载可能会失败。")


        # 1. 初始化 Vosk 模型
        print(f"正在加载本地语音模型: {model_path} ...")
        try:
            # Vosk 会自动在 model_path 下寻找 final.mdl 等文件
            self.model = Model(model_path)
            print("[Audio] Vosk 模型加载成功！")
        except Exception as e:
            print(f"[Audio Critical] 模型加载崩溃。原因可能是文件结构被破坏。")
            print(f"模型加载失败: {e}")
            print("提示: 请确保 'model' 文件夹内直接包含 'conf', 'graph', 'am' 和 'ivector' 等文件夹")
            raise e

        # 2. 初始化识别器
        # 16000 是采样率，Vosk 模型需要 16k
        self.recognizer = KaldiRecognizer(self.model, 16000)

        # 3. 初始化 PyAudio
        self.p = pyaudio.PyAudio()
        self.stream = None

        print(f"音频引擎初始化完毕。监听关键词: {self.keywords}")

        # 启动监听线程
        self.start_listening()

    def start_listening(self):
        """启动后台监听线程"""
        if self.running:
            return

        self.running = True
        self.stream = self.p.open(format=pyaudio.paInt16,
                                  channels=1,
                                  rate=16000,
                                  input=True,
                                  frames_per_buffer=4000)
        self.stream.start_stream()

        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()

    def _listen_loop(self):
        """后台循环：持续读取音频流并识别"""
        print("语音监听线程已启动...")
        while self.running:
            try:
                # 读取音频数据
                data = self.stream.read(4000, exception_on_overflow=False)
                if len(data) == 0:
                    continue

                # 识别处理
                if self.recognizer.AcceptWaveform(data):
                    # 获取完整句子结果
                    result_json = json.loads(self.recognizer.Result())
                    text = result_json.get('text', '')
                else:
                    # 获取实时部分结果 (Partial) - 反应更快
                    result_json = json.loads(self.recognizer.PartialResult())
                    text = result_json.get('partial', '')

                if text:
                    # 检查是否包含关键词
                    for kw in self.keywords:
                        if kw in text:
                            print(f"【语音触发】检测到关键词: {kw}")
                            with self.lock:
                                self.triggered_keyword = kw
                            # 识别到后重置识别器，防止重复触发
                            self.recognizer.Reset()

            except Exception as e:
                print(f"监听循环出错: {e}")

    def check_trigger(self):
        """
        主程序调用的接口
        查询自上次检查以来是否有关键词被触发
        :return: True/False
        """
        with self.lock:
            if self.triggered_keyword:
                print(f"主程序获取到触发信号: {self.triggered_keyword}")
                self.triggered_keyword = None  # 消费掉这个信号
                return True
            return False

    def stop(self):
        """停止资源"""
        self.running = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        self.p.terminate()