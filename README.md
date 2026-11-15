# WorkBuddy Windows 桌面操控

给国内版 WorkBuddy 接上一只真实的 Windows 鼠标。你可以让它在选定的窗口里移动指针、单击或双击，在指定输入框写入中文并读回，或者把最小化的窗口还原。操控时，屏幕顶部会显示当前动作，边缘光效和指针标记能让你看到它点在哪里。

这是为国内版 WorkBuddy 编写的第三方本地 MCP 连接器。它通过 Windows 的窗口、控件和鼠标接口操作当前登录桌面。控件能否被识别，取决于目标应用提供的辅助功能信息。

## 安装

1. 在 Windows 10 或 11 上打开一次国内版 WorkBuddy，切换到本地环境。电脑需要 Python 3.10 或更高版本。使用 Python 官方 Windows 安装程序时，可勾选将 python.exe 添加到 PATH。
2. 下载发布页里的 `WorkBuddy-Windows-Desktop-1.4.3.zip`，**完整解压**后双击 `Install-WorkBuddy.cmd`。安装器会复制程序到当前用户目录，并向 WorkBuddy 添加名为 `windows-desktop-control` 的连接器。[下载 v1.4.3](https://github.com/tukitohosi/workbuddy-windows-desktop/releases/tag/v1.4.3)
3. 在 WorkBuddy 打开「专家·技能·连接器 → 连接器 → 自定义连接器」，找到 `windows-desktop-control`，按提示信任。若列表暂未更新，在 WorkBuddy 5.9.3 可点「＋ 添加 MCP」，确认配置中已有该名称，在最后一个右花括号后加一个空格，保存并返回列表。
4. 新建本地任务，试一句：「请用 windows-desktop-control 打开空白记事本，输入『春天的风吹过窗前』，再从记事本里读回来给我。」

多个 Python 并存时，可以在解压目录打开 PowerShell，把下面的路径替换为想使用的解释器路径。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -PythonExe "C:\你的安装目录\python.exe"
```

## 它能操作什么

| 动作 | 使用方式 |
| --- | --- |
| 移动、单击与双击 | 选定窗口，使用其客户区坐标。双击只需一次 `desktop_click` 调用，传 `click_count=2`。 |
| 写入并读回中文 | 指定输入框的 `element_id`，或选择已核实焦点的输入框。Chrome 有多个输入框时也能明确指定目标。 |
| 还原与最大化 | 查询已绑定窗口的状态，再请求最小化、还原或最大化。 |
| 核对结果 | 使用 `operation_id` 查询已提交的点击数或字符数。遇到部分完成时先核对目标，避免重复输入。 |

1.4.3 改进了桌面快捷方式的双击。另一个窗口在前台、目标图标仍露出时，连接器会核对落点上的原生图标，让第一击自然激活桌面。第二击前会再次核对图标。如果图标被遮住，先露出桌面再操作。

## 实机结果

在一台 Windows 电脑上，国内版 WorkBuddy 连续四轮双击桌面的 Google Chrome 快捷方式。四轮开始时桌面均在后台，每轮只调用一次双击。第一轮冷启动浏览器，另外三轮各新开一个窗口，四个窗口均进入前台。Windows 记录到的两击间隔依次为 94、109、110、78 毫秒，本机双击时限为 340 毫秒。后三轮在点击前先显示桌面，使图标露出。测试用 Windows 辅助功能取得图标坐标，同时核对了真实鼠标事件和 Chrome 窗口变化。

## 安装位置与卸载

安装器把连接器放在当前用户的 `.workbuddy\local-tools\windows-desktop-control` 下。用 U 盘安装后可以拔盘；如果指定了 Python 路径，解释器也应安装在这台电脑的本地磁盘上。需要卸载时，在解压目录运行下面的命令。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\uninstall.ps1
```

连接器提供的 11 个工具、窗口绑定、回执字段与回退旧版的操作见[使用说明](./使用说明.txt)。
