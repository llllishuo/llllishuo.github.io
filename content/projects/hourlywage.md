---
title: 时薪计算器
tagline: 把月薪拆成每一小时的价钱。
summary: 填 4 个数，中间那个大数字就是时薪——边填边算，没有按钮。Windows / 网页 / 终端三端同一套公式与进位规则，结果逐条比对一致。
badges: Windows, 网页, Linux / macOS, 单文件零依赖
meta: 三端|exe / index.html / .sh
meta: 口径|21.75 天/月
meta: 依赖|无（终端版只要 sh + awk）
meta: 许可|见仓库
accent: '#2b6f9e'
card: /assets/img/projects/hourlywage/card.jpg
order: 2
links: 网页版|/demo/hourlywage/
links: 下载 Windows 版（.exe）|/assets/files/hourlywage.exe
links: 源码仓库|https://github.com/llllishuo/HourlyWage
links: GitHub Pages 版|https://llllishuo.github.io/HourlyWage/
---

## 在线试一下

下面就是网页版本体（单文件 HTML，直接嵌进来）：

<div class="demo-frame">
  <div class="demo-bar">
    <span class="demo-dots"><i></i><i></i><i></i></span>
    <span>在线演示 · 网页版</span>
    <a href="/demo/hourlywage/" target="_blank" rel="noopener">全屏打开 ↗</a>
  </div>
  <iframe src="/demo/hourlywage/" title="时薪计算器在线演示" loading="lazy"></iframe>
</div>

<p class="demo-note">改任意一个数字，时薪立刻跟着变。留空按 0 计算；总工时算出 0 或者填了负数时，会直接把原因写在数字的位置上。</p>

## 三个端，一套算法

| 端 | 文件 | 说明 |
| --- | --- | --- |
| Windows | `时薪计算器.exe` | 单文件，双击即用，不用装 .NET 运行时 |
| 网页 | `index.html` | 单文件，有浏览器就能用（Windows / Linux / macOS / 手机） |
| Linux / macOS | `hourlywage.sh` | 终端版，只依赖 `sh` + `awk` |

三端各自实现同一套公式与进位规则，再由 `test/consistency.sh` 把同一组输入分别交给 awk、JS、C# 计算，逐条比对输出。

## 计算口径

```
时薪 =（月薪 + 奖金）÷（每日工时 × 21.75 + 节假日总工时）

月计薪天数 =（365 − 104）÷ 12 = 21.75 天/月
```

21.75 是年均值：一年 365 天，扣掉 52 周 × 2 天周末共 104 天，剩 261 天计薪，平均到每月就是 21.75 天。

所以「每日工时 × 21.75」得到的是一个月的常规工时，「节假日总工时」再单独加上去，最后用月薪加奖金去除。

结果**四舍五入到分，半分向上进位**，三端同一规则；实现里都先乘 100 取整再除回去，避免浮点数格式化带来的偏差。

<div class="feature-grid">
  <div class="feature">
    <h4>边填边算，没有按钮</h4>
    <p>输入框一变就重算，中间那个大数字直接给出结果，不需要点「计算」。</p>
  </div>
  <div class="feature">
    <h4>错就说清楚</h4>
    <p>输入非法、总工时为 0、填了负数，都会在结果位置显示具体原因，而不是给你一个空值。</p>
  </div>
  <div class="feature">
    <h4>三端逐条比对</h4>
    <p>一致性脚本覆盖常规用例和半分进位边界（45.125 → 45.13），三端结果必须完全相同。</p>
  </div>
  <div class="feature">
    <h4>零依赖单文件</h4>
    <p>网页版和终端版都不需要构建，拷走一个文件就能跑；exe 用 csc 直接编译出来。</p>
  </div>
</div>

## 终端版用法

```sh
chmod +x hourlywage.sh          # 第一次
./hourlywage.sh 8000 8 0 0      # 月薪 每日工时 节假日总工时 奖金 → 45.98
./hourlywage.sh                 # 不带参数则交互输入，直接回车取默认值
./hourlywage.sh -h              # 帮助
```

只输出数字，方便接管道：

```sh
rate=$(./hourlywage.sh 8000 8 0 0); echo "时薪 $rate 元/小时"
```

参数非法时打印原因并以退出码 2 结束。

## 三端一致性测试

```sh
sh test/consistency.sh
```

同一组输入分别交给 awk / JS / C# 计算并逐条比对。JS 需要 `node`；C# 需要先编译出 `wage-test.exe`，没有会自动跳过。

## 从源码构建（Windows）

```bat
build.cmd
```

或手动：

```bat
%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe /target:winexe /codepage:65001 /optimize+ ^
  /out:"时薪计算器.exe" /r:System.Windows.Forms.dll /r:System.Drawing.dll ^
  src\Wage.cs src\Program.cs
```

`/codepage:65001` 不能省，否则 UTF-8 源码里的中文会被按本地代码页误读。

## 目录

| 文件 | 作用 |
| --- | --- |
| `src/Wage.cs` | 计算内核：公式、月计薪天数、校验、进位 |
| `src/Program.cs` | Windows 界面（WinForms） |
| `src/TestMain.cs` | 控制台自检，输出一致性测试用的 `VALUE` 行 |
| `index.html` | 网页版（跨平台，单文件） |
| `hourlywage.sh` | 终端版（Linux / macOS，零依赖） |
| `test/consistency.sh` | 三端一致性检查 |

月计薪天数写在三个地方，改口径要一起改：`src/Wage.cs` 的 `PaidDaysPerYear` / `PayDaysPerMonth`、`index.html` 的 `wage-logic` 段、`hourlywage.sh` 的 `PAY_DAYS_PER_MONTH`。改完跑一遍 `sh test/consistency.sh`。

## 下载

- [Windows 版 `hourlywage.exe`](/assets/files/hourlywage.exe)（本站直链，与原仓库同名产物一致）
- [在线网页版](/demo/hourlywage/)
- [仓库源码](https://github.com/llllishuo/HourlyWage)
