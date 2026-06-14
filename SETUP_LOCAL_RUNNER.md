# 本地 Runner 配置指南

## 概述

在 Windows PC 上配置 Content Digest 本地 Runner，实现 B站 + 小红书内容抓取、AI 日报生成、RSS Feed 推送。

核心流程：`Git Pull → 爬取全平台 → DeepSeek 日报 → 生成 feed.xml → Git Push`

## 前置条件

- Windows 10/11，校园网内，能访问 github.com 和 xiaohongshu.com
- 电脑不关机或至少每天 5:00-6:00 开着

---

## 第一步：安装 Python 3.12+

```bash
winget install Python.Python.3.12
```

如果 winget 不可用，下载安装：
```
https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe
```
**安装时勾选 "Add Python 3.12 to PATH"**。

装完重启命令行，验证：
```bash
python --version
# 应显示 Python 3.12.x
```

---

## 第二步：Clone 代码

```bash
git clone https://github.com/RickMCCC/content-digest.git
cd content-digest
pip install -r requirements.txt
```

---

## 第三步：配置环境变量

Win+R → `sysdm.cpl` → 高级 → 环境变量 → **系统变量** → 新建：

| 变量名 | 值 |
|--------|----|
| `DEEPSEEK_API_KEY` | 从 GitHub Secrets 或 DeepSeek 开放平台获取 |
| `BILIBILI_COOKIE` | 浏览器登录 B站 → F12 → Application → Cookies → 拼成 `SESSDATA=xxx; bili_jct=xxx; buvid3=xxx` |
| `XIAOHONGSHU_COOKIE` | 浏览器登录小红书 → F12 → Application → Cookies → 拼成 `a1=xxx; web_session=xxx; ...` |

> ⚠️ 环境变量配完需要**重启命令行窗口**才能生效。

验证：
```bash
echo %DEEPSEEK_API_KEY%
echo %BILIBILI_COOKIE%
echo %XIAOHONGSHU_COOKIE%
```

---

## 第四步：测试运行

在 `content-digest` 目录下双击运行 `run_local.bat`，或命令行执行：

```bash
run_local.bat
```

观察输出：
- `[bilibili] New: ...` → B站抓取成功
- `[xiaohongshu] New: ...` → 小红书抓取成功
- `Done! [local] X new, Y in feed` → 完成
- 最后自动 git push 到 GitHub

---

## 第五步：创建定时任务

Win+R → `taskschd.msc` → 右侧 **创建基本任务**：

1. **名称**：`Content Digest Daily`
2. **触发器**：每天 → 时间 `5:30`
3. **操作**：启动程序 → 浏览选择 `run_local.bat`（在 content-digest 目录下）
4. 勾选 **"单击完成时打开此任务属性的对话框"** → 完成

在弹出的属性窗口：
- **常规** 标签 → 勾选 **"不管用户是否登录都要运行"**
- **条件** 标签 → **取消** "仅在使用交流电源时才运行此任务"
- 确定。如弹出密码提示，输入 Windows 登录密码。

---

## 后续维护

### 添加新博主
在 GitHub 网页上编辑 `config.yaml`（或本地编辑后 git push），第二天自动生效。

### 添加小红书博主
1. 小红书 App/网页打开博主主页
2. URL 中 `/user/profile/` 后面的字符串就是 ID
3. 填入 `config.yaml` 的 `xiaohongshu` 段

### 排查问题
1. 命令行手动跑一次 `run_local.bat`，看报错信息
2. 检查 `data/.last_run` 是否存在且时间正确
3. 云端兜底：如果本地 Runner 离线超过 24h，GitHub Actions 会自动降级为 B站-only

### 云端兜底说明
GitHub Actions 每天同时运行，会检查 `data/.last_run` 是否在 24h 内：
- **活跃** → 云端跳过（不重复跑）
- **离线** → 云端自动跑 B站，Feed 中插入 ⚠️ 离线警告

---

## feed.xml 订阅地址（folo 中使用）

```
https://raw.githubusercontent.com/RickMCCC/content-digest/main/output/feed.xml
```
