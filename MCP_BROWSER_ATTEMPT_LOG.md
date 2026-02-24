
## 6. Docker 迁移计划 (2026-02-17)

### 6.1 创建 Docker 环境配置
为了彻底解决 Windows 环境下的 NumPy 冲突和 Socket 通信问题，已在 `docker/agent-browser/` 目录下创建了专用的 Docker 配置。

- **Dockerfile**: `docker/agent-browser/Dockerfile`
  - 基于 `python:3.10-bookworm` (Debian 12)，提供稳定的 Linux 环境。
  - 集成了 Node.js 20 和 `agent-browser` 全局安装。
  - 预装了 Chromium 及其依赖 (通过 apt 和 playwright install-deps)。
  - 配置了 Python 环境，强制 `numpy<2` 以兼容 `nvidia-nat-core`。
  - 自动将 `agent_browser_mcp.py` 中的 `agent-browser.cmd` 替换为 `agent-browser`。

- **使用说明**: `docker/agent-browser/README.md`
  - 提供了详细的步骤，指导用户如何在一个全新的文件夹中组织文件并构建镜像。

### 6.2 下一步
用户将根据 README 指引，在新的文件夹中构建并运行此 Docker 容器，验证 `agent-browser` 是否能在 Linux 容器中正常工作。
