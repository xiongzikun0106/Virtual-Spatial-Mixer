# Virtual Spatial Mixer

3D 空间混音原型工具 —— 通过在三维空间中移动音轨球体来直觉式控制混音参数。

## 功能

- **3D 空间声场映射**: 球体距原点距离控制音量衰减和低通滤波, x 轴位置映射为声像
- **双模式轨迹**: 实时录制球体运动轨迹, 或手动编辑关键帧 + 样条插值自动飞行
- **冲突避让**: 球体距离过近时自动对次要音轨进行增益抑制
- **时间轴编辑**: 波形概览、关键帧拖拽、播放指针同步
- **离线导出**: 渲染混音结果为 WAV 文件

## 安装

```bash
pip install -r requirements.txt
```

## 运行

```bash
python main.py
```

## 使用流程

1. 拖入 WAV 文件（或点击 Import WAV）
2. 在 3D 视图中拖拽球体到期望位置
3. 点击 Record + Play, 播放期间拖动球体录制运动轨迹
4. 停止后在时间轴上双击添加/微调关键帧
5. 播放预览空间效果
6. 点击 Export Mix 导出混音文件

## 技术栈

- Python 3.10+
- PyQt6 (UI)
- pyqtgraph (3D 渲染)
- sounddevice (音频播放)
- numpy / scipy (DSP)
- soundfile (音频文件 I/O)
