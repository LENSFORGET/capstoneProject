# --------------------------------------------------------------------------------------
# Dockerfile.login
# 小红书手动登录辅助容器
#
# 功能：
#   - 基于主 Dockerfile（已含 agent-browser + Chromium）扩展
#   - 新增 Xvfb 虚拟显示 + x11vnc + noVNC，提供 Web 图形界面（port 6080）
#   - 用户通过 http://localhost:6080 打开 Chromium，手动登录小红书
#   - 登录后自动将会话状态保存至 /app/data/xhs_state.json（与 app_data 卷共享）
#
# 使用方式：
#   docker-compose --profile login up xhs-login
#   打开 http://localhost:6080，完成登录后按容器内终端 Enter
# --------------------------------------------------------------------------------------
FROM capstoneproject-app

# 安装 Xvfb（虚拟显示） + x11vnc（VNC服务） + noVNC + websockify（WebSocket 代理）
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    x11vnc \
    novnc \
    websockify \
    x11-xserver-utils \
    && rm -rf /var/lib/apt/lists/*

# 设置虚拟显示环境变量，agent-browser 有头模式依赖此变量
ENV DISPLAY=:99

# 复制登录辅助脚本
COPY xhs_login_helper.py /app/

# 容器入口：启动 Xvfb → x11vnc → noVNC websockify → 运行登录脚本
CMD ["sh", "-c", "\
  echo '=== 启动虚拟显示 ===' && \
  Xvfb :99 -screen 0 1280x900x24 -ac +extension GLX +render -noreset & \
  sleep 2 && \
  echo '=== 启动 VNC 服务 ===' && \
  x11vnc -display :99 -forever -nopw -rfbport 5900 -shared -bg -quiet && \
  echo '=== 启动 noVNC Web UI (http://localhost:6080) ===' && \
  websockify --web /usr/share/novnc 6080 localhost:5900 & \
  sleep 2 && \
  echo '=== 启动登录助手 ===' && \
  python /app/xhs_login_helper.py \
"]
