# PhoneAudioSink —— 把 Android 手机当作电脑的 WiFi 无线音箱

把 **Windows 电脑的声音** 通过 **局域网 WiFi** 推送到 **Android 手机** 播放，
手机相当于电脑的一台无线外接音箱（单向：电脑 → 手机）。

- PC 端：Python 图形界面（Windows UI 3 风格）+ 系统托盘，抓取系统声音 → **Opus 编码** → TCP 发送
- 手机端：Android App，底部四页（播放 / 音效 / 设置 / 关于），UDP 自动发现或直接连 IP → TCP 收流 → Opus 解码 → 播放
- 连接两个方向都支持：**手机连电脑**（扫描发现，默认）或 **电脑直连手机**（PC 窗口里手输 IP）
- 音效：App 内自带 **7 段 EQ + 场景预设 + 虚拟低音 + 低频增强 + 增益**（短窗 IIR，总延迟 <10ms）
- 传输：局域网 **TCP**，**UDP 广播自动发现**，**心跳保活 + 读超时**防僵死链接
- 音频：48kHz / 立体声 / Opus，默认 **10ms 帧**，64 kbps
- 语言：**中英双语**。安装器默认跟随系统语言（也可在安装向导里手动选），
  PC 窗口在「设置 → 界面语言」切换、手机 App 在「设置 → 语言」切换，改完立即生效

---

## 一、先读：能力边界与关键概念

### 1. 声音列表里出现的是「虚拟声卡」，不是手机

Windows 声音设置里的输出设备，是**音频驱动注册出来的系统端点**；手机 App 是普通应用，
无法把自己注册成 Windows 音频端点，WiFi 协议层面也没有把网络音箱挂进声音列表的标准接口。

所有同类软件（含商业 AudioRelay）的通用链路是：

```
系统声音 → 【虚拟声卡播放端】← 出现在 Windows 声音列表里的是它
              │（虚拟线缆）
              └→ 虚拟声卡录制端 → PC 转发程序采集 → WiFi(TCP) → 手机 App 播放
```

- 你机器上已装有 **Virtual Audio Cable** 和 **VoiceMeeter**，这一环已具备。
- 想让列表里直接显示"手机"二字，只有 USB 声卡（UAC）或蓝牙 A2DP Sink 两条路，
  且多数安卓不开放；WiFi 方案做不到。

### 2. 其他限制

- **延迟**：采集 + Opus 编解码 + 网络 + 手机缓冲，端到端通常数十到上百毫秒；
  看视频/听音乐可用，不适合游戏听声辨位、口播对轨。
- **同一局域网**：手机和电脑需连同一 WiFi（或同一热点/USB 网络共享）。
- **防火墙**：首次运行需允许 PC 程序访问专用网络，否则手机发现不到、连不上。

---

## 二、目录结构

```
new-chat-1/
├── pc/                          # PC 端（Windows 发送服务，Python 3.10+）
│   ├── protocol.py              # 二进制帧协议 + UDP 发现协议（与手机端一致）
│   ├── opus_encoder.py           # Opus 编码封装
│   ├── net_link.py              # TCP 音频服务端 + UDP 发现响应
│   ├── audio_capture.py          # 系统音频采集（loopback / 立体声混音 / 虚拟声卡）
│   ├── app_core.py              # 共享状态 + 后台采集/发送 Worker（listen / connect 双模式）
│   ├── desktop.py               # PC 图形界面主入口（WinUI3 窗口 + 托盘，打包 exe 入口）
│   ├── tray_app.py               # 旧版纯托盘入口（pystray，保留备用）
│   ├── sender.py                 # 命令行入口（无界面，调试用）
│   ├── assets/app.ico            # 应用/托盘图标
│   ├── config.example.json       # 配置模板
│   ├── config.json               # 实际配置（首次运行自动生成）
│   └── requirements.txt
│
└── android/PhoneAudioSink/       # Android 接收播放 App（Kotlin）
    ├── settings.gradle           # 仓库（阿里云 + JitPack）
    ├── build.gradle
    └── app/
        ├── build.gradle          # jopus 依赖
        └── src/main/
            ├── AndroidManifest.xml
            ├── java/com/example/phoneaudiosink/
            │   ├── App.kt             # Application：初始化设置 + 主题
            │   ├── MainActivity.kt    # 底部 tab 容器（播放/音效/设置/关于）
            │   ├── PlayFragment.kt    # 连接状态、扫描、手输 IP、等待电脑直连
            │   ├── EffectsFragment.kt # 场景预设、7 段 EQ、虚拟低音、低频增强、增益
            │   ├── SettingsFragment.kt# 缓冲档位、自动重连、心跳、主题
            │   ├── AudioHub.kt        # 单例：player + client，状态广播与自动重连
            │   ├── NetClient.kt       # UDP 扫描 + TCP 收流（客户端/服务端双模式）
            │   ├── AudioEffects.kt    # DSP：biquad EQ + low shelf + 谐波低音 + 软限幅
            │   ├── EqView.kt          # 可拖动 7 段图示 EQ
            │   ├── AudioSinkPlayer.kt # 有界播放队列 + 音效链
            │   ├── OpusDecoder.kt     # JOpus 解码封装
            │   ├── Settings.kt        # EffectSettings / AppSettings 持久化
            │   └── Protocol.kt        # 帧解析（与 PC 端一致）
            └── res/                   # VectorDrawable 图标 + 深浅两套配色
```

