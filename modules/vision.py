import face_recognition
import cv2
import numpy as np
import os


class VisionMonitor:
    def __init__(self, user_image_path, tolerance=0.6, camera_index=0, process_scale=0.5):
        """
        初始化视觉监控模块
        :param user_image_path: 用户照片路径
        :param tolerance: 识别容差 (0.1-1.0)，越低越严格
        :param camera_index: 摄像头索引
        :param process_scale: 图片缩放比例 (0.25-1.0)，越高越清晰越慢
        """
        self.tolerance = float(tolerance)
        self.process_scale = float(process_scale)

        try:
            self.camera_index = int(camera_index)
        except:
            self.camera_index = 0

        self.known_face_encodings = []
        self.is_ready = False

        # 加载用户画像
        self.load_user_profile(user_image_path)

        # 初始化摄像头
        self.video_capture = None

    def load_user_profile(self, path):
        """加载并编码用户人脸"""
        if not os.path.exists(path):
            print(f"错误: 找不到用户照片 {path}")
            return

        try:
            print("正在加载用户人脸特征...")
            user_image = face_recognition.load_image_file(path)
            encodings = face_recognition.face_encodings(user_image)

            if len(encodings) > 0:
                self.known_face_encodings = [encodings[0]]
                self.is_ready = True
                print("用户人脸特征加载成功。")
            else:
                print("错误: 照片中未检测到人脸，请更换清晰的正脸照片。")
        except Exception as e:
            print(f"人脸处理异常: {e}")

    def start_camera(self):
        if self.video_capture is None or not self.video_capture.isOpened():
            self.video_capture = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)

    def stop_camera(self):
        if self.video_capture and self.video_capture.isOpened():
            self.video_capture.release()
            self.video_capture = None

    def get_status(self):
        """
        检测当前帧状态
        返回: 'safe' (本人在), 'stranger' (陌生人在), 'absence' (没人), 'error' (摄像头错误)
        """
        if not self.is_ready:
            return 'error'

        if self.video_capture is None or not self.video_capture.isOpened():
            self.start_camera()

        ret, frame = self.video_capture.read()
        if not ret:
            print("无法读取摄像头画面")
            return 'error'

        # --- 使用动态配置的缩放比例 ---
        # 为 1.0，表示保持原图大小（最清晰，但计算最慢）
        scale = self.process_scale
        small_frame = cv2.resize(frame, (0, 0), fx=scale, fy=scale)

        # BGR 转 RGB
        rgb_small_frame = small_frame[:, :, ::-1]

        # 检测人脸位置和特征
        face_locations = face_recognition.face_locations(rgb_small_frame)
        face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

        # 1. 没人 -> 离席
        if len(face_locations) == 0:
            return 'absence'

        # 2. 多人 -> 陌生人
        if len(face_locations) > 1:
            # 即使其中有一张脸是你，只要旁边还有人，环境就不安全
            return 'stranger'

        # 3. 单人 -> 鉴权
        # 取出唯一的那张脸特征
        face_encoding = face_encodings[0]

        # 比对
        matches = face_recognition.compare_faces(self.known_face_encodings, face_encoding, tolerance=self.tolerance)

        if True in matches:
            return 'safe'  # 是本人，且只有一人
        else:
            return 'stranger'  # 有一张脸，但不是你

    def __del__(self):
        self.stop_camera()