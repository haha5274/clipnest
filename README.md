# ClipNest

Windows 剪贴板历史管理器。后台记录复制过的文字、图片、文件和富文本，按 `Ctrl+Alt+V` 呼出，搜一下就能重新复制。

![截图](docs/screenshot.png)

数据存在本地 SQLite 文件里，不联网。只用 Python 标准库，不需要装第三方包。

## 功能

- 记录文本、图片、文件和富文本，图片显示缩略图，复制时按原格式写回
- 文件按 `CF_HDROP` 存路径，复制回来的还是文件本身，能直接粘进资源管理器
- 富文本同时保留 `HTML Format` 和 RTF，粘进 Word 保留加粗之类的格式，粘进记事本退化成纯文本
- 模糊搜索：前缀、子串、词边界、多词命中、子序列依次降级匹配
- 条目可以置顶，清空历史时置顶项保留
- 全局热键呼出，回车复制后窗口自动隐藏
- 内容相同的记录合并成一条，累加使用次数并移到最近
- 关闭窗口不退出，缩到托盘；左键点图标唤出，右键有菜单
- 再开一个实例不会报错，它会把已经运行的那个窗口叫出来
- 默认保留 500 条，超出后淘汰最旧的

## 运行

需要 Windows 和 Python 3.9 以上（[官方安装包](https://www.python.org/downloads/windows/) 自带 tkinter）。

```bash
git clone https://github.com/haha5274/clipnest.git
cd clipnest
python -m clipnest
```

双击 `run.pyw` 可以不弹控制台窗口。也可以 `pip install .` 装成命令，`clipnest --hidden` 启动即隐藏。

窗口出来后去别处复制点东西，再按 `Ctrl+Alt+V` 试试。

## 快捷键

| 按键 | 作用 |
| --- | --- |
| `Ctrl+Alt+V` | 显示或隐藏窗口（全局） |
| `↑` `↓` | 上下移动选择 |
| `Enter` | 复制选中项并隐藏窗口 |
| `Ctrl+P` | 置顶 / 取消置顶 |
| `Delete` | 删除选中项 |
| `Esc` | 先清空搜索框，搜索框为空时隐藏窗口 |
| 双击条目 | 直接复制 |

点 `☆` 也能切换置顶。关窗口只是缩到托盘，退出要点托盘右键菜单里的「退出」，或者窗口右下角那个「退出」。

## 配置

首次运行生成 `%APPDATA%\ClipNest\config.json`：

```json
{
  "hotkey": "ctrl+alt+v",
  "max_items": 500,
  "poll_interval_ms": 250,
  "max_text_kb": 512,
  "capture_images": true,
  "dark": false
}
```

- `hotkey` 支持 `ctrl` / `alt` / `shift` / `win` 组合，主键可以是字母、数字、`F1`~`F24`，或者 `space`、`enter` 这类名字，必须带至少一个修饰键
- `max_items` 只限制非置顶条目
- `poll_interval_ms` 调大能省点 CPU，代价是复制后要等一下才记录
- `max_text_kb` 用来挡住误复制的大段日志

数据库是同目录的 `clipnest.db`，直接删掉就清空了。想放别处用 `--db`：

```bash
python -m clipnest --db D:\data\clipnest.db
```

## 一些实现选择

- **只在序号变化时读剪贴板。** `GetClipboardSequenceNumber()` 没变就整轮跳过，不碰剪贴板内容，挂后台时 CPU 占用接近 0。
- **PNG 是自己编的。** tkinter 只认 PNG 和 GIF，剪贴板给的却是 DIB。为此拉 Pillow 进来不划算，所以直接拼 IHDR/IDAT/IEND，用 `zlib.compress` 压扫描线、`zlib.crc32` 算校验。像素搬运走 `bytes` 步长切片（`line[0::4]`），由 C 层完成，4K 截图解码也在百毫秒级。
- **热键跑在独立线程。** `RegisterHotKey(None, ...)` 绑到线程消息队列，`GetMessageW` 循环收到 `WM_HOTKEY` 后把事件塞进 `queue`，由主线程的 `after` 泵取走。tkinter 不是线程安全的，这层隔离省不掉。
- **托盘是一个隐藏窗口。** `Shell_NotifyIcon` 只认窗口句柄，所以另起一个线程建了个不显示的窗口，`WndProc` 里处理 `WM_TRAY` 回调消息，右键菜单用 `TrackPopupMenu`。图标没有外部资源文件，是运行时按 16×16 像素表画进 DIB 再 `CreateIconIndirect`。
- **单实例靠命名互斥量。** 第二个进程 `CreateMutexW` 拿到 `ERROR_ALREADY_EXISTS` 就 `SetEvent` 唤醒第一个，然后自己退出，退出码 0。之前的版本是靠热键冲突被动发现的，现在这条路明确了。

## 目录

```
clipnest/
├── clipnest/
│   ├── app.py          # 界面、轮询调度、事件泵
│   ├── winclip.py      # Win32 剪贴板读写（文本 / DIB / HDROP / HTML / RTF）
│   ├── imageutil.py    # DIB 解码 + PNG 编码
│   ├── hotkey.py       # RegisterHotKey + 消息循环
│   ├── tray.py         # 托盘图标与右键菜单
│   ├── instance.py     # 单实例互斥量与唤醒事件
│   ├── store.py        # SQLite 存储、去重、淘汰
│   ├── search.py       # 匹配打分
│   └── config.py       # 配置读写
├── tests/
├── run.pyw
└── docs/screenshot.png
```

## 测试

```bash
python -m unittest discover -s tests -v
```

覆盖 DIB 解码（24/32 位、上下翻转）、PNG 编码（签名、尺寸、IDAT 解压比对、降采样）、搜索打分、存储层（去重、置顶、淘汰、清空、文件与富文本的打包解包）、`CF_HDROP` 结构布局与往返、富文本多格式往返、HTML/RTF 转纯文本、托盘图标绘制与 `NOTIFYICONDATAW` 结构尺寸、单实例唤醒，以及几个会真的开窗口的 UI 测试（搜索过滤、置顶排序、复制、删除、图片行、文件行、富文本行渲染）。

## 限制

- 只支持 Windows
- 富文本只取 `HTML Format` 和 `RTF` 两种，Word 里嵌的表格样式、OLE 对象这些不在其中
- 文件记录只存路径，源文件被改名或删除后这条就废了，复制时会在状态栏提示有几个失效
- 图片只处理 `CF_DIB`，`CF_BITMAP` 之类没做
- 托盘图标是运行时画的 16×16 位图，125% 以上缩放时会有点糊；系统托盘本身缩放的话只能交给 Windows 拉伸
- 单个条目上限 512 KB（`max_text_kb`），超了跳过不记

## TODO

开机自启、按日期归档、剪贴板加密存储。

## License

MIT