---

## 三、快速开始

### 1. 配置音频采集来源（虚拟声卡）

要把系统声音送到手机，先决定声音从哪里被 PC 程序抓到，三选一：

1. **虚拟声卡（推荐，最稳，本机已有 VBCable）**
   - Windows 声音设置 → 输出设备选 `Line 1 (Virtual Audio Cable)`（CABLE Input）；
   - PC 程序从它的录制端 `CABLE Output` 采集（在 `config.json` 的 `input_device` 填
     设备名关键字，如 `Virtual Audio Cable`）。
   - 这样声音只进手机、不从本机扬声器放出；想本机也听到，可用 VoiceMeeter 混音。
2. **立体声混音（Stereo Mix）**：声卡驱动提供时，在 `--list-devices` 里找
   "立体声混音 / Stereo Mix / What U Hear" 填入 `input_device`。
3. **默认输入**：留空 `input_device`，抓到的是默认麦克风（不是系统声音）。

### 2. 安装手机 App

从 [Releases](https://github.com/Bobo0925-a/PhoneAudioSink/releases) 下载
`PhoneAudioSink-android.apk`（Android 7.0+，release 签名包），
传到手机安装，允许「安装未知来源应用」。

界面语言默认跟随系统，可在 App 内「设置 → 语言」选择 **跟随系统 / 简体中文 / English**，
点选后界面即时重建为对应语言。

### 3. 启动 PC 端（二选一）

#### 方式 A：安装包图形界面版（推荐，免装 Python）

从 [Releases](https://github.com/Bobo0925-a/PhoneAudioSink/releases) 下载
`PhoneAudioSink-windows-setup-v1.0.0.exe`，按当前用户安装（不需要管理员权限），
开始菜单或桌面快捷方式启动；弹出无边框大圆角主窗口，同时常驻系统托盘。
首次启动若弹出 Windows 防火墙提示，**勾选专用网络并允许访问**。

- 主窗口：左侧汉堡侧边栏切换「连接 / 音量 / 采集设备 / 日志 / 设置」，侧边栏底部常驻音量滑块。
- 连接页：显示状态、本机 IP、对端地址、已发送帧数；可切换「等待手机连入」与「直连手机」
  （直连时在输入框填手机 IP，点开始）。
- 托盘：左键单击恢复窗口；右键菜单含「显示主窗口 / 推送音量 / 开始或停止连接 / 退出」。
- 点窗口右上角关闭只会**隐藏到托盘**，推流不中断；要真正退出请用托盘菜单「退出」。
- `config.json`、`phone_audio.log` 自动生成在 **exe 同目录**。

#### 方式 B：从源码运行

```powershell
cd pc
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

查看可选采集设备：

```powershell
python sender.py --list-devices
```

托盘 GUI 入口（等价于 exe）：

```powershell
python desktop.py
```

旧版纯托盘入口（pystray 版，保留备用）：

```powershell
python tray_app.py
```

无界面命令行入口（调试用）：

```powershell
python sender.py --config config.json
```

按需要编辑 `config.json`（一般只需改 `input_device`）。

### 4. 手机连接（两种方向，任选其一）

**方向一：手机连电脑（默认，最省事）**

1. PC 端保持「等待手机连入」；
2. 手机 App 播放页点「扫描电脑」，列表里选中你的电脑，自动连接播放；
3. 扫不到就手动输入电脑 IP（PC 窗口与手机播放页都会显示本机 IP）。

**方向二：电脑直连手机**

1. 手机 App 播放页切换到「等待电脑连接」，此时手机监听 42101 端口；
2. PC 窗口连接页切到「直连手机」，填手机 IP 后点「开始」；
3. 连上后结束会话会自动回到等待，可反复接入。

> 手机处于「等待电脑连接」时，扫描/手动连接区域会隐藏，避免两种方向互相打架。

---

## 四、网络与端口

| 端口 | 协议 | 用途 |
| --- | --- | --- |
| 42100 | UDP | 局域网自动发现：手机广播请求，PC 回复名称与 TCP 端口 |
| 42101 | TCP | 音频流：手机连入后接收 Opus 帧 |

- 手机与电脑须在同一局域网；PC 防火墙需放行这两个端口（或放行 `python.exe`）。
- 若扫描不到：确认 PC 程序已启动、网络配置为「专用网络」、两台设备同网段。

### 配置项 `config.json`

| 字段 | 说明 |
| --- | --- |
| `tcp_port` | 音频 TCP 端口，默认 `42101` |
| `discover_port` | UDP 发现端口，默认 `42100` |
| `sample_rate` | 采样率，`48000` |
| `channels` | `2` = 立体声，`1` = 单声道 |
| `codec` | `1` = Opus |
| `frame_size` | 每帧样本数/声道，`480`（48kHz × 10ms）；改回 `960` 即 20ms 帧 |
| `bitrate` | Opus 码率 bps，默认 `64000` |
| `input_device` | 采集设备名关键字或索引；留空用默认输入 |
| `ping_interval_sec` | 保活间隔（秒），默认 `1.5` |
| `volume` | PC 推流增益，`1.0` = 原音量，最大 `1.5`（界面滑块 0–150%） |
| `show_window_on_start` | 启动时是否显示主窗口，`false` 则只驻留托盘 |

---

## 五、通信协议（两端必须一致）

### 二进制音频帧（TCP，大端）

```
偏移  长度  字段
0     2     魔数 0xAA 0x55
2     1     版本 = 2
3     1     类型 type
4     2     负载长度 N (uint16 BE)
6     N     payload
```

| type | 含义 | payload |
| --- | --- | --- |
| `0x01` HELLO | 建链后 PC 发一次，协商格式 | `u16 sample_rate, u8 channels, u8 codec, u16 frame_size, u32 bitrate` |
| `0x02` AUDIO | Opus 包 | 单帧 Opus 数据 |
| `0x03` PING | 保活 | 无 |
| `0x04` PONG | 保活应答 | 无 |
| `0x05` BYE | 断开 | 无 |

### UDP 发现协议（文本）

- 手机 → 广播 `255.255.255.255:42100`：`PHONE_AUDIO_DISCOVER`
- PC 回复：`PHONE_AUDIO_SERVER|<电脑名>|<tcp_port>`

---

## 六、调优与排障

**扫描不到电脑**
- PC 程序已启动；防火墙放行 `python.exe` / 42100(UDP)、42101(TCP)；网络为专用网络。
- 手机与电脑连同一 WiFi；路由器未隔离客户端（AP 隔离）。

**延迟（低延迟档：目标水位调度）**

2026-11 这一版把播放缓冲从「硬上限」改成「目标水位」，延迟不再随档位时长整体堆积：

- PC：TCP 连接开启 `TCP_NODELAY`，关闭 Nagle 攒包；采集流 `latency='low'`（实测设备
  缓冲约 20ms）；默认 **10ms 帧（480 样本）**，采集队列上限 3 块（≈30ms），积压即丢旧块保实时
  （`audio_capture.py` 的 `max_queue`）。
- Opus：10ms 帧算法预读约 5ms，单帧编码实测 0.2ms（预算 10ms，开销可忽略）。
- 手机：解码后进入播放队列，**稳态只维持「目标水位」那么多块**——
  低于水位就等补货再取（开播预填 + 运行回填），高出「目标 + 抖动余量」才一次追平到目标；
  `AudioTrack` 引擎缓冲用 `setBufferSizeInFrames()` 压到 2 块，播放线程提
  `THREAD_PRIORITY_URGENT_AUDIO`。
- 预期端到端约 **75–90ms**（局域网、5GHz WiFi，60 档）；物理上 WiFi + 编解码 + 安卓输出
  很难稳定低于 40–60ms。
- **实际更慢时先查采集源**：虚拟声卡（如 VAC）自身有内部缓冲，把它的 Max MS / 缓冲调小，
  往往比改本 App 更立竿见影。

**几秒级严重积压（延迟 7–8 秒且不回落）**

这类问题不是缓冲调大调小造成的，而是数据在 TCP 内核缓冲 / 喇叭缓冲里**持续堆积、
排空后不追平**：某次播放跟不上后，积压的旧数据被逐帧播完，延迟就卡在几秒。本版治理：

- 手机播放队列有目标水位，**明显超出才丢弃最旧块追平实时**，不再把几秒旧数据播完；
  界面「缓冲: xx ms」实时显示队列深度，括号内为累计追平丢弃的块数。
- PC 端 TCP 发送缓冲限 8KB（`SO_SNDBUF`），限制发送侧内核积压。
- 判读缓冲深度：
  - 缓冲**持续走高、丢块不断增加** → 手机播放/解码跟不上（性能、采样率不匹配、系统音效）；
  - 缓冲**突发冲高后被丢弃追平** → 网络抖动/批量到达，属链路问题。

**环境排查（几秒积压先查这些）**

- 手机与电脑连 **5GHz WiFi**、近距离、同一 AP；避开 2.4G 拥塞；关闭路由器 AP 隔离。
- 手机关闭 **WiFi 省电 / 息屏断流**，App 保持前台；别在后台被系统杀掉。
- Windows 声音设置里**关闭系统级音频增强、空间音效、响度均衡、Bass Boost**（这类音效常自带
  几百毫秒甚至更大缓冲）。想要音效就用**本 App 的音效页**，DSP 在解码后做，不引入额外缓冲。
- 确认采集来源是虚拟声卡 / 立体声混音，**不是麦克风**。

**两档回调**

- 出现偶发爆音/卡顿（抗抖优先）：手机缓冲档位往上调一档（60 → 120 → 250 → 400），
  目标水位随之抬高；PC 端队列 `max_queue` 调回 6 也可多扛一点抖动。
- 已落地：Opus 帧长默认 10ms（480 样本）。想回到更抗抖的 20ms 帧，把两端
  `frame_size` 改回 960 即可（HELLO 里带帧长，手机端自动适配，不用重编译 App）。

**连上但无声 / 卡顿**
- 确认 HELLO 协商成功（App 界面显示格式）；检查媒体音量。
- 卡顿/爆音：`bitrate` 适当下调，或 `channels` 改 `1`；爆音严重时把手机端播放缓冲
  调大（`AudioSinkPlayer` 中 `bufferSize` 由 `minBuf` 改为 `minBuf * 2`/`*3`，
  代价是延迟上升）。
- 采集来源是否选对（别选成麦克风）。

**PC 本地也想听到声音**
- 用 VoiceMeeter 把虚拟声卡输入同时分到物理扬声器；或采集来源改用 loopback。

---

## 七、打包 PC 端 exe

```powershell
cd pc
pip install pyinstaller
python -m PyInstaller --noconfirm --clean PhoneAudioSink.spec
# 产物：pc\dist\PhoneAudioSink.exe
```

要点（已固化在 `PhoneAudioSink.spec`）：

- 入口是 `desktop.py`（PyQt5 图形界面），`console=False` 不弹控制台黑窗。
- `collect_all('opuslib_next')` 带入内置 `opus.dll`；`collect_all('_sounddevice_data')`
  带入 PortAudio 各位数 DLL；`collect_all('sounddevice')` 带入 Python 封装。
- `hiddenimports` 显式带 `PyQt5.QtSvg`（窗口图标用 SVG 渲染）与 `cffi` / `_cffi_backend`。
- 本机未开启 Windows 长路径时 **PySide6 装不上**（`qrc_qmake_*.cpp.obj` 路径过长），
  因此界面固定用 PyQt5，不要改回 PySide6。
- 配置 `config.json` 与日志 `phone_audio.log` 不打进包，运行时在 exe 同目录生成。

### 打包 Windows 安装程序

上面的 PyInstaller 产物是单文件便携版；发布用的安装器由 Inno Setup 6 再封装一层：

```powershell
# 先按上一步把 PhoneAudioSink.exe 放到仓库根目录
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installers\phoneaudiosink.iss
# 产物：installers\Output\PhoneAudioSink-setup-v1.0.0.exe
```

安装器按当前用户装到 `%LOCALAPPDATA%\Programs\PhoneAudioSink`，带开始菜单快捷方式、
可选桌面图标与卸载项，不需要管理员权限。

安装向导内置 **简体中文 / English** 两套语言：`ShowLanguageDialog=auto` 按系统语言自动预选，
也可在向导首页手动改。中文包用 Inno 官方仓库之外的社区翻译文件
`installers\ChineseSimplified.isl`（**必须保持 UTF-8 with BOM**，否则 Inno 不识别语言名）。
静默安装可指定：`PhoneAudioSink-setup.exe /VERYSILENT /LANG=chinesesimplified`。

---

## 八、本机开发环境记录（已装好）

| 组件 | 版本 | 路径 / 说明 |
| --- | --- | --- |
| JDK (Microsoft OpenJDK) | 17.0.21 LTS | `C:\Program Files\Microsoft\jdk-17.0.21.102-hotspot`，`JAVA_HOME` 已入用户环境变量 |
| Android SDK | — | `%LOCALAPPDATA%\Android\Sdk`，`ANDROID_HOME` / `ANDROID_SDK_ROOT` 已入用户环境变量 |
| platform-tools | 37.0.3 | 含 `adb.exe` |
| platforms | android-34 | `Sdk\platforms\android-34` |
| build-tools | 34.0.0 | `Sdk\build-tools\34.0.0` |
| Gradle | 8.9 | `%LOCALAPPDATA%\Programs\Gradle\gradle-8.9` |
| PC Opus | opuslib-next-bundled 0.1.1 | wheel 内置 libopus，无需系统装库 |
| Android Opus | JOpus 0.4.0 | JitPack 预编译 `.so`，含全部 ABI |

- 镜像：SDK 组件走腾讯云；Maven 走阿里云；JOpus 走 JitPack。
- 工程内 `local.properties` 指向本机 SDK，换机需按本机路径重写。

### 命令行重新构建

```powershell
$env:JAVA_HOME = "C:\Program Files\Microsoft\jdk-17.0.21.102-hotspot"
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
$gradle = "$env:LOCALAPPDATA\Programs\Gradle\gradle-8.9\bin\gradle.bat"
cd android\PhoneAudioSink
& $gradle :app:assembleDebug
# 调试产物：app\build\outputs\apk\debug\app-debug.apk
& $gradle :app:assembleRelease
# 发布产物：app\build\outputs\apk\release\app-release.apk
```

Release 包用本机密钥库签名；凭据只写在 `local.properties`（已 gitignore），
`release.keystore` 同样不入库。全新机器需自行生成 keystore，并在 `local.properties`
填 `store.file` / `store.password` / `key.alias` / `key.password`；缺省时
release 构建不挂签名配置，产物为未签名包。

> 备注：JOpus 0.4.0 以 Kotlin 2.3 元数据编译，工程在 `app/build.gradle` 中通过
> 排除其传递的 `kotlin-stdlib` 并加 `-Xskip-metadata-version-check` 与本机 Kotlin 1.9 工具链兼容。

---

## 九、后续可扩展方向

- 手机端 jitter buffer 自适应与丢包补偿（PLC）。
- 反向链路：手机麦克风回传电脑。
- 安卓前台 Service + 常驻通知，防止后台被系统冻结。
- 音效增加限幅之外的玩法：混响、动态压缩、夜间模式。

---

## 十、本版界面与音效（新增）

### 1. 安卓端设计规范落实

| 规范要求 | 实现方式 |
| --- | --- |
| 界面简约 | 纯 XML + Material Components，无多余装饰，卡片内只放必要信息 |
| 底部 tab 栏 | `BottomNavigationView` 四页：播放 / 音效 / 设置 / 关于 |
| 禁止 emoji | 所有文案纯文字，无 emoji 字符 |
| 图标必须 SVG | 全部用 `VectorDrawable`（Android 原生矢量格式，即 SVG 等价物），无位图图标 |
| 大圆角 | 卡片 24dp、按钮 16dp、输入框 16dp |
| 深浅色 | 默认深色，`values-night` 提供深色调色板、`values` 提供浅色，可在设置页切换 |

### 2. PC 端设计规范落实

| 规范要求 | 实现方式 |
| --- | --- |
| Windows UI 3 | 深色底 `#101317`、分层卡片、细分隔线、蓝色主色 `#4C8DFF`、无系统标题栏 |
| 侧边汉堡栏 + 音量 | 左上角汉堡按钮折叠侧栏；侧栏底常驻音量滑块（0–150%） |
| 右键托盘 | `QSystemTrayIcon` 菜单：显示主窗口 / 推送音量滑块 / 开始或停止连接 / 退出 |
| 窗口内手输 IP | 连接页「直连手机」模式下填 IP，点「开始」即由 PC 主动连手机 |
| 所有设计大圆角 | 窗口 24px、卡片 24px、按钮 / 输入框 / 菜单 16px、托盘菜单项 8px |

### 3. 音效（手机端 DSP，解码后处理）

- **7 段图示 EQ**：60 / 150 / 400 / 1k / 2.4k / 6k / 15k Hz，每段 ±12dB，可在曲线上拖动；
- **场景预设**：自定义 / 电子音乐 / 人声 / 清脆 / 弦乐（一键套用 EQ 曲线）；
- **虚拟低音**：用谐波激励模拟低频下潜，小喇叭也能听出低频量感；
- **低频增强**：low shelf 抬升 60–150Hz 区间；
- **增益**：+0–12dB，出口带软限幅防削波爆音；
- 全部为短窗 biquad（IIR），总延迟 **<10ms**，不改变原有的低延迟链路；
- 参数存 `SharedPreferences`，重开 App 自动恢复。

### 4. 稳流增强

- **心跳**：PC 每 1.5s 发 PING，手机回 PONG；手机 6s 无数据判定链路超时并主动断开，
  避免僵死连接一直堆积音频；
- **缓冲档位**：60 极速 / 120 低延迟 / 250 平衡 / 400 抗抖动，设置页可切，播放器实时重算目标水位；
- **自动重连**：手机侧断线 2.2s 后按上次 IP 重连（可关闭）；
- **目标水位**：队列低于水位等补货、高于分散值才追平，缓冲深度与丢弃计数在播放页实时显示。

---

## 十一、交互反馈与动效（两端一致的分层）

时长与曲线遵循同一套口径：**点按 130ms、小控件 240ms、页面/转场 240–320ms**，
入场用 decelerate（先快后慢），离场用 accelerate，只有按压回弹带一点过冲。

### 1. 必须有：即时反馈

| 场景 | 安卓 | PC |
| --- | --- | --- |
| 按钮按压 | scale 0.96 + 240ms 内回弹（`Motion.pressable`） | 水波纹扩散 320ms + 130ms 内缩回弹（`RippleButton`），叠加 `:pressed` 变深 |
| 可点元素 hover | 触屏无 hover，改为水波纹/缩放 | 主按钮 hover 提亮、ghost 抬升底色、指针变手型 |
| 开关勾选 | MaterialSwitch 自带弹性切换 | QCheckBox 勾选即变色 |
| 输入校验 | 错误：红框 + 抖动 320ms + 红字提示；正确：绿框 1.5s 后恢复 | 同左：红框、`pos` 抖动、绿框，提示文字同色 |

### 2. 必须有：等待状态有形

- **按钮三态**：空闲 → 加载中（禁用 + 文案变化 + 转圈）→ 成功/失败。
  - 安卓：扫描时按钮变「扫描中」并禁用，下方出现 18dp 环形进度 + 说明文字；
    等待电脑时显示「正在等待」，拨号失败自动回到「连接」。
  - PC：连接模式下状态卡内出现 6px 不定进度条，直到连上；停止时按钮变「停止中」并
    **非阻塞**等待线程退出（旧版 `join(2s)` 会卡住界面，已改成 150ms 轮询）。
- **骨架屏**：安卓扫描时先出 3 条 52dp 占位条，结果回来换成真实设备列表（逐项错峰入场）。

### 3. 必须有：界面衔接

- 安卓 Tab 切换：`slide_fade_in/out`，新页淡入并上移 10%，旧页淡出，180ms 离场。
- PC 侧栏切页：目标页内的卡片按 55ms 间隔淡入，总时长 240ms。
- 弹窗、抽屉本轮无新增，代码里未引入遮罩层，因此不涉及。

### 4. 建议有：入场编排

- 安卓各页首屏卡片按 60ms 错峰淡入上移 18dp；PC 按 55ms、240ms 淡入。
- 设备列表每项额外 60ms 递延，点开扫描不会整屏一起跳。
- 连接状态用颜色区分（已连接绿、异常红、等待中性），避免靠动画表达紧急信息。

### 5. 底线：可关闭、只动合成层

- 两端都提供 **「减弱动态效果」开关**（安卓设置页 / PC 设置页，写入本地配置）。
- 安卓同时读取系统 `ANIMATOR_DURATION_SCALE`，系统关动画时 App 自动静止。
- 动画只改 `alpha`、`translationY`、`scale`（合成层属性），不动宽高与布局参数，
  列表项与卡片不会引发布局重排。
- 违反"不要一直闪"：状态变化只做一次高亮/变色，不做循环闪烁。

未做（属可选锦上添花）：3D 翻转、粒子光斑、拖拽惯性、跨列表 FLIP。


## 十二、本轮修复记录（Android，真机验证）

- **音效 / 设置页点击闪退**：`MaterialSwitch` 在 MaterialComponents 主题下测量时，`StaticLayout` 收到 null 文本抛出 `NullPointerException`（堆栈落在 `SwitchCompat.makeLayout`）。改为 `androidx.appcompat.widget.SwitchCompat` 并显式 `app:showText="false"`，两页均恢复正常，真机 `adb logcat` 已确认无 `FATAL EXCEPTION`。
- **拖动均衡器时整页跟着滚动**：`EqView` 在 `ACTION_DOWN` 时调用 `requestDisallowInterceptTouchEvent(true)` 锁定父 `ScrollView`，`ACTION_UP/CANCEL` 再释放；按下的频段在拖动中保持不变，手指横向漂移不会跳到相邻频段。
- 验证机型：2307BRPDCC（`a454e1ec`），2880×1800 横屏窗口，`adb install -r` 覆盖安装。

## 十三、应用图标（两端统一）

- 图形：深色底（#101317→#202B3A + 极淡蓝色光晕）+ 左侧显示器 → 三段浅蓝声波 → 右侧手机，一眼能读出「电脑的声音推到手机」。配色沿用 App 的 ACCENT #4C8DFF。
- 安卓：`res/mipmap-{mdpi..xxxhdpi}/ic_launcher.png`、`ic_launcher_round.png`、`ic_launcher_foreground.png`（108dp 画布，图形在中心安全区）；`res/mipmap-anydpi-v26/ic_launcher(.round).xml` 自适应图标；清单有 `android:icon` / `android:roundIcon`。
- PC：`pc/assets/app.ico` 含 16/20/24/32/40/48/64/96/128/256 共 10 档，每档单独渲染（不是从大图缩放）；同时输出 `icon_<size>.png`，运行期用 `QIcon.addFile()` 逐档注册，Windows 按 DPI 取最合适的一档。
- **高 DPI 模糊的根因**：旧版窗口/托盘图标是把 64px 的 SVG 位图集直接给 `QIcon`，再被系统放大到 24/32/48px；现在改为多尺寸注册 + exe 内嵌 10 档 ico，不再有放大插值。
- 生成脚本（两端同一套图形）：
  `python tools/make_app_icons.py android/PhoneAudioSink/app/src/main/res pc/assets app-icon-preview.png`
- 预览：`app-icon-preview.png`；`pc/assets/icon_1024.png` 为 1024 母图。

## 十四、PC 点按动效的帧率自适应

- Qt 默认动画定时器约 16ms（≈60fps），在 120Hz 屏上波纹与按压缩放会两帧才更新一次，看起来"跟不上手"。
- 改为自定义帧时钟：`display_refresh_hz()` 读 `QGuiApplication.primaryScreen().refreshRate()`，`frame_interval_ms()` 换算成 8ms（120Hz）/ 7ms（144Hz）/ 17ms（60Hz），单个 `PreciseTimer` 驱动所有进行中的点按动效。
- 时长仍按毫秒算（波纹 320ms、按下 110ms、回弹 170ms），帧率只决定采样密度，所以不同刷新率下快慢一致；缓动曲线用 `QEasingCurve.valueForProgress()` 按已过时间求值，掉帧也不会拖慢动画。
- 「减弱动态效果」开启时整条路径不启动，只剩颜色反馈。
- 自测（强制 8ms 间隔）：波纹 41 帧 / 312ms，平均间隔 7.8ms；按压缩放正常落到目标内缩值。
