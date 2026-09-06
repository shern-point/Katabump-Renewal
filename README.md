# Katabump-Renewal

基于 GitHub Actions + SeleniumBase 的 Katabump 自动续期脚本，支持多账号、可选代理与 Telegram 通知。

## 1. 仓库结构

- `/home/runner/work/Katabump-Renewal/Katabump-Renewal/main.py`：登录、验证、续期主逻辑
- `/home/runner/work/Katabump-Renewal/Katabump-Renewal/proxy_handler.py`：解析 `PROXY_URL` 并生成 sing-box `config.json`
- `/home/runner/work/Katabump-Renewal/Katabump-Renewal/.github/workflows/renew.yml`：定时/手动运行的工作流
- `/home/runner/work/Katabump-Renewal/Katabump-Renewal/login.json.template`：账号 JSON 示例

---

## 2. 环境变量

### 2.1 必填：账号配置（二选一）

#### 方式 A：`USERS_JSON`（推荐，多账号）

- 变量名：`USERS_JSON`
- 类型：JSON 字符串，内容为账号对象数组
- 支持字段：`username` 或 `email`、`password`，以及可选的续期基准日期 `renewal_date`

示例：

```json
[
  {"username": "your_email@example.com", "password": "your_password", "renewal_date": "2026-09-02"},
  {"username": "another@example.com", "password": "pwd", "renewal_date": "2026-09-03"}
]
```

`renewal_date` 填写某一次续期的日期，格式为 `YYYY-MM-DD`，具体执行时刻由工作流的定时设置决定。每个账号独立以该日期为基准，每隔 **4 天**执行一次：基准日当天及之后第 4、8、12… 天为续期日。例如 `2026-09-02` 对应 `09-02`、`09-06`、`09-10`、`09-14`…，其他日期直接跳过该账号。

- 日期按 **UTC+8（北京时间 / 台北时间）**计算，不受运行机器的时区影响；未来的基准日期会等待到当天再执行。
- 判断发生在启动浏览器和登录之前；跳过的账号不会访问 Katabump 或触发其 Cloudflare 验证，日志会显示下次续期日期。
- 不填写、填空字符串或 `null` 时保留原有行为，每次运行都尝试续期；填写无效日期时跳过该账号并报告配置错误，其他账号继续处理。
- 这是按日历日期计算的固定周期，无需每次修改基准日期，也不会自动更新该字段；同一天多次运行都会执行到期账号。错过某个续期日后不会自动补跑，可手动续期后按实际日期调整基准日。

#### 方式 B：单账号

- `KATABUMP_EMAIL`
- `KATABUMP_PASSWORD`
- `KATABUMP_RENEWAL_DATE`（可选）：格式与规则同 `renewal_date`

> 脚本会优先读取 `USERS_JSON`；若未配置，再回退到 `KATABUMP_EMAIL` / `KATABUMP_PASSWORD`。

### 2.2 可选变量

- `PROXY_URL`：代理节点分享链接；配置后工作流会启动 sing-box，并通过 `http://127.0.0.1:8080` 出站
- `格式示例:
- `vmess：vmess://base64EncodedJSON
- `vless：vless://uuid@host:port?security=tls&type=ws&...#name
- `hy2：hy2://password@host:port?sni=xxx
- `sock5：socks5://user:pass@host:port
- 
- `TG_BOT_TOKEN`：Telegram Bot Token（通知可选）
- `TG_CHAT_ID`：Telegram Chat ID（通知可选）
- `NODE_ATTEMPTS`：每个账号的最大节点重试次数，默认 `3`

### 2.3 工作流内部变量（无需手动配置）

以下变量由工作流自动注入给脚本，不需要在 Secrets 中手动添加：

- `IS_PROXY`
- `PROXY_SERVER`

---

## 3. GitHub 部署教程（详细步骤）

### 步骤 1：Fork 并启用 Actions

1. Fork 本仓库到你的 GitHub 账号。
2. 进入你自己的仓库页面，确认 `Actions` 功能已启用。

### 步骤 2：配置 Secrets

1. 打开：`Settings -> Secrets and variables -> Actions`
2. 点击 `New repository secret`，逐个添加：
   - 必填（二选一）：
     - `USERS_JSON`，或
     - `KATABUMP_EMAIL` + `KATABUMP_PASSWORD`
   - 可选：
     - `PROXY_URL`
     - `TG_BOT_TOKEN`
     - `TG_CHAT_ID`
     - `NODE_ATTEMPTS`（不填默认 3）
     - `KATABUMP_RENEWAL_DATE`（单账号模式的续期基准日期，可选）

### 步骤 3：手动首次运行

1. 打开 `Actions` 页。
2. 选择工作流：`Katabump Auto Renew`。
3. 点击 `Run workflow` 执行一次，检查日志是否正常。

手动运行同样遵循各账号的续期日期；当天没有到期账号时会正常跳过。

### 步骤 4：定时运行

- 当前默认定时：每天 UTC `00:00`（北京时间 `08:00`）。
- 工作流每天检查各账号的日期，只登录当天需要续期的账号；各账号可以配置不同的基准日期。
- 如需调整，编辑文件：
  `/home/runner/work/Katabump-Renewal/Katabump-Renewal/.github/workflows/renew.yml`
  中的 `cron` 表达式。

### 步骤 5：查看结果与排错文件

工作流会上传 `renew-artifacts`，常见文件包括：

- `screenshots/` 与 `*.png`：页面截图
- `singbox.log`：代理日志（启用代理时）
- `config.json`：代理生成配置（启用代理时）

---

## 4. 本地部署与运行

### 4.1 环境准备

- Python 3.12（建议）
- Chrome 浏览器
- Linux 下建议可用 Xvfb（无头环境）

### 4.2 安装依赖

```bash
pip install seleniumbase requests
seleniumbase install chromedriver
```

### 4.3 设置环境变量并运行

#### 多账号示例

```bash
export USERS_JSON='[{"username":"user@example.com","password":"your_password","renewal_date":"2026-09-02"}]'
python3 /home/runner/work/Katabump-Renewal/Katabump-Renewal/main.py
```

#### 单账号示例

```bash
export KATABUMP_EMAIL='user@example.com'
export KATABUMP_PASSWORD='your_password'
export KATABUMP_RENEWAL_DATE='2026-09-02'  # 可选
python3 /home/runner/work/Katabump-Renewal/Katabump-Renewal/main.py
```

#### 启用代理（可选）

```bash
export PROXY_URL='你的代理链接'
python3 /home/runner/work/Katabump-Renewal/Katabump-Renewal/proxy_handler.py
```

---

## 5. 常见问题

### Q1：日志提示“未配置 USERS_JSON 或 KATABUMP_EMAIL/KATABUMP_PASSWORD”

- 原因：账号变量未配置，或 JSON 格式错误。
- 处理：优先检查 `USERS_JSON` 是否为合法 JSON 数组，且每项包含账号和密码。

### Q2：代理启动失败或连通性失败

- 检查 `PROXY_URL` 是否有效。
- 在 Actions Artifact 中下载 `singbox.log` 查看失败原因。

### Q3：没有收到 Telegram 通知

- 检查 `TG_BOT_TOKEN` 与 `TG_CHAT_ID` 是否正确。
- 未配置这两个变量时，脚本会跳过通知，但不影响续期。

---

## 6. 安全建议

- 所有账号和令牌仅放在 GitHub Secrets，不要写入仓库文件。
- 建议先用测试账号验证流程，再切换正式账号。
