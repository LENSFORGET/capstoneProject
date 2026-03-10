# 小红书登录助手（xhs-login）跑通指南

本文档说明如何从零跑通 `docker-compose --profile login up xhs-login --build`，完成小红书登录并将会话持久化到 Docker 卷，供后续采集使用。

---

## 前置条件

- **Docker Desktop** 已安装并运行（Windows 下需保证 Docker 引擎正常）。
- 在**项目根目录**执行命令（即存在 `docker-compose.yml` 的目录）。
- 若从未构建过主应用镜像，首次会先构建 `app`（Dockerfile），再构建 `xhs-login`（Dockerfile.login 依赖 `capstoneproject-app`），耗时可能较长。

---

## 推荐执行顺序

| 步骤 | 操作 | 说明 |
|------|------|------|
| 1 | `docker-compose --profile login up xhs-login --build` | 构建并前台启动 xhs-login；首次构建可能较久 |
| 2 | 等待终端出现「请打开浏览器访问: http://localhost:6080」及 noVNC 启动完成 | 若 6080 被占用需先释放或改端口 |
| 3 | 浏览器打开 [http://localhost:6080](http://localhost:6080) | 进入 noVNC 界面，可见容器内 Chromium |
| 4 | 在 Chromium 中打开小红书并完成登录（扫码或账号密码） | 确认能看到首页或个人内容 |
| 5 | **另开一终端**执行 `docker exec xhs-login touch /app/data/xhs_login_trigger` | 触发脚本检测并保存会话 |
| 6 | 回到 xhs-login 终端，确认出现「会话已保存」及 `xhs_state.json` 路径 | 会话写入 app_data 卷，供 api/app 使用 |

### 步骤 1：启动登录容器

```bash
docker-compose --profile login up xhs-login --build
```

保持该终端前台运行，不要关闭。

### 步骤 2～4：在浏览器中登录小红书

1. 终端中看到 noVNC 与登录助手提示后，用浏览器打开 **http://localhost:6080**。
2. 在 noVNC 页面中会看到容器内的 Chromium 浏览器窗口。
3. 在 Chromium 中访问小红书并完成登录（扫码或账号密码），确认已进入首页或个人页。

### 步骤 5：触发保存会话

由于 `docker-compose up` 通常不连接标准输入，无法在终端按 Enter，改为**文件触发**：

在**另一个终端**（新开 CMD 或 PowerShell）执行：

```bash
docker exec xhs-login touch /app/data/xhs_login_trigger
```

脚本会检测到该文件后自动保存当前浏览器会话到 `/app/data/xhs_state.json`。

### 步骤 6：确认保存成功

回到运行 `docker-compose --profile login up xhs-login` 的终端，应看到类似输出：

- `[INFO] 检测到触发信号，开始保存会话...`
- `[OK] 会话已保存！文件大小: xxx bytes`

会话文件位于共享卷 `app_data` 的 `/app/data/xhs_state.json`，api 与 nat-app 容器均可读取，重启 Docker 后只要不删卷，登录态会保留。

---

## 常见问题与处理

### 端口 6080 被占用

修改 `docker-compose.yml` 中 xhs-login 的 `ports`，例如改为 `6081:6080`，然后访问 **http://localhost:6081**。

### 构建失败

1. 先单独构建主应用镜像：  
   `docker-compose build app`
2. 再构建登录镜像：  
   `docker-compose --profile login build xhs-login`
3. 根据终端报错排查（如网络、Dockerfile 中 apt/npm 等）。

### noVNC 白屏或无法连接

- 确认 xhs-login 终端中已出现「启动 noVNC Web UI」「启动登录助手」等日志。
- 确认 Xvfb、x11vnc、websockify 均已启动（无报错）。
- 可尝试重启容器：先 Ctrl+C 停止，再重新执行 `docker-compose --profile login up xhs-login --build`。

### 保存后仍提示「未检测到登录态」

- 确认 **api** 服务挂载了同一 **app_data** 卷（docker-compose 中 api 的 `volumes` 包含 `app_data:/app/data`）。
- 若执行过 `docker-compose down -v`，会删除卷，需重新执行登录流程并再次触发保存。

### agent-browser 未找到

说明主镜像（app）未正确安装 agent-browser。请先确保 `docker-compose build app` 成功，Dockerfile 中包含 `npm install -g agent-browser` 及 Playwright 安装步骤。

### 采集时出现「安全限制 IP存在风险，请切换可靠网络环境后重试 300012」

小红书检测到当前网络环境为风险 IP，常见原因与应对：

- **VPN/代理**：若使用 VPN 或代理，先关闭后重试；或更换为住宅代理（避免数据中心 IP）。
- **网络环境**：Docker 容器出网通常使用宿主机 IP；若宿主机在云服务器、办公网等，IP 可能被标记为风险。可尝试：
  - 使用家庭宽带或手机热点
  - 更换网络环境后重试
- **短时间内多次访问**：等待一段时间（如 30 分钟～数小时）后再试。
- **后续可选项**：若持续遇到该问题，可考虑为 agent-browser 配置住宅代理（HTTP_PROXY/HTTPS_PROXY）或使用 host 网络模式运行采集。

---

## 登录之后

- 在 **nat-app** 中运行爬虫：  
  `docker exec -it nat-app bash -c "nat run --config_file workflow_scraper.yaml --input '请现在开始执行采集任务。'"`
- 在 **http://localhost:4000/xhs**（Next.js，端口 4000 为 Windows 兼容）或 **http://localhost:8080**（Gradio）的「小红书」相关页面可查看登录态状态、手动启动采集等。

会话通常有效约 30 天，过期后按本文档重新执行登录与保存即可。
